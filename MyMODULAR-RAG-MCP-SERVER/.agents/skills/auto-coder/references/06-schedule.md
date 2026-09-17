## 6. 项目排期

> **排期原则（严格对齐本 DEV_SPEC 的架构分层与目录结构）**
> 
> - **只按本文档设计落地**：以第 5.2 节原目录树和第 5.7 节 Self-RAG 增量目录为“交付清单”，每一步都要在文件系统上产生可见变化。
> - **1 小时一个可验收增量**：每个小阶段（≈1h）都必须同时给出“验收标准 + 测试方法”，尽量做到 TDD。
> - **先打通主闭环，再补齐默认实现**：优先做“可跑通的端到端路径（Ingestion → Retrieval → MCP Tool）”，并在 Libs 层补齐可运行的默认后端实现，避免出现“只有接口没有实现”的空转。
> - **外部依赖可替换/可 Mock**：LLM/Embedding/Vision/VectorStore 的真实调用在单元测试中一律用 Fake/Mock，集成测试再开真实后端（可选）。

### 阶段总览（大阶段 → 目的）

1. **阶段 A：工程骨架与测试基座**
   - 目的：建立可运行、可配置、可测试的工程骨架；后续所有模块都能以 TDD 方式落地。
2. **阶段 B：Libs 可插拔层（Factory + Base 接口 + 默认可运行实现）**
  - 目的：把“可替换”变成代码事实；并补齐可运行的默认后端实现，确保 Core / Ingestion 不仅“可编译”，还可在真实环境跑通。
3. **阶段 C：Ingestion Pipeline（PDF→MD→Chunk→Embedding→Upsert）**
  - 目的：离线摄取链路跑通，能把样例文档写入向量库/BM25 索引并支持增量。
4. **阶段 D：Retrieval（Dense + Sparse + RRF + 可选 Rerank）**
  - 目的：在线查询链路跑通，得到 Top-K chunks（含引用信息），并具备稳定回退策略。
5. **阶段 E：MCP Server 层与 Tools 落地**
   - 目的：按 MCP 标准暴露 tools，让 Copilot/Claude 可直接调用查询能力。
6. **阶段 F：Trace 基础设施与打点**
   - 目的：增强 TraceContext，实现结构化日志持久化，在 Ingestion + Query 双链路打点，添加 Pipeline 进度回调。
7. **阶段 G：可视化管理平台 Dashboard**
   - 目的：搭建 Streamlit 六页面管理平台（系统总览 / 数据浏览 / Ingestion 管理 / Ingestion 追踪 / Query 追踪 / 评估占位），实现 DocumentManager 跨存储协调。
8. **阶段 H：评估体系**
   - 目的：实现 RagasEvaluator + CompositeEvaluator + EvalRunner，启用评估面板页面，建立 golden test set 回归基线。
9. **阶段 I：端到端验收与文档收口**
   - 目的：补齐 E2E 测试（MCP Client 模拟 + Dashboard 冒烟），完善 README，全链路验收，确保“开箱即用 + 可复现”。
10. **阶段 J：Self-RAG 在线推理基础**
   - 目的：在传统 RAG 主链路上增加 Reflection Token、响应解析、按需检索、证据批判、分段生成与受控重试，保持 MCP 向后兼容。
11. **阶段 K：训练样本构建与 Teacher 蒸馏**
   - 目的：建立可断点、可审计、可预算控制的数据 Pipeline，以 Kimi K3 为主 Teacher、DeepSeek V4 为备选生成高质量 Reflection Labels。
12. **阶段 L：Critic / Generator 微调 Pipeline**
   - 目的：完成 Tokenizer 扩展、Critic SFT、Generator SFT、可选偏好训练、checkpoint 与模型产物管理。
13. **阶段 M：Student Serving、评估与可观测性**
   - 目的：将微调 Student 接入 LLM Factory，完成模型注册、Self-RAG Trace、Dashboard、基线对比和生产回退。
14. **阶段 N：Self-RAG 端到端验收与文档收口**
   - 目的：验证数据构建→训练→模型发布→MCP 推理的完整闭环，提供可复现 runbook、dataset card 与 model card。


---

### 📊 进度跟踪表 (Progress Tracking)

> **状态说明**：`[ ]` 未开始 | `[~]` 进行中 | `[x]` 已完成
> 
> **更新时间**：每完成一个子任务后更新对应状态
> **最近更新**：2026-09-01（4 份真实 PDF + DashScope 有界验收；离线分层 1328 passed / 0 failed / 1 skipped / 49 deselected）

#### 阶段 A：工程骨架与测试基座

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| A1 | 初始化目录树与最小可运行入口 | [x] | 2026-09-01 | 独立 `.venv`；`main.py`、compileall、顶层兼容 import 均通过 |
| A2 | 引入 pytest 并建立测试目录约定 | [x] | 2026-09-01 | unit/integration/e2e 分层及 marker 已验证 |
| A3 | 配置加载与校验（Settings） | [x] | 2026-09-01 | Settings 单元测试通过，示例配置仅含占位值 |

#### 阶段 B：Libs 可插拔层

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| B1 | LLM 抽象接口与工厂 | [x] | 2026-09-01 | 工厂注册、provider 选择、异常契约单测通过 |
| B2 | Embedding 抽象接口与工厂 | [x] | 2026-09-01 | 工厂与 BaseEmbedding 契约单测通过 |
| B3 | Splitter 抽象接口与工厂 | [x] | 2026-09-01 | 工厂与 splitter 契约单测通过 |
| B4 | VectorStore 抽象接口与工厂 | [x] | 2026-09-01 | 工厂与 CRUD 契约单测通过 |
| B5 | Reranker 抽象接口与工厂（含 None 回退） | [x] | 2026-09-01 | None fallback 与工厂单测通过 |
| B6 | Evaluator 抽象接口与工厂 | [x] | 2026-09-01 | evaluator factory/none/custom 契约单测通过 |
| B7.1 | OpenAI-Compatible LLM 实现 | [x] | 2026-09-01 | Mock 契约通过；`qwen-plus` OpenAI-compatible 端点及真实增强调用通过 |
| B7.2 | Ollama LLM 实现 | [x] | 2026-09-01 | Mock provider 单测通过，未调用真实服务 |
| B7.3 | OpenAI & Azure Embedding 实现 | [x] | 2026-09-01 | 配置优先级及 `text-embedding-v4` 1024 维通过；真实入库/20 QA 曾成功，后续查询出现 provider 403 |
| B7.4 | Ollama Embedding 实现 | [x] | 2026-09-01 | Mock provider 单测通过 |
| B7.5 | Recursive Splitter 默认实现 | [x] | 2026-09-01 | 分块、overlap、metadata 单测通过 |
| B7.6 | ChromaStore 默认实现 | [x] | 2026-09-01 | 本地持久化 round-trip 通过；Windows SQLite 句柄显式 close 并连续复测通过 |
| B7.7 | LLM Reranker 实现 | [x] | 2026-09-01 | Mock LLM 与 fallback 单测通过 |
| B7.8 | Cross-Encoder Reranker 实现 | [x] | 2026-09-01 | Mock model、排序及 fallback 单测通过 |
| B8 | Vision LLM 抽象接口与工厂集成 | [x] | 2026-09-01 | 工厂/Mock 契约通过；`qwen-vl-max` OpenAI-compatible 端点与 4 图真实 caption 通过 |
| B9 | Azure Vision LLM 实现 | [x] | 2026-09-01 | Mock Azure 多模态请求/响应契约通过 |

#### 阶段 C：Ingestion Pipeline MVP

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| C1 | 定义核心数据类型/契约（Document/Chunk/ChunkRecord） | [x] | 2026-09-01 | 数据类型序列化与校验单测通过 |
| C2 | 文件完整性检查（SHA256） | [x] | 2026-09-01 | 哈希、增量状态单测通过 |
| C3 | Loader 抽象基类与 PDF Loader | [x] | 2026-09-01 | 4 份真实 PDF 共 159 页解析；图片提取及逐页 citation 边界通过 |
| C4 | Splitter 集成（调用 Libs） | [x] | 2026-09-01 | page-aware splitter、稳定 ID 与 `page/page_num` 契约通过 |
| C5 | Transform 基类 + ChunkRefiner | [x] | 2026-09-01 | 规则/Mock 路径通过；`qwen-plus` 对 11/11 chunks 真实增强通过 |
| C6 | MetadataEnricher | [x] | 2026-09-01 | 规则/Mock 路径通过；`qwen-plus` 对 11/11 chunks 真实增强通过 |
| C7 | ImageCaptioner | [x] | 2026-09-01 | Mock/降级契约通过；`qwen-vl-max` 对 4/4 图片真实 caption 通过 |
| C8 | DenseEncoder | [x] | 2026-09-01 | 离线 deterministic embedding 与维度契约通过 |
| C9 | SparseEncoder | [x] | 2026-09-01 | 中英文、复合 ASCII token 与权重测试通过 |
| C10 | BatchProcessor | [x] | 2026-09-01 | 批次、重试、耗时统计测试通过 |
| C11 | BM25Indexer（倒排索引+IDF计算） | [x] | 2026-09-01 | 本地索引、持久化、检索测试通过 |
| C12 | VectorUpserter（幂等upsert） | [x] | 2026-09-01 | 幂等 upsert 与资源关闭测试通过 |
| C13 | ImageStorage（图片存储+SQLite索引） | [x] | 2026-09-01 | 临时目录 SQLite/文件 round-trip 通过 |
| C14 | Pipeline 编排（MVP 串起来） | [x] | 2026-09-01 | 4 份真实 PDF 入库 251 chunks/36 images；真实 embedding、LLM/vision 小样及幂等跳过通过 |
| C15 | 脚本入口 ingest.py | [x] | 2026-09-01 | help/dry-run/错误分支通过；真实 provider CLI 摄取 4/4 成功（1 个二次运行幂等 skip） |

#### 阶段 D：Retrieval MVP

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| D1 | QueryProcessor（关键词提取 + filters） | [x] | 2026-09-01 | query/filters 单测通过 |
| D2 | DenseRetriever（调用 VectorStore.query） | [x] | 2026-09-01 | Mock 与本地 Chroma 查询契约通过 |
| D3 | SparseRetriever（BM25 查询） | [x] | 2026-09-01 | 本地 BM25 检索测试通过 |
| D4 | RRF Fusion | [x] | 2026-09-01 | 排名融合、去重和权重测试通过 |
| D5 | HybridSearch 编排 | [x] | 2026-09-01 | 离线编排、filter、fallback 测试通过 |
| D6 | Reranker（Core 层编排 + Fallback） | [x] | 2026-09-01 | 可选 rerank 与失败回退通过 |
| D7 | 脚本入口 query.py（查询可用） | [x] | 2026-09-01 | 真实集合 CLI 返回二六三第 9 页 Top-1；dense 403 时 BM25 fallback 生效 |

#### 阶段 E：MCP Server 层与 Tools

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| E1 | MCP Server 入口与 Stdio 约束 | [x] | 2026-09-01 | MCP SDK 2.x stdio initialize/tools-list E2E 通过 |
| E2 | Protocol Handler 协议解析与能力协商 | [x] | 2026-09-01 | SDK 2.x handler 与 wire contract 通过 |
| E3 | query_knowledge_hub Tool | [x] | 2026-09-01 | 注入式离线传统检索、参数、结果、引用及 MCP 返回契约通过 |
| E4 | list_collections Tool | [x] | 2026-09-01 | 单测及 stdio E2E 通过 |
| E5 | get_document_summary Tool | [x] | 2026-09-01 | 单测及 missing-doc stdio E2E 通过 |
| E6 | 多模态返回组装（Text + Image） | [x] | 2026-09-01 | MCP content alias 与 image 组装测试通过 |

#### 阶段 F：Trace 基础设施与打点

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| F1 | TraceContext 增强（finish + 耗时统计 + trace_type） | [x] | 2026-09-01 | Windows 同 tick 正耗时契约修复并通过 |
| F2 | 结构化日志 logger（JSON Lines） | [x] | 2026-09-01 | JSONL 序列化/读取测试通过 |
| F3 | 在 Query 链路打点 | [x] | 2026-09-01 | query stage trace 测试通过 |
| F4 | 在 Ingestion 链路打点 | [x] | 2026-09-01 | 离线 pipeline stage trace 集成测试通过 |
| F5 | Pipeline 进度回调 (on_progress) | [x] | 2026-09-01 | 回调顺序和离线 pipeline 集成测试通过 |

#### 阶段 G：可视化管理平台 Dashboard

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| G1 | Dashboard 基础架构与系统总览页 | [x] | 2026-09-01 | Streamlit AppTest 六页面无头渲染通过 |
| G2 | DocumentManager 实现 | [x] | 2026-09-01 | 跨存储协调与删除单测通过 |
| G3 | 数据浏览器页面 | [~] | | Mock 空数据渲染通过；缺带真实本地索引的浏览/筛选人工验收 |
| G4 | Ingestion 管理页面 | [~] | | Mock 渲染通过；缺上传/摄取/删除交互人工验收 |
| G5 | Ingestion 追踪页面 | [~] | | trace service/空页通过；缺真实 trace 筛选与详情人工验收 |
| G6 | Query 追踪页面 | [~] | | trace service/空页通过；缺真实 query trace 交互人工验收 |

#### 阶段 H：评估体系

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| H1 | RagasEvaluator 实现 | [x] | 2026-09-01 | lazy import、Mock dataset/result 与错误契约通过 |
| H2 | CompositeEvaluator 实现 | [x] | 2026-09-01 | 聚合、命名冲突及失败隔离测试通过 |
| H3 | EvalRunner + Golden Test Set | [x] | 2026-09-01 | 4 文档/20 条页码标注 QA 已落盘；真实 hybrid 评估输出 Hit@10/MRR |
| H4 | 评估面板页面 | [~] | | 无头渲染通过；缺带真实评估结果的交互人工验收 |
| H5 | Recall 回归测试（E2E） | [x] | 2026-09-01 | 251-chunk 真实索引：20/20 页码命中，Hit@10=1.000，MRR=0.7138 |

#### 阶段 I：端到端验收与文档收口

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| I1 | E2E：MCP Client 侧调用模拟 | [x] | 2026-09-01 | stdio E2E 通过；真实 `query_knowledge_hub` 返回 3 citations，首条润本第 1 页 |
| I2 | E2E：Dashboard 冒烟测试 | [x] | 2026-09-01 | 六页面 Streamlit AppTest 全部通过 |
| I3 | 完善 README（运行说明 + MCP + Dashboard） | [~] | | 安装/配置/MCP/Dashboard/测试/FAQ 已补；缺截图和人工 walkthrough |
| I4 | 清理接口一致性（契约测试补齐） | [x] | 2026-09-01 | 离线分层回归：1328 passed、0 failed、1 skipped、49 LLM tests deselected |
| I5 | 全链路 E2E 验收 | [~] | | ingestion→hybrid→CLI/MCP→citation/eval 已实测；缺 Dashboard 人工联调，且 embedding 后续查询出现间歇性 403 |

**2026-09-01 正式验收证据（含用户授权的小额 DashScope 调用）**：

- 静态入口：10/10 公共导入通过，settings 与 3/3 prompts 加载通过，`compileall` 和 `python main.py` 通过。
- 分层测试：unit 1219 passed / 1 skipped；integration 90 passed / 36 LLM deselected；E2E 19 passed / 13 LLM deselected，合计 1328 passed / 0 failed。
- 真实数据：4 份 PDF、159 页、251 chunks、36 images；`qwen-plus` 11+11 次 transform、`qwen-vl-max` 4 图、`text-embedding-v4` 1024 维入库完成。
- 真实检索：20 条结构化 QA 的 Hit@10=1.000、MRR=0.7138；CLI/MCP 在后续 embedding 403 时验证 BM25 fallback 与页码 citation。
- Dashboard 截图/人工交互及 DashScope embedding 权限稳定性未满足的任务继续保留 `[~]`；J1–J2 已完成，J3–N 未实施。

