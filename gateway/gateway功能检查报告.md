# Velab Gateway 功能检查报告

> 检查日期：2026-06-04
> 检查范围：`/home/Velab/gateway`
> 检查对象：LiteLLM Gateway 配置、部署脚本、systemd、Nginx、文档一致性
> 说明：本报告只记录 gateway 子项目状态，不包含 backend/web/根目录文档修改。

## 一、当前结论

Gateway 子项目已经具备生产部署所需的基础文件：

| 模块 | 文件 | 当前状态 | 说明 |
| --- | --- | --- | --- |
| LiteLLM 配置 | `config.yaml` | 已具备 | 包含 router/agent/synthesizer/embedding 模型、Fallback、Key Pool、Prometheus callback |
| 环境变量模板 | `.env.example` | 已具备 | 使用占位值，无真实密钥；覆盖供应商 Key、API Base、监听地址、日志路径 |
| 生产部署脚本 | `scripts/deploy.sh` | 已具备 | 部署到 `/opt/litellm-proxy`，创建用户、venv、依赖、systemd 服务 |
| 本地启动脚本 | `scripts/start.sh` | 已具备 | 适合开发环境快速启动 |
| 配置检查脚本 | `scripts/validate_config.sh` | 已具备 | 检查 YAML、结构、环境变量和 Key 格式 |
| systemd 服务 | `systemd/litellm.service` | 已具备 | 以 `litellm` 用户运行，读取 `/opt/litellm-proxy/.env`，监听 `HOST/PORT` |
| Nginx 反代 | `nginx/litellm.conf` | 已具备 | 转发到 `127.0.0.1:4000`，包含 HTTPS、Cloudflare、SSE 配置 |
| README | `README.md` | 已更新 | 已补充当前架构、部署、验证、backend `/ready` 关系与故障排查 |

总体判断：gateway 文档已从早期“待补生产部署文件”的状态更新为“生产部署文件已存在，重点关注环境变量、验证路径和运维排障”。

## 二、当前架构

生产链路：

```text
Backend /ready 或业务 LLM 调用
  -> LITELLM_BASE_URL(.../v1)
  -> Nginx Host/路径反代
  -> LiteLLM Proxy(systemd: litellm)
  -> 127.0.0.1:4000
  -> Anthropic/OpenAI 上游
```

关键部署约束：

- LiteLLM 生产进程由 `systemd` 服务 `litellm` 管理。
- 默认只监听 `127.0.0.1:4000`，不直接暴露公网。
- Nginx 负责 TLS、Host 入口、Cloudflare 白名单和 streaming 转发。
- 配置文件部署到 `/opt/litellm-proxy/config.yaml`。
- 真实密钥只存在于 `/opt/litellm-proxy/.env`，仓库内只保留 `.env.example`。

## 三、配置检查

`config.yaml` 当前包含：

- `router-model`：Claude Haiku 主力，OpenAI fallback。
- `agent-model`：Claude Sonnet 双 Key Pool，OpenAI fallback。
- `synthesizer-model`：Claude Sonnet 主力，OpenAI fallback。
- `embedding-model`：OpenAI embedding。
- `litellm_settings.fallbacks`：同名模型 fallback 链。
- `allowed_fails` / `cooldown_time`：异常 deployment 临时冷却。
- `router_settings.routing_strategy=usage-based-routing`：按使用量路由。
- `general_settings.master_key=os.environ/LITELLM_MASTER_KEY`：统一认证入口。

需要持续注意：

- `config.yaml` 中引用的每个 `os.environ/...` 都必须在生产 `.env` 中有值，或确认空值时 LiteLLM 能按预期回退。
- `ANTHROPIC_API_BASE` / `OPENAI_API_BASE` 为空时表示使用供应商默认地址；如果接入中转服务，应填写对应兼容地址。
- Key Pool 扩容时，应同步更新 `config.yaml` 和 `.env.example`，但不要提交真实 Key。

## 四、部署与验证命令

生产部署：

```bash
cd /home/Velab/gateway
sudo ./scripts/deploy.sh
sudo nano /opt/litellm-proxy/.env
sudo systemctl restart litellm
sudo systemctl status litellm
```

配置检查：

