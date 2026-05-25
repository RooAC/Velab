# Changelog

本文件记录 Velab FOTA 智能诊断平台的所有重要变更，格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

## [Unreleased]

### Changed
- **技术债深度清理（零 lint 错误目标）**
  - 后端 `datetime.utcnow()` 全量替换为 `datetime.now(timezone.utc)`：
    `models/case.py`、`models/chat_session.py`、`models/diagnosis.py`、`api/feedback.py`、`api/session_store.py`、`services/semantic_cache.py`、`tests/conftest.py`（SQLAlchemy `Column(default=)` 用 lambda 包装）。`pytest -W error::DeprecationWarning` 通过。
  - `ruff` 三轮自动修复共消除 233 个问题：F401 未使用 import × 45、W293 空白行尾随空格 × 63、E302/E303/E305 空行规则 × 6 等。
  - 手工修复真实 bug：`services/evaluation.py` 缩进与单行 `if` 语句拆分；`main.py:272` `agents` 局部变量遮蔽导入名（重命名为 `registered_agents`）。
  - 清理无用局部变量：`log_pipeline/decoders/stage.py`（`total`）、`log_pipeline/tests/test_prescan.py`（`p`/`fake_year`/`real_line`）、`log_pipeline/tests/test_query.py`（`year`/`dt`）、`tasks/worker.py`（`redis`）、`tests/test_log_analytics_bundle.py`（`mock_ws`）。
  - 长行重排：`agents/doc_retrieval.py`、`agents/jira_knowledge.py` 的 `notes_content` 多行 f-string 化；`tests/test_log_analytics_bundle.py` 长 MagicMock 调用多行化。
  - 入口脚本 sys.path 后置 import 加 `# noqa: E402`：`run_worker.py`、`scripts/ingest_embeddings.py`、`tests/test_doc_chunker_xlsx.py`。
  - 前端：`npm audit fix` 修复 3 个 Next.js CVE（缓存投毒 + 中间件绕过）；`eslint.config.mjs` 忽略 `coverage/**`；`DocManagerButton.tsx`/`bundle-logs/route.test.ts` 移除未用 catch 变量。
- **新增 `backend/.flake8` 配置**：`max-line-length = 127`，`extend-ignore = E203`（PEP 8 切片风格分歧），`max-complexity = 25`，`per-file-ignores = agents/orchestrator.py:E501,C901`（系统提示词长字符串与 orchestrate 协调函数）。

### Verified
- 后端 `flake8 .` → **0 issues**；CI 严格模式（`E9,F63,F7,F82`）→ **0 issues**。
- 后端 `pytest -q` → **444 passed**（无回归）。
- 前端 `npm test -- --run` → **226 passed | 11 skipped**（11 个 skipped 为 FeedbackButtons + page.test 的预存 Vitest 定时器/SSE flaky 用例，独立追踪）。
- 前端 `npm run lint` → 0 warnings；`npm audit` → 0 vulnerabilities。

---

## [2026-05-26 晚] · 功-4 落地后技术债批量清理

### Added

- **`api/docs.py` 多进程安全锁**：新增 `_manifest_lock()` 复合上下文管理器，组合 `threading.Lock` + `fcntl.flock(LOCK_EX)`（`_MANIFEST_LOCKFILE = data/docs/.manifest.lock` 哨兵文件），保护 manifest.json 在 Gunicorn `--workers>1` 多进程部署下并发上传不丢失记录；Windows 上 `fcntl` ImportError 自动降级为纯 `threading.Lock`
- **文件类型 magic bytes 校验**：新增 `_validate_content_signature(path, suffix)`，PDF 校验 `%PDF-` / xlsx 校验 `PK\x03\x04` / txt-md 通过 utf-8/gbk 解码首 1KB；拒绝伪装后缀（如 `.pdf` 实为 plain text），上传错误码 `415 unsupported_format`
- **embedding 状态机**：manifest 新增 `embedding_status` 字段，5 状态 `disabled` / `skipped_no_key` / `pending` / `ok` / `failed`；`_reindex_embeddings` 在 disabled/no_key/ok/failed 四路径均回写状态；前端 `DocManagerButton` 文档卡片渲染彩色徽标（TF-IDF / 无Key / 索引中 / 向量 / 失败）
- **requirements 分层**：新增 `requirements-base.txt`（51 个运行时依赖）+ `requirements-dev.txt`（pytest 5 件套，以 `-r requirements-base.txt` 接入）；原 `requirements.txt` 保留不变，向后兼容 CI/deploy

