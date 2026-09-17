# 传统 RAG Baseline Migration 正式验收报告

- 验收日期：2026-09-01
- 目标仓库：`MyMODULAR-RAG-MCP-SERVER`
- 只读基线：`../MODULAR-RAG-MCP-SERVER`
- 范围：传统 RAG 的 A1–I5；J–N 未实施；使用用户提供的 DashScope 凭证做小额有界验收；未创建 Git commit。
- 最终结论：4 份真实 PDF 的 ingestion、hybrid retrieval、CLI/MCP citation 和 golden evaluation 已通过；Dashboard 人工 walkthrough 与 DashScope embedding 权限稳定性仍保留 `[~]`。

## A1–I5 验收映射

状态以目标仓库中的实现和本轮实际测试为准，不继承旧项目 `DEV_SPEC.md` 的完成记录。

| ID | 目标实现文件 | 目标测试/证据 | 状态 |
|---|---|---|---|
| A1 | `main.py`, `src/**/__init__.py`, 根兼容包 | `test_smoke_imports.py`, `test_public_imports.py`, `python main.py`, `compileall` | `[x]` |
| A2 | `pyproject.toml`, `tests/{unit,integration,e2e}` | pytest 收集 1378 项，marker/目录分层有效 | `[x]` |
| A3 | `src/core/settings.py`, `config/settings.yaml` | `test_config_loading.py`, 静态 settings/prompts 加载 | `[x]` |
| B1 | `src/libs/llm/base_llm.py`, `llm_factory.py` | `test_llm_factory.py` | `[x]` |
| B2 | `src/libs/embedding/base_embedding.py`, `embedding_factory.py` | `test_embedding_factory.py` | `[x]` |
| B3 | `src/libs/splitter/base_splitter.py`, `splitter_factory.py` | `test_splitter_factory.py` | `[x]` |
| B4 | `src/libs/vector_store/base_vector_store.py`, `vector_store_factory.py` | `test_vector_store_contract.py` | `[x]` |
| B5 | `src/libs/reranker/base_reranker.py`, `reranker_factory.py` | `test_reranker_factory.py`, `test_reranker_fallback.py` | `[x]` |
| B6 | `src/libs/evaluator/base_evaluator.py`, `evaluator_factory.py`, `custom_evaluator.py` | `test_custom_evaluator.py` | `[x]` |
| B7.1 | `openai_llm.py`, `azure_llm.py`, `deepseek_llm.py` | `test_llm_providers_smoke.py`（mock） | `[x]` |
| B7.2 | `src/libs/llm/ollama_llm.py` | `test_ollama_llm.py`（mock） | `[x]` |
| B7.3 | `openai_embedding.py`, `azure_embedding.py` | `test_embedding_providers_smoke.py`（mock） | `[x]` |
| B7.4 | `src/libs/embedding/ollama_embedding.py` | `test_ollama_embedding.py`（mock） | `[x]` |
| B7.5 | `src/libs/splitter/recursive_splitter.py` | `test_recursive_splitter_lib.py` | `[x]` |
| B7.6 | `src/libs/vector_store/chroma_store.py` | `test_chroma_store_roundtrip.py`，20/20 连续两轮通过 | `[x]` |
| B7.7 | `src/libs/reranker/llm_reranker.py` | `test_llm_reranker.py`（mock/fallback） | `[x]` |
| B7.8 | `src/libs/reranker/cross_encoder_reranker.py` | `test_cross_encoder_reranker.py`（mock/fallback） | `[x]` |
| B8 | `base_vision_llm.py`, `openai_vision_llm.py`, factory | `test_vision_llm_factory.py` | `[x]` |
| B9 | `src/libs/llm/azure_vision_llm.py` | `test_azure_vision_llm.py`（mock） | `[x]` |
| C1 | `src/core/types.py` | `test_core_types.py` | `[x]` |
| C2 | `src/libs/loader/file_integrity.py` | `test_file_integrity.py` | `[x]` |
| C3 | `base_loader.py`, `pdf_loader.py` | 4 份真实 PDF/159 页；图片提取与 page-aware metadata；loader 测试 | `[x]` |
| C4 | `src/ingestion/chunking/document_chunker.py` | 稳定 ID、逐页切块、`page/page_num` 测试 | `[x]` |
| C5 | `base_transform.py`, `chunk_refiner.py` | 规则/Mock 通过；`qwen-plus` 真实 refine 11/11 | `[x]` |
| C6 | `src/ingestion/transform/metadata_enricher.py` | 规则/Mock 通过；`qwen-plus` 真实 enrich 11/11 | `[x]` |
| C7 | `src/ingestion/transform/image_captioner.py` | fallback 测试；`qwen-vl-max` 真实 caption 4/4 | `[x]` |
| C8 | `src/ingestion/embedding/dense_encoder.py` | `test_dense_encoder.py` | `[x]` |
| C9 | `src/ingestion/embedding/sparse_encoder.py` | `test_sparse_encoder.py` | `[x]` |
| C10 | `src/ingestion/embedding/batch_processor.py` | `test_batch_processor.py` | `[x]` |
| C11 | `src/ingestion/storage/bm25_indexer.py` | `test_bm25_indexer_roundtrip.py` | `[x]` |
| C12 | `src/ingestion/storage/vector_upserter.py` | `test_vector_upserter_idempotency.py` | `[x]` |
| C13 | `src/ingestion/storage/image_storage.py` | `test_image_storage.py` | `[x]` |
| C14 | `src/ingestion/pipeline.py` | 4 PDF→251 chunks/36 images→dense/BM25/Chroma；幂等 skip | `[x]` |
| C15 | `scripts/ingest.py` | 本地分支通过；真实 provider CLI 4/4 成功 | `[x]` |
| D1 | `src/core/query_engine/query_processor.py` | `test_query_processor.py` | `[x]` |
| D2 | `src/core/query_engine/dense_retriever.py` | `test_dense_retriever.py`, Chroma round-trip | `[x]` |
| D3 | `src/core/query_engine/sparse_retriever.py` | `test_sparse_retriever.py` | `[x]` |
| D4 | `src/core/query_engine/fusion.py` | `test_fusion_rrf.py` | `[x]` |
| D5 | `src/core/query_engine/hybrid_search.py` | `test_hybrid_search.py` | `[x]` |
| D6 | `src/core/query_engine/reranker.py` | `test_reranker_fallback.py` | `[x]` |
| D7 | `scripts/query.py` | 真实集合查询正确页 Top-1；dense 403 时 BM25 fallback | `[x]` |
| E1 | `src/mcp_server/server.py` | `test_mcp_server.py`, `test_mcp_client.py` 的离线 stdio 用例 | `[x]` |
| E2 | `src/mcp_server/protocol_handler.py` | `test_protocol_handler.py` | `[x]` |
| E3 | `src/mcp_server/tools/query_knowledge_hub.py` | `test_query_knowledge_hub.py`（注入式传统路径、citation、MCP） | `[x]` |
| E4 | `src/mcp_server/tools/list_collections.py` | `test_list_collections.py`, 离线 stdio E2E | `[x]` |
| E5 | `src/mcp_server/tools/get_document_summary.py` | `test_get_document_summary.py`, 离线 stdio E2E | `[x]` |
| E6 | `response_builder.py`, `multimodal_assembler.py` | `test_response_builder.py`, `test_multimodal_assembler.py` | `[x]` |
| F1 | `src/core/trace/trace_context.py` | `test_trace_context.py` | `[x]` |
| F2 | `src/observability/logger.py` | `test_jsonl_logger.py` | `[x]` |
| F3 | query engine + query tool trace hooks | `test_query_trace.py`, query tool 离线 trace | `[x]` |
| F4 | `src/ingestion/pipeline.py` trace hooks | `test_ingestion_trace.py` | `[x]` |
| F5 | `src/ingestion/pipeline.py` `on_progress` | `test_pipeline_progress.py`, offline pipeline | `[x]` |
| G1 | dashboard `app.py`, `overview.py`, `config_service.py` | `test_dashboard_smoke.py`, `test_dashboard_config.py` | `[x]` |
| G2 | `src/ingestion/document_manager.py` | `test_document_manager.py` | `[x]` |
| G3 | `dashboard/pages/data_browser.py`, `data_service.py` | 空数据 AppTest 通过；真实索引浏览/筛选未人工验收 | `[~]` |
| G4 | `dashboard/pages/ingestion_manager.py` | 无头渲染通过；上传/摄取/删除交互未人工验收 | `[~]` |
| G5 | `dashboard/pages/ingestion_traces.py`, `trace_service.py` | service/空页通过；真实 trace 交互未人工验收 | `[~]` |
| G6 | `dashboard/pages/query_traces.py`, `trace_service.py` | service/空页通过；真实 query trace 交互未人工验收 | `[~]` |
| H1 | `src/observability/evaluation/ragas_evaluator.py` | `test_ragas_evaluator.py`（mock） | `[x]` |
| H2 | `composite_evaluator.py` | `test_composite_evaluator.py` | `[x]` |
| H3 | `eval_runner.py`, `scripts/evaluate.py`, acceptance golden/runner | 20 条页码标注 QA，真实指标输出 | `[x]` |
| H4 | `dashboard/pages/evaluation_panel.py` | `test_evaluation_panel.py`；真实结果交互未人工验收 | `[~]` |
| H5 | `tests/e2e/test_recall.py`, acceptance runner | 251 chunks：Hit@10=1.000，MRR=0.7138 | `[x]` |
| I1 | MCP server + 三个 tools | stdio E2E；真实 `query_knowledge_hub` 返回 3 citations/正确页码 | `[x]` |
| I2 | 六个 dashboard 页面 | `test_dashboard_smoke.py` 6/6 | `[x]` |
| I3 | `README.md` | 内容审查通过；截图与人工 walkthrough 缺失 | `[~]` |
| I4 | 公共接口、兼容包及契约测试 | 分层：1328 passed / 0 failed / 1 skipped / 49 deselected | `[x]` |
| I5 | ingestion/query/MCP/dashboard/evaluation 全链路 | 除 Dashboard 人工联调外已实测；embedding 权限出现间歇性 403 | `[~]` |

