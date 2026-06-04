# Velab LiteLLM Gateway

`gateway/` 是 Velab 项目的 LiteLLM Proxy 网关子项目，用于把 Claude、OpenAI 等上游模型统一暴露为 OpenAI 兼容接口，并在网关层承担 Key Pool、Fallback、重试、限流与跨境访问优化。

当前生产形态：

```text
Backend/FastAPI
  └─ LITELLM_BASE_URL=http(s)://<gateway-host>/v1
       └─ Nginx 按 Host/路径反代
            └─ LiteLLM Proxy(systemd: litellm)
                 └─ 监听 127.0.0.1:4000
```

网关进程不应直接暴露公网端口。生产由 `systemd` 的 `litellm` 服务管理，LiteLLM 监听 `127.0.0.1:4000`，外部访问通过 `gateway/nginx/litellm.conf` 反向代理。

## 目录结构

```text
gateway/
├── config.yaml                 # LiteLLM 模型、Fallback、Key Pool、全局参数
├── .env.example                # 环境变量模板，不含真实密钥
├── README.md                   # 本文档
├── gateway功能检查报告.md       # 当前功能状态与检查结论
├── nginx/
│   └── litellm.conf            # Nginx 反向代理、SSE、Cloudflare 源站证书示例
├── scripts/
│   ├── deploy.sh               # 生产部署脚本，安装到 /opt/litellm-proxy
│   ├── start.sh                # 本地/开发启动脚本
│   └── validate_config.sh      # 配置和环境变量检查
└── systemd/
    └── litellm.service         # 生产 systemd 服务
```

## 当前配置

`gateway/config.yaml` 定义了 4 类对外模型名：

| 对外模型名 | 用途 | 当前上游 |
| --- | --- | --- |
| `router-model` | 意图路由，低成本快速判断 | Claude Haiku + OpenAI Fallback |
| `agent-model` | Agent 推理与 Tool Use | Claude Sonnet Key Pool + OpenAI Fallback |
| `synthesizer-model` | 综合推理/总结 | Claude Sonnet + OpenAI Fallback |
| `embedding-model` | 向量化 | OpenAI text-embedding-3-large |

关键策略：

- `agent-model` 通过同名 deployment + `ANTHROPIC_API_KEY_1/2` 实现 Key Pool。
- `fallbacks` 允许 Claude deployment 失败后切到同一对外模型名下的 OpenAI deployment。
- `allowed_fails` 与 `cooldown_time` 用于短时摘除异常 deployment，避免持续打到不健康上游。
- `general_settings.master_key` 从 `LITELLM_MASTER_KEY` 读取，用于访问 LiteLLM 管理接口和普通 OpenAI 兼容接口。

## 环境变量安全

不要把真实密钥写进仓库、README、工单或聊天记录。仓库只保留 `.env.example`。

生产环境变量文件位置：

```bash
/opt/litellm-proxy/.env
```

首次部署后复制模板并编辑：

```bash
cd /home/Velab/gateway
sudo cp .env.example /opt/litellm-proxy/.env
sudo nano /opt/litellm-proxy/.env
sudo chmod 600 /opt/litellm-proxy/.env
sudo chown litellm:litellm /opt/litellm-proxy/.env
```

必填变量：

```bash
ANTHROPIC_API_KEY=...
ANTHROPIC_API_KEY_1=...
ANTHROPIC_API_KEY_2=...
OPENAI_API_KEY=...
LITELLM_MASTER_KEY=...
HOST=127.0.0.1
PORT=4000
```

可选变量：

```bash
ANTHROPIC_API_BASE=
OPENAI_API_BASE=
GATEWAY_LOG_PATH=/opt/litellm-proxy/logs/request.log
```

安全约束：

- `.env` 权限保持 `600`。
- `LITELLM_MASTER_KEY` 使用强随机值，例如 `openssl rand -hex 32` 生成后自行加前缀。
- 生产默认 `HOST=127.0.0.1`，公网入口交给 Nginx。
- 不要在命令历史里粘贴真实供应商 Key；需要临时测试时优先从 `.env` 加载。