```bash
cd /home/Velab/gateway
./scripts/validate_config.sh --verbose
```

本地 LiteLLM 进程检查：

```bash
ss -ltnp | grep ':4000'
curl -sS http://127.0.0.1:4000/health
```

认证轻量探针：

```bash
source /opt/litellm-proxy/.env
curl -sS http://127.0.0.1:4000/v1/models \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}"
```

端到端模型调用：

```bash
source /opt/litellm-proxy/.env
curl -sS http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "router-model",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## 五、与 backend /ready 的关系

当前 backend `/ready` 对 gateway 的检查应理解为轻量认证探针：

```text
GET {LITELLM_BASE_URL}/models
Authorization: Bearer {LITELLM_API_KEY}
```

当 backend 配置为：

```bash
LITELLM_BASE_URL=http://127.0.0.1:4000/v1
```

实际探针为：

```text
http://127.0.0.1:4000/v1/models
```

该探针验证：

- LiteLLM 网关是否可达。
- backend 使用的认证 Key 是否可用。
- `/v1` OpenAI 兼容入口是否正确。

该探针不做：

- 不调用 `/health` 作为深度模型端点检查。
- 不触发真实上游模型请求。
- 不把 Anthropic/OpenAI 等外部供应商短时波动直接放大为 backend 本地部署不可用。

这是当前 readiness 策略的核心点：backend `/ready` 应判断本地依赖和网关认证连通性，而不是用外部模型健康状态代表本地服务健康状态。

## 六、故障排查重点

### systemd 启动失败

```bash
sudo systemctl status litellm
journalctl -u litellm -n 100
sudo -u litellm test -r /opt/litellm-proxy/.env && echo ok
```

优先检查：

- `.env` 是否存在、权限是否为 `600`。
- `.env` 是否仍保留占位值。
- `LITELLM_MASTER_KEY` 是否存在。
- `config.yaml` 引用的 Key 是否都存在。
- `PORT=4000` 是否被占用。

### Nginx 502

```bash
sudo systemctl status litellm
ss -ltnp | grep ':4000'
sudo nginx -t
sudo tail -n 100 /var/log/nginx/litellm-error.log
```

优先检查：

- LiteLLM 是否正在监听 `127.0.0.1:4000`。
- Nginx `proxy_pass` 是否仍指向正确端口。
- systemd 是否启动失败但 Nginx 已经接管请求。

### 认证失败

```bash
source /opt/litellm-proxy/.env
curl -i http://127.0.0.1:4000/v1/models \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}"
```

优先检查：

- backend `LITELLM_API_KEY` 是否和 gateway 授权 Key 一致。
- 请求是否带 `Authorization: Bearer ...`。
- 使用 Nginx 域名访问时 Cloudflare 白名单、Host、证书是否正确。

### `/v1/models` 正常但模型调用失败

```bash
journalctl -u litellm -f
curl -I https://api.anthropic.com
curl -I https://api.openai.com
```

优先检查：

- 上游供应商 Key 是否有效。
- 供应商账号是否有对应模型权限。
- 是否触发 429、额度不足或地区网络问题。
- `api_base` 是否填错。

## 七、未验证项

本次为文档更新，没有执行真实生产验证。仍需在目标服务器上确认：

- `sudo ./scripts/deploy.sh` 是否完整成功。
- `litellm` systemd 服务是否可长期稳定运行。
- `/opt/litellm-proxy/.env` 中真实 Key 是否可用。
- Nginx 证书、域名、Cloudflare 白名单是否匹配生产环境。
- `/v1/models` 与一次真实 `chat/completions` 是否均通过。
- backend `/ready` 是否在场景 A 下返回 `ready`，且不会因上游供应商短时波动误判。

## 八、维护建议

- 修改 `config.yaml` 后先运行 `./scripts/validate_config.sh --verbose`。
- 增加或删除 Key Pool 时，同步维护 `.env.example` 的变量说明。
- 部署前不要把真实 Key 写入任何仓库文件。
- 调整 `PORT` 时同步检查 systemd `.env` 与 Nginx `proxy_pass`。
- readiness 相关变更要同时确认 gateway README 和 backend `/ready` 实现语义一致。
