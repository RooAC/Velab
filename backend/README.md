# Velab Backend 文档

Velab backend 是 FOTA 智能诊断平台的 FastAPI 服务，负责诊断对话、案例与反馈 API、技术文档检索、Jira 知识同步、整车日志摄取与 Agent 编排。当前生产形态为：

- FastAPI 入口：`backend/main.py` 中的 `app`
- 监听地址：systemd 启动 `uvicorn main:app --host 127.0.0.1 --port 8000`
- 对外入口：Nginx 将 `/backend-api` 反向代理到 `http://127.0.0.1:8000`
- 进程管理：`fota-backend.service` 管 API，`fota-worker.service` 管 Arq worker
- 依赖服务：PostgreSQL、Redis、log_pipeline 自管 SQLite catalog 与磁盘日志文件

---

## 目录结构

```text
backend/
├── main.py                       # FastAPI 应用入口；lifespan 初始化 PG、Redis/Arq client、log_pipeline、向量索引
├── config.py                     # 统一配置：PG / Redis / LLM / CORS / API key / Agent 开关
├── database.py                   # SQLAlchemy PostgreSQL 连接池与业务表初始化
├── run_worker.py                 # Arq Worker 启动脚本
├── requirements.txt              # 运行依赖
├── requirements-dev.txt          # 开发/测试依赖
├── .env.example                  # 环境变量示例，不要在文档或提交中写真实密钥
│
├── api/                          # /api 路由：cases、feedback、docs、jira、sessions、bundles
├── agents/                       # Agent 实现与 orchestrator 编排
├── common/                       # API key 鉴权、日志链路、脱敏
├── log_pipeline/                 # 整车日志摄取、解码、预扫、对齐、查询与 Prometheus metrics
├── models/                       # PostgreSQL ORM：Case、ConfirmedDiagnosis、ChatSession 等
├── services/                     # LLM、向量检索、语义缓存、文档切块、workspace、评测等
├── tasks/                        # Arq 任务队列：parse_bundle_task 与 TaskClient
├── tests/                        # backend 平台侧测试
├── scripts/                      # 开发、初始化、清理、embedding、部署脚本
├── systemd/                      # fota-backend / fota-worker systemd unit
└── nginx/                        # Nginx 示例配置
```

---

## HTTP 入口与路由

生产环境中，后端只监听本机 `127.0.0.1:8000`，外部请求应从 Nginx 前缀进入：

```bash
curl http://127.0.0.1:8000/health
curl https://<your-domain>/backend-api/health
```

主要端点：

| 端点 | 说明 | 鉴权 |
|---|---|---|
| `GET /health` | 轻量存活检查，只确认 FastAPI 进程可响应并列出已注册 Agent | 不要求 |
| `GET /ready` | 深度就绪检查，检查 PostgreSQL、Redis/Arq 队列、log_pipeline state、Agent 注册、LiteLLM Gateway | 不要求 |
| `POST /chat` | SSE 诊断对话入口，调用 orchestrator 编排 Agent | `AUTH_ENABLED=true` 时要求 |
| `/api/cases/*` | 案例管理 | `AUTH_ENABLED=true` 时要求 |
| `/api/feedback/*` | 已确认诊断与反馈闭环 | `AUTH_ENABLED=true` 时要求 |
| `/api/docs/*` | 技术文档上传、列表、删除与检索数据准备 | `AUTH_ENABLED=true` 时要求 |
| `/api/jira/*` | Jira 知识同步 API | `AUTH_ENABLED=true` 时要求 |
| `/api/sessions/*` | 会话存储与标题生成 | `AUTH_ENABLED=true` 时要求 |
| `/api/bundles/*` | log_pipeline 日志包上传、状态、日志、事件查询 | `AUTH_ENABLED=true` 时要求 |
| `GET /metrics` | log_pipeline Prometheus 指标 | 不要求 |
| `GET /docs` | Swagger UI | 不要求 |

