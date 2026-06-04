# Velab Web 测试与覆盖率文档

本文档描述 `web` 子项目的测试配置、运行命令、覆盖率门禁和 BFF/API 测试约定。所有命令默认在 `/home/Velab/web` 下执行。

## 测试技术栈

| 类别 | 工具 |
| --- | --- |
| 测试框架 | Vitest 4.1.2 |
| React 组件测试 | React Testing Library 16.3.2 |
| 用户交互 | `@testing-library/user-event` 14.6.1 |
| API Mock | MSW 2.12.14 |
| 覆盖率 | `@vitest/coverage-v8` 4.1.2 |
| DOM 环境 | jsdom 29.0.1 |
| UI 调试 | `@vitest/ui` 4.1.2 |

## 命令

```bash
cd /home/Velab/web

# 运行全部测试
npm test

# 开发时监听
npm run test:watch

# 生成覆盖率报告
npm run test:coverage

# CI 覆盖率门禁
npm run test:ci

# Vitest UI
npm run test:ui
```

运行覆盖率后，HTML 报告位于：

```bash
xdg-open coverage/index.html
```

## 覆盖率门禁

门禁配置在 `vitest.config.ts`：

| 指标 | 阈值 |
| --- | --- |
| branches | `>= 70%` |
| functions | `>= 70%` |
| lines | `>= 80%` |
| statements | `>= 80%` |

覆盖率排除项包括 `node_modules/`、`.next/`、构建输出、配置文件、类型声明、`src/__tests__/**` 测试辅助代码，以及当前主页面入口 `src/app/page.tsx`。

## 测试结构

```text
web/
├── vitest.config.ts
├── vitest.setup.ts
└── src/
    ├── __tests__/
    │   ├── mocks/             # MSW handlers 与测试数据
    │   ├── utils/             # render helper
    │   └── setup.d.ts
    ├── app/
    │   ├── __tests__/         # 页面集成与 SSE 事件测试
    │   └── api/
    │       ├── auth/          # Web 登录 / 状态 / 登出路由测试
    │       └── chat/          # BFF chat 代理测试
    ├── components/
    │   └── __tests__/         # 组件测试
    └── lib/
        └── __tests__/         # SSE、鉴权、路由校验等工具测试
```

## BFF/API 测试约定

Web 的浏览器侧请求应落到同源 `/api/*`，测试也应优先覆盖这个边界。MSW 用于模拟 backend，不需要真实 backend 进程。

当前核心代理关系：

| Web BFF 路由 | backend 上游 | 测试重点 |
| --- | --- | --- |
| `POST /api/chat` | `${BACKEND_URL}/chat` | 请求校验、鉴权头转发、SSE 透传、错误处理 |
| `POST /api/upload-log` | `${BACKEND_URL}/api/bundles` | 文件上传、状态码与错误响应 |
| `GET /api/bundle-*` | `${BACKEND_URL}/api/bundles/*` | 查询参数透传、404/5xx 处理 |
| `/api/sessions*` | `${BACKEND_URL}/api/sessions*` | 会话 CRUD 转发 |
| `/api/docs*` | `${BACKEND_URL}/api/docs*` | 文档列表、上传、删除 |
| `/api/auth/*` | Web 本地鉴权路由 | cookie、登录开关、密码校验 |

测试环境可用 `vi.stubEnv` 设置环境变量，例如：

```typescript
vi.stubEnv("BACKEND_URL", "http://localhost:8000");
vi.stubEnv("WEB_AUTH_ENABLED", "true");
vi.stubEnv("BACKEND_API_KEY", "test-backend-key");
```

不要在测试中写入真实密钥；测试 key 只能是占位值。

## Backend ready 联动的测试边界

`/backend-api/health` 与 `/backend-api/ready` 是生产 Nginx 暴露的 backend 探针路径，不属于 Next.js BFF 本身。Web 单元测试通常不启动 Nginx，也不应依赖真实 `/backend-api/*`。

发布验证或端到端排障时使用：

```bash
curl -fsS http://<web-domain>/backend-api/health
curl -fsS http://<web-domain>/backend-api/ready
```

本地只验证 backend 进程时使用：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

如果要为 ready 联动增加自动化测试，建议放在部署或端到端层，而不是 Vitest 的组件/BFF 单元测试里。

## 编写测试的约定

### 组件测试

- 优先使用用户可见语义查询，例如 `getByRole`、`getByText`、`getByPlaceholderText`。
- 用 `userEvent` 模拟用户输入和点击。
- 异步状态用 `await waitFor(...)` 或 `findBy...`。
- 避免依赖 CSS class 或内部 DOM 结构。

```typescript
const user = userEvent.setup();
render(<InputBar onSend={onSend} disabled={false} />);

await user.type(screen.getByPlaceholderText(/输入/), "诊断一下");
await user.click(screen.getByRole("button", { name: /发送/ }));

expect(onSend).toHaveBeenCalledWith("诊断一下");
```

### API 路由测试

- 使用 `NextRequest` 构造请求。
- 使用 `vi.stubEnv` 控制 `BACKEND_URL`、鉴权开关和 API Key。
- 使用 `vi.stubGlobal("fetch", ...)` 或 MSW 模拟上游。
- 覆盖成功、上游错误、网络错误、请求体验证失败和鉴权分支。

### SSE 测试

- 覆盖完整事件、不完整 chunk、`\r\n` 行结束符、注释行和增量解析。
- 对 `/api/chat`，同时验证 `Content-Type: text/event-stream` 和错误路径。

## 常见问题

### 测试超时

Vitest 默认 `testTimeout` 和 `hookTimeout` 为 10 秒。单个测试需要更长时间时：

```typescript
it("长时间运行的测试", async () => {
  // ...
}, 15000);
```

### 定时器测试不稳定

```typescript
vi.useFakeTimers();
// 触发逻辑
await vi.runOnlyPendingTimersAsync();
vi.useRealTimers();
```

### 环境变量污染

```typescript
afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});
```

### 只运行一个测试文件或名称

```bash
npm test -- src/lib/__tests__/sseParse.test.ts
npm test -- --testNamePattern="SSE"
```

## CI 示例

```yaml
name: web-tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm ci
      - run: npm run test:ci
```

## 发布前建议

```bash
cd /home/Velab/web
npm run build
npm run test:ci
```

发布后再做运行态探针：

```bash
curl -fsS http://127.0.0.1:3000/
curl -fsS http://<web-domain>/backend-api/ready
```

**最后更新**: 2026-06-04