## 本地开发

```bash
cd /home/Velab/gateway
python3 -m venv .venv
source .venv/bin/activate
pip install 'litellm[proxy]' prometheus-client
cp .env.example .env
nano .env
./scripts/validate_config.sh
./scripts/start.sh
```

也可以直接启动：

```bash
cd /home/Velab/gateway
set -a
source .env
set +a
litellm --config config.yaml --host "${HOST:-127.0.0.1}" --port "${PORT:-4000}" --num_workers 4
```

## 生产部署

推荐使用部署脚本，它会把 gateway 文件同步到 `/opt/litellm-proxy`，创建 `litellm` 系统用户、虚拟环境、依赖和 systemd 服务。

```bash
cd /home/Velab/gateway
sudo ./scripts/deploy.sh
sudo nano /opt/litellm-proxy/.env
sudo systemctl restart litellm
sudo systemctl status litellm
```

部署脚本会安装并启用：

```bash
/etc/systemd/system/litellm.service
```

该服务读取：

```bash
/opt/litellm-proxy/config.yaml
/opt/litellm-proxy/.env
```

常用 systemd 命令：

```bash
sudo systemctl start litellm
sudo systemctl stop litellm
sudo systemctl restart litellm
sudo systemctl status litellm
journalctl -u litellm -n 100
journalctl -u litellm -f
```

升级 LiteLLM：

```bash
sudo -u litellm /opt/litellm-proxy/venv/bin/pip install --upgrade 'litellm[proxy]' prometheus-client
sudo systemctl restart litellm
```

## Nginx 反向代理

`gateway/nginx/litellm.conf` 是生产反代模板，包含：

- HTTPS 入口。
- Cloudflare Origin Certificate 示例。
- Cloudflare IP 白名单。
- SSE/streaming 必要配置：`proxy_buffering off`、长 `proxy_read_timeout`。
- `/health`、`/ui` 和普通 API 路径转发到 `127.0.0.1:4000`。

安装示例：

```bash
cd /home/Velab/gateway
sudo apt install nginx
sudo cp nginx/litellm.conf /etc/nginx/sites-available/litellm.conf
sudo nano /etc/nginx/sites-available/litellm.conf
sudo ln -s /etc/nginx/sites-available/litellm.conf /etc/nginx/sites-enabled/litellm.conf
sudo nginx -t
sudo systemctl reload nginx
```

证书示例路径：

```bash
sudo mkdir -p /etc/nginx/ssl
sudo nano /etc/nginx/ssl/origin-cert.pem
sudo nano /etc/nginx/ssl/origin-key.pem
sudo chmod 600 /etc/nginx/ssl/origin-key.pem
```

Cloudflare SSL/TLS 模式应使用 `Full (strict)`。上线前把模板里的 `llm-proxy.example.com` 替换成真实域名。

## 验证命令

配置静态检查：

```bash
cd /home/Velab/gateway
./scripts/validate_config.sh --verbose
```

确认本地监听：

```bash
ss -ltnp | grep ':4000'
curl -sS http://127.0.0.1:4000/health
```

认证轻量探针，推荐用于部署验证：

```bash
source /opt/litellm-proxy/.env
curl -sS http://127.0.0.1:4000/v1/models \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}"
```

经 Nginx 验证：

```bash
curl -sS https://llm-proxy.example.com/v1/models \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}"
```

OpenAI 兼容调用验证：