### Fixed

- **`test_doc_retrieval.py` LLM hang**：文件级 autouse fixture `monkeypatch.setattr(settings, "AGENTS_USE_LLM", False, raising=False)`，10 用例从挂起 → 0.03s 通过
- **`doc_retrieval._load_documents()` 阻塞 event loop**：`execute()` 改为 `await asyncio.to_thread(self._load_documents)`，PDF/Excel chunking 同步 I/O 不再阻塞 FastAPI worker
- **`conftest.py::client` fixture PG 强依赖**：在 `TestClient(app)` 进入 lifespan 前 monkeypatch `db_manager.initialize/create_tables/close` + `tasks.client.get_task_client/close_task_client` + `vector_service.load_embed_index`，原本 ERROR 的 `test_feedback_api.py` 14 用例无需 PG 即可通过

### Tests

- 后端 `test_docs_api.py` +6（magic bytes 4 + embedding_status 2 = 18 passing）
- 前端 `DocManagerButton.test.tsx` +4（上传成功+徽标 / 删除 confirm 接受 / confirm 拒绝 / 上传失败 detail = 9 passing）
- 全量：后端 **444 passed**（从 350）/ 前端 **226 passed | 11 skipped**（从 222）

### Notes

未实施（架构/业务决策，留待独立工作流）：① 功-1 用户认证 & 多租户隔离；② embedding 默认开关（API 成本 vs 检索质量）；③ `_reindex_embeddings` 全量 → 增量（需 `VectorSearchService` 引入 doc_id 级 API）；④ Bundle 状态轮询 → SSE/WS；⑤ 统一异常处理中间件；⑥ data/ 目录清理策略；⑦ CI 实跑 pdfplumber/openpyxl。

---

## [2026-05-26] · 功-4 PDF/Excel 技术文档上传索引

### Added

- **后端 `POST /api/docs/upload` / `GET /api/docs` / `DELETE /api/docs/{doc_id}`**：支持 PDF / Excel(.xlsx/.xlsm) / TXT / Markdown 上传（20MB 上限），SHA-256 内容去重，路径遍历净化，原子写 manifest.json，`BackgroundTasks` 触发 embedding 增量重建（`AGENTS_USE_EMBEDDINGS=true` 时）
- **`services/doc_chunker.py::_extract_xlsx_text()`**：openpyxl 读取多 sheet Excel，按 sheet 拼接 Tab 分隔行，损坏文件返回空字符串
- **`agents/doc_retrieval.py::_load_documents()`**：递归扫描 `data/docs/uploaded/` 下 PDF/Excel/文本；调用包入 `asyncio.to_thread()` 避免阻塞 event loop
- **`components/DocManagerButton.tsx`**：Header 上"📚 技术文档"按钮 + 弹窗式上传/列表/删除 UI
- **新依赖**：`pdfplumber 0.11.4`、`openpyxl 3.1.5`（及 transitives）

### Fixed

- **`test_doc_retrieval.py` 在 `AGENTS_USE_LLM=true` 下 hang**：autouse fixture 关闭 LLM 调用，10 用例从挂起改为 0.03s 通过
- **manifest.json 并发写竞态**：新增 `threading.Lock()` 串行化 read-modify-write
- **`api/docs.py` UploadResponse `populate_by_name`**：迁移到 Pydantic v2 `ConfigDict`

### Tests