#### 阶段 J：Self-RAG 在线推理基础

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| J1 | Reflection Token 与核心类型契约 | [x] | 2026-09-01 | 29 项 J1 单测、完整 unit 1248 passed/1 skipped、MCP/Hybrid 集成 35 passed；无外部调用 |
| J2 | Self-RAG Response Parser | [x] | 2026-09-08 | 37 项 J2 单测、完整 unit 1285 passed/1 skipped、integration 90 passed/36 skipped（跳过项为需真实凭证的 provider 用例）；无外部调用 |
| J3 | RetrievalGate 与策略阈值 | [ ] | | |
| J4 | Evidence Relevance Critic | [ ] | | |
| J5 | Support / Utility Critic | [ ] | | |
| J6 | Segment Generator + Query Rewriter | [ ] | | |
| J7 | SelfRAGOrchestrator + 候选打分 | [ ] | | |
| J8 | MCP/CLI 向后兼容与传统 RAG 回退 | [ ] | | |

#### 阶段 K：训练样本构建与 Teacher 蒸馏

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| K1 | 训练数据 Schema、版本与 Manifest | [x] | 2026-09-08 | 34 项 K1 单测、完整 unit 1317 passed/1 skipped；修正 `/data/` 忽略规则以纳入训练源码；无外部调用 |
| K2 | Seed/Trace 数据收集与脱敏 | [x] | 2026-09-08 | 12 项 K2 单测、training unit 46 passed；PII/密钥隔离、双重 Trace opt-in、只读输入与 provenance 验证通过 |
| K3 | Synthetic Query Generator | [x] | 2026-09-08 | 10 项 K3 单测、training unit 56 passed；六类 Query、精确配额、来源绑定、规范化去重与零调用 dry-run 验证通过 |
| K4 | Candidate Builder + Hard Negatives | [x] | 2026-09-08 | 7 项 K4 集成测试、完整 integration 97 passed/36 skipped；分数/来源可追溯、collection 与测试源防泄漏、难负例不足标记及固定索引确定性验证通过 |
| K5 | Teacher Provider（Kimi/DeepSeek） | [x] | 2026-09-08 | 11 项 K5 单测；Kimi/DeepSeek/OpenAI-compatible 配置切换、主备回退、Schema/限速/预算/探针/FakeTeacher 验证通过；账户重置后 `qwen3.8-27b`、`qwen3.5-omni-plus` 和 `kimi-k2.5` 均完成实际生成探测，Qwen 批量额度耗尽时 Kimi 回退成功产出真实样本 |
| K6 | Reflection Labeler + Prompt 版本化 | [x] | 2026-09-08 | 7 项 K6 单测、training unit 74 passed；五类独立版本 Prompt、Prompt/Response 哈希、短理由、未知枚举/引用/失败隔离与无 RETRY/ABSTAIN 标签验证通过 |
| K7 | 双教师一致性与 Adjudication | [ ] | | |
| K8 | 质量过滤、去重与防泄漏切分 | [ ] | | |
| K9 | Dataset Export、断点续跑与成本报告 | [ ] | | |

#### 阶段 L：Critic / Generator 微调 Pipeline

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| L1 | Tokenizer 扩展与 Manifest 校验 | [ ] | | |
| L2 | Critic Dataset/Collator 与 Loss Mask | [ ] | | |
| L3 | Critic LoRA/QLoRA 训练 Pipeline | [ ] | | |
| L4 | Critic 评估与置信度校准 | [ ] | | |
| L5 | Generator 数据离线构建 | [ ] | | |
| L6 | Generator LoRA/QLoRA SFT Pipeline | [ ] | | |
| L7 | 可选 Preference/DPO Pipeline | [ ] | | |
| L8 | Checkpoint、Adapter、量化与导出 | [ ] | | |
| L9 | 训练复现、恢复与 Model Card | [ ] | | |

#### 阶段 M：Student Serving、评估与可观测性

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| M1 | FineTunedReflectionModel Provider | [ ] | | |
| M2 | SelfRAGPolicy 配置与运行时校准 | [ ] | | |
| M3 | Self-RAG Trace Schema 与日志 | [ ] | | |
| M4 | Self-RAG Trace Dashboard | [ ] | | |
| M5 | Training Monitor + Model Registry | [ ] | | |
| M6 | Self-RAG 评估集与基线对比 | [ ] | | |
| M7 | MCP/CLI E2E 与并发隔离 | [ ] | | |
| M8 | 故障回退、超时、预算与安全测试 | [ ] | | |

#### 阶段 N：Self-RAG 端到端验收与文档收口

| 任务编号 | 任务名称 | 状态 | 完成日期 | 备注 |
|---------|---------|------|---------|------|
| N1 | 数据构建 Pipeline E2E Smoke | [ ] | | |
| N2 | 最小 Critic/Generator 训练闭环 | [ ] | | |
| N3 | 模型发布到 MCP 全链路 E2E | [ ] | | |
| N4 | README、Runbook、Dataset/Model Card | [ ] | | |
| N5 | 全量回归与发布验收 | [ ] | | |

---

### 📈 总体进度

| 阶段 | 总任务数 | 已完成 | 进度 |
|------|---------|--------|------|
| 阶段 A | 3 | 3 | 100% |
| 阶段 B | 16 | 16 | 100% |
| 阶段 C | 15 | 15 | 100% |
| 阶段 D | 7 | 7 | 100% |
| 阶段 E | 6 | 6 | 100% |
| 阶段 F | 5 | 5 | 100% |
| 阶段 G | 6 | 2 | 33.3% |
| 阶段 H | 5 | 4 | 80% |
| 阶段 I | 5 | 3 | 60% |
| 阶段 J | 8 | 2 | 25% |
| 阶段 K | 9 | 6 | 66.7% |
| 阶段 L | 9 | 0 | 0% |
| 阶段 M | 8 | 0 | 0% |
| 阶段 N | 5 | 0 | 0% |
| **总计** | **107** | **69** | **64.5%** |


---

## 阶段 A：工程骨架与测试基座（目标：先可导入，再可测试）

### A1：初始化目录树与最小可运行入口
- **目标**：在 repo 根目录创建第 5.2 节所述目录骨架与空模块文件（可 import）。
- **修改文件**：
  - `main.py`
  - `pyproject.toml`
  - `README.md`
  - `.gitignore`（Python 项目标准忽略规则：`__pycache__`、`.venv`、`.env`、`*.pyc`、IDE 配置等）
  - `src/**/__init__.py`（按目录树补齐）
  - `config/settings.yaml`（最小可解析配置）
  - `config/prompts/image_captioning.txt`（可先放占位内容，后续阶段补充 Prompt）
  - `config/prompts/chunk_refinement.txt`（可先放占位内容，后续阶段补充 Prompt）
  - `config/prompts/rerank.txt`（可先放占位内容，后续阶段补充 Prompt）
- **实现类/函数**：无（仅骨架）。
- **实现类/函数**：无（仅骨架，不实现业务逻辑）。
- **实现类/函数**：为当前项目创建一个虚拟环境模块。
 - **验收标准**：
  - 目录结构与 DEV_SPEC 5.2 一致（至少把对应目录创建出来）。
  - `config/prompts/` 目录存在，且三个 prompt 文件可被读取（即使只是占位文本）。
  - 能导入关键顶层包（与目录结构一一对应）：
    - `python -c "import mcp_server; import core; import ingestion; import libs; import observability"`
  - 可以启动虚拟环境模块
- **测试方法**：运行 `python -m compileall src`（仅做语法/可导入性检查；pytest 基座在 A2 建立）。

### A2：引入 pytest 并建立测试目录约定
- **目标**：建立 `tests/unit|integration|e2e|fixtures` 目录与 pytest 运行基座。
- **修改文件**：
  - `pyproject.toml`（添加 pytest 配置：testpaths、markers 等）
  - `tests/unit/test_smoke_imports.py`
  - `tests/fixtures/sample_documents/`（放 1 个最小样例文档占位）
- **实现类/函数**：无。
- **实现类/函数**：无（新增的是测试文件与 pytest 配置）。
- **验收标准**：
  - `pytest -q` 可运行并通过。
  - 至少 1 个冒烟测试（例如 `tests/unit/test_smoke_imports.py` 只做关键包 import 校验）。
- **测试方法**：`pytest -q tests/unit/test_smoke_imports.py`。

### A3：配置加载与校验（Settings）
- **目标**：实现读取 `config/settings.yaml` 的配置加载器，并在启动时校验关键字段存在。
- **修改文件**：
  - `main.py`（启动时调用 `load_settings()`，缺字段直接 fail-fast 退出）
  - `src/observability/logger.py`（先占位：提供 get_logger，stderr 输出）
  - `src/core/settings.py`（新增：集中放 Settings 数据结构与加载/校验逻辑）
  - `config/settings.yaml`（补齐字段：llm/embedding/vector_store/retrieval/rerank/evaluation/observability）
  - `tests/unit/test_config_loading.py`
- **实现类/函数**：
  - `Settings`（dataclass：只做结构与最小校验；不在这里做任何网络/IO 的“业务初始化”）
  - `load_settings(path: str) -> Settings`（读取 YAML -> 解析为 Settings -> 校验必填字段）
  - `validate_settings(settings: Settings) -> None`（把“必填字段检查”集中化，错误信息包含字段路径，例如 `embedding.provider`）
- **验收标准**：
  - `main.py` 启动时能成功加载 `config/settings.yaml` 并拿到 `Settings` 对象。
  - 删除/缺失关键字段时（例如 `embedding.provider`），启动或 `load_settings()` 抛出“可读错误”（明确指出缺的是哪个字段）。
- **测试方法**：`pytest -q tests/unit/test_config_loading.py`。

---

## 阶段 B：Libs 可插拔层（目标：Factory 可工作，且至少有“默认后端”可跑通端到端）

### B1：LLM 抽象接口与工厂
- **目标**：定义 `BaseLLM` 与 `LLMFactory`，支持按配置选择 provider。
- **修改文件**：
  - `src/libs/llm/base_llm.py`
  - `src/libs/llm/llm_factory.py`
  - `tests/unit/test_llm_factory.py`
- **实现类/函数**：
  - `BaseLLM.chat(messages) -> str`（或统一 response 对象）
  - `LLMFactory.create(settings) -> BaseLLM`
- **验收标准**：在测试里用 Fake provider（测试内 stub）验证工厂路由逻辑。
- **测试方法**：`pytest -q tests/unit/test_llm_factory.py`。

### B2：Embedding 抽象接口与工厂
- **目标**：定义 `BaseEmbedding` 与 `EmbeddingFactory`，支持批量 embed。
- **修改文件**：
  - `src/libs/embedding/base_embedding.py`
  - `src/libs/embedding/embedding_factory.py`
  - `tests/unit/test_embedding_factory.py`
- **实现类/函数**：
  - `BaseEmbedding.embed(texts: list[str], trace: TraceContext | None = None) -> list[list[float]]`
  - `EmbeddingFactory.create(settings) -> BaseEmbedding`
- **验收标准**：Fake embedding 返回稳定向量，工厂按 provider 分流。
- **测试方法**：`pytest -q tests/unit/test_embedding_factory.py`。

### B3：Splitter 抽象接口与工厂
- **目标**：定义 `BaseSplitter` 与 `SplitterFactory`，支持不同切分策略（Recursive/Semantic/Fixed）。
- **修改文件**：
  - `src/libs/splitter/base_splitter.py`
  - `src/libs/splitter/splitter_factory.py`
  - `tests/unit/test_splitter_factory.py`
- **实现类/函数**：
  - `BaseSplitter.split_text(text: str, trace: TraceContext | None = None) -> List[str]`
  - `SplitterFactory.create(settings) -> BaseSplitter`
- **验收标准**：Factory 能根据配置返回不同类型的 Splitter 实例（测试中可用 Fake 实现）。
- **测试方法**：`pytest -q tests/unit/test_splitter_factory.py`。

### B4：VectorStore 抽象接口与工厂（先定义契约）
- **目标**：定义 `BaseVectorStore` 与 `VectorStoreFactory`，先不接真实 DB。
- **修改文件**：
  - `src/libs/vector_store/base_vector_store.py`
  - `src/libs/vector_store/vector_store_factory.py`
  - `tests/unit/test_vector_store_contract.py`
- **实现类/函数**：
  - `BaseVectorStore.upsert(records, trace: TraceContext | None = None)`
  - `BaseVectorStore.query(vector, top_k, filters, trace: TraceContext | None = None)`
- **验收标准**：契约测试（contract test）约束输入输出 shape。
- **测试方法**：`pytest -q tests/unit/test_vector_store_contract.py`。

### B5：Reranker 抽象接口与工厂（含 None 回退）
- **目标**：实现 `BaseReranker`、`RerankerFactory`，提供 `NoneReranker` 作为默认回退。
- **修改文件**：
  - `src/libs/reranker/base_reranker.py`
  - `src/libs/reranker/reranker_factory.py`
  - `tests/unit/test_reranker_factory.py`
- **实现类/函数**：
  - `BaseReranker.rerank(query, candidates, trace: TraceContext | None = None) -> ranked_candidates`
  - `NoneReranker`（保持原顺序）
- **验收标准**：backend=none 时不会改变排序；未知 backend 明确报错。
- **测试方法**：`pytest -q tests/unit/test_reranker_factory.py`。

### B6：Evaluator 抽象接口与工厂（先做自定义轻量指标）
- **目标**：定义 `BaseEvaluator`、`EvaluatorFactory`，实现最小 `CustomEvaluator`（例如 hit_rate/mrr）。
- **修改文件**：
  - `src/libs/evaluator/base_evaluator.py`
  - `src/libs/evaluator/evaluator_factory.py`
  - `src/libs/evaluator/custom_evaluator.py`
  - `tests/unit/test_custom_evaluator.py`
- **验收标准**：输入 query + retrieved_ids + golden_ids 能输出稳定 metrics。
- **测试方法**：`pytest -q tests/unit/test_custom_evaluator.py`。

### B7：补齐 Libs 默认实现（拆分为≈1h可验收增量）

> 说明：B7 只补齐与端到端主链路强相关的默认实现（LLM/Embedding/Splitter/VectorStore/Reranker）。其余可选扩展（例如额外 splitter 策略、更多 vector store 后端、更多 evaluator 后端等）保持原排期不提前。

### B7.1：OpenAI-Compatible LLM（OpenAI/Azure/DeepSeek）
- **目标**：补齐 OpenAI-compatible 的 LLM 实现，确保通过 `LLMFactory` 可创建并可被 mock 测试。
- **修改文件**：
  - `src/libs/llm/openai_llm.py`
  - `src/libs/llm/azure_llm.py`
  - `src/libs/llm/deepseek_llm.py`
  - `tests/unit/test_llm_providers_smoke.py`（mock HTTP，不走真实网络）
- **验收标准**：
  - 配置不同 `provider` 时工厂路由正确。
  - `chat(messages)` 对输入 shape 校验清晰，异常信息可读（包含 provider 与错误类型）。
- **测试方法**：`pytest -q tests/unit/test_llm_providers_smoke.py`。

### B7.2：Ollama LLM（本地后端）
- **目标**：补齐 `ollama_llm.py`，支持本地 HTTP endpoint（默认 `base_url` + `model`），并可被 mock 测试。
- **修改文件**：
  - `src/libs/llm/ollama_llm.py`
  - `tests/unit/test_ollama_llm.py`（mock HTTP）