### `/health` 与 `/ready`

`/health` 是轻量存活检查，适合作为进程是否活着的低成本探针：

```bash
curl http://127.0.0.1:8000/health
```

返回示例：

```json
{"status":"ok","agents":[{"name":"log_analytics","display_name":"Log Analytics Agent"}]}
```

`/ready` 是深度就绪检查，适合作为部署后验收、Nginx upstream 检查或发布前检查。任一关键依赖失败时返回 HTTP 503：

```bash
curl -i http://127.0.0.1:8000/ready
```

检查项：

- `database`：执行 `SELECT 1` 并返回连接池状态
- `redis_queue`：通过 `TaskClient.get_queue_info()` 检查 Redis/Arq 队列
- `log_pipeline`：确认 `app.state` 中 pipeline、eventdb、range_query 等组件已初始化
- `agents`：确认 Agent registry 非空
- `llm_gateway`：`DEPLOYMENT_MODE=A` 时探测 LiteLLM `/models`；`DEPLOYMENT_MODE=B` 时跳过

---

## 核心组件

### FastAPI 与生命周期

`main.py` 创建 FastAPI app，并在 lifespan 中完成启动初始化：

1. 初始化 PostgreSQL 连接池：`db_manager.initialize()`
2. 创建缺失业务表：`db_manager.create_tables()`
3. 初始化 Arq `TaskClient`
4. 初始化 log_pipeline state：pipeline、catalog、eventdb、slim filter、range query
5. 打印 LLM 路由决策，预热 embedding 索引

关闭时会关闭 Arq task client 和 PostgreSQL 连接。

### PostgreSQL

PostgreSQL 是平台业务数据库，连接配置来自 `.env` 中的 `POSTGRES_*`。当前由 SQLAlchemy ORM 管理业务表，部署脚本会执行：

```bash
sudo -u fota sh -c "cd /opt/fota-backend && venv/bin/python -c 'from database import db_manager; db_manager.initialize(); db_manager.create_tables()'"
```

注意：`create_tables()` 只创建不存在的表，不做字段迁移。字段变更需要手动 SQL 或后续迁移工具承接。

### Redis 与 Arq Worker

Redis 同时用于 Arq 队列和任务进度缓存。生产由 `fota-worker.service` 启动：

```bash
sudo systemctl status fota-worker
sudo journalctl -u fota-worker -f
```

Arq 任务入口是 `tasks.worker.parse_bundle_task`，它把日志包摄取委托给 `log_pipeline.IngestPipeline`，并把任务进度写入 `task_progress:{task_id}`。更多细节见 [tasks/README.md](tasks/README.md)。

### log_pipeline

log_pipeline 是整车日志摄取子系统，挂载在同一个 FastAPI app 下：

- `POST /api/bundles`：上传 `.zip`、`.tar.gz`、`.tgz`、`.tar`、`.rar`、`.log`、`.txt`、`.dlt`
- `GET /api/bundles/{bundle_id}`：查询 bundle 状态、进度、控制器文件数
- `GET /api/bundles/{bundle_id}/logs`：按时间窗、控制器、`full/slim` 格式流式返回 NDJSON 日志
- `GET /api/bundles/{bundle_id}/events`：查询重要事件
- `GET /metrics`：Prometheus 指标

存储边界：

- 原始日志与处理产物写磁盘，默认在 `backend/data/`；生产建议使用 `/opt/fota-backend/data` 或独立数据盘
- bundle、file、ImportantEvent 等元数据写 log_pipeline 自管 SQLite `catalog.db`
- 原始日志行不写 PostgreSQL

### Agent 编排

`POST /chat` 调用 `agents.orchestrator.orchestrate()`，根据场景与输入编排多个 Agent：