汇总：A–I 共 68 项，`[x]` 61 项，`[~]` 7 项，阻塞 `[ ]` 0 项。全规格 107 项中 J–N 的 39 项保持 `[ ]`。

## 迁移完整性与工作区审计

- 对源项目要求范围 `src/`、`tests/`、`config/`、`scripts/`、`main.py`、`pyproject.toml`、`README.md` 做逐文件内容比对（文本统一换行后比较，二进制逐字节比较）：源文件 201 个，目标同内容 154 个，因兼容/迁移调整不同 47 个，缺失 0 个。
- 目标新增 3 个基线验收测试：`test_ingestion_pipeline_offline.py`、`test_image_captioner_fallback.py`、`test_public_imports.py`；本轮再新增 `test_query_knowledge_hub.py`。
- 保留目标根兼容包 `core/`、`ingestion/`、`libs/`、`mcp_server/`、`observability/`，公共 `src.*` 与旧导入路径均可导入。
- 目标自有 `AGENTS.md`、`.agents/`、`DEV_SPEC_selfrag.md` 均存在；`.agents` 的 sync 脚本明确以 `DEV_SPEC_selfrag.md` 为输入。目标已有且受 Git 跟踪的 `.claude/` 未被迁移覆盖。
- 未发现迁入的源 `.git`、`.venv`、cache、build/dist、日志、数据库、运行数据、`.env` 或真实密钥。凭证始终从仓库外文件读取并只注入子进程环境；配置文件不含 key。目标 `.venv` 是本仓库独立环境。
- 测试生成的 `.pytest_cache`、`__pycache__` 和临时验收目录仅为本地可再生数据，交付前清理；空的版本化测试 fixture 目录不包含运行数据。