- **验收标准**：
  - provider=ollama 时可由 `LLMFactory` 创建。
  - 在连接失败/超时等场景下，抛出可读错误且不泄露敏感配置。
- **测试方法**：`pytest -q tests/unit/test_ollama_llm.py`。

### B7.3：OpenAI & Azure Embedding 实现
- **目标**：补齐 `openai_embedding.py` 和 `azure_embedding.py`，支持 OpenAI 官方 API 和 Azure OpenAI 服务的 Embedding 调用，支持批量 `embed(texts)`，并可被 mock 测试。
- **修改文件**：
  - `src/libs/embedding/openai_embedding.py`
  - `src/libs/embedding/azure_embedding.py`
  - `tests/unit/test_embedding_providers_smoke.py`（mock HTTP，包含 OpenAI 和 Azure 测试用例）
- **验收标准**：
  - provider=openai 时 `EmbeddingFactory` 可创建，支持 OpenAI 官方 API 的 text-embedding-3-small/large 等模型。
  - provider=azure 时 `EmbeddingFactory` 可创建，正确处理 Azure 特有的 endpoint、api-version、api-key 配置，支持 Azure 部署的 text-embedding-ada-002 等模型。
  - 空输入、超长输入有明确行为（报错或截断策略由配置决定）。
  - Azure 实现复用 OpenAI Embedding 的核心逻辑，保持行为一致性。
- **测试方法**：`pytest -q tests/unit/test_embedding_providers_smoke.py`。

### B7.4：Ollama Embedding 实现
- **目标**：补齐 `ollama_embedding.py`，支持通过 Ollama HTTP API 调用本地部署的 Embedding 模型（如 `nomic-embed-text`、`mxbai-embed-large` 等），实现 `embed(texts)` 批量向量化功能。
- **修改文件**：
  - `src/libs/embedding/ollama_embedding.py`
  - `tests/unit/test_ollama_embedding.py`（包含 mock HTTP 测试）
- **验收标准**：
  - provider=ollama 时 `EmbeddingFactory` 可创建。
  - 支持配置 Ollama 服务地址（默认 http://localhost:11434）和模型名称。
  - 输出向量维度由模型决定（如 nomic-embed-text 为 768 维），满足 ingestion/retrieval 的接口契约。
  - 支持批量 `embed(texts)` 调用，内部处理单条/批量请求逻辑。
  - 空输入、超长输入有明确行为（报错或截断策略）。
  - mock 测试覆盖正常响应、连接失败、超时等场景。
- **测试方法**：`pytest -q tests/unit/test_ollama_embedding.py`。

### B7.5：Recursive Splitter 默认实现
- **目标**：补齐 `recursive_splitter.py`，封装 LangChain 的切分逻辑，作为默认切分器。
- **修改文件**：
  - `src/libs/splitter/recursive_splitter.py`
  - `tests/unit/test_recursive_splitter_lib.py`
- **验收标准**：
  - provider=recursive 时 `SplitterFactory` 可创建。
  - `split_text` 能正确处理 Markdown 结构（标题/代码块不被打断）。
- **测试方法**：`pytest -q tests/unit/test_recursive_splitter_lib.py`。

### B7.6：ChromaStore（VectorStore 默认后端）
- **目标**：补齐 `chroma_store.py`，支持最小 `upsert(records)` 与 `query(vector, top_k, filters)`，并支持本地持久化目录（例如 `data/db/chroma/`）。
- **修改文件**：
  - `src/libs/vector_store/chroma_store.py`
  - `tests/integration/test_chroma_store_roundtrip.py`
- **验收标准**：
  - provider=chroma 时 `VectorStoreFactory` 可创建。
  - **必须完成完整的 upsert→query roundtrip 测试**：使用 mock 数据完成真实的存储和检索流程，验证返回结果的确定性和正确性。
  - 测试应覆盖：基本 upsert、向量查询、top_k 参数、metadata filters（如支持）。
  - 使用临时目录进行持久化测试，测试结束后清理。
- **测试方法**：`pytest -q tests/integration/test_chroma_store_roundtrip.py`

### B7.7：LLM Reranker（读取 rerank prompt）
- **目标**：补齐 `llm_reranker.py`，读取 `config/prompts/rerank.txt` 构造 prompt（测试中可注入替代文本），并可在失败时返回可回退信号。
- **修改文件**：
  - `src/libs/reranker/llm_reranker.py`
  - `tests/unit/test_llm_reranker.py`（mock LLM）
- **验收标准**：
  - backend=llm 时 `RerankerFactory` 可创建。
  - 输出严格结构化（例如 ranked ids），不满足 schema 时抛出可读错误。
- **测试方法**：`pytest -q tests/unit/test_llm_reranker.py`。

### B7.8：Cross-Encoder Reranker（本地/托管模型，占位可跑）
- **目标**：补齐 `cross_encoder_reranker.py`，支持对 Top-M candidates 打分排序；测试中用 mock scorer 保证 deterministic。
- **修改文件**：
  - `src/libs/reranker/cross_encoder_reranker.py`
  - `tests/unit/test_cross_encoder_reranker.py`（mock scorer）
- **验收标准**：
  - backend=cross_encoder 时 `RerankerFactory` 可创建。
  - 提供超时/失败回退信号（供 Core 层 `D6` fallback 使用）。
- **测试方法**：`pytest -q tests/unit/test_cross_encoder_reranker.py`。

### B8：Vision LLM 抽象接口与工厂集成
- **目标**：定义 `BaseVisionLLM` 抽象接口，扩展 `LLMFactory` 支持 Vision LLM 创建，为 C7 的 ImageCaptioner 提供底层抽象。
- **修改文件**：
  - `src/libs/llm/base_vision_llm.py`
  - `src/libs/llm/llm_factory.py`（扩展 `create_vision_llm` 方法）
  - `tests/unit/test_vision_llm_factory.py`
- **实现类/函数**：
  - `BaseVisionLLM.chat_with_image(text: str, image_path: str | bytes, trace: TraceContext | None = None) -> ChatResponse`
  - `LLMFactory.create_vision_llm(settings) -> BaseVisionLLM`
- **验收标准**：
  - 抽象接口清晰定义多模态输入（文本+图片路径/base64）。
  - 工厂方法 `create_vision_llm` 能根据配置路由到不同 provider（测试中用 Fake Vision LLM 验证）。
  - 接口设计支持图片预处理（压缩、格式转换）的扩展点。
- **测试方法**：`pytest -q tests/unit/test_vision_llm_factory.py`。

### B9：Azure Vision LLM 实现
- **目标**：实现 `AzureVisionLLM`，支持通过 Azure OpenAI 调用 GPT-4o/GPT-4-Vision-Preview 进行图像理解。
- **修改文件**：
  - `src/libs/llm/azure_vision_llm.py`
  - `tests/unit/test_azure_vision_llm.py`（mock HTTP，不走真实 API）
- **实现类/函数**：
  - `AzureVisionLLM(BaseVisionLLM)`：实现 `chat_with_image` 方法
  - 支持 Azure 特有配置：`azure_endpoint`, `api_version`, `deployment_name`, `api_key`
- **验收标准**：
  - provider=azure 且配置 vision_llm 时，`LLMFactory.create_vision_llm()` 可创建 Azure Vision LLM 实例。
  - 支持图片路径和 base64 两种输入方式。
  - 图片过大时自动压缩至 `max_image_size` 配置的尺寸（默认2048px）。
  - API 调用失败时抛出清晰错误，包含 Azure 特有错误码。
  - mock 测试覆盖：正常调用、图片压缩、超时、认证失败等场景。
- **测试方法**：`pytest -q tests/unit/test_azure_vision_llm.py`。

---

## 阶段 C：Ingestion Pipeline MVP（目标：能把 PDF 样例摄取到本地存储）

> 注：本阶段严格按 5.4.1 的离线数据流落地，并优先实现“增量跳过（SHA256）”。

### C1：定义核心数据类型/契约（Document/Chunk/ChunkRecord）
- **目标**：定义全链路（ingestion → retrieval → mcp tools）共用的数据结构/契约，避免散落在各子模块内导致的耦合与重复。
- **修改文件**：
  - `src/core/types.py`
  - `src/core/__init__.py`（可选：统一 re-export 以简化导入路径）
  - `tests/unit/test_core_types.py`
- **实现类/函数**（建议）：
  - `Document(id, text, metadata)`
  - `Chunk(id, text, metadata, start_offset, end_offset, source_ref?)`
  - `ChunkRecord(id, text, metadata, dense_vector?, sparse_vector?)`（用于存储/检索载体；字段按后续 C8~C12 演进）
- **验收标准**：
  - 类型可序列化（dict/json）且字段稳定（单元测试断言）。
  - `metadata` 约定最少包含 `source_path`，其余字段允许增量扩展但不得破坏兼容。
  - **`metadata.images` 字段规范**（用于多模态支持）：
    - 结构：`List[{"id": str, "path": str, "page": int, "text_offset": int, "text_length": int, "position": dict}]`
    - `id`：全局唯一图片标识符（建议格式：`{doc_hash}_{page}_{seq}`）
    - `path`：图片文件存储路径（约定：`data/images/{collection}/{image_id}.png`）
    - `page`：图片在原文档中的页码（可选，适用于PDF等分页文档）
    - `text_offset`：占位符在 `Document.text` 中的起始字符位置（从0开始计数）
    - `text_length`：占位符的字符长度（通常为 `len("[IMAGE: {image_id}]")`）
    - `position`：图片在原文档中的物理位置信息（可选，如PDF坐标、像素位置、尺寸等）
    - 说明：通过 `text_offset` 和 `text_length` 可精确定位图片在文本中的位置，支持同一图片多次出现的场景
  - **文本中图片占位符规范**：在 `Document.text` 中，图片位置使用 `[IMAGE: {image_id}]` 格式标记。
- **测试方法**：`pytest -q tests/unit/test_core_types.py`。

### C2：文件完整性检查（SHA256）
- **目标**：在Libs中实现 `file_integrity.py`：计算文件 hash，并提供“是否跳过”的判定接口（使用 SQLite 作为默认存储，支持后续替换为 Redis/PostgreSQL）。
- **修改文件**：
  - `src/libs/loader/file_integrity.py`
  - `tests/unit/test_file_integrity.py`
  - 数据库文件：`data/db/ingestion_history.db`（自动创建）
- **实现类/函数**：
  - `FileIntegrityChecker` 类（抽象接口）
  - `SQLiteIntegrityChecker(FileIntegrityChecker)` 类（默认实现）
    - `compute_sha256(path: str) -> str`
    - `should_skip(file_hash: str) -> bool`
    - `mark_success(file_hash: str, file_path: str, ...)`
    - `mark_failed(file_hash: str, error_msg: str)`
- **验收标准**：
  - 同一文件多次计算hash结果一致
  - 标记 success 后，`should_skip` 返回 `True`
  - 数据库文件正确创建在 `data/db/ingestion_history.db`
  - 支持并发写入（SQLite WAL模式）
- **测试方法**：`pytest -q tests/unit/test_file_integrity.py`。

### C3：Loader 抽象基类与 PDF Loader 壳子
- **目标**：在Libs中定义 `BaseLoader`，并实现 `PdfLoader` 的最小行为。
- **修改文件**：
  - `src/libs/loader/base_loader.py`
  - `src/libs/loader/pdf_loader.py`
  - `tests/unit/test_loader_pdf_contract.py`
- **实现类/函数**：
  - `BaseLoader.load(path) -> Document`
  - `PdfLoader.load(path)`
- **验收标准**：
  - **基础要求**：对 sample PDF（fixtures）能产出 Document，metadata 至少含 `source_path`。
  - **图片处理要求**（遵循 C1 定义的契约）：
    - 若 PDF 包含图片，应提取图片并保存到 `data/images/{doc_hash}/` 目录
    - 在 `Document.text` 中，图片位置插入占位符：`[IMAGE: {image_id}]`
    - 在 `metadata.images` 中记录图片信息（格式见 C1 规范）
    - 若 PDF 无图片，`metadata.images` 可为空列表或省略该字段
  - **降级行为**：图片提取失败不应阻塞文本解析，可在日志中记录警告。
- **测试方法**：`pytest -q tests/unit/test_loader_pdf_contract.py`。
- **测试建议**：
  - 准备两个测试文件：`simple.pdf`（纯文本）和 `with_images.pdf`（包含图片）
  - 验证纯文本PDF能正常解析
  - 验证带图片PDF能提取图片并正确插入占位符

### C4：Splitter 集成（调用 Libs）
- **目标**：实现 Chunking 模块作为 `libs.splitter` 和 Ingestion Pipeline 之间的**适配器层**，完成 Document→Chunks 的业务对象转换。
- **核心职责（DocumentChunker 相比 libs.splitter 的增值）**：
  - **职责边界说明**：
    - `libs.splitter`：纯文本切分工具（`str → List[str]`），不涉及业务对象
    - `DocumentChunker`：业务适配器（`Document对象 → List[Chunk对象]`），添加业务逻辑
  - **6 个增值功能**：
    1. **Chunk ID 生成**：为每个文本片段生成唯一且确定性的 ID（格式：`{doc_id}_{index:04d}_{hash_8chars}`）
    2. **元数据继承**：将 Document.metadata 复制到每个 Chunk.metadata（source_path, doc_type, title 等）
    3. **添加 chunk_index**：记录 chunk 在文档中的序号（从 0 开始），用于排序和定位
    4. **建立 source_ref**：记录 Chunk.source_ref 指向父 Document.id，支持溯源
    5. **图片引用按需分发**：扫描每个 chunk 文本中的 `[IMAGE: {id}]` 占位符，从 `Document.metadata["images"]` 中提取该 chunk 实际引用的 ImageRef，写入 `chunk.metadata["images"]`（仅含该 chunk 引用的子集）和 `chunk.metadata["image_refs"]`（image_id 列表）。无占位符的 chunk 不含 `images` 字段。⚠️ 不可简单整体继承或丢弃文档级 `images`，否则下游 C7 ImageCaptioner 将无法定位图片路径。
    6. **类型转换**：将 libs.splitter 的 `List[str]` 转换为符合 core.types 契约的 `List[Chunk]` 对象
- **修改文件**：
  - `src/ingestion/chunking/document_chunker.py`
  - `src/ingestion/chunking/__init__.py`
  - `tests/unit/test_document_chunker.py`
- **实现类/函数**：
  - `DocumentChunker` 类
  - `__init__(settings: Settings)`：通过 SplitterFactory 获取配置的 splitter 实例
  - `split_document(document: Document) -> List[Chunk]`：完整的转换流程
  - `_generate_chunk_id(doc_id: str, index: int, text: str) -> str`：生成稳定 Chunk ID
  - `_inherit_metadata(document: Document, chunk_index: int, chunk_text: str) -> dict`：元数据继承 + 图片引用按需分发逻辑（需要 chunk_text 来扫描 `[IMAGE: id]` 占位符）
- **验收标准**：
  - **配置驱动**：通过修改 settings.yaml 中的 splitter 配置（如 chunk_size），产出的 chunk 数量和长度发生相应变化
  - **ID 唯一性**：每个 Chunk 的 ID 在整个文档中唯一
  - **ID 确定性**：同一 Document 对象重复切分产生相同的 Chunk ID 序列
  - **元数据完整性**：Chunk.metadata 包含所有 Document.metadata 字段 + chunk_index 字段
  - **图片分发正确性**：含 `[IMAGE: id]` 占位符的 chunk 其 `metadata["images"]` 仅包含该 chunk 引用的图片子集；不含占位符的 chunk 无 `images` 字段；`metadata["image_refs"]` 列表与占位符一致
  - **溯源链接**：所有 Chunk.source_ref 正确指向父 Document.id
  - **类型契约**：输出的 Chunk 对象符合 `core/types.py` 中的 Chunk 定义（可序列化、字段完整）