- `log_analytics`：读取 bundle 日志窗口、事件和 slim/full 日志
- `jira_knowledge`：检索 Jira 历史工单知识
- `doc_retrieval`：检索上传技术文档
- `rca_synthesizer`：综合多路证据输出 RCA

常用配置：

```bash
AGENTS_USE_LLM=true
AGENTS_USE_EMBEDDINGS=false
ORCHESTRATOR_STREAM=false
BACKEND_BASE_URL=http://127.0.0.1:8000
```

生成或刷新预计算向量索引：

```bash
cd /home/Velab/backend
python scripts/ingest_embeddings.py
```

### API Key 鉴权

本地默认 `AUTH_ENABLED=false`。生产建议开启：

```bash
AUTH_ENABLED=true
AUTH_API_KEY=<strong-random-key>
```

开启后，`/chat` 和 `/api/*` 需要携带以下任一请求头：

```bash
curl -H "Authorization: Bearer <AUTH_API_KEY>" http://127.0.0.1:8000/api/cases
curl -H "X-API-Key: <AUTH_API_KEY>" http://127.0.0.1:8000/api/cases
```

不要把真实 `AUTH_API_KEY`、LLM key、Jira token 或数据库密码写入文档、日志、提交记录。

---

## 本地开发

```bash
cd /home/Velab/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env
```

启动 API 与 worker：

```bash
cd /home/Velab/backend
./scripts/start-dev.sh
```

或分别启动：

```bash
cd /home/Velab/backend
python main.py
python run_worker.py
```

验证：

```bash
curl http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/metrics
```

上传日志包：

```bash
curl -F "file=@/path/to/bundle.zip" http://127.0.0.1:8000/api/bundles
curl http://127.0.0.1:8000/api/bundles/<bundle_id>
```

---

## 测试

在 backend 目录运行：

```bash
cd /home/Velab/backend
python -m pytest tests/ log_pipeline/tests/ -q
```

常用子集：

```bash
# 平台业务测试
python -m pytest tests/ -q

# log_pipeline 独立测试
python -m pytest log_pipeline/tests/ -q

# 鉴权与 readiness
python -m pytest tests/test_auth.py tests/test_readiness.py -q

# 使用封装脚本，仅跑 tests/
python run_tests.py
```

更多测试说明见 [tests/README.md](tests/README.md)。

---

## 生产部署

部署脚本：`backend/scripts/deploy.sh`。它仅适用于 Linux + apt + systemd 环境。

```bash
cd /home/Velab/backend
sudo ./scripts/deploy.sh
```

脚本会执行：

1. 安装或确认 Python、PostgreSQL、Redis
2. 创建专用用户 `fota`
3. 复制 backend 到 `/opt/fota-backend`
4. 创建 Python venv 并安装 `requirements.txt`
5. 首次从 `.env.example` 创建 `/opt/fota-backend/.env`
6. 在默认弱密码存在时自动生成随机 `POSTGRES_PASSWORD`
7. 执行 `scripts/init_postgres.sh` 并创建业务表
8. 安装并重启 `fota-backend.service` 与 `fota-worker.service`
9. 校验存储目录写权限

部署后需要按生产环境编辑：

```bash
sudo nano /opt/fota-backend/.env
sudo chmod 600 /opt/fota-backend/.env
sudo chown fota:fota /opt/fota-backend/.env
sudo systemctl restart fota-backend fota-worker
```

systemd 服务文件：

- [systemd/fota-backend.service](systemd/fota-backend.service)：`uvicorn main:app`，监听 `127.0.0.1:8000`
- [systemd/fota-worker.service](systemd/fota-worker.service)：`python run_worker.py`

Nginx 生产反代应把 `/backend-api` 转发到 `http://127.0.0.1:8000`，并保留 SSE 所需设置：

```nginx
location /backend-api/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
}
```

---

## 运维命令