- 后端 +16：`test_docs_api.py`(12) + `test_doc_chunker_xlsx.py`(4)
- 前端 +13：`api/docs/__tests__/route.test.ts`(8) + `components/__tests__/DocManagerButton.test.tsx`(5)
- 全量：后端核心 112 passed / 前端 **222 passed | 11 skipped**

---

## [2026-05-25 深夜] · PDF 试用反馈批量修复（AI首-2 + AI根-1）

### Added
- **模糊提问澄清门控**（AI首-2，P0）：`backend/agents/orchestrator.py` 在 meta-query 短路之后新增 `_is_vague_diagnosis_query()` 检测器和 `VAGUE_QUERY_REPLY` 引导文案。命中条件需同时满足：长度 4–30 字 + 含泛化动词（检查/看看/分析/诊断）或泛化宾语（问题/情况/这台车） + 未命中任何具体锚点（ECU 名/错误码/时间词/具体故障动词）。命中时 emit `chain_debug.path="vague_shortcut"`，直接返回 5 段式补充信息引导（故障现象/ECU/时间/错误信息/是否完成），不调 LLM、不触发 Log Analytics 在零信息下空跑。
- **无关键词日志窗口加大**（AI根-1，P0）：`backend/config.py` 新增 `LOG_ANALYSIS_NO_KEYWORD_LIMIT: int = 5000`。`backend/agents/log_analytics.py` `_load_logs_from_bundle()` 当 `keywords` 为空（用户粗粒度概览场景）时使用 `min(NO_KEYWORD_LIMIT, MAX_LIMIT)` 作为初始拉取窗口，避免「分析下这台车」类请求被困在 2000 行内遗漏关键事件。仍保持「关键词模式按 LOG_ANALYSIS_LIMIT 起步 + 阈值不足时翻倍扩窗」原行为。

### Tests
- 新增 `backend/tests/test_orchestrator_vague_shortcut.py`（25 cases）：参数化 10 hit（"检查下这台车的问题"等）+ 13 miss（含具体 ECU/错误码/时间词/meta query/短串/长描述）；端到端验证模糊提问不调 `chat_completion`、回复包含「故障现象」「ECU」、具体提问仍走正常 router。
- 更新 `backend/tests/test_log_analytics_auto_expand.py`：扩充 `test_no_expand_when_no_keywords` 断言第二次 GET 携带 `LOG_ANALYSIS_NO_KEYWORD_LIMIT` 而非旧的 `LOG_ANALYSIS_LIMIT`；新增 `test_no_keyword_limit_capped_by_max` 验证 NO_KEYWORD_LIMIT 受 MAX_LIMIT 上限钳制。
- 修正 `backend/tests/test_log_analytics_bundle.py::test_orchestrator_passes_bundle_id_to_agent_context`：原测试用 "请分析日志" 会被新模糊门控拦截，调整为 "请分析 iCGM 升级失败日志"（保留具体 ECU + 错误动词锚点）。

### Notes
- 功-3（重开浏览器默认在新会话）：经代码审查，`web/src/app/page.tsx` 的 `restoreSessions()` 已实现「localStorage preferredId → restored[0] 兜底」恢复链，逻辑正确；本轮不再修改，等待用户在最新构建上复现后再处理。
- 功-1（用户登录/隔离）+ 功-4（PDF/Excel 索引）按原计划继续暂缓。

---

## [2026-05-25] · 二次审查批量加固

### Security
- **UUID 正则收紧**（BLOCKER）：`backend/main.py` `/chat` 端点、`backend/agents/orchestrator.py` `_UUID_RE`、`web/src/app/api/chat/route.ts` 三处 `bundleId` 校验正则从宽松的 `[0-9a-f]{8}-?...` 改为严格标准格式 `^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$`，禁止 dash 混用，缩小注入面。
- **上传 `.partial` 文件清理**（MEDIUM）：`backend/log_pipeline/api/http.py` upload_bundle 的写入循环包裹 try/except，磁盘满/客户端断开/IO 异常时调用 `partial.unlink(missing_ok=True)` 并 `logger.exception` 记录上下文，防止半成品文件堆积。