- **测试方法**：`pytest -q tests/unit/test_document_chunker.py`（使用 FakeSplitter 隔离测试，无需真实 LLM/外部依赖）。

### C5：Transform 抽象基类 + ChunkRefiner（规则去噪 + LLM 增强）
- **目标**：定义 `BaseTransform`；实现 `ChunkRefiner`：先做规则去噪，再通过LLM进行智能增强，并提供失败降级机制（LLM异常时回退到规则结果，不阻塞 ingestion）。
- **前置条件**（必须准备）：
  - **必须配置LLM**：在 `config/settings.yaml` 中配置可用的LLM（provider/model/api_key）
  - **环境变量**：设置对应的API key环境变量（`OPENAI_API_KEY`/`OLLAMA_BASE_URL`等）
  - **验证目的**：通过真实LLM测试验证配置正确性和refinement效果
- **修改文件**：
  - `src/ingestion/transform/base_transform.py`（新增）
  - `src/ingestion/transform/chunk_refiner.py`（新增）
  - `src/core/trace/trace_context.py`（新增：最小实现，Phase F 完善）
  - `config/prompts/chunk_refinement.txt`（已存在，需验证内容并补充 {text} 占位符）
  - `tests/fixtures/noisy_chunks.json`（新增：8个典型噪声场景）
  - `tests/unit/test_chunk_refiner.py`（新增：27个单元测试）
  - `tests/integration/test_chunk_refiner_llm.py`（新增：真实LLM集成测试）
- **实现类/函数**：
  - `BaseTransform.transform(chunks, trace) -> List[Chunk]`
  - `ChunkRefiner.__init__(settings, llm?, prompt_path?)`
  - `ChunkRefiner.transform(chunks, trace) -> List[Chunk]`
  - `ChunkRefiner._rule_based_refine(text) -> str`（去空白/页眉页脚/格式标记/HTML注释）
  - `ChunkRefiner._llm_refine(text, trace) -> str | None`（可选 LLM 重写，失败返回 None）
  - `ChunkRefiner._load_prompt(prompt_path?)`（从文件加载prompt模板，支持默认fallback）
- **实现流程建议**：
  1. 先创建 `tests/fixtures/noisy_chunks.json`，包含8个典型噪声场景：
     - typical_noise_scenario: 综合噪声（页眉/页脚/空白）
     - ocr_errors: OCR错误文本
     - page_header_footer: 页眉页脚模式
     - excessive_whitespace: 多余空白
     - format_markers: HTML/Markdown标记
     - clean_text: 干净文本（验证不过度清理）
     - code_blocks: 代码块（验证保留内部格式）
     - mixed_noise: 真实混合场景
  2. 创建 `TraceContext` 占位实现（uuid生成trace_id，record_stage存储阶段数据）
  3. 实现 `BaseTransform` 抽象接口
  4. 实现 `ChunkRefiner._rule_based_refine` 规则去噪逻辑（正则匹配+分段处理）
  5. 编写规则模式单元测试（使用 fixtures 断言清洗效果）
  6. 实现 `_llm_refine` 可选增强（读取 prompt、调用 LLM、错误处理）
  7. 编写 LLM 模式单元测试（mock LLM 断言调用与输出）
  8. 编写降级场景测试（LLM 失败时回退到规则结果，标记 metadata）
  9. **编写真实LLM集成测试并执行验证**（必须执行，验证LLM配置）
- **验收标准**：
  - **单元测试（快速反馈循环）**：
    - 规则模式：对 fixtures 噪声样例能正确去噪（连续空白/页眉页脚/格式标记/分隔线）
    - 保留能力：代码块内部格式不被破坏，Markdown结构完整保留
    - LLM 模式：mock LLM 时能正确调用并返回重写结果，metadata 标记 `refined_by: "llm"`
    - 降级行为：LLM 失败时回退到规则结果，metadata 标记 `refined_by: "rule"` 和 fallback 原因
    - 配置开关：通过 `settings.yaml` 的 `ingestion.chunk_refiner.use_llm` 控制行为
    - 异常处理：单个chunk处理异常不影响其他chunk，保留原文
  - **集成测试（验收必须项）**：
    - ✅ **必须验证真实LLM调用成功**：使用前置条件中配置的LLM进行真实refinement
    - ✅ **必须验证输出质量**：LLM refined文本确实更干净（噪声减少、内容保留）
    - ✅ **必须验证降级机制**：无效模型名称时优雅降级到rule-based，不崩溃
    - 说明：这是验证"前置条件中准备的LLM配置是否正确"的必要步骤
- **测试方法**：
  - **阶段1-单元测试（开发中快速迭代）**：
    ```bash
    pytest tests/unit/test_chunk_refiner.py -v
    # ✅ 27个测试全部通过，使用Mock隔离，无需真实API
    ```
  - **阶段2-集成测试（验收必须执行）**：
    ```bash
    # 1. 运行真实LLM集成测试（必须）
    pytest tests/integration/test_chunk_refiner_llm.py -v -s
    # ✅ 验证LLM配置正确，refinement效果符合预期
    # ⚠️ 会产生真实API调用与费用
    
    # 2. Review打印输出，确认精炼质量
    # - 噪声是否被有效去除？
    # - 有效内容是否完整保留？
    # - 降级机制是否正常工作？
    ```
  - **测试分层逻辑**：
    - 单元测试：验证代码逻辑正确
    - 集成测试：验证系统可用性
    - 两者互补，缺一不可

### C6：MetadataEnricher（规则增强 + 可选 LLM 增强 + 降级）
- **目标**：实现元数据增强模块：提供规则增强的默认实现，并重点支持 LLM 增强（配置已就绪，LLM 开关打开）。利用 LLM 对 chunk 进行高质量的 title 生成、summary 摘要和 tags 提取。同时保留失败降级机制，确保不阻塞 ingestion。
- **修改文件**：
  - `src/ingestion/transform/metadata_enricher.py`
  - `tests/unit/test_metadata_enricher_contract.py`
- **验收标准**：
  - 规则模式：作为兜底逻辑，输出 metadata 必须包含 `title/summary/tags`（至少非空）。
  - **LLM 模式（核心）**：在 LLM 打开的情况下，确保真实调用 LLM（或高质量 Mock）并生成语义丰富的 metadata。需验证在有真实 LLM 配置下的连通性与效果。
  - 降级行为：LLM 调用失败时回退到规则模式结果（可在 metadata 标记降级原因，但不抛出致命异常）。
- **测试方法**：`pytest -q tests/unit/test_metadata_enricher_contract.py`，并确保包含开启 LLM 的集成测试用例。

### C7：ImageCaptioner（可选生成 caption + 降级不阻塞）
- **目标**：实现 `image_captioner.py`：当启用 Vision LLM 且存在 image_refs 时生成 caption 并写回 chunk metadata；当禁用/不可用/异常时走降级路径，不阻塞 ingestion。
- **修改文件**：
  - `src/ingestion/transform/image_captioner.py`
  - `config/prompts/image_captioning.txt`（作为默认 prompt 来源；可在测试中注入替代文本）
  - `tests/unit/test_image_captioner_fallback.py`
- **验收标准**：
  - 启用模式：存在 image_refs 时会生成 caption 并写入 metadata（测试中用 mock Vision LLM 断言调用与输出）。
  - 降级模式：当配置禁用或异常时，chunk 保留 image_refs，但不生成 caption 且标记 `has_unprocessed_images`。
- **测试方法**：`pytest -q tests/unit/test_image_captioner_fallback.py`。

### C8：DenseEncoder（依赖 libs.embedding）
- **目标**：实现 `dense_encoder.py`，把 chunks.text 批量送入 `BaseEmbedding`。
- **修改文件**：
  - `src/ingestion/embedding/dense_encoder.py`
  - `tests/unit/test_dense_encoder.py`
- **验收标准**：encoder 输出向量数量与 chunks 数量一致，维度一致。
- **测试方法**：`pytest -q tests/unit/test_dense_encoder.py`。

### C9：SparseEncoder（BM25 统计与输出契约）
- **目标**：实现 `sparse_encoder.py`：对 chunks 建立 BM25 所需统计（可先仅输出 term weights 结构，索引落地下一步做）。
- **修改文件**：
  - `src/ingestion/embedding/sparse_encoder.py`
  - `tests/unit/test_sparse_encoder.py`
- **验收标准**：输出结构可用于 bm25_indexer；对空文本有明确行为。
- **测试方法**：`pytest -q tests/unit/test_sparse_encoder.py`。

### C10：BatchProcessor（批处理编排）
- **目标**：实现 `batch_processor.py`：将 chunks 分 batch，驱动 dense/sparse 编码，记录批次耗时（为 trace 预留）。
- **修改文件**：
  - `src/ingestion/embedding/batch_processor.py`
  - `tests/unit/test_batch_processor.py`
- **验收标准**：batch_size=2 时对 5 chunks 分成 3 批，且顺序稳定。
- **测试方法**：`pytest -q tests/unit/test_batch_processor.py`。

---

**━━━━ 存储阶段分界线：以下任务负责将编码结果持久化 ━━━━**

> **说明**：C8-C10完成了Dense和Sparse的编码工作，C11-C13负责将编码结果存储到不同的后端。
> - **C11 (BM25Indexer)**：处理Sparse编码结果 → 构建倒排索引 → 存储到文件系统
> - **C12 (VectorUpserter)**：处理Dense编码结果 → 生成稳定ID → 存储到向量数据库
> - **C13 (ImageStorage)**：处理图片数据 → 文件存储 + 索引映射

---

### C11：BM25Indexer（倒排索引构建与持久化）
- **目标**：实现 `bm25_indexer.py`：接收 SparseEncoder 的term statistics输出，计算IDF，构建倒排索引，并持久化到 `data/db/bm25/`。
- **核心功能**：
  - 计算 IDF (Inverse Document Frequency)：`IDF(term) = log((N - df + 0.5) / (df + 0.5))`
  - 构建倒排索引结构：`{term: {idf, postings: [{chunk_id, tf, doc_length}]}}`
  - 索引序列化与加载（支持增量更新与重建）
- **修改文件**：
  - `src/ingestion/storage/bm25_indexer.py`
  - `tests/unit/test_bm25_indexer_roundtrip.py`
- **验收标准**：
  - build 后能 load 并对同一语料查询返回稳定 top ids
  - IDF计算准确（可用已知语料对比验证）
  - 支持索引重建与增量更新
- **测试方法**：`pytest -q tests/unit/test_bm25_indexer_roundtrip.py`。
- **备注**：本任务完成Sparse路径的最后一环，为D3 (SparseRetriever) 提供可查询的BM25索引。

### C12：VectorUpserter（向量存储与幂等性保证）
- **目标**：实现 `vector_upserter.py`：接收 DenseEncoder 的向量输出，生成稳定的 `chunk_id`，并调用 VectorStore 进行幂等写入。
- **核心功能**：
  - 生成确定性 chunk_id：`hash(source_path + chunk_index + content_hash[:8])`
  - 调用 `BaseVectorStore.upsert()` 写入向量数据库
  - 保证幂等性：同一内容重复写入不产生重复记录
- **修改文件**：
  - `src/ingestion/storage/vector_upserter.py`
  - `tests/unit/test_vector_upserter_idempotency.py`
- **验收标准**：
  - 同一 chunk 两次 upsert 产生相同 id
  - 内容变更时 id 变更
  - 支持批量 upsert 且保持顺序
- **测试方法**：`pytest -q tests/unit/test_vector_upserter_idempotency.py`。
- **备注**：本任务完成Dense路径的最后一环，为D2 (DenseRetriever) 提供可查询的向量数据库。

### C13：ImageStorage（图片文件存储与索引表契约）
- **目标**：实现 `image_storage.py`：保存图片到 `data/images/{collection}/`，并使用 **SQLite** 记录 image_id→path 映射。
- **修改文件**：
  - `src/ingestion/storage/image_storage.py`
  - `tests/unit/test_image_storage.py`
- **验收标准**：保存后文件存在；查找 image_id 返回正确路径；映射关系持久化在 `data/db/image_index.db`。
- **技术方案**：
  - 复用项目已有的 SQLite 架构模式（参考 `file_integrity.py` 的 `SQLiteIntegrityChecker`）
  - 数据库表结构：
    ```sql
    CREATE TABLE image_index (
        image_id TEXT PRIMARY KEY,
        file_path TEXT NOT NULL,
        collection TEXT,
        doc_hash TEXT,
        page_num INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_collection ON image_index(collection);
    CREATE INDEX idx_doc_hash ON image_index(doc_hash);
    ```
  - 提供并发安全访问（WAL 模式）
  - 支持按 collection 批量查询
- **测试方法**：`pytest -q tests/unit/test_image_storage.py`。

### C14：Pipeline 编排（MVP 串起来）
- **目标**：实现 `pipeline.py`：串行执行（integrity→load→split→transform→encode→store），并对失败步骤做清晰异常。
- **修改文件**：
  - `src/ingestion/pipeline.py`
  - `tests/integration/test_ingestion_pipeline.py`
- **测试数据**：
  - **主测试文档**：`tests/fixtures/sample_documents/complex_technical_doc.pdf`
    - 8章节技术文档（~21KB）
    - 包含3张嵌入图片（需测试图片提取和描述）
    - 包含5个表格（测试表格内容解析）
    - 多页多段落（测试完整分块流程）
  - **辅助测试**：`tests/fixtures/sample_documents/simple.pdf`（简单场景回归）
- **验收标准**：
  - 对 `complex_technical_doc.pdf` 跑完整 pipeline，成功输出：
    - 向量索引文件到 ChromaDB
    - BM25 索引文件到 `data/db/bm25/`
    - 提取的图片到 `data/images/` (SHA256命名)
  - Pipeline 日志清晰展示各阶段进度
  - 失败步骤抛出明确异常信息
- **测试方法**：`pytest -v tests/integration/test_ingestion_pipeline.py`。

### C15：脚本入口 ingest.py（离线可用）
- **目标**：实现 `scripts/ingest.py`，支持 `--collection`、`--path`、`--force`，并调用 pipeline。
- **修改文件**：
  - `scripts/ingest.py`
  - `tests/e2e/test_data_ingestion.py`
- **验收标准**：命令行可运行并在 `data/db` 产生产物；重复运行在未变更时跳过。
- **测试方法**：`pytest -q tests/e2e/test_data_ingestion.py`（尽量用临时目录）。

---

## 阶段 D：Retrieval MVP（目标：能 query 并返回 Top-K chunks）

### D1：QueryProcessor（关键词提取 + filters 结构）
- **目标**：实现 `query_processor.py`：关键词提取（先规则/分词），并解析通用 filters 结构（可空实现）。
- **修改文件**：
  - `src/core/query_engine/query_processor.py`
  - `tests/unit/test_query_processor.py`
- **验收标准**：对输入 query 输出 `keywords` 非空（可根据停用词策略），filters 为 dict。
- **测试方法**：`pytest -q tests/unit/test_query_processor.py`。

### D2：DenseRetriever（调用 VectorStore.query）
- **目标**：实现 `dense_retriever.py`，组合 `EmbeddingClient`（query 向量化）+ `VectorStore`（向量检索），完成语义召回。
- **前置任务**：
  1. 需先在 `src/core/types.py` 中定义 `RetrievalResult` 类型（包含 `chunk_id`, `score`, `text`, `metadata` 字段）
  2. 需确认 ChromaStore.query() 返回结果包含 text（当前存储在 documents 字段，需补充返回）