```bash
# 服务状态
sudo systemctl status fota-backend
sudo systemctl status fota-worker

# 重启
sudo systemctl restart fota-backend
sudo systemctl restart fota-worker

# 日志
sudo journalctl -u fota-backend -f
sudo journalctl -u fota-worker -f
sudo journalctl -u fota-backend -n 100 --no-pager

# 本机探针
curl http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/metrics

# Nginx 外部入口探针
curl https://<your-domain>/backend-api/health
curl -i https://<your-domain>/backend-api/ready
```

Redis / Arq：

```bash
redis-cli ping
redis-cli ZCARD arq:queue
redis-cli ZRANGE arq:queue 0 -1 WITHSCORES
redis-cli GET task_progress:<task_id>
```

PostgreSQL：

```bash
sudo systemctl status postgresql
sudo -u postgres psql -d fota_db -c "SELECT 1;"
```

log_pipeline catalog：

```bash
sqlite3 /opt/fota-backend/data/catalog.db "SELECT bundle_id,status,progress,error FROM bundles ORDER BY updated_at DESC LIMIT 5;"
```

---

## 故障排查

### `/health` 正常但 `/ready` 返回 503

```bash
curl -s http://127.0.0.1:8000/ready | python -m json.tool
sudo journalctl -u fota-backend -n 100 --no-pager
```

根据 `checks` 定位：

- `database failed`：检查 PostgreSQL、`.env` 中 `POSTGRES_*`、业务库和用户
- `redis_queue failed`：检查 Redis、`REDIS_HOST`、`REDIS_PORT`、`fota-worker`
- `log_pipeline failed`：检查 FastAPI lifespan 是否完整启动、数据目录权限
- `agents failed`：检查 Agent 模块导入错误
- `llm_gateway failed`：`DEPLOYMENT_MODE=A` 时检查 LiteLLM Gateway 地址与虚拟 key

### Nginx 502

```bash
sudo systemctl status fota-backend
ss -tlnp | grep 8000
sudo tail -n 100 /var/log/nginx/fota-backend-error.log
```

### 上传后 bundle 长时间不动

```bash
sudo journalctl -u fota-backend -f
sudo journalctl -u fota-worker -f
redis-cli ZCARD arq:queue
sqlite3 /opt/fota-backend/data/catalog.db "SELECT bundle_id,status,progress,error FROM bundles ORDER BY updated_at DESC LIMIT 10;"
```

### LLM 或 Agent 输出异常

```bash
sudo journalctl -u fota-backend -f
```

重点检查：

- `DEPLOYMENT_MODE`
- `LITELLM_BASE_URL` / `LITELLM_API_KEY`
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`
- `AGENTS_USE_LLM`
- `AGENTS_USE_EMBEDDINGS`
- `BACKEND_BASE_URL`

---

## 数据与安全

- `.env` 权限应为 `600`，不得提交真实密钥
- FastAPI 生产只监听 `127.0.0.1:8000`，公网入口交给 Nginx + HTTPS
- `AUTH_ENABLED=true` 时，前端或服务端代理需要转发 `Authorization: Bearer ...` 或 `X-API-Key`
- systemd 使用专用用户 `fota`，服务文件限制写入路径为 `/opt/fota-backend/logs` 与 `/opt/fota-backend/data`
- 日志与 API 出口应通过 `common/redaction.py` 处理敏感信息
- `backend/data/**` 是运行产物，可能包含真实日志、workspace、catalog、索引和上传文档，不应提交

清理运行产物：

```bash
cd /opt/fota-backend
sudo -u fota venv/bin/python scripts/cleanup_data.py --older-than-days 30
sudo -u fota venv/bin/python scripts/cleanup_data.py --older-than-days 30 --execute
```

---

## 相关文档

- [tasks/README.md](tasks/README.md)：Arq worker 与任务队列
- [tests/README.md](tests/README.md)：测试运行方式
- [log_pipeline/CLAUDE.md](log_pipeline/CLAUDE.md)：log_pipeline 设计契约
