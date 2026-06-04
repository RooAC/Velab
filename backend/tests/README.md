# Backend 测试说明

本目录包含 Velab backend 平台业务侧测试，覆盖 FastAPI API、鉴权、就绪检查、Agent 编排、检索、文档处理、反馈、会话、脱敏和工具函数等。log_pipeline 子系统有独立测试目录：`backend/log_pipeline/tests/`。

---

## 当前测试文件

```text
tests/
├── conftest.py
├── test_api_sessions.py
├── test_auth.py
├── test_chain_log.py
├── test_doc_chunker.py
├── test_doc_chunker_xlsx.py
├── test_doc_retrieval.py
├── test_docs_api.py
├── test_evaluation.py
├── test_feedback_api.py
├── test_jira_knowledge.py
├── test_jira_sync.py
├── test_log_analytics_auto_expand.py
├── test_log_analytics_bundle.py
├── test_orchestrator_meta_shortcut.py
├── test_orchestrator_vague_shortcut.py
├── test_rca_synthesizer.py
├── test_readiness.py
├── test_redaction.py
├── test_semantic_cache.py
├── test_session_title.py
├── test_tool_functions.py
├── test_vector_search_embedding.py
└── test_workspace_manager.py
```

重点覆盖：

- `test_auth.py`：`AUTH_ENABLED`、Bearer token、`X-API-Key` 行为
- `test_readiness.py`：`/ready` 深度就绪检查成功与失败路径
- `test_docs_api.py` / `test_doc_chunker*.py` / `test_doc_retrieval.py`：技术文档上传、切块和检索
- `test_log_analytics*.py`：LogAnalyticsAgent 调用 bundle API、自动扩窗与证据整理
- `test_orchestrator_*.py` / `test_rca_synthesizer.py`：Agent 编排和 RCA 汇总
- `test_feedback_api.py` / `test_api_sessions.py` / `test_session_title.py`：业务 API
- `test_redaction.py` / `test_chain_log.py`：脱敏与链路日志

---

## 安装依赖

```bash
cd /home/Velab/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

如只需要快速补齐 pytest：

```bash
cd /home/Velab/backend
pip install pytest pytest-cov
```

---

## 运行测试

建议从 backend 目录运行，确保模块导入路径与生产入口一致：

```bash
cd /home/Velab/backend
```

常用命令：

```bash
# 平台业务侧测试
python -m pytest tests/ -q

# log_pipeline 独立测试
python -m pytest log_pipeline/tests/ -q

# backend 全量测试
python -m pytest tests/ log_pipeline/tests/ -q

# 鉴权与深度就绪检查
python -m pytest tests/test_auth.py tests/test_readiness.py -q

# 单文件或单用例
python -m pytest tests/test_docs_api.py -q
python -m pytest tests/test_readiness.py::test_ready_returns_503_when_database_fails -q

# 封装脚本：默认只跑 tests/
python run_tests.py
python run_tests.py tests/test_auth.py -q
```

覆盖率：

```bash
cd /home/Velab/backend
python -m pytest tests/ --cov=api --cov=agents --cov=services --cov=common --cov-report=term-missing
```

---

## 测试环境说明

- `tests/conftest.py` 会为平台业务测试提供测试 client、临时数据目录和数据库替身，避免依赖生产 PostgreSQL
- 测试默认不需要真实 `.env` 密钥；不要为了测试把真实 API key 写进仓库
- 涉及 LLM、embedding、外部 Jira 的测试应使用 mock、fixture 或本地样例数据
- `log_pipeline/tests/` 使用自己的 fixtures，聚焦 SQLite catalog、文件存储、解码、预扫、对齐和查询

---

## 新增测试建议

新增行为时优先增加靠近行为边界的测试：

- API 鉴权、状态码、响应结构：放在 `tests/test_*_api.py`
- Agent 分支、编排快捷路径、证据字段：放在对应 Agent 或 orchestrator 测试中
- log_pipeline 解码、索引、查询、状态流转：放在 `log_pipeline/tests/`
- 部署探针或依赖检查：放在 `tests/test_readiness.py`

测试命名建议：

```python
def test_ready_returns_503_when_redis_queue_fails():
    ...
```

保持 AAA 结构即可：

```python
def test_example(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

---

## 常见问题

### `ModuleNotFoundError`

确认从 backend 目录运行：

```bash
cd /home/Velab/backend
python -m pytest tests/ -q
```

### `/ready` 测试失败

`/ready` 会检查 PostgreSQL、Redis/Arq、log_pipeline state、Agent 和 LiteLLM Gateway。测试应 mock 依赖失败或成功路径，不应访问生产服务。

### 误连真实服务

检查测试中是否直接读取了真实 shell 环境变量。需要外部依赖的逻辑应通过 monkeypatch/mock 固定输入。

---

## 相关文档

- [../README.md](../README.md)：backend 当前生产形态与运维
- [../tasks/README.md](../tasks/README.md)：Arq worker 与任务队列
- [../log_pipeline/CLAUDE.md](../log_pipeline/CLAUDE.md)：log_pipeline 设计契约