- **修改文件**：
  - `src/core/types.py`（新增 `RetrievalResult` 类型）
  - `src/libs/vector_store/chroma_store.py`（修复：query 返回结果需包含 text 字段）
  - `src/core/query_engine/dense_retriever.py`
  - `tests/unit/test_dense_retriever.py`
- **实现类/函数**：
  - `RetrievalResult` dataclass：`chunk_id: str`, `score: float`, `text: str`, `metadata: Dict`
  - `DenseRetriever.__init__(settings, embedding_client?, vector_store?)`：支持依赖注入用于测试
  - `DenseRetriever.retrieve(query: str, top_k: int, filters?: dict, trace?) -> List[RetrievalResult]`
  - 内部流程：`query → embedding_client.embed([query]) → vector_store.query(vector, top_k, filters) → 从返回结果提取 text → 规范化结果`
- **验收标准**：
  - `RetrievalResult` 类型已定义并可序列化
  - ChromaStore.query() 返回结果包含 `text` 字段
  - 对输入 query 能生成 embedding 并调用 VectorStore 检索
  - 返回结果包含 `chunk_id`、`score`、`text`、`metadata`
  - mock EmbeddingClient 和 VectorStore 时能正确编排调用
- **测试方法**：`pytest -q tests/unit/test_dense_retriever.py`（mock embedding + vector store）。

### D3：SparseRetriever（BM25 查询）
- **目标**：实现 `sparse_retriever.py`：从 `data/db/bm25/` 载入索引并查询。
- **前置任务**：需在 `BaseVectorStore` 和 `ChromaStore` 中添加 `get_by_ids()` 方法，用于根据 chunk_id 批量获取 text 和 metadata
- **修改文件**：
  - `src/libs/vector_store/base_vector_store.py`（新增 `get_by_ids()` 抽象方法）
  - `src/libs/vector_store/chroma_store.py`（实现 `get_by_ids()` 方法）
  - `src/core/query_engine/sparse_retriever.py`
  - `tests/unit/test_sparse_retriever.py`
- **实现类/函数**：
  - `BaseVectorStore.get_by_ids(ids: List[str]) -> List[Dict]`：根据 ID 批量获取记录
  - `ChromaStore.get_by_ids(ids: List[str]) -> List[Dict]`：调用 ChromaDB 的 get 方法
  - `SparseRetriever.__init__(settings, bm25_indexer?, vector_store?)`：支持依赖注入用于测试
  - `SparseRetriever.retrieve(keywords: List[str], top_k: int, trace?) -> List[RetrievalResult]`
  - 内部流程：
    1. `keywords → bm25_indexer.query(keywords, top_k) → [{chunk_id, score}]`
    2. `chunk_ids → vector_store.get_by_ids(chunk_ids) → [{id, text, metadata}]`
    3. 合并 score 与 text/metadata，组装为 `RetrievalResult` 列表
  - 注意：keywords 来自 `QueryProcessor.process()` 的 `ProcessedQuery.keywords`
- **验收标准**：
  - `BaseVectorStore.get_by_ids()` 和 `ChromaStore.get_by_ids()` 已实现
  - 对已构建索引的 fixtures 语料，关键词检索命中预期 chunk_id
  - 返回结果包含完整的 text 和 metadata
- **测试方法**：`pytest -q tests/unit/test_sparse_retriever.py`。

### D4：Fusion（RRF 实现）
- **目标**：实现 `fusion.py`：RRF 融合 dense/sparse 排名并输出统一排序。
- **修改文件**：
  - `src/core/query_engine/fusion.py`
  - `tests/unit/test_fusion_rrf.py`
- **验收标准**：对构造的排名输入输出 deterministic；k 参数可配置。
- **测试方法**：`pytest -q tests/unit/test_fusion_rrf.py`。

### D5：HybridSearch 编排
- **目标**：实现 `hybrid_search.py`：编排 Dense + Sparse + Fusion 的完整混合检索流程，并集成 Metadata 过滤逻辑。
- **前置依赖**：D1（QueryProcessor）、D2（DenseRetriever）、D3（SparseRetriever）、D4（Fusion）
- **修改文件**：
  - `src/core/query_engine/hybrid_search.py`
  - `tests/integration/test_hybrid_search.py`
- **实现类/函数**：
  - `HybridSearch.__init__(settings, query_processor, dense_retriever, sparse_retriever, fusion)`
  - `HybridSearch.search(query: str, top_k: int, filters?: dict, trace?) -> List[RetrievalResult]`
  - `HybridSearch._apply_metadata_filters(candidates, filters) -> List[RetrievalResult]`：后置过滤兜底
  - 内部流程：`query_processor.process() → 并行(dense.retrieve + sparse.retrieve) → fusion.fuse() → metadata_filter → Top-K`
- **验收标准**：
  - 对 fixtures 数据，能返回 Top-K（包含 chunk 文本与 metadata）
  - 支持 filters 参数（如 `collection`、`doc_type`）进行过滤
  - Dense/Sparse 任一路径失败时能降级到单路结果
- **测试方法**：`pytest -q tests/integration/test_hybrid_search.py`。

### D6：Reranker（Core 层编排 + fallback）
- **目标**：实现 `core/query_engine/reranker.py`：接入 `libs.reranker` 后端，失败/超时回退 fusion 排名。
- **修改文件**：
  - `src/core/query_engine/reranker.py`
  - `config/prompts/rerank.txt`（仅当启用 LLM Rerank 后端时使用）
  - `tests/unit/test_reranker_fallback.py`
- **验收标准**：模拟后端异常时不影响最终返回，且标记 fallback=true。
- **测试方法**：`pytest -q tests/unit/test_reranker_fallback.py`。

### D7：脚本入口 query.py（查询可用）
- **目标**：实现 `scripts/query.py`，作为在线查询的命令行入口，调用完整的 HybridSearch + Reranker 流程并输出检索结果。
- **前置依赖**：D5（HybridSearch）、D6（Reranker）
- **修改文件**：
  - `scripts/query.py`
- **实现功能**：
  - **参数支持**：
    - `--query "问题"`：必填，查询文本
    - `--top-k 10`：可选，返回结果数量（默认 10）
    - `--collection xxx`：可选，限定检索集合
    - `--verbose`：可选，显示各阶段中间结果
    - `--no-rerank`：可选，跳过 Reranker 阶段
  - **输出内容**：
    - 默认模式：Top-K 结果（序号、score、文本摘要、来源文件、页码）
    - Verbose 模式：额外显示 Dense 召回结果、Sparse 召回结果、Fusion 结果、Rerank 结果
  - **内部流程**：
    1. 加载配置 `Settings`
    2. 初始化组件（EmbeddingClient、VectorStore、BM25Indexer、Reranker）
    3. 创建 `QueryProcessor`、`DenseRetriever`、`SparseRetriever`、`HybridSearch` 实例
    4. 调用 `HybridSearch.search()` 获取候选结果
    5. 调用 `Reranker.rerank()` 进行精排（除非 `--no-rerank`）
    6. 格式化输出结果
- **验收标准**：
  - 命令行可运行：`python scripts/query.py --query "如何配置 Azure？"`
  - 返回格式化的 Top-K 检索结果
  - `--verbose` 模式显示各阶段中间结果（便于调试）
  - 无数据时返回友好提示（如"未找到相关文档，请先运行 ingest.py 摄取数据"）
- **测试方法**：手动运行 `python scripts/query.py --query "测试查询" --verbose`（依赖已摄取的数据）。
- **与 MCP Tool 的关系**：
  - `scripts/query.py` 是开发调试用的命令行工具
  - `E3 query_knowledge_hub` 是生产环境的 MCP Tool
  - 两者共享 Core 层逻辑（HybridSearch + Reranker），但入口和输出格式不同

---

## 阶段 E：MCP Server 层与 Tools（目标：对外可用的 MCP tools）

### E1：MCP Server 入口与 Stdio 约束
- **目标**：实现 `mcp_server/server.py`：遵循"stdout 只输出 MCP 消息，日志到 stderr"。
- **修改文件**：
  - `src/mcp_server/server.py`
  - `tests/integration/test_mcp_server.py`
- **验收标准**：启动 server 能完成 initialize；stderr 有日志但 stdout 不污染。
- **测试方法**：`pytest -q tests/integration/test_mcp_server.py`（子进程方式）。

### E2：Protocol Handler 协议解析与能力协商
- **目标**：实现 `mcp_server/protocol_handler.py`：封装 JSON-RPC 2.0 协议解析，处理 `initialize`、`tools/list`、`tools/call` 三类核心方法，并实现规范的错误处理。
- **修改文件**：
  - `src/mcp_server/protocol_handler.py`
  - `tests/unit/test_protocol_handler.py`
- **实现要点**：
  - **ProtocolHandler 类**：
    - `handle_initialize(params)` → 返回 server capabilities（支持的 tools 列表、版本信息）
    - `handle_tools_list()` → 返回已注册的 tool schema（name, description, inputSchema）
    - `handle_tools_call(name, arguments)` → 路由到具体 tool 执行，捕获异常并转换为 JSON-RPC error
  - **错误码规范**：遵循 JSON-RPC 2.0（-32600 Invalid Request, -32601 Method not found, -32602 Invalid params, -32603 Internal error）
  - **能力协商**：在 `initialize` 响应中声明 `capabilities.tools`
- **验收标准**：
  - 发送 `initialize` 请求能返回正确的 `serverInfo` 和 `capabilities`
  - 发送 `tools/list` 能返回已注册 tools 的 schema
  - 发送 `tools/call` 能正确路由并返回结果或规范错误
  - **错误处理**：无效方法返回 -32601，参数错误返回 -32602，内部异常返回 -32603 且不泄露堆栈
- **测试方法**：`pytest -q tests/unit/test_protocol_handler.py`。

### E3：实现 tool：query_knowledge_hub
- **目标**：实现 `tools/query_knowledge_hub.py`：调用 HybridSearch + Reranker，构建带引用的响应，返回 Markdown + structured citations。
- **前置依赖**：D5（HybridSearch）、D6（Reranker）、E1（Server）、E2（Protocol Handler）
- **修改文件**：
  - `src/mcp_server/tools/query_knowledge_hub.py`
  - `src/core/response/response_builder.py`（新增：构建 MCP 响应格式）
  - `src/core/response/citation_generator.py`（新增：生成引用信息）
  - `tests/unit/test_response_builder.py`（新增）
  - `tests/integration/test_mcp_server.py`（补用例）
- **实现类/函数**：
  - `ResponseBuilder.build(retrieval_results, query) -> MCPResponse`：构建 MCP 格式响应
  - `CitationGenerator.generate(retrieval_results) -> List[Citation]`：生成引用列表
  - `query_knowledge_hub(query, top_k?, collection?) -> MCPToolResult`：Tool 入口函数
- **验收标准**：
  - tool 返回 `content[0]` 为可读 Markdown（含 `[1]`、`[2]` 等引用标注）
  - `structuredContent.citations` 包含 `source`/`page`/`chunk_id`/`score` 字段
  - 无结果时返回友好提示而非空数组
- **测试方法**：`pytest -q tests/integration/test_mcp_server.py -k query_knowledge_hub`。

### E4：实现 tool：list_collections
- **目标**：实现 `tools/list_collections.py`：列出 `data/documents/` 下集合并附带统计（可延后到下一步）。
- **修改文件**：
  - `src/mcp_server/tools/list_collections.py`
  - `tests/unit/test_list_collections.py`
- **验收标准**：对 fixtures 中的目录结构能返回集合名列表。
- **测试方法**：`pytest -q tests/unit/test_list_collections.py`。

### E5：实现 tool：get_document_summary
- **目标**：实现 `tools/get_document_summary.py`：按 doc_id 返回 title/summary/tags（可先从 metadata/缓存取）。
- **修改文件**：
  - `src/mcp_server/tools/get_document_summary.py`
  - `tests/unit/test_get_document_summary.py`
- **验收标准**：对不存在 doc_id 返回规范错误；存在时返回结构化信息。
- **测试方法**：`pytest -q tests/unit/test_get_document_summary.py`。

### E6：多模态返回组装（Text + Image）
- **目标**：实现 `multimodal_assembler.py`：命中 chunk 含 image_refs 时读取图片并 base64 返回 ImageContent。
- **修改文件**：
  - `src/core/response/multimodal_assembler.py`
  - `tests/integration/test_mcp_server.py`（补图像返回用例）
- **验收标准**：返回 content 中包含 image type，mimeType 正确，data 为 base64 字符串。
- **测试方法**：`pytest -q tests/integration/test_mcp_server.py -k image`。

---

## 阶段 F：Trace 基础设施与打点（目标：Ingestion + Query 双链路可追踪）

### F1：TraceContext 增强（finish + 耗时统计 + trace_type）
- **目标**：增强已有的 `TraceContext`（C5 已实现基础版），添加 `finish()` 方法、耗时统计、`trace_type` 字段（区分 query/ingestion）、`to_dict()` 序列化功能。
- **修改文件**：
  - `src/core/trace/trace_context.py`（增强：添加 trace_type/finish/elapsed_ms/to_dict）
  - `src/core/trace/trace_collector.py`（新增：收集并持久化 trace）
  - `tests/unit/test_trace_context.py`（补充 finish/to_dict 相关测试）
- **实现类/函数**：
  - `TraceContext.__init__(trace_type: str = "query")`：支持 `"query"` 或 `"ingestion"` 类型
  - `TraceContext.finish() -> None`：标记 trace 结束，计算总耗时
  - `TraceContext.elapsed_ms(stage_name?) -> float`：获取指定阶段或总耗时
  - `TraceContext.to_dict() -> dict`：序列化为可 JSON 输出的字典（含 trace_type）
  - `TraceCollector.collect(trace: TraceContext) -> None`：收集 trace 并触发持久化
- **验收标准**：
  - `record_stage` 追加阶段数据（已有）
  - `finish()` 后 `to_dict()` 输出包含 `trace_id`、`trace_type`、`started_at`、`finished_at`、`total_elapsed_ms`、`stages`
  - 输出 dict 可直接 `json.dumps()` 序列化
- **测试方法**：`pytest -q tests/unit/test_trace_context.py`。


### F2：结构化日志 logger（JSON Lines）
- **目标**：增强 `observability/logger.py`，支持 JSON Lines 格式输出，并实现 trace 持久化到 `logs/traces.jsonl`。
- **修改文件**：
  - `src/observability/logger.py`（增强：添加 JSONFormatter + FileHandler）
  - `tests/unit/test_jsonl_logger.py`
- **实现类/函数**：
  - `JSONFormatter`：自定义 logging Formatter，输出 JSON 格式
  - `get_trace_logger() -> logging.Logger`：获取配置了 JSON Lines 输出的 logger
  - `write_trace(trace_dict: dict) -> None`：将 trace 字典写入 `logs/traces.jsonl`
- **与 F1 的分工**：
  - F1 负责 TraceContext 的数据结构（含 `trace_type`）和 `finish()` 方法
  - F2 负责将 `trace.to_dict()` 的结果持久化到文件
- **验收标准**：写入一条 trace 后文件新增一行合法 JSON，包含 `trace_type` 字段。
- **测试方法**：`pytest -q tests/unit/test_jsonl_logger.py`。