```bash
curl -sS http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "router-model",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

说明：

- `/v1/models` 只验证网关可达和认证可用，适合 readiness。
- `/v1/chat/completions` 会真实调用上游模型，适合上线前端到端验证。
- `/health` 可用于 LiteLLM 进程级检查，但不要把它作为 backend `/ready` 的深度模型端点检查依据。

## 与 backend /ready 的关系

Backend 在场景 A 下通过 `LITELLM_BASE_URL` 和 `LITELLM_API_KEY` 访问 Gateway。

推荐 backend 配置：

```bash
DEPLOYMENT_MODE=A
LITELLM_BASE_URL=http://127.0.0.1:4000/v1
LITELLM_API_KEY=<与 gateway LITELLM_MASTER_KEY 或 Virtual Key 对应的值>
```

如果 backend 与 gateway 不在同一台机器，`LITELLM_BASE_URL` 应改成 Nginx 暴露的 HTTPS 地址：

```bash
LITELLM_BASE_URL=https://llm-proxy.example.com/v1
```

当前 backend `/ready` 对 LiteLLM 使用：

```text
GET {LITELLM_BASE_URL}/models
Authorization: Bearer {LITELLM_API_KEY}
```

也就是当 `LITELLM_BASE_URL=http://127.0.0.1:4000/v1` 时，实际探针为：

```text
http://127.0.0.1:4000/v1/models
```

这个设计只验证网关可达性和认证是否正确，不触发上游模型深度检查，避免 Anthropic/OpenAI 等外部供应商短时波动导致本地 backend `/ready` 被误判为不可用。

## 日志与监控

LiteLLM 服务日志：

```bash
journalctl -u litellm -f
journalctl -u litellm -n 100
journalctl -u litellm -p err
```

请求日志默认写入：

```bash
/opt/litellm-proxy/logs/request.log
```

Nginx 日志：

```bash
sudo tail -f /var/log/nginx/litellm-access.log
sudo tail -f /var/log/nginx/litellm-error.log
```

Prometheus 指标：

```bash
curl -sS http://127.0.0.1:4000/metrics
```

## 故障排查

### litellm 服务无法启动

```bash
sudo systemctl status litellm
journalctl -u litellm -n 100
sudo -u litellm test -r /opt/litellm-proxy/.env && echo ok
```

常见原因：

- `/opt/litellm-proxy/.env` 不存在、权限错误或仍是占位值。
- `config.yaml` 引用的环境变量缺失。
- `127.0.0.1:4000` 已被占用。
- 虚拟环境依赖安装不完整。

### Nginx 返回 502

```bash
sudo systemctl status litellm
ss -ltnp | grep ':4000'
sudo nginx -t
sudo tail -n 100 /var/log/nginx/litellm-error.log
```

常见原因：

- LiteLLM 未监听 `127.0.0.1:4000`。
- Nginx `proxy_pass` 端口与 `.env` 中 `PORT` 不一致。
- systemd 服务启动失败但 Nginx 仍在转发。

### 返回 401 或 403

```bash
source /opt/litellm-proxy/.env
curl -i http://127.0.0.1:4000/v1/models \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}"
```

常见原因：

- backend 的 `LITELLM_API_KEY` 与 gateway 的 `LITELLM_MASTER_KEY` 或 Virtual Key 不一致。
- 请求头缺少 `Authorization: Bearer ...`。
- 经 Cloudflare/Nginx 访问时源站白名单或 Host 配置不匹配。

### chat/completions 失败但 /v1/models 正常

```bash
journalctl -u litellm -f
curl -I https://api.anthropic.com
curl -I https://api.openai.com
```

常见原因：

- 上游供应商 Key 无效或余额/额度不足。
- 上游网络不可达。
- 上游返回 429，需观察 Key Pool 和 Fallback 是否按预期生效。
- 模型名或供应商侧模型权限不匹配。

### backend /ready 返回 not_ready

```bash
curl -sS http://127.0.0.1:4000/v1/models \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}"
curl -sS http://127.0.0.1:8000/ready
```

排查顺序：

1. 先确认 gateway `/v1/models` 本地探针成功。
2. 再确认 backend `.env` 中 `LITELLM_BASE_URL` 以 `/v1` 结尾。
3. 再确认 backend `LITELLM_API_KEY` 与 gateway 授权 Key 一致。
4. 最后看 backend `/ready` 响应里的 `checks.litellm_gateway` 字段。

## 相关文件

- [config.yaml](config.yaml)
- [.env.example](.env.example)
- [deploy.sh](scripts/deploy.sh)
- [litellm.service](systemd/litellm.service)
- [litellm.conf](nginx/litellm.conf)
