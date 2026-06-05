# Velab Web 前端 / BFF

Velab Web 是基于 Next.js 16 / React 19 的前端与服务端 BFF 子项目。浏览器访问 Web 页面和 `/api/*` 路由，Next.js 服务端再把诊断、上传、会话、文档等请求转发到 backend。

生产环境中，`fota-web` systemd 服务监听 `127.0.0.1:3000`，由 Nginx 对外暴露；backend 可经 Nginx 的 `/backend-api/health` 与 `/backend-api/ready` 验证健康和依赖就绪状态。

## 目录结构

```text
web/
├── src/
│   ├── app/
│   │   ├── api/               # Next.js BFF / API 代理路由
│   │   ├── page.tsx           # 主页面
│   │   ├── layout.tsx         # 根布局
│   │   └── globals.css        # 全局样式
│   ├── components/            # React 组件
│   └── lib/                   # SSE、鉴权、路由校验等工具
├── public/                    # 静态资源
├── scripts/deploy.sh          # Web 单服务部署脚本
├── systemd/fota-web.service   # 生产 systemd unit 模板
├── package.json
├── next.config.ts
├── vitest.config.ts
└── README_TESTING.md
```

## 运行方式

### 本地开发

```bash
cd /home/Velab/web
npm install
cp .env.example .env.local
npm run dev
```

默认访问地址：

```bash
xdg-open http://localhost:3000
```

本地默认把 BFF 上游指向 `http://localhost:8000`。如果 backend 不在本机默认端口，修改 `web/.env.local` 中的 `BACKEND_URL`。

### 生产拓扑

```text
Browser
  │
  ▼
Nginx
  ├─ /, /api/*      -> http://127.0.0.1:3000  (fota-web / Next.js)
  └─ /backend-api/* -> http://127.0.0.1:8000  (backend)
        │
        └─ /backend-api/ready 用于验证 backend 依赖是否就绪
```

`fota-web` 服务只绑定本机回环地址：

```ini
ExecStart=/opt/fota-web/node_modules/.bin/next start --hostname 127.0.0.1
```

因此生产访问应通过 Nginx 域名或服务器入口，不应直接暴露 3000 端口。

## 环境变量

环境变量从 `web/.env.local` 读取；生产落地位置通常是 `/opt/fota-web/.env.local`，并由 `web/systemd/fota-web.service` 的 `EnvironmentFile=/opt/fota-web/.env.local` 加载。

### 本地示例

```bash
BACKEND_URL=http://localhost:8000
WEB_AUTH_ENABLED=false
NEXT_PUBLIC_WEB_AUTH_ENABLED=false
NEXT_PUBLIC_SHOW_SCENARIO_SWITCHER=true
```

### 生产示例

```bash
BACKEND_URL=http://127.0.0.1:8000
WEB_AUTH_ENABLED=true
NEXT_PUBLIC_WEB_AUTH_ENABLED=true
AUTH_LOGIN_PASSWORD=<set-a-strong-password>
AUTH_SESSION_SECRET=<set-a-random-cookie-secret>
BACKEND_API_KEY=<same-as-backend-auth-api-key>
NEXT_PUBLIC_SHOW_SCENARIO_SWITCHER=false
```

不要把真实密钥写进仓库。`AUTH_LOGIN_PASSWORD`、`AUTH_SESSION_SECRET`、`BACKEND_API_KEY` 只应存在于服务器环境文件或密钥管理系统中。

### 变量说明

| 变量 | 作用 | 是否暴露给浏览器 |
| --- | --- | --- |
| `BACKEND_URL` | Next.js BFF 访问 backend 的服务端上游地址 | 否 |
| `WEB_AUTH_ENABLED` | 服务端鉴权开关 | 否 |
| `NEXT_PUBLIC_WEB_AUTH_ENABLED` | 浏览器端鉴权 UI 开关，应与 `WEB_AUTH_ENABLED` 保持一致 | 是 |
| `AUTH_LOGIN_PASSWORD` | Web 登录口令，仅在鉴权开启时需要 | 否 |
| `AUTH_SESSION_SECRET` | httpOnly cookie 签名 secret；未设置时会退回使用登录口令 | 否 |
| `BACKEND_API_KEY` | BFF 转发到 backend 时附带的服务端 API Key | 否 |
| `NEXT_PUBLIC_SHOW_SCENARIO_SWITCHER` | 是否显示场景切换入口 | 是 |

## BFF / API 转发

浏览器侧应调用同源 `/api/*`，不要直接调用 backend 内网地址。当前 Web BFF 包括：

| Web 路由 | 上游 backend 路径 | 用途 |
| --- | --- | --- |
| `POST /api/chat` | `POST ${BACKEND_URL}/chat` | SSE 诊断流代理 |
| `POST /api/upload-log` | `POST ${BACKEND_URL}/api/bundles` | 日志包上传 |
| `GET /api/bundle-status/[bundleId]` | `GET ${BACKEND_URL}/api/bundles/{bundleId}` | Bundle 状态 |
| `GET /api/bundle-events/[bundleId]` | `GET ${BACKEND_URL}/api/bundles/{bundleId}/events` | Bundle 事件 |
| `GET /api/bundle-logs/[bundleId]` | `GET ${BACKEND_URL}/api/bundles/{bundleId}/logs` | Bundle 日志内容 |
| `GET/POST /api/sessions` | `${BACKEND_URL}/api/sessions` | 会话列表与创建 |
| `GET/PUT/DELETE /api/sessions/[sessionId]` | `${BACKEND_URL}/api/sessions/{sessionId}` | 会话读写删除 |
| `POST /api/session-title` | `POST ${BACKEND_URL}/api/sessions/title` | 会话标题生成 |
| `GET/POST /api/docs` | `${BACKEND_URL}/api/docs` | 文档列表与上传 |
| `GET/DELETE /api/docs/[docId]` | `${BACKEND_URL}/api/docs/{docId}` | 文档读取与删除 |