### F3：在 Query 链路打点
- **目标**：在 HybridSearch/Rerank 中注入 TraceContext（`trace_type="query"`），利用 B 阶段抽象接口中预留的 `trace` 参数，显式调用 `trace.record_stage()` 记录各阶段数据。
- **前置依赖**：D5（HybridSearch）、D6（Reranker）、F1（TraceContext 增强）、F2（结构化日志）
- **修改文件**：
  - `src/core/query_engine/hybrid_search.py`（增加 trace 记录：dense/sparse/fusion 阶段）
  - `src/core/query_engine/reranker.py`（增加 trace 记录：rerank 阶段）
  - `tests/integration/test_hybrid_search.py`（断言 trace 中存在各阶段）
- **说明**：B 阶段的接口已预留 `trace: TraceContext | None = None` 参数，本任务负责在调用时传入实际的 TraceContext 实例，并在各阶段记录 `method`/`provider`/`details` 字段。
- **验收标准**：
  - 一次查询生成 trace，包含 `query_processing`/`dense_retrieval`/`sparse_retrieval`/`fusion`/`rerank` 阶段
  - 每个阶段记录 `elapsed_ms` 耗时字段和 `method` 字段
  - `trace.to_dict()` 中 `trace_type == "query"`
- **测试方法**：`pytest -q tests/integration/test_hybrid_search.py`。

### F4：在 Ingestion 链路打点
- **目标**：在 IngestionPipeline 中注入 TraceContext（`trace_type="ingestion"`），记录各摄取阶段的处理数据。
- **前置依赖**：C5（Pipeline）、F1（TraceContext 增强）、F2（结构化日志）
- **修改文件**：
  - `src/ingestion/pipeline.py`（增加 trace 传递：load/split/transform/embed/upsert 阶段）
  - `tests/integration/test_ingestion_pipeline.py`（断言 trace 中存在各阶段）
- **验收标准**：
  - 一次摄取生成 trace，包含 `load`/`split`/`transform`/`embed`/`upsert` 阶段
  - 每个阶段记录 `elapsed_ms`、`method`（如 markitdown/recursive/chroma）和处理详情
  - `trace.to_dict()` 中 `trace_type == "ingestion"`
- **测试方法**：`pytest -q tests/integration/test_ingestion_pipeline.py`。

### F5：Pipeline 进度回调 (on_progress)
- **目标**：在 `IngestionPipeline.run()` 方法中新增可选 `on_progress` 回调参数，支持外部实时获取处理进度。
- **前置依赖**：F4（Ingestion 打点）
- **修改文件**：
  - `src/ingestion/pipeline.py`（在各阶段调用 `on_progress(stage_name, current, total)`）
  - `tests/unit/test_pipeline_progress.py`（新增：验证回调被正确调用）
- **实现要点**：
  - 回调签名：`on_progress(stage_name: str, current: int, total: int)`
  - `on_progress` 为 `None` 时完全不影响现有行为
  - 各阶段在处理每个 batch 或完成时触发回调
- **验收标准**：Pipeline 运行时传入 mock 回调，断言各阶段均被调用且参数正确。
- **测试方法**：`pytest -q tests/unit/test_pipeline_progress.py`。

---

## 阶段 G：可视化管理平台 Dashboard（目标：六页面完整可视化管理）

### G1：Dashboard 基础架构与系统总览页
- **目标**：搭建 Streamlit 多页面应用框架，实现系统总览页面（展示组件配置与数据统计）。
- **前置依赖**：F1-F2（Trace 基础设施）
- **修改文件**：
  - `src/observability/dashboard/app.py`（重写：多页面导航架构）
  - `src/observability/dashboard/pages/overview.py`（新增：系统总览页面）
  - `src/observability/dashboard/services/config_service.py`（新增：配置读取服务）
  - `scripts/start_dashboard.py`（新增：Dashboard 启动脚本）
- **实现要点**：
  - `app.py` 使用 `st.navigation()` 注册六个页面（未完成的页面显示占位提示）
  - Overview 页面：读取 `Settings` 展示组件卡片，调用 `ChromaStore.get_collection_stats()` 展示数据统计
  - `ConfigService`：封装 Settings 读取，格式化组件配置信息
- **验收标准**：`streamlit run src/observability/dashboard/app.py` 可启动，总览页展示当前配置信息。
- **测试方法**：手动运行 `python scripts/start_dashboard.py` 并验证页面渲染。

### G2：DocumentManager 实现
- **目标**：实现 `src/ingestion/document_manager.py`：跨存储的文档生命周期管理（list/delete/stats）。
- **前置依赖**：C5（Pipeline + 各存储模块已就绪）
- **修改文件**：
  - `src/ingestion/document_manager.py`（新增）
  - `src/libs/vector_store/chroma_store.py`（增强：添加 `delete_by_metadata`）
  - `src/ingestion/storage/bm25_indexer.py`（增强：添加 `remove_document`）
  - `src/libs/loader/file_integrity.py`（增强：添加 `remove_record` + `list_processed`）
  - `tests/unit/test_document_manager.py`（新增）
- **实现类/函数**：
  - `DocumentManager.__init__(chroma_store, bm25_indexer, image_storage, file_integrity)`
  - `DocumentManager.list_documents(collection?) -> List[DocumentInfo]`
  - `DocumentManager.get_document_detail(doc_id) -> DocumentDetail`
  - `DocumentManager.delete_document(source_path, collection) -> DeleteResult`
  - `DocumentManager.get_collection_stats(collection?) -> CollectionStats`
- **验收标准**：
  - `list_documents` 返回已摄入文档列表（source、chunk 数、图片数）
  - `delete_document` 协调删除 Chroma + BM25 + ImageStorage + FileIntegrity 四个存储
  - 删除后再次 list 不包含已删除文档
- **测试方法**：`pytest -q tests/unit/test_document_manager.py`。

### G3：数据浏览器页面
- **目标**：实现 Dashboard 数据浏览器页面（查看文档列表、Chunk 详情、图片预览）。
- **前置依赖**：G1（Dashboard 架构）、G2（DocumentManager）
- **修改文件**：
  - `src/observability/dashboard/pages/data_browser.py`（新增）
  - `src/observability/dashboard/services/data_service.py`（新增：封装 ChromaStore/ImageStorage 读取）
- **实现要点**：
  - 文档列表视图：展示 source_path、集合、chunk 数、摄入时间；支持集合筛选
  - Chunk 详情视图：点击文档展开所有 chunk，显示内容（可折叠）、metadata 字段、关联图片
  - `DataService`：封装 `ChromaStore.get_by_metadata()` 和 `ImageStorage.list_images()` 调用
- **验收标准**：可在 Dashboard 中浏览已摄入的文档和 chunk 详情。
- **测试方法**：手动验证（先 ingest 样例数据，再在 Dashboard 浏览）。

### G4：Ingestion 管理页面
- **目标**：实现 Dashboard Ingestion 管理页面（文件上传触发摄取、进度展示、文档删除）。
- **前置依赖**：G2（DocumentManager）、G3（DataService）、F5（on_progress 回调）
- **修改文件**：
  - `src/observability/dashboard/pages/ingestion_manager.py`（新增）
- **实现要点**：
  - 文件上传：`st.file_uploader` 选择文件 + 集合选择
  - 摄取触发：调用 `IngestionPipeline.run(on_progress=...)` + `st.progress()` 实时进度
  - 文档删除：在文档列表中提供删除按钮，调用 `DocumentManager.delete_document()`
- **验收标准**：可在 Dashboard 中上传文件触发摄取、看到实时进度条、删除已有文档。
- **测试方法**：手动验证（上传 PDF → 观察进度 → 删除 → 确认已移除）。

### G5：Ingestion 追踪页面
- **目标**：实现 Dashboard Ingestion 追踪页面（摄取历史列表、阶段耗时瀑布图）。
- **前置依赖**：F4（Ingestion 打点）、G1（Dashboard 架构）
- **修改文件**：
  - `src/observability/dashboard/pages/ingestion_traces.py`（新增）
  - `src/observability/dashboard/services/trace_service.py`（新增：解析 traces.jsonl）
- **实现要点**：
  - 历史列表：按时间倒序展示 `trace_type == "ingestion"` 记录
  - 详情页：横向条形图展示 load/split/transform/embed/upsert 耗时分布
  - `TraceService`：读取 `logs/traces.jsonl`，解析为 Trace 对象列表
- **验收标准**：执行 ingest 后，Dashboard 显示对应的追踪记录与耗时瀑布图。
- **测试方法**：手动验证（先 ingest → 打开 Dashboard → 查看追踪）。

### G6：Query 追踪页面
- **目标**：实现 Dashboard Query 追踪页面（查询历史、Dense/Sparse 对比、Rerank 变化）。
- **前置依赖**：F3（Query 打点）、G1（Dashboard 架构）、G5（TraceService 已实现）
- **修改文件**：
  - `src/observability/dashboard/pages/query_traces.py`（新增）
- **实现要点**：
  - 历史列表：按时间倒序展示 `trace_type == "query"` 记录，支持按 Query 关键词搜索
  - 详情页：耗时瀑布图 + Dense vs Sparse 并列对比 + Rerank 前后排名变化
- **验收标准**：执行 query 后，Dashboard 显示查询追踪详情与各阶段对比。
- **测试方法**：手动验证（先 query → 打开 Dashboard → 查看追踪）。

---

## 阶段 H：评估体系（目标：可插拔评估 + 可量化回归）

### H1：RagasEvaluator 实现
- **目标**：实现 `ragas_evaluator.py`：封装 Ragas 框架，实现 `BaseEvaluator` 接口。
- **修改文件**：
  - `src/observability/evaluation/ragas_evaluator.py`（新增）
  - `src/libs/evaluator/evaluator_factory.py`（注册 ragas provider）
  - `tests/unit/test_ragas_evaluator.py`（新增）
- **实现类/函数**：
  - `RagasEvaluator(BaseEvaluator)`：实现 `evaluate()` 方法
  - 支持指标：Faithfulness, Answer Relevancy, Context Precision
  - 优雅降级：Ragas 未安装时抛出明确的 `ImportError` 提示
- **验收标准**：mock LLM 环境下，`evaluate()` 返回包含 faithfulness/answer_relevancy 的 metrics 字典。
- **测试方法**：`pytest -q tests/unit/test_ragas_evaluator.py`。

### H2：CompositeEvaluator 实现
- **目标**：实现 `composite_evaluator.py`：组合多个 Evaluator 并行执行，汇总结果。
- **修改文件**：
  - `src/observability/evaluation/composite_evaluator.py`（新增）
  - `tests/unit/test_composite_evaluator.py`（新增）
- **实现类/函数**：
  - `CompositeEvaluator.__init__(evaluators: List[BaseEvaluator])`
  - `CompositeEvaluator.evaluate() -> dict`：并行执行所有 evaluator，合并 metrics
  - 配置驱动：`evaluation.backends: [ragas, custom]` → 工厂自动组合
- **验收标准**：配置两个 evaluator 时，返回的 metrics 包含两者的指标。
- **测试方法**：`pytest -q tests/unit/test_composite_evaluator.py`。

### H3：EvalRunner + Golden Test Set
- **目标**：实现 `eval_runner.py`：读取 `tests/fixtures/golden_test_set.json`，跑 retrieval 并产出 metrics。
- **前置依赖**：D5（HybridSearch）、H1-H2（评估器）
- **修改文件**：
  - `src/observability/evaluation/eval_runner.py`（新增）
  - `tests/fixtures/golden_test_set.json`（新增：黄金测试集）
  - `scripts/evaluate.py`（新增：评估运行脚本）
- **实现类/函数**：
  - `EvalRunner.__init__(settings, hybrid_search, evaluator)`
  - `EvalRunner.run(test_set_path) -> EvalReport`：运行评估并返回报告
  - `EvalReport`：包含 hit_rate, mrr, 各 query 结果详情
- **golden_test_set.json 格式**：
  ```json
  {
    "test_cases": [
      {
        "query": "如何配置 Azure OpenAI？",
        "expected_chunk_ids": ["chunk_abc_001", "chunk_abc_002"],
        "expected_sources": ["config_guide.pdf"]
      }
    ]
  }
  ```
- **验收标准**：`python scripts/evaluate.py` 可运行，输出 metrics。
- **测试方法**：`pytest -q tests/integration/test_hybrid_search.py` 或 `python scripts/evaluate.py`。

### H4：评估面板页面
- **目标**：实现 Dashboard 评估面板页面（运行评估、查看指标、历史对比）。
- **前置依赖**：H3（EvalRunner）、G1（Dashboard 架构）
- **修改文件**：
  - `src/observability/dashboard/pages/evaluation_panel.py`（实现：替换占位提示）
- **实现要点**：
  - 选择评估后端与 golden test set
  - 点击运行，展示评估结果（hit_rate、mrr、各 query 明细）
  - 可选：历史评估结果对比图
- **验收标准**：可在 Dashboard 中运行评估并查看指标。
- **测试方法**：手动验证。

### H5：Recall 回归测试（E2E）
- **目标**：实现 `tests/e2e/test_recall.py`：基于 golden set 做最小召回阈值（例如 hit@k）。
- **前置依赖**：H3（EvalRunner + golden_test_set）
- **修改文件**：
  - `tests/e2e/test_recall.py`（新增）
  - `tests/fixtures/golden_test_set.json`（补齐若干条）
- **验收标准**：hit@k 达到阈值（阈值写死在测试里，便于回归）。
- **测试方法**：`pytest -q tests/e2e/test_recall.py`。

---

## 阶段 I：端到端验收与文档收口（目标：开箱即用的"可复现"工程）

### I1：E2E：MCP Client 侧调用模拟
- **目标**：实现 `tests/e2e/test_mcp_client.py`：以子进程启动 server，模拟 tools/list + tools/call。
- **修改文件**：
  - `tests/e2e/test_mcp_client.py`
- **验收标准**：完整走通 query_knowledge_hub 并返回 citations。
- **测试方法**：`pytest -q tests/e2e/test_mcp_client.py`。

### I2：E2E：Dashboard 冒烟测试
- **目标**：验证 Dashboard 各页面在有数据时可正常渲染、无 Python 异常。
- **修改文件**：
  - `tests/e2e/test_dashboard_smoke.py`（新增）
- **实现要点**：
  - 使用 Streamlit 的 `AppTest` 框架进行自动化冒烟测试
  - 验证 6 个页面均可加载、不抛异常
- **验收标准**：所有页面冒烟测试通过。
- **测试方法**：`pytest -q tests/e2e/test_dashboard_smoke.py`。

### I3：完善 README（运行说明 + 测试说明 + MCP 配置 + Dashboard 使用）
- **目标**：让新用户能在 10 分钟内跑通 ingest + query + dashboard + tests，并能在 Copilot/Claude 中使用。
- **修改文件**：
  - `README.md`
- **验收标准**：README 包含以下章节：
  - **快速开始**：安装依赖、配置 API Key、运行首次摄取
  - **配置说明**：`settings.yaml` 各字段含义
  - **MCP 配置示例**：GitHub Copilot `mcp.json` 与 Claude Desktop `claude_desktop_config.json`
  - **Dashboard 使用指南**：启动命令、各页面功能说明、截图示例
  - **运行测试**：单元测试、集成测试、E2E 测试命令
  - **常见问题**：API Key 配置、依赖安装、连接问题排查
- **测试方法**：按 README 手动走一遍。

### I4：清理接口一致性（契约测试补齐）
- **目标**：为关键抽象（VectorStore / Reranker / Evaluator / DocumentManager）补齐契约测试。
- **修改文件**：
  - `tests/unit/test_vector_store_contract.py`（补齐 delete_by_metadata 边界）
  - `tests/unit/test_reranker_factory.py`（补齐边界）
  - `tests/unit/test_custom_evaluator.py`（补齐边界）
- **验收标准**：`pytest -q` 全绿，且 contract tests 覆盖主要输入输出形状。
- **测试方法**：`pytest -q`。