### Fixed
- **session-title 502 fallback**（BLOCKER）：`web/src/app/api/session-title/route.ts` 包裹 fetch 于 try/catch，后端不可达时返回 502 + `{"title":"新会话","error":"backend_unreachable"}`，避免前端把未定义错误作为标题展示。
- **SSE 异常事件 emit**（MEDIUM）：`backend/main.py` `event_generator()` 包裹 `async for event in orchestrate(...)` 于 try/except，捕获到异常时先 `log.exception` 再 emit `{"type":"error","message":"诊断服务异常，请稍后重试"}` 和 `{"type":"done"}`，保证前端不会卡在永久 loading。
- **前端轮询资源泄漏**（HIGH）：`web/src/app/page.tsx` bundle status 轮询副作用的 `for` 循环改为 try/catch/finally 结构，捕获 fetch 异常并 `console.warn`，finally 中无条件清理 `resumedPollingKeysRef`，避免组件卸载或网络抖动导致 ref 残留。
- **extractor 异常诊断信息缺失**（HIGH）：`backend/log_pipeline/ingest/extractor.py` `extract()` 异常处理改为 `logger.exception("Extract failed: archive=%s work_dir=%s", ...)` 后再 `rmtree` 并重抛，便于线上排障。
- **workspace `append()` workspace_dir 不存在时静默成功**（bugfix）：原子写助手会 `mkdir(parents=True)` 自动创建父目录，导致 `append(fake_ctx, ...)` 不再返回 False。在 `append()` 入口新增 `ctx.workspace_dir.exists()` 前置校验恢复原契约。

### Changed
- **workspace 原子写入**（MEDIUM）：`backend/services/workspace_manager.py` 新增模块级 `_atomic_write_text()` 助手（`.partial + write + flush + fsync + os.replace`，fsync 失败容忍 OSError）；`create()` 中 focus/notes/todo 三个模板写入与 `append()` 的最终写入全部迁移到原子写。
- **`update_todo_status` 复用原子写**（MEDIUM）：`backend/services/tool_functions.py` 从 `services.workspace_manager` 延迟导入 `_atomic_write_text` 替换原 `write_text`，防止进程崩溃时 todo.md 截断。
- **embed index 写入加 fsync**（LOW）：`backend/services/vector_search.py` `save_embed_index()` 从 `partial.write_text` 改为显式 `open + write + flush + fsync(OSError 容忍) + os.replace`，与 workspace 写入保持一致的持久化保证。

### Notes
- 回归：后端聚焦套件 **360 passed**（含 workspace_manager 17、tool_functions、log_pipeline、jira/doc/rca/orchestrator/redaction/chain_log/semantic_cache/doc_chunker/evaluation/session_title）；前端全量 **209 passed | 11 skipped**。
- 所有修改文件 `get_errors` 0 错误。
- 未实施：`backend/api/session_title.py` 已是 `except Exception` + `logger.exception` 设计；`extractor.py` rarfile 延迟导入为可选依赖设计；`route.ts` `BACKEND_URL` 默认值由 systemd 注入，均为有意保留。

---

## [2026-05-25]