## 本轮迁移缺陷修复

- 外部服务测试默认显式 skip：`tests/conftest.py` 增加 `--run-llm` opt-in；README 同步说明。
- CWD/Windows 路径：`scripts/query.py`、`scripts/evaluate.py`、`list_collections.py`、`get_document_summary.py`、`evaluation_panel.py` 统一通过 `resolve_path()` 解析仓库相对数据路径。
- `query_knowledge_hub.py` 遵守构造器的 hybrid-search 注入契约，离线传统路径不会隐式创建真实 provider。
- `chroma_store.py` 在关闭时释放 collection/client 和 Rust 引用周期，修复 Windows SQLite 临时文件锁。
- 新增 `tests/unit/test_query_knowledge_hub.py`；更新 `DEV_SPEC_selfrag.md` 的逐项状态与测试证据。
- OpenAI-compatible LLM/Vision 现在遵守 YAML `base_url`；`text-embedding-v4` 可发送配置的 1024 维参数，并补充回归测试。
- PDF loader 增加逐页临时文本，chunker 产生 `page/page_num` citation metadata，同时不把逐页全文写入向量元数据；图片占位符保留真实页归属。
- 新增 4 份受控 PDF fixtures、20 条带来源页码 QA、DashScope 小额/批量配置及真实 hybrid acceptance runner。