### I5：全链路 E2E 验收
- **目标**：执行完整的端到端验收流程：ingest → query via MCP → Dashboard 可视化 → evaluate。
- **修改文件**：无新文件，验收已有功能
- **验收标准**：
  - `python scripts/ingest.py --path tests/fixtures/sample_documents/ --collection test` 成功
  - `python scripts/query.py --query "测试查询" --verbose` 返回结果
  - Dashboard 可展示摄取与查询追踪
  - `python scripts/evaluate.py` 输出评估指标
- **测试方法**：手动全链路走通 + `pytest -q` 全量测试。

---

## 阶段 J：Self-RAG 在线推理基础（目标：在不破坏传统 RAG 的前提下形成反思闭环）

### J1：Reflection Token 与核心类型契约
- **目标**：定义稳定的检索、相关性、支持度与效用判断语义；重试/拒答属于 Policy 控制动作，不进入 Reflection Token。
- **前置依赖**：A3（Settings）、C1（核心类型）。
- **修改文件**：
  - `src/core/self_rag_types.py`（新增）
  - `config/self_rag.yaml`（新增 Token 语义映射）
  - `tests/unit/self_rag/test_self_rag_types.py`（新增）
- **实现要点**：枚举与 Token 字符串解耦；概率范围校验；对象可 JSON 序列化；禁止隐式默认“已支持”。
- **验收标准**：所有标签、分数和结果对象具备明确类型与边界，非法概率/效用等级被拒绝。
- **测试方法**：`pytest -q tests/unit/self_rag/test_self_rag_types.py`。

### J2：Self-RAG Response Parser
- **目标**：将 Provider JSON、控制 Token 与流式响应统一解析为领域对象。
- **前置依赖**：J1、B1（LLM 抽象）。
- **修改文件**：
  - `src/core/self_rag/response_parser.py`（新增）
  - `tests/unit/self_rag/test_response_parser.py`（新增）
  - `tests/fixtures/self_rag/raw_responses/`（新增脱敏 Fixture）
- **实现要点**：Schema-first、Token ID 状态机、单次格式修复、无 logprobs 时 confidence=null、控制 Token 清理。
- **验收标准**：合法响应解析成功；损坏响应产生明确 `ParseError`；不泄漏 reasoning/control tokens。
- **测试方法**：`pytest -q tests/unit/self_rag/test_response_parser.py`。

### J3：RetrievalGate 与策略阈值
- **目标**：在检索前判断 retrieve/no-retrieve，并支持 prompted/finetuned/rule 三种来源。
- **前置依赖**：J1-J2、D1（QueryProcessor）。
- **修改文件**：
  - `src/core/self_rag/retrieval_gate.py`（新增）
  - `src/core/self_rag/policy.py`（新增基础策略）
  - `tests/unit/self_rag/test_retrieval_gate.py`（新增）
- **实现要点**：阈值配置、低置信度策略、请求预算、决策来源和概率进入 Trace。
- **验收标准**：无需检索样本不调用 Retriever；低置信度按配置检索或兜底；阈值边界确定性。
- **测试方法**：`pytest -q tests/unit/self_rag/test_retrieval_gate.py`。

### J4：Evidence Relevance Critic
- **目标**：对 Hybrid Search/Rerank 候选逐条预测 Relevant/Irrelevant 并过滤无关证据。
- **前置依赖**：D5-D6、J1-J2。
- **修改文件**：
  - `src/core/self_rag/evidence_critic.py`（新增）
  - `tests/unit/self_rag/test_evidence_critic.py`（新增）
- **实现要点**：保留原检索分数；批量判定；空证据与全部 irrelevant 明确返回；按 chunk_id 稳定排序。
- **验收标准**：难负例可被过滤，过滤结果与原候选引用关系一致，Critic 失败可配置为保留/丢弃/回退。
- **测试方法**：`pytest -q tests/unit/self_rag/test_evidence_critic.py`。

### J5：Support / Utility Critic
- **目标**：对生成段落判断证据支持度和整体效用等级。
- **前置依赖**：J1-J2、J4。
- **修改文件**：
  - `src/core/self_rag/support_critic.py`（新增）
  - `src/core/self_rag/utility_critic.py`（新增）
  - `tests/unit/self_rag/test_generation_critics.py`（新增）
- **实现要点**：段落原子事实与 evidence_ids 绑定；支持 full/partial/none；效用为 1–5 分布而非随意文本。
- **验收标准**：不存在的引用不能评为 fully supported；概率和标签一致；Critic 输出可进入 Policy。
- **测试方法**：`pytest -q tests/unit/self_rag/test_generation_critics.py`。

### J6：Segment Generator + Query Rewriter
- **目标**：实现带证据引用的分段生成，以及证据不足时的 Query 重写。
- **前置依赖**：J3-J5、E3（ResponseBuilder/Citation）。
- **修改文件**：
  - `src/core/self_rag/segment_generator.py`（新增）
  - `src/core/self_rag/query_rewriter.py`（新增）
  - `config/prompts/self_rag/runtime/`（新增）
  - `tests/unit/self_rag/test_segment_generator.py`（新增）
- **实现要点**：只引用当前可见 evidence；保持用户原始 Query 不变；区分 no-evidence、conflict、low-support 三类重写原因。
- **验收标准**：每个生成段可追溯到 evidence_ids；重写 Query 有最大长度和去重；不把内部 Token 暴露给用户。
- **测试方法**：`pytest -q tests/unit/self_rag/test_segment_generator.py`。

### J7：SelfRAGOrchestrator + 候选打分
- **目标**：串联 Gate→Retrieve→Critique→Generate→Support/Utility→Accept/Retry/Abstain。
- **前置依赖**：J3-J6、D5-D6、F1。
- **修改文件**：
  - `src/core/self_rag/orchestrator.py`（新增）
  - `src/core/self_rag/segment_scorer.py`（新增）
  - `tests/integration/test_self_rag_pipeline.py`（新增）
- **实现要点**：有限状态机、轮次/Token/时间/成本预算、beam_size=1 MVP、所有终止原因显式记录。
- **验收标准**：支持跳过检索、一次检索、重写重试和拒答四条路径；任何路径不会无限循环。
- **测试方法**：`pytest -q tests/integration/test_self_rag_pipeline.py`。

### J8：MCP/CLI 向后兼容与传统 RAG 回退
- **目标**：将 Self-RAG 接入现有 Query/MCP，但不破坏旧调用。
- **前置依赖**：J7、D7、E3、E6。
- **修改文件**：
  - `scripts/query.py`
  - `src/mcp_server/tools/query_knowledge_hub.py`
  - `src/core/response_builder.py`
  - `tests/integration/test_self_rag_mcp_compat.py`（新增）
- **实现要点**：新增可选 `self_rag`/`return_diagnostics`；基础返回字段稳定；失败按配置回退 conventional RAG。
- **验收标准**：旧请求 Fixture 完全兼容；新诊断字段不含 reasoning；回退原因可观测。
- **测试方法**：`pytest -q tests/integration/test_self_rag_mcp_compat.py`。

---

## 阶段 K：训练样本构建与 Teacher 蒸馏（目标：可审计地产生高质量 Reflection 数据）

### K1：训练数据 Schema、版本与 Manifest
- **目标**：定义 Critic、Generator、Preference 数据契约和版本元数据。
- **前置依赖**：J1、A3。
- **修改文件**：
  - `src/training/data/schemas.py`（新增）
  - `src/training/data/manifest.py`（新增）
  - `config/dataset.yaml`（新增）
  - `tests/unit/training/test_data_schemas.py`（新增）
- **实现要点**：sample_id 内容寻址；Teacher/Prompt/索引 provenance；Pydantic/dataclass 严格校验；JSONL 可演进版本。
- **验收标准**：错误 evidence ID、未知标签和缺失 provenance 无法进入 accepted 数据集。
- **测试方法**：`pytest -q tests/unit/training/test_data_schemas.py`。

### K2：Seed/Trace 数据收集与脱敏
- **目标**：从文档快照、Golden QA 和授权 Trace 生成 canonical seeds。
- **前置依赖**：C14、F3、H3、K1。
- **修改文件**：
  - `src/training/data/seed_collector.py`（新增）
  - `src/training/data/privacy_filter.py`（新增）
  - `tests/unit/training/test_seed_collector.py`（新增）
- **实现要点**：默认只读来源；PII/API Key 过滤；许可证/授权字段；Source Snapshot 哈希；线上 Trace opt-in。
- **验收标准**：密钥、邮箱/手机号 Fixture 和未授权 Trace 被隔离；输入不被原地修改。
- **测试方法**：`pytest -q tests/unit/training/test_seed_collector.py`。

### K3：Synthetic Query Generator
- **目标**：基于文档生成事实、多跳、比较、摘要、无需检索和不可回答 Query。
- **前置依赖**：K1-K2、K5 可先用 FakeTeacher。
- **修改文件**：
  - `src/training/data/synthetic_query_generator.py`（新增）
  - `config/prompts/self_rag/teacher/query_generation_v1.md`（新增）
  - `tests/unit/training/test_synthetic_query_generator.py`（新增）
- **实现要点**：任务配额、语言比例、来源绑定、模板去重、Schema 输出、dry-run。
- **验收标准**：生成 Query 均带 source_group_id/task_type；无需检索样本与文档事实题可区分。
- **测试方法**：`pytest -q tests/unit/training/test_synthetic_query_generator.py`。

### K4：Candidate Builder + Hard Negatives
- **目标**：复用真实 Retrieval/Rerank 为训练样本构建正证据、难负例和冲突证据。
- **前置依赖**：D5-D6、K1-K3。
- **修改文件**：
  - `src/training/data/candidate_builder.py`（新增）
  - `tests/integration/test_candidate_builder.py`（新增）
- **实现要点**：保存索引版本和所有分数；同 collection 限制；交叉编码器难负例；不足时明确标记。
- **验收标准**：每个候选可回溯到 Chunk；不从 test source 泄漏到 train；固定索引时确定性。
- **测试方法**：`pytest -q tests/integration/test_candidate_builder.py`。

### K5：Teacher Provider（Kimi/DeepSeek）
- **目标**：实现独立 Teacher 抽象、Kimi K3 主 Provider、DeepSeek V4 备选和 FakeTeacher。
- **前置依赖**：B1、A3。
- **修改文件**：
  - `src/training/teacher/base_teacher.py`（新增）
  - `src/training/teacher/kimi_teacher.py`（新增）
  - `src/training/teacher/deepseek_teacher.py`（新增）
  - `src/training/teacher/teacher_factory.py`（新增）
  - `tests/unit/training/test_teacher_factory.py`（新增）
- **实现要点**：OpenAI-compatible 适配但保留 Provider 差异；JSON Schema；速率/预算；启动模型探针；密钥不落日志。
- **验收标准**：Provider 可纯配置切换；Kimi 失败可回退 DeepSeek；FakeTeacher 离线全绿。
- **测试方法**：`pytest -q tests/unit/training/test_teacher_factory.py`；真实 API 用 `-m teacher` 可选运行。

### K6：Reflection Labeler + Prompt 版本化
- **目标**：分别生成 Retrieval、Relevance、Support、Utility 与 Grounded Answer 标签。
- **前置依赖**：K1、K4-K5。
- **修改文件**：
  - `src/training/teacher/labeler.py`（新增）
  - `config/prompts/self_rag/teacher/*.md`（新增）
  - `tests/unit/training/test_reflection_labeler.py`（新增）
- **实现要点**：每类标签独立 Prompt；温度 0 默认；输出短理由而非隐藏 CoT；Prompt 哈希入样本。
- **验收标准**：所有标签通过 Schema；失败进入 retry/quarantine；accepted 样本无未知枚举。
- **测试方法**：`pytest -q tests/unit/training/test_reflection_labeler.py`。

### K7：双教师一致性与 Adjudication
- **目标**：对低置信度/高风险样本进行双教师复核和冲突裁决。
- **前置依赖**：K5-K6。
- **修改文件**：
  - `src/training/teacher/adjudicator.py`（新增）
  - `tests/unit/training/test_adjudicator.py`（新增）
- **实现要点**：模型身份盲化；一致/冲突状态；预算优先级；人工审核出口；不可强行制造一致。
- **验收标准**：冲突样本不直接 accepted；裁决来源和最终置信度可审计。
- **测试方法**：`pytest -q tests/unit/training/test_adjudicator.py`。

### K8：质量过滤、去重与防泄漏切分
- **目标**：实现 Schema 后的事实/引用检查、去重、污染检测和 source-group split。
- **前置依赖**：K1、K6-K7。
- **修改文件**：
  - `src/training/data/quality_filter.py`（新增）
  - `src/training/data/deduplicator.py`（新增）
  - `src/training/data/splitter.py`（新增）
  - `tests/unit/training/test_quality_pipeline.py`（新增）
- **实现要点**：引用存在性、支持标签一致性、MinHash+Embedding 去重、Golden 污染、分组切分。
- **验收标准**：同 source_group 不跨 split；重复与污染 Fixture 被拦截；quarantine 原因统计完整。
- **测试方法**：`pytest -q tests/unit/training/test_quality_pipeline.py`。

### K9：Dataset Export、断点续跑与成本报告
- **目标**：把 K2-K8 串成可恢复 CLI，输出三类数据集、Manifest、质量和成本报告。
- **前置依赖**：K1-K8。
- **修改文件**：
  - `scripts/build_selfrag_dataset.py`（新增）
  - `scripts/label_selfrag_data.py`（新增）
  - `src/training/data/pipeline.py`（新增）
  - `tests/integration/test_dataset_pipeline.py`（新增）
- **实现要点**：分片、checkpoint、请求 cache、失败队列、dry-run、预算停止、原子 manifest。
- **验收标准**：中断后续跑不重复计费；总输入数=accepted+quarantine+failed；报告可复核。
- **测试方法**：`pytest -q tests/integration/test_dataset_pipeline.py`。

---

## 阶段 L：Critic / Generator 微调 Pipeline（目标：形成可复现可部署的 Student 模型）

### L1：Tokenizer 扩展与 Manifest 校验
- **目标**：注册 Reflection Tokens，保存稳定 Token ID 与哈希。
- **前置依赖**：J1、K1。
- **修改文件**：
  - `src/training/tokenizer_manager.py`（新增）
  - `tests/unit/training/test_tokenizer_manager.py`（新增）
- **实现要点**：唯一单 Token、resize embeddings、manifest、训练/服务哈希一致性。
- **验收标准**：所有 Token 可无损 encode/decode；重复/UNK/哈希不符时失败。
- **测试方法**：`pytest -q tests/unit/training/test_tokenizer_manager.py`。

### L2：Critic Dataset/Collator 与 Loss Mask
- **目标**：将 Critic JSONL 转成多任务 CausalLM batch，并正确 mask context。
- **前置依赖**：K9、L1。
- **修改文件**：
  - `src/training/datasets/critic_dataset.py`（新增）
  - `src/training/datasets/collators.py`（新增）
  - `tests/unit/training/test_critic_dataset.py`（新增）
- **实现要点**：任务模板、采样权重、truncate、padding、labels=-100、reflection loss weight。
- **验收标准**：只在目标标签计算 loss；固定 seed 可复现；无跨样本污染。
- **测试方法**：`pytest -q tests/unit/training/test_critic_dataset.py`。

### L3：Critic LoRA/QLoRA 训练 Pipeline
- **目标**：实现可配置 Trainer、checkpoint、resume 和本地 tracking。
- **前置依赖**：L1-L2。
- **修改文件**：
  - `src/training/backends/base_trainer.py`（新增）
  - `src/training/backends/hf_trainer.py`（新增）
  - `src/training/critic_pipeline.py`（新增）
  - `scripts/train_selfrag_critic.py`（新增）
  - `config/training.yaml`（新增）