### Added
- **元问题确定性短路**（A1/A2）：`backend/agents/orchestrator.py` 在 LLM 路由前增加 `_META_QUERY_PATTERNS` 正则集与 `_is_meta_query()` 判定（长度 ≤30 + pattern 命中，覆盖"你是谁/什么模型/能做什么/版本/介绍一下/你好/在吗/hi"等）。命中后直接 emit `META_QUERY_REPLY`（"Velab FOTA 智能诊断助手"友好自我介绍）+ `chain_debug.path="meta_shortcut"`，**完全不消耗 LLM token**。
- **日志窗口自动扩展**（R1）：`backend/config.py` 新增 4 个可调参数 `LOG_ANALYSIS_LIMIT=2000`、`LOG_ANALYSIS_MAX_LIMIT=10000`、`LOG_ANALYSIS_AUTO_EXPAND=True`、`LOG_ANALYSIS_EXPAND_THRESHOLD=50`。`LogAnalyticsAgent._load_logs_from_bundle()` 改为 `while True` 循环：当启用 auto_expand 且有关键词且命中行数 < 阈值且当前 limit < max 时，limit 翻倍重新拉取，直至命中足够或触顶。
- **场景切换器特性开关**（F2）：`web/src/components/Header.tsx` 新增 `NEXT_PUBLIC_SHOW_SCENARIO_SWITCHER` 环境变量；设为 `false` 时下拉按钮替换为纯文本场景名，下拉面板不展开（默认未设置时保持可见，向后兼容）。
- **新增测试**：
  - `backend/tests/test_orchestrator_meta_shortcut.py`（28 cases）— 参数化 19 hit + 7 miss + 2 LLM 调用断言。
  - `backend/tests/test_log_analytics_auto_expand.py`（5 cases）— 覆盖阈值上下、触顶、disabled、no_keywords 场景。

### Fixed
- **上传摘要卡窄视口溢出**（A3）：`web/src/components/UploadSummaryCard.tsx` 外层 `<section>` className 追加 `min-w-0 max-w-full overflow-hidden`，修复 EventDigest/Brush 在窄视口下横向溢出主气泡。

### Changed
- **`SYSTEM_PROMPT_TEMPLATE` 加固**：`orchestrator.py` 强化"何时不要调用 Agent"章节，明确即使已有 bundle 上下文，遇到模糊问题也应先反问澄清而非直接调用 Agent。

### Deferred
- **F1 认证体系**：本轮暂缓，纳入 Sprint 6 后续规划。
- **F4 文档上传 UI**：本轮暂缓，纳入 Sprint 6 后续规划。

### Notes
- F3（模型分层路由）已在 [2026-05-07] 修复，本轮验证可用。
- 验证：新增 33 用例全绿；既有 `test_log_analytics_bundle.py`（11）回归通过；Agent 层聚焦回归 88+ 测试无失败；前端全量 `npm test -- --run` **209 passed | 11 skipped**。

---

## [2026-05-23]

### Added
- **Embedding 知识检索闭环**：`jira_knowledge` 与 `doc_retrieval` 现在支持 `AGENTS_USE_EMBEDDINGS=true` 时优先加载离线预计算索引（`backend/data/indexes/vector/`），启动时会预热 `jira_tickets.json` / `tech_docs.json`，并在 `AgentResult` / workspace notes 中透传 `retrieval_mode`（`embedding` / `tfidf` / `tfidf_fallback`）。
- **预计算索引版本化**：`services/vector_search.py` 的索引文件新增 `version` 与 `items` 结构，并对格式进行读取校验，避免未来格式升级时静默失配。
- **知识检索可观测性增强**：检索结果 now carry `retrieval_mode`，方便在日志、workspace 与后续排障中识别实际命中的检索路径。

### Fixed
- **Scenario B 模型全部落到 Haiku**：`llm.py` 的 `_resolve_anthropic_model()` / `_resolve_openai_model()` 原将三个虚拟别名（`router-model`、`agent-model`、`synthesizer-model`）统一映射到同一个 `ANTHROPIC_DEFAULT_MODEL`（默认 `claude-haiku-4-5-20251001`），导致场景 B 直连模式下所有 Agent（含 RCA 根因分析）均跑 Haiku。
- **`rca_synthesizer.py` 错用 `agent-model`**：`_llm_synthesize()` 中 `model="agent-model"` 改为 `model="synthesizer-model"`，确保 RCA 走 Synthesizer 层路由。
- **Embedding 索引未被运行时消费**：`doc_retrieval.py` 之前始终走 TF-IDF，`jira_knowledge.py` 之前每次请求重复全量向量化，现已统一为"预计算索引优先 + 在线 embedding 兜底 + TF-IDF 回退"的生产链路。
- **前端 CI 分支覆盖率误计入测试辅助代码**：`vitest.config.ts` 排除 `src/__tests__/**`，避免 MSW handlers / 测试工具代码拉低全局 branch coverage，恢复 `branches >= 70%` 质量门槛的有效性。