## 执行命令与结果

所有产生验收证据或工作区变更的命令归一化记录如下（所有 Python/pytest 命令均使用目标 `.venv`；重复命令及中间失败另列）：

```powershell
git status --short --branch
git diff --stat
git diff -- .gitignore README.md
git diff --quiet HEAD -- AGENTS.md .agents DEV_SPEC_selfrag.md .claude
rg --files src tests config scripts
# PowerShell SHA-256 源/目标逐文件审计与禁止产物/敏感字面量扫描
# Get-Content/rg 审查 AGENTS、DEV_SPEC_selfrag、auto-coder/qa-tester 技能说明、QA plan/progress、源码与测试契约

.\.venv\Scripts\python.exe .agents\skills\auto-coder\scripts\sync_spec.py
.\.venv\Scripts\python.exe -c "# import 10 public packages; load settings and 3 prompts"
.\.venv\Scripts\python.exe -m compileall -q main.py src mcp_server core ingestion libs observability scripts tests
.\.venv\Scripts\python.exe main.py

.\.venv\Scripts\python.exe -m pytest -q tests\unit
.\.venv\Scripts\python.exe -m pytest -q -rs tests\unit\test_recursive_splitter_lib.py
.\.venv\Scripts\python.exe -m pytest -q -rs tests\integration
.\.venv\Scripts\python.exe -m pytest -q -rs tests\e2e
.\.venv\Scripts\python.exe -m pytest -q tests\integration\test_chunk_refiner_llm.py
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_list_collections.py
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_get_document_summary.py
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_evaluation_panel.py

# 从临时非仓库 CWD 执行：
..\.venv\Scripts\python.exe ..\scripts\query.py --help
..\.venv\Scripts\python.exe ..\scripts\evaluate.py --no-search --json

.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_query_knowledge_hub.py
.\.venv\Scripts\python.exe -m pytest -q tests\integration\test_chroma_store_roundtrip.py
.\.venv\Scripts\python.exe -m pytest -q tests\integration\test_chroma_store_roundtrip.py
.\.venv\Scripts\python.exe -m pytest -q -rs

# 本轮真实资料与 provider 验收（凭证仅从仓库外文件注入环境变量）
.\.venv\Scripts\python.exe scripts\ingest.py --path tests\fixtures\acceptance_documents\润本股份.pdf --collection acceptance_2025_reports --config config\settings.dashscope.yaml --verbose
.\.venv\Scripts\python.exe scripts\ingest.py --path tests\fixtures\acceptance_documents --collection acceptance_2025_reports --config config\settings.dashscope.bulk.yaml
.\.venv\Scripts\python.exe scripts\evaluate_acceptance_corpus.py --config config\settings.dashscope.bulk.yaml --top-k 10
.\.venv\Scripts\python.exe scripts\query.py --query "二六三重点布局的三大业务领域是什么？" --collection acceptance_2025_reports --top-k 3 --config config\settings.dashscope.bulk.yaml --no-rerank
# Python one-liner：使用 QueryKnowledgeHubTool 查询润本预测收入/EPS，并检查 citations/source/page/structured keys

.\.venv\Scripts\python.exe -m pytest tests\unit\test_llm_providers_smoke.py tests\unit\test_embedding_providers_smoke.py tests\unit\test_vision_llm_factory.py tests\unit\test_acceptance_golden_set.py -q
.\.venv\Scripts\python.exe -m pytest tests\unit\test_document_chunker.py tests\unit\test_loader_pdf_contract.py tests\integration\test_pdf_loader_integration.py -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m pytest tests\integration -m "not llm" -q
.\.venv\Scripts\python.exe -m pytest tests\e2e -m "not llm" -q

python .agents\skills\auto-coder\scripts\sync_spec.py --force
# PowerShell 校验绝对目标路径后清理 .pytest_cache、非 .venv 的 __pycache__、临时 CWD、data、logs、test_data
# PowerShell/rg 最终复扫禁止目录、数据库/日志/.env、Self-RAG 运行时代码引用、规格同步结果与 git 状态
```