- **实现要点**：LoRA/QLoRA、bf16/fp16、梯度累积、checkpoint、seed、run manifest。
- **验收标准**：tiny model smoke loss 有限且下降；checkpoint 可在新进程恢复。
- **测试方法**：`pytest -q tests/integration/test_training_smoke.py -k critic`。

### L4：Critic 评估与置信度校准
- **目标**：为四类 Reflection 任务输出独立指标和校准阈值。
- **前置依赖**：L3。
- **修改文件**：
  - `src/training/evaluator.py`（新增 Critic 部分）
  - `scripts/evaluate_selfrag.py`（新增/扩展）
  - `tests/unit/training/test_critic_metrics.py`（新增）
- **实现要点**：macro-F1、per-class、ECE、混淆矩阵；只在 dev 调阈值。
- **验收标准**：指标可从固定 Fixture 精确复算；test 数据不参与阈值选择。
- **测试方法**：`pytest -q tests/unit/training/test_critic_metrics.py`。

### L5：Generator 数据离线构建
- **目标**：用 accepted Teacher 标签和高置信度 Critic 标签构建交错 Reflection Token 的 Generator 数据。
- **前置依赖**：K9、L4。
- **修改文件**：
  - `src/training/data/generator_data_builder.py`（新增）
  - `scripts/build_generator_data.py`（新增）
  - `tests/unit/training/test_generator_data_builder.py`（新增）
- **实现要点**：低置信度回 Teacher；证据 Context mask；Token 顺序状态机；引用映射。
- **验收标准**：每条训练目标 Token 序列合法，引用存在，来源和标签版本可追溯。
- **测试方法**：`pytest -q tests/unit/training/test_generator_data_builder.py`。

### L6：Generator LoRA/QLoRA SFT Pipeline
- **目标**：训练能够生成答案与 Reflection Tokens 的 Student Generator。
- **前置依赖**：L1、L5、L3 Trainer 基础。
- **修改文件**：
  - `src/training/datasets/generator_dataset.py`（新增）
  - `src/training/generator_pipeline.py`（新增）
  - `scripts/train_selfrag_generator.py`（新增）
- **实现要点**：文本/reflection loss 分报；SFT checkpoint；真实状态机 dev eval；传统 RAG baseline。
- **验收标准**：Smoke 模型可生成合法控制 Token；Parser 可解析；resume 一致。
- **测试方法**：`pytest -q tests/integration/test_training_smoke.py -k generator`。

### L7：可选 Preference/DPO Pipeline
- **目标**：使用支持度、引用、效用和检索成本构建 chosen/rejected 并执行可选偏好训练。
- **前置依赖**：L6 通过 SFT 门禁后才启动。
- **修改文件**：
  - `src/training/datasets/preference_dataset.py`（新增）
  - `src/training/backends/trl_trainer.py`（新增）
  - `src/training/preference_pipeline.py`（新增）
  - `tests/unit/training/test_preference_dataset.py`（新增）
- **实现要点**：不以 reasoning 长度为偏好；对比依据入样本；可完全关闭。
- **验收标准**：chosen/rejected prompt 一致；DPO 关闭不影响 SFT；有单独消融报告。
- **测试方法**：`pytest -q tests/unit/training/test_preference_dataset.py`。

### L8：Checkpoint、Adapter、量化与导出
- **目标**：统一 checkpoint、Adapter 合并、量化和 serving artifact 导出。
- **前置依赖**：L3、L6。
- **修改文件**：
  - `src/training/artifact_manager.py`（新增）
  - `scripts/export_selfrag_model.py`（新增）
  - `tests/integration/test_model_export.py`（新增）
- **实现要点**：safetensors、tokenizer manifest、原子目录、量化前后评估、损坏产物检测。
- **验收标准**：导出模型可在新进程加载并生成控制 Token；hash 和依赖信息完整。
- **测试方法**：`pytest -q tests/integration/test_model_export.py`。

### L9：训练复现、恢复与 Model Card
- **目标**：标准化 Run Manifest、实验追踪、复现脚本与 Model Card。
- **前置依赖**：L3-L8。
- **修改文件**：
  - `src/training/run_manifest.py`（新增）
  - `scripts/training/reproduce.ps1`（新增）
  - `scripts/training/reproduce.sh`（新增）
  - `artifacts/templates/model_card.md`（新增模板）
  - `tests/unit/training/test_run_manifest.py`（新增）
- **实现要点**：commit/config/data/tokenizer/device/dependency 哈希；不含密钥；不兼容 resume 拒绝。
- **验收标准**：任意 validated Run 可由 manifest 定位数据、配置、checkpoint 与指标；Model Card 字段完整。
- **测试方法**：`pytest -q tests/unit/training/test_run_manifest.py`。

---

## 阶段 M：Student Serving、评估与可观测性（目标：让微调模型可靠进入现有 MCP 服务）

### M1：FineTunedReflectionModel Provider
- **目标**：用统一接口加载本地 Transformers/vLLM Student，并读取控制 Token/logprobs。
- **前置依赖**：J1-J2、L8。
- **修改文件**：
  - `src/libs/reflection/base_reflection_model.py`（新增）
  - `src/libs/reflection/finetuned_reflection_model.py`（新增）
  - `src/libs/reflection/reflection_factory.py`（新增）
  - `tests/unit/self_rag/test_reflection_factory.py`（新增）
- **实现要点**：Tokenizer hash 校验、批量推理、设备选择、模型能力探针、线程安全。
- **验收标准**：Fake/tiny/local endpoint 均遵守同一契约；模型不兼容时拒绝启动而非静默错误。
- **测试方法**：`pytest -q tests/unit/self_rag/test_reflection_factory.py`。

### M2：SelfRAGPolicy 配置与运行时校准
- **目标**：从 dev 指标生成检索/支持/效用阈值和候选权重配置。
- **前置依赖**：L4、L6、M1、J7。
- **修改文件**：
  - `src/core/self_rag/policy.py`
  - `src/training/policy_calibrator.py`（新增）
  - `scripts/calibrate_selfrag_policy.py`（新增）
  - `tests/unit/self_rag/test_policy_calibration.py`（新增）
- **实现要点**：只读 dev；约束 over-retrieval/latency；输出版本化 policy；不在 test 调参。
- **验收标准**：相同输入与 seed 得到同一 policy；阈值来源和目标指标可审计。
- **测试方法**：`pytest -q tests/unit/self_rag/test_policy_calibration.py`。

### M3：Self-RAG Trace Schema 与日志
- **目标**：记录 Gate、检索轮次、证据过滤、段落支持度、效用、终止和 fallback。
- **前置依赖**：F1-F3、J7。
- **修改文件**：
  - `src/core/trace_context.py`
  - `src/observability/logger.py`
  - `tests/unit/test_self_rag_trace.py`（新增）
- **实现要点**：schema version；事件顺序；概率/ID/耗时；不记录 reasoning、密钥和完整训练正文。
- **验收标准**：传统 query Trace 不变；Self-RAG Trace 可序列化、可回放且敏感字段被过滤。
- **测试方法**：`pytest -q tests/unit/test_self_rag_trace.py`。

### M4：Self-RAG Trace Dashboard
- **目标**：可视化检索决策、重试、证据过滤、支持度与效用。
- **前置依赖**：G1、G6、M3。
- **修改文件**：
  - `src/observability/dashboard/pages/self_rag_traces.py`（新增）
  - `src/observability/dashboard/services/trace_service.py`
  - `tests/unit/test_self_rag_trace_page.py`（新增）
- **实现要点**：时间线、证据表、段落-引用映射、fallback reason、无隐藏推理。
- **验收标准**：有/无数据、传统/新 Trace、损坏日志均可稳定渲染。
- **测试方法**：`pytest -q tests/unit/test_self_rag_trace_page.py`。

### M5：Training Monitor + Model Registry
- **目标**：展示 Dataset/Run/模型状态并实现本地模型注册与原子激活。
- **前置依赖**：G1、K9、L9。
- **修改文件**：
  - `src/training/model_registry.py`（新增）
  - `src/observability/dashboard/pages/training_monitor.py`（新增）
  - `scripts/promote_selfrag_model.py`（新增）
  - `tests/unit/training/test_model_registry.py`（新增）
- **实现要点**：candidate/validated/deployable/active/archived；指标门禁；旧模型保留；Dashboard 只读。
- **验收标准**：未通过门禁模型不可 active；激活失败不影响旧模型；Registry 可恢复。
- **测试方法**：`pytest -q tests/unit/training/test_model_registry.py`。

### M6：Self-RAG 评估集与基线对比
- **目标**：构建冻结 test set，对比传统 RAG、Prompted Self-RAG、微调 Student。
- **前置依赖**：H1-H5、K8、L6、M2。
- **修改文件**：
  - `tests/fixtures/self_rag/self_rag_test_set.jsonl`（新增）
  - `src/training/evaluator.py`（扩展在线指标）
  - `scripts/evaluate_selfrag.py`
  - `tests/unit/training/test_self_rag_metrics.py`（新增）
- **实现要点**：决策/相关性/支持度/引用/拒答/延迟/成本；置信区间；版本固定。
- **验收标准**：三种模式在相同索引、数据、seed 下出完整可比较报告；test 不用于调参。
- **测试方法**：`pytest -q tests/unit/training/test_self_rag_metrics.py` + `python scripts/evaluate_selfrag.py --config ...`。

### M7：MCP/CLI E2E 与并发隔离
- **目标**：验证 active Student 通过 MCP/CLI 完成 Self-RAG 查询，且并发状态隔离。
- **前置依赖**：M1-M6、I1。
- **修改文件**：
  - `tests/e2e/test_self_rag_mcp.py`（新增）
  - `tests/e2e/test_self_rag_concurrency.py`（新增）
- **实现要点**：stdio 无调试污染；新旧请求；并发预算/证据/轮次隔离；取消和超时。
- **验收标准**：完整答案/引用/diagnostics 可解析；并发请求无串线；旧 MCP Client 仍通过。
- **测试方法**：`pytest -q tests/e2e/test_self_rag_mcp.py tests/e2e/test_self_rag_concurrency.py`。

### M8：故障回退、超时、预算与安全测试
- **目标**：验证 Student、Teacher、Retriever、Parser 和 Registry 故障时的安全行为。
- **前置依赖**：M1-M7。
- **修改文件**：
  - `tests/integration/test_self_rag_fallbacks.py`（新增）
  - `tests/integration/test_self_rag_security.py`（新增）
- **实现要点**：模型加载失败、坏 Tokenizer、429/timeout、预算耗尽、Prompt injection、日志脱敏。
- **验收标准**：失败不会生成伪支持答案或泄密；fallback/错误结构明确；无无限重试。
- **测试方法**：`pytest -q tests/integration/test_self_rag_fallbacks.py tests/integration/test_self_rag_security.py`。

---

## 阶段 N：Self-RAG 端到端验收与文档收口（目标：形成可复现训练与推理工程）

### N1：数据构建 Pipeline E2E Smoke
- **目标**：用小型文档集和 Fake/录制 Teacher 完成 seed→candidate→label→QC→split→export。
- **前置依赖**：K1-K9。
- **修改文件**：
  - `tests/e2e/test_self_rag_data_pipeline.py`（新增）
  - `tests/fixtures/self_rag/mini_corpus/`（新增）
- **验收标准**：产出 Critic/Generator/Preference 数据、Manifest、质量/成本报告；重跑幂等。
- **测试方法**：`pytest -q tests/e2e/test_self_rag_data_pipeline.py`。

### N2：最小 Critic/Generator 训练闭环
- **目标**：用 tiny model 和小数据完成 Critic SFT→Generator Data→Generator SFT→导出→解析。
- **前置依赖**：L1-L9、N1。
- **修改文件**：
  - `tests/e2e/test_self_rag_training_loop.py`（新增）
- **验收标准**：两个阶段 loss 有限、checkpoint 可恢复、导出模型生成合法 Token、manifest 链路完整。
- **测试方法**：`pytest -q tests/e2e/test_self_rag_training_loop.py -m training_smoke`。

### N3：模型发布到 MCP 全链路 E2E
- **目标**：将 Smoke Student 注册为 candidate、验证、激活并通过 MCP 完成查询。
- **前置依赖**：M1-M8、N2。
- **修改文件**：
  - `tests/e2e/test_self_rag_release_flow.py`（新增）
- **验收标准**：Model Registry 状态迁移正确；MCP 返回引用与 Self-RAG 诊断；切回旧模型成功。
- **测试方法**：`pytest -q tests/e2e/test_self_rag_release_flow.py`。

### N4：README、Runbook、Dataset/Model Card
- **目标**：让新用户能复现 Prompted Self-RAG、数据构建、Smoke 训练、模型评估与 MCP 接入。
- **前置依赖**：N1-N3。
- **修改文件**：
  - `README.md`
  - `docs/self_rag_architecture.md`（新增）
  - `docs/dataset_runbook.md`（新增）
  - `docs/training_runbook.md`（新增）
  - `docs/model_release_runbook.md`（新增）
  - `artifacts/templates/dataset_card.md`（新增）
  - `artifacts/templates/model_card.md`
- **验收标准**：命令、配置、硬件档位、成本提示、密钥方式、限制、许可证、回退与故障排查完整。
- **测试方法**：在干净环境按文档执行最小闭环；命令通过 smoke 校验。

### N5：全量回归与发布验收
- **目标**：执行传统 RAG + Self-RAG + 数据 + 训练 Smoke + MCP + Dashboard 全量验收。
- **前置依赖**：A1-N4。
- **修改文件**：无固定新文件；修复验收问题并生成发布报告。
- **验收标准**：
  - 原 A-I 功能和测试不回归；
  - J-N 目标测试全部通过，真实 API/GPU 测试的跳过条件明确；
  - Self-RAG 指标满足 4.9 发布门禁；
  - 数据、模型、Prompt、Policy 与代码版本可追溯；
  - 没有 API Key、PII、隐藏 reasoning、模型权重或受限原始数据进入 Git；
  - Traditional RAG 回退、旧 MCP Client 与模型回滚成功。
- **测试方法**：`pytest -q` + `python scripts/evaluate_selfrag.py` + 数据/训练/MCP E2E runbook。

---

### 交付里程碑（建议）

- **Milestone 1（完成阶段 A+B）**：工程可测 + 可插拔抽象层就绪，后续实现可并行推进。
- **Milestone 2（完成阶段 C）**：离线摄取链路可用，能构建本地索引。
- **Milestone 3（完成阶段 D+E）**：在线查询 + MCP tools 可用，可在 Copilot/Claude 中调用。
- **Milestone 4（完成阶段 F）**：Ingestion + Query 双链路可追踪，JSON Lines 持久化。
- **Milestone 5（完成阶段 G）**：六页面可视化管理平台就绪（评估面板为占位），数据可浏览、可管理、链路可追踪。
- **Milestone 6（完成阶段 H+I）**：传统 RAG 评估体系完整 + E2E 验收通过，形成可复现基线。
- **Milestone 7（完成阶段 J）**：Prompted/Fake 模式的 Self-RAG 在线反思闭环可用，并可安全回退传统 RAG。
- **Milestone 8（完成阶段 K）**：Kimi K3 主 Teacher、DeepSeek V4 备选的训练数据流水线可断点、可审计、可预算运行。
- **Milestone 9（完成阶段 L）**：Critic/Generator 微调闭环、Tokenizer、Checkpoint、Adapter 与 Model Card 完整。
- **Milestone 10（完成阶段 M+N）**：微调 Student 正式接入 MCP，评估达标，数据→训练→发布→推理全链路可复现。