### Changed
- `services/llm.py`：三层别名分别映射，各自支持独立环境变量覆盖：
  - `router-model` → `ANTHROPIC_ROUTER_MODEL`（默认 `claude-haiku-4-5-20251001`）/ `OPENAI_ROUTER_MODEL`（默认 `gpt-4o-mini`）
  - `agent-model` → `ANTHROPIC_AGENT_MODEL`（默认 `claude-sonnet-4-6`）/ `OPENAI_AGENT_MODEL`（默认 `gpt-4o`）
  - `synthesizer-model` → `ANTHROPIC_SYNTHESIZER_MODEL`（默认 `claude-sonnet-4-6`）/ `OPENAI_SYNTHESIZER_MODEL`（默认 `gpt-4o`）
- `backend/.env` / `.env.example`：废弃 `ANTHROPIC_DEFAULT_MODEL`，替换为三条分层配置注释。
- `_pick_available_anthropic_model()` 降级列表：首位改为读取 `ANTHROPIC_AGENT_MODEL`，`claude-sonnet-4-6` 置于优先队首。
- `backend/main.py`：启动时预热 embedding 索引，降低首请求延迟并保证离线索引可直接复用。
- `backend/services/vector_search.py`：embedding 索引增加版本号与进程内缓存，查询结果增加 `retrieval_mode`，embedding 失败显式回退 TF-IDF。
- `backend/agents/base.py`：`AgentResult` 增加 `retrieval_mode` 字段，统一承载检索模式信息。

---

## [2026-05-07]

### Added
- `LogAnalyticsAgent` 新增可选 `time_hint` 参数支持：用户用自然语言描述故障时间（如"9月11日凌晨"、"晚上21点"），LLM 提取后通过 orchestrator 注入 agent context，将日志查询窗口缩窄至相关时段；无法解析时自动退化为全量分析。
- 新增 `_parse_time_hint()` 函数，支持中文月日、时段限定词（凌晨/上午/下午/晚上等）及精确小时的解析，以 bundle 有效时间范围为日历参考锚点。
- `LogAnalyticsAgent.tool_schema()` 覆盖方法：在 LLM 函数调用 schema 中暴露可选 `time_hint` 字段。
- `orchestrator._run_agent()` 注入 `time_hint` 到 `agent_context`。

---

## [2026-05-03 23:59]

### Added
- **EventDigest 上传摘要卡**：日志包处理完成后，聊天界面自动展示事件摘要（最近重启、最后严重故障、FOTA 升级结果及事件计数）。
  - `web/src/lib/types.ts`：新增 `EventDigestItem`、`EventDigest` 接口；`UploadSummary` 扩展可选 `eventDigest` 字段。
  - `web/src/app/page.tsx`：`handleSend()` 在 bundle 处理完成后调用 `/api/bundle-events/{id}?limit=500`，计算 digest 并附加到 `uploadSummaries`。
  - `web/src/components/UploadSummaryCard.tsx`：新增 `EventDigestPanel` 组件，渲染重启/故障/FOTA 结果行。