当 `BACKEND_API_KEY` 存在时，BFF 会在服务端转发认证信息给 backend；浏览器只持有 Web 登录态 cookie，不直接接触 backend API Key。

## Backend 健康与 ready 联动

Nginx 暴露 `/backend-api/*` 作为 backend 的外部探针入口：

```bash
curl -fsS http://<web-domain>/backend-api/health
curl -fsS http://<web-domain>/backend-api/ready
```

本机排障可绕过 Nginx：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

建议发布或重启后同时检查 Web 服务与 backend ready：

```bash
curl -fsS http://127.0.0.1:3000/
curl -fsS http://<web-domain>/backend-api/ready
```

`/health` 仅表示 backend 进程基本健康；`/ready` 还会检查 backend 依赖，返回非 ready 时 Web 页面可能能打开，但诊断、上传或会话能力可能不可用。

## 构建与部署

### 本地构建

```bash
cd /home/Velab/web
npm run build
npm run start
```

### 生产单服务部署

```bash
cd /home/Velab/web
sudo ./scripts/deploy.sh
```

脚本会同步 Web 代码到 `/opt/fota-web`，安装依赖，执行 `npm run build`，安装并重启 `fota-web` systemd 服务。脚本不会覆盖已存在的 `/opt/fota-web/.env.local`。

### 手动部署步骤

```bash
sudo mkdir -p /opt/fota-web
sudo rsync -av --exclude node_modules --exclude .next --exclude .env.local /home/Velab/web/ /opt/fota-web/
sudo chown -R fota-web:fota-web /opt/fota-web

cd /opt/fota-web
sudo -u fota-web npm install
sudo -u fota-web npm run build

sudo cp /opt/fota-web/systemd/fota-web.service /etc/systemd/system/fota-web.service
sudo systemctl daemon-reload
sudo systemctl enable fota-web
sudo systemctl restart fota-web
```

确认服务状态：

```bash
systemctl status fota-web --no-pager
journalctl -u fota-web -n 80 --no-pager
curl -fsS http://127.0.0.1:3000/
```

## systemd 运维命令

```bash
# 查看状态
systemctl status fota-web --no-pager

# 查看实时日志
journalctl -u fota-web -f

# 重启
sudo systemctl restart fota-web

# 修改 unit 后重新加载
sudo systemctl daemon-reload
sudo systemctl restart fota-web

# 修改 /opt/fota-web/.env.local 后重启生效
sudo systemctl restart fota-web
```

## 测试与覆盖率

Web 使用 Vitest、React Testing Library、MSW 和 V8 coverage。

```bash
cd /home/Velab/web
npm test
npm run test:coverage
npm run test:ci
npm run test:ui
```

覆盖率门禁来自 `vitest.config.ts`：

| 指标 | 阈值 |
| --- | --- |
| branches | `>= 70%` |
| functions | `>= 70%` |
| lines | `>= 80%` |
| statements | `>= 80%` |

详细测试说明见 `web/README_TESTING.md`。

## 常见排障

### Web 页面打不开

```bash
systemctl status fota-web --no-pager
journalctl -u fota-web -n 80 --no-pager
curl -v http://127.0.0.1:3000/
```

如果本机 3000 正常但域名不通，继续检查 Nginx 反向代理。

### 页面打开但诊断不可用

```bash
grep '^BACKEND_URL=' /opt/fota-web/.env.local
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://<web-domain>/backend-api/ready
```

优先看 `/ready` 返回的依赖检查项，再检查 `BACKEND_URL` 是否指向生产 backend。

### 登录页或鉴权状态异常

```bash
grep -E '^(WEB_AUTH_ENABLED|NEXT_PUBLIC_WEB_AUTH_ENABLED|AUTH_SESSION_SECRET|BACKEND_API_KEY)=' /opt/fota-web/.env.local
sudo systemctl restart fota-web
```

`WEB_AUTH_ENABLED` 与 `NEXT_PUBLIC_WEB_AUTH_ENABLED` 应保持一致。`AUTH_SESSION_SECRET` 改动会使旧 cookie 失效，需要重新登录。

### SSE 中断或响应超时

```bash
journalctl -u fota-web -f
curl -fsS http://<web-domain>/backend-api/ready
```

同时检查 Nginx 对 `/api/chat` 的代理超时配置是否足够支撑长连接。

## 维护提示

- 只把示例密钥写成占位符，不提交真实 `.env.local`。
- 修改 BFF 路由时，同步更新本文档的转发表和测试文档中的 API 测试说明。
- 发布前至少运行 `npm run build` 与 `npm run test:ci`。

**最后更新**: 2026-06-04