本轮最终分层测试统计：**1328 passed，0 failed，1 skipped，49 deselected**。其中 unit 1219/0/1，integration 90/0/0（36 个 `llm` 用例 deselected），E2E 19/0/0（13 个 `llm` 用例 deselected）。真实 provider 流程另计：4 PDF 入库成功、20/20 QA 页码命中、CLI/MCP 各返回有效结果。

修复轮次中的中间失败没有被隐藏：首次 query tool 定向测试为 2 passed / 1 failed（测试使用了 Pydantic 字段别名，修正断言后 3 passed）；第一次修复后全量回归为 1322 passed / 50 skipped / 3 Windows teardown errors；Chroma 定向重测依次出现 20 passed / 9 errors、20 passed / 1 error，完成资源释放修复后连续两次 20 passed，最终全量再跑为 1322 passed / 50 skipped / 0 failed。

## 未执行项、提交就绪度与 J1 前风险

- 未执行：36 个 integration 与 13 个 E2E `llm` 标记用例没有批量运行，因为它们面向 OpenAI/Azure/Ollama 等不同外部条件；1 个可选依赖反向环境单测按条件 skipped。实际需要的 DashScope ingestion、vision、chat、embedding、CLI 和 MCP 路径已用有界调用单独验证。
- 未执行：Dashboard 截图与上传/摄取/删除/筛选等人工交互 walkthrough；因此 G3–G6、H4、I3、I5 保持 `[~]`。
- 提交就绪度：**暂不建议立即建立最终“传统 RAG baseline”提交**。代码和离线回归已就绪，但应先确认 DashScope 工作空间为何在成功完成真实入库和 20 QA 后，对后续 `text-embedding-v4` 查询间歇返回 `403 AccessDenied.Unpurchased`；同时由维护者复核当前大量 untracked migration 文件的纳入范围。
- J1 前风险：embedding 模型授权/计费状态不稳定；Dashboard 写操作缺人工验收；真实 collection 隔离主要由离线测试覆盖，尚未对第二个真实 provider collection 做交叉查询。J–N 均未实施，也未被传统配置启用。