- **RAR 归档上传支持**：`log_pipeline/ingest/extractor.py` 支持 `.rar` 格式，依赖系统 `unrar`；`requirements.txt` 新增 `rarfile==4.2`。
- **裸文件上传支持**：`.log / .txt / .dlt` 文件可直接上传，不再要求打包成压缩档。
- **一键开发脚本 `scripts/dev.sh`**：启动前自动清理旧进程（SIGTERM→SIGKILL），按 `DEPLOYMENT_MODE` 决定是否启动 LiteLLM Gateway。
- **本地 CI 验证脚本 `scripts/test-ci.sh`**：复刻完整 CI 流程（PostgreSQL/Redis 前置检查 → flake8 → pytest → eslint → vitest），发 PR 前必跑。
- **Copilot 辅助开发体系**：`.agents/skills/` 25 个领域技能文件 + `.github/agents/` 3 个 Persona 文件 + `.github/copilot-instructions.md`。
- **后端集成测试补全**（共新增 8 个文件 131 个用例）：覆盖 `session_title`、`rca_synthesizer`、`doc_chunker`、`feedback_api`、`jira_knowledge`、`doc_retrieval`、`evaluation`、`log_analytics_bundle`，及 `log_pipeline/tests/test_http_upload.py`（10 用例）。
- **后端单元测试补全**（新增 4 个文件 63 个用例）：覆盖 `common/redaction.py`（VIN/手机号/车牌脱敏 + async 装饰器）、`common/chain_log.py`（trace_id 管理 + step_timer）、`services/tool_functions.py`、`services/semantic_cache.py`。
- **前端 API Route 测试**（新增 7 个文件 16 个用例）：sessions、sessions/[sessionId]、session-title、upload-log、bundle-status/[bundleId]、bundle-events/[bundleId]、bundle-logs/[bundleId] 全覆盖。

### Fixed
- **Bundle-Agent 断链**：`LogAnalyticsAgent._load_logs()` 原固定读取 `data/logs/` mock 数据，与上传的真实日志完全断链。新增 `_load_logs_from_bundle()` 方法，正确读取 `valid_time_range_by_controller` 字段（修复字段名错误 `valid_time_range` → `valid_time_range_by_controller`）。
- **catalog.py 时间范围计算**：SQL CASE 表达式的 `ELSE NULL` 改为 `ELSE valid_ts_min/max`，修复 FOTA Java 文本日志（`clock_offset=NULL`、时间戳已是 wall-clock）被排除在有效时间范围之外的问题。
- **`_file_overlaps()` 空窗口**：`range_query.py` 修复 `clock_offset is None` 时错误返回 `False`，导致有效日志文件被跳过。
- **`unsynced_files` 双重发送**：修复已在窗口集中的文件又出现在 `unsynced_files` 列表的问题，条件增加 `valid_ts_min is None`。
- **`_extract_plain` UUID 前缀 Bug**：上传文件保存为 `{uuid32}__原始名`，修复后使用原始文件名供分类器匹配（`_UPLOAD_PREFIX_RE` 剥离前缀）。
- **路径遍历漏洞**：`_should_skip()` 新增 `".." in parts` 和绝对路径检测，阻断 RAR/ZIP/TAR 归档中的任意文件写入攻击（[C-2]）。
- **`main.py` bundle_id UUID 校验**：API 边界增加 `re.fullmatch` UUID 格式验证，非法值返回 400（[I-1]）。
- **orchestrator bundle_id 防伪造**：从 `conversation_history` 自动提取的 `bundleId` 增加正则校验（[I-2]）。
- **前端 XSS 防护**：`ChatMessage.tsx` 新增 `escapeHtml()`/`sanitizeUrl()`；`next.config.ts` 添加 5 个安全响应头（[I-5]）。
- **CI 修复**：`ci.yml` 补全 `POSTGRES_DB` 等环境变量；新增 Redis 7 service；flake8 增加 `--exclude=venv,.venv`。
- **前端 CVE 修复**：`npm audit fix` 修复 Vite 3 个 HIGH CVE；`package.json overrides` 强制 `postcss ≥ 8.5.10`。

### Changed
- `backend/main.py` CORS 由通配符收窄为 `ALLOWED_ORIGINS` 环境变量控制。
- `orchestrator.orchestrate()` 新增 `bundle_id` 参数，未传时自动从 `conversation_history` 中扫描最近 `upload_summary` 提取。
- `web/src/app/api/chat/route.ts` 新增 `bundleId` 校验，透传给后端 `/chat` 端点。
- `vitest.config.ts` 新增覆盖率红线：branches ≥ 70%，functions ≥ 70%，lines ≥ 80%，statements ≥ 80%。
- `vector_search.py` 原子写入：`.partial + os.replace()` 模式防止索引文件损坏（[I-4]）。

---

## [2026-04-10 03:36]

### Fixed
- **部署脚本加固**：
  - `backend/scripts/check_env.sh`：修复 `CRITICAL_PACKAGES` 格式（`pip包名:模块名`）、`set -e` + heredoc 失效问题、变量名与实际 env 不对齐三处 Bug。
  - `backend/scripts/deploy.sh`：Step 6 新增强随机 `POSTGRES_PASSWORD` 自动生成（检测弱密码 `fota_password` 时替换）；Step 8 systemd restart 后执行 `is-active` 验证。
  - `gateway/scripts/deploy.sh`：venv 检查改为检测 `venv/bin/pip` 存在性，防止不完整 venv 跳过重建。
  - `scripts/deploy-all.sh`：新增 `--mode`/`--domain` 命令行参数，支持非交互式 CI/CD 执行；对账阶段新增 LLM API Key 占位值检测和弱密码检测。

### Changed
- `config.py` 新增 `REDIS_PASSWORD` 字段；`LITELLM_API_KEY` 默认值对齐为 `sk-fota-virtual-key`。
- `gateway/systemd/litellm.service`：`--host`/`--port` 改为读取环境变量 `${HOST:-127.0.0.1}`/`${PORT:-4000}`。
- `backend/.env.example` / `gateway/.env.example`：补全注解、修正注释错误、新增 `GATEWAY_LOG_PATH` 文档化。

---

## [2026-04-06 18:57] — Sprint 4

### Added
- **DocRetrieval Agent**（第 3 个 Agent）：`agents/doc_retrieval.py`，加入 `SCENARIO_AGENT_MAP`。
- **向量检索服务**：`services/vector_search.py`，TF-IDF baseline，预留 embedding 接口。
- **语义缓存服务**：`services/semantic_cache.py`，SHA-256 精确匹配模式。
- **Agent Tool Use 函数**：`services/tool_functions.py`，实现 `extract_timeline_events`、`fetch_raw_line_context`、`search_fota_stage_transitions`。
- **PDF/文本切块服务**：`services/doc_chunker.py`，支持 3 种切块策略。
- **诊断反馈 API**：`api/feedback.py`，5 个端点。
- **Prometheus 监控指标**：`api/metrics.py`。
- **评测框架**：`services/evaluation.py`，5 个标准 case，5 维评分。
- 演示日志扩充至 5 份，Jira 工单扩充至 10 个。
- `vitest.config.ts` 添加覆盖率 thresholds。

### Changed
- `backend/main.py` 从废弃的 `@app.on_event` 迁移至 `lifespan` context manager。
- `agents/rca_synthesizer.py` 新增 `_validate_citations()` 引用 ID 断言验证。

---

## [2026-03-23 15:35]

### Added
- 多 Agent 协作架构初始实现：`LogAnalyticsAgent`、`JiraKnowledgeAgent`、`RCASynthesizerAgent`、`Orchestrator`。
- `BaseAgent` 抽象基类与 `registry` 全局注册表。
- FastAPI 后端骨架（SSE 流式响应、`/chat` 端点）。
- Next.js 前端骨架（App Router、SSE 消费、`ChatMessage` / `ThinkingProcess` 组件）。
- `common/chain_log.py`：全链路 trace_id 追踪。
- `common/redaction.py`：VIN 码、手机号、车牌号脱敏。
- `services/llm.py`：统一 LLM 客户端抽象，支持 LiteLLM Gateway 转发。
- `gateway/`：基于 LiteLLM 的模型网关配置（多模型路由、负载均衡）。
- `log_pipeline/` 子系统：DLT 解码器、FOTA 文本解码器、事件规则引擎、SQLite bundle catalog、NDJSON 流式查询。
- PostgreSQL + Redis 基础设施集成，systemd 服务单元文件。

