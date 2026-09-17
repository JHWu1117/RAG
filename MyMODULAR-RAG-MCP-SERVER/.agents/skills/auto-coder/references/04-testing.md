## 4. 测试方案

### 4.1 设计理念：测试驱动开发 (TDD)

本项目采用**测试驱动开发（Test-Driven Development）**作为核心开发范式，确保每个组件在实现前就已明确其预期行为，通过自动化测试持续验证系统质量。

**核心原则**：
- **早测试、常测试**：每个功能模块实现的同时就编写对应的单元测试，而非事后补测。
- **测试即文档**：测试用例本身就是最准确的行为规范，新加入的开发者可通过阅读测试快速理解各模块功能。
- **快速反馈循环**：单元测试应在秒级完成，支持开发者高频执行，立即发现引入的问题。
- **分层测试金字塔**：大量快速的单元测试作为基座，少量关键路径的集成测试作为保障，极少数端到端测试验证完整流程。

```
        /\
       /E2E\         <- 少量，验证关键业务流程
      /------\
     /Integration\   <- 中量，验证模块协作
    /------------\
   /  Unit Tests  \  <- 大量，验证单个函数/类
  /________________\
```

### 4.2 测试分层策略

#### 4.2.1 单元测试 (Unit Tests)

**目标**：验证每个独立组件的内部逻辑正确性，隔离外部依赖。

**覆盖范围**：

| 模块 | 测试重点 | 典型测试用例 |
|-----|---------|------------|
| **Loader (文档解析器)** | 格式解析、元数据提取、图片引用收集 | - 测试解析单页/多页 PDF<br>- 验证 Markdown 标题层级提取<br>- 检查图片占位符插入位置 |
| **Splitter (切分器)** | 切分边界、上下文保留、元数据传递 | - 验证按标题切分不破坏段落<br>- 测试超长文本的递归切分<br>- 检查 Chunk 的 `source` 字段正确性 |
| **Transform (增强器)** | 图片描述生成、元数据注入 | - Mock Vision LLM，验证描述注入逻辑<br>- 测试无图片时的降级行为<br>- 验证幂等性（重复处理相同输入） |
| **Embedding (向量化)** | 批处理、差量计算、向量维度 | - 验证相同文本生成相同向量<br>- 测试批量请求的拆分与合并<br>- 检查缓存命中逻辑 |
| **BM25 (稀疏编码)** | 关键词提取、权重计算 | - 验证停用词过滤<br>- 测试 IDF 计算准确性<br>- 检查稀疏向量格式 |
| **Retrieval (检索器)** | 召回精度、融合算法 | - 测试纯 Dense/Sparse/Hybrid 三种模式<br>- 验证 RRF 融合分数计算<br>- 检查 Top-K 结果排序 |
| **Reranker (重排器)** | 分数归一化、降级回退 | - Mock Cross-Encoder，验证分数重排<br>- 测试超时后的 Fallback 逻辑<br>- 验证空候选集处理 |

**技术选型**：
- **测试框架**：`pytest`（Python 标准选择，支持参数化测试、Fixture 机制）
- **Mock 工具**：`unittest.mock` / `pytest-mock`（隔离外部依赖，如 LLM API）
- **断言增强**：`pytest-check`（支持多断言不中断执行）

#### 4.2.2 集成测试 (Integration Tests)

**目标**：验证多个组件协作时的数据流转与接口兼容性。

**覆盖范围**：

| 测试场景 | 验证要点 | 测试策略 |
|---------|---------|---------|
| **Ingestion Pipeline** | Loader → Splitter → Transform → Storage 的完整流程 | - 使用真实的测试 PDF 文件<br>- 验证最终存入向量库的数据完整性<br>- 检查中间产物（如临时图片文件）是否正确清理 |
| **Hybrid Search** | Dense + Sparse 召回的融合结果 | - 准备已知答案的查询-文档对<br>- 验证融合后的 Top-1 是否命中正确文档<br>- 测试极端情况（某一路无结果） |
| **Rerank Pipeline** | 召回 → 过滤 → 重排的组合 | - 验证 Metadata 过滤后的候选集正确性<br>- 检查 Reranker 是否改变了 Top-1 结果<br>- 测试 Reranker 失败时的回退 |
| **MCP Server** | 工具调用的端到端流程 | - 模拟 MCP Client 发送 JSON-RPC 请求<br>- 验证返回的 `content` 格式符合协议<br>- 测试错误处理（如查询语法错误） |

**技术选型**：
- **数据隔离**：每个测试使用独立的临时数据库/向量库（`pytest-tempdir`）
- **异步测试**：`pytest-asyncio`（若 MCP Server 采用异步实现）
- **契约测试**：定义各模块间的 Schema，确保接口不漂移

#### 4.2.3 端到端测试 (End-to-End Tests)

**目标**：模拟真实用户操作，验证完整业务流程的可用性。

**核心场景**：

**场景 1：数据准备（离线摄取）**
- **测试目标**：验证文档摄取流程的完整性与正确性
- **测试步骤**：
  - 准备测试文档（PDF 文件，包含文本、图片、表格等多种元素）
  - 执行离线摄取脚本，将文档导入知识库
  - 验证摄取结果：检查生成的 Chunk 数量、元数据完整性、图片描述生成
  - 验证存储状态：确认向量库和 BM25 索引正确创建
  - 验证幂等性：重复摄取同一文档，确保不产生重复数据
- **验证要点**：
  - Chunk 的切分质量（语义完整性、上下文保留）
  - 元数据字段完整性（source、page、title、tags 等）
  - 图片处理结果（Caption 生成、Base64 编码存储）
  - 向量与稀疏索引的正确性

**场景 2：召回测试**
- **测试目标**：验证检索系统的召回精度与排序质量
- **测试步骤**：
  - 基于已摄取的知识库，准备一组测试查询（包含不同难度与类型）
  - 执行混合检索（Dense + Sparse + Rerank）
  - 验证召回结果：检查 Top-K 文档是否包含预期来源
  - 对比不同检索策略的效果（纯 Dense、纯 Sparse、Hybrid）
  - 验证 Rerank 的影响：对比重排前后的结果变化
- **验证要点**：
  - Hit Rate@K：Top-K 结果命中率是否达标
  - 排序质量：正确答案是否排在前列（MRR、NDCG）
  - 边界情况处理：空查询、无结果查询、超长查询
  - 多模态召回：包含图片的文档是否能通过文本查询召回

**场景 3：MCP Client 功能测试**
- **测试目标**：验证 MCP Server 与 Client（如 GitHub Copilot）的协议兼容性与功能完整性
- **测试步骤**：
  - 启动 MCP Server（Stdio Transport 模式）
  - 模拟 MCP Client 发送各类 JSON-RPC 请求
  - 测试工具调用：`query_knowledge_hub`、`list_collections` 等
  - 验证返回格式：符合 MCP 协议规范（content 数组、structuredContent）
  - 测试引用透明性：返回结果包含完整的 Citation 信息
  - 测试多模态返回：包含图片的响应正确编码为 Base64
- **验证要点**：
  - 协议合规性：JSON-RPC 2.0 格式、错误码映射
  - 工具注册：`tools/list` 返回所有可用工具及其 Schema
  - 响应格式：TextContent 与 ImageContent 的正确组合
  - 错误处理：无效参数、超时、服务不可用等异常场景
  - 性能指标：单次请求的端到端延迟（含检索、重排、格式化）

**测试工具**：
- **BDD 框架**：`behave` 或 `pytest-bdd`（以 Gherkin 语法描述场景）
- **环境准备**：
  - 临时测试向量库（独立于生产数据）
  - 预置的标准测试文档集
  - 本地 MCP Server 进程（Stdio Transport）

### 4.3 RAG 质量评估测试

**目标**：验证已设计的评估体系（见 3.3.4 评估框架抽象）是否正确实现，并能有效评估 RAG 系统的召回与生成质量。

**测试要点**：

1. **黄金测试集准备**
   - 构建标准的"问题-答案-来源文档"测试集（JSON 格式）
   - 初期人工标注核心场景，后期持续积累坏 Case

2. **评估框架实现验证**
   - 验证 Ragas/DeepEval 等评估框架的正确集成
   - 确认评估接口能输出标准化的指标字典
   - 测试多评估器并行执行与结果汇总

3. **关键指标达标验证**
   - 检索指标：Hit Rate@K ≥ 90%、MRR ≥ 0.8、NDCG@K ≥ 0.85
   - 生成指标：Faithfulness ≥ 0.9、Answer Relevancy ≥ 0.85
   - 定期运行评估，监控指标是否回归

**说明**：本节重点是验证评估体系的工程实现，而非重新设计评估方法（评估方法的设计见第 3 章技术选型）。

### 4.4 性能与压力测试（可选）

> **说明**：本项目定位为本地 MCP Server，单用户开发环境，采用 Stdio Transport 通信方式。性能与压力测试在当前阶段**不是必需的**，此处列出主要用于：
> 1. **架构完整性**：展示完整的工程化测试体系，体现系统设计的专业性
> 2. **未来扩展性**：若后续需要云端部署或多用户支持，可直接参考此方案
> 3. **性能基准建立**：通过基础性能测试了解系统瓶颈，为优化提供数据支撑

**可选测试场景**：

| 测试类型 | 验证点 | 工具 | 优先级 |
|---------|-------|------|-------|
| **延迟测试** | 单次查询的 P50/P95/P99 延迟 | `pytest-benchmark` | 中（可帮助识别慢查询） |
| **吞吐量测试** | 并发查询时的 QPS 上限 | `locust` | 低（本地单用户无需求） |
| **内存泄漏检测** | 长时间运行后的内存占用 | `memory_profiler` | 低（短期运行无影响） |
| **向量库性能** | 不同数据规模下的查询速度 | 自定义 Benchmark | 中（验证扩展性） |

### 4.5 测试工具链与 CI/CD 集成

**本地开发工作流**：
- **快速验证**：仅运行单元测试，秒级反馈
- **完整验证**：单元测试 + 集成测试，生成覆盖率报告
- **质量评估**：定期执行 RAG 质量测试，监控指标变化

**CI/CD Pipeline 设计**（可选）：
> **说明**：本地项目不强制要求 CI/CD，但配置自动化测试流程有助于代码质量保障与持续集成实践。

- **单元测试阶段**：每次提交自动触发，验证基础功能，生成覆盖率报告
- **集成测试阶段**：单元测试通过后执行，验证模块协作
- **质量评估阶段**：PR 触发，运行完整的 RAG 质量测试，发布评估报告

**测试覆盖率目标**：
- **单元测试**：核心逻辑覆盖率 ≥ 80%
- **集成测试**：关键路径覆盖率 100%（如 Ingestion、Hybrid Search）
- **E2E 测试**：核心用户场景覆盖率 100%（至少 3 个关键流程）


### 4.6 Self-RAG 在线推理测试

#### 4.6.1 单元测试

| 测试对象 | 必测场景 |
|---------|---------|
| `SelfRAGResponseParser` | 合法 JSON、控制 Token 流式拆分、缺字段、非法枚举、重复 Token、混合文本、无 logprobs、修复失败 |
| `RetrievalGate` | 明确需检索、明确无需检索、阈值边界、低置信度、Provider 失败 |
| `EvidenceCritic` | 正证据、难负例、空证据、重复证据、跨 collection 证据 |
| `SupportCritic` | fully/partial/none、引用不存在、一个段落多事实、多证据冲突 |
| `SelfRAGPolicy` | 接受、重试、拒答、超轮次、超 token、超预算、超时 |
| `SegmentScorer` | 权重组合、`log(0)`、NaN/Inf、beam tie-break、硬过滤 |
| `ResponseBuilder` | 控制 Token 清理、引用映射、diagnostics 开关、隐藏 reasoning 不泄漏 |

所有 Provider 响应使用录制 Fixture 或 Fake，不发起真实网络请求。

#### 4.6.2 集成测试

- PromptedReflectionModel + Fake LLM + ResponseParser；
- FineTunedReflectionModel + tiny 本地模型 + tokenizer manifest；
- SelfRAGOrchestrator + HybridSearch + Reranker + Trace；
- 多轮 Query Rewrite 后成功检索；
- Self-RAG 初始化失败回退传统 RAG；
- MCP `query_knowledge_hub` 新旧请求结构兼容；
- Stream 与非 Stream 输出产生相同规范化结果；
- 并发请求之间状态、预算和证据列表隔离。

#### 4.6.3 E2E 场景集

最少覆盖：

1. 无需检索的闲聊/改写问题，系统输出 `<RET_NO>` 且不访问向量库；
2. 单文档事实问答，触发检索并返回完整支持和正确引用；
3. Dense 命中但证据无关，被 Evidence Critic 过滤；
4. 首轮检索不足，重写 Query 后第二轮成功；
5. 文档中不存在答案，Critic 判定证据不支持，Policy 决定拒答；
6. 多文档冲突，答案明确说明冲突并引用双方；
7. 长回答按段落绑定证据，任一段引用不可串线；
8. Student 输出格式损坏，触发解析修复或可解释降级；
9. Kimi/DeepSeek/本地 Student Provider 切换不改变领域契约；
10. `self_rag=false` 与原传统 RAG 基线输出路径一致。

### 4.7 数据构建与 Teacher 标注测试

- **Schema Contract**：每种 `task_type` 的必填字段、枚举、概率和引用关系；
- **幂等性**：相同输入快照 + Prompt + Teacher 参数产生相同 `sample_id`，已完成分片不会重复计费；
- **断点恢复**：随机中断后从 checkpoint 继续，accepted/failed 数量不丢失；
- **Rate Limit**：模拟 429、5xx、timeout，验证退避、重试上限和 fallback；
- **Budget Gate**：达到日预算后停止新请求但安全落盘当前进度；
- **Provider Fallback**：Kimi 失败切换 DeepSeek，并在样本 provenance 中准确记录；
- **Quality Gate**：不存在的 evidence ID、无支持却标 full、跨集合泄漏样本必须被拦截；
- **Dedup**：精确重复、模板变体和语义近重复均有测试；
- **Split Leakage**：同一 `source_group_id` 不得跨 train/dev/test；
- **Security**：Prompt injection 文档不能改变 Teacher 的输出 Schema，密钥/PII 不进入产物和日志；
- **Replay**：对固定 Teacher Fixture 可在离线环境重放并得到确定性规范化结果。

少量真实 Teacher API 测试使用 `@pytest.mark.teacher`，默认跳过，只有显式提供密钥和预算时运行。

### 4.8 训练 Pipeline 测试

#### 4.8.1 数据与 Loss 测试

- Reflection Tokens 均为唯一单 token ID；
- context/instruction/padding labels 全为 `-100`；
- answer 与 reflection target 未被误 mask；
- truncate 后保留必要控制 Token 与 evidence mapping；
- packing 不跨样本污染 attention/labels；
- critic/generator/preference collator 输出 shape、dtype 与 device 正确；
- 固定 seed 下样本顺序和 split 可复现。

#### 4.8.2 Smoke Training

CI 不训练大模型，而使用 tiny CausalLM 与 32–128 条 Fixture：

1. 运行 10–50 steps，loss 必须有限且有下降趋势；
2. 保存 checkpoint 后在新进程恢复，global step、optimizer 和 RNG 连续；
3. 导出 Adapter/Tokenizer 后可重新加载；
4. 推理至少生成一个合法 Reflection Token；
5. Parser 能将输出转换为 `SelfRAGResult`；
6. Dataset/Tokenizer hash 不匹配时拒绝错误续训。

#### 4.8.3 多卡/量化测试

多卡、FSDP/DeepSpeed 与 QLoRA 测试放入可选 GPU Pipeline：

- 单卡和多卡在固定小数据上的首批 loss 近似一致；
- gradient accumulation 与 effective batch size 计算正确；
- 量化前后检索决策、支持度和效用指标退化不超过配置阈值；
- 合并 Adapter 后 tokenizer 和控制 Token embedding 不丢失；
- OOM 时输出可操作诊断，不产生“成功”标记或损坏 checkpoint。

### 4.9 Self-RAG 评估矩阵与发布阈值

| 维度 | 指标 | 对比对象 |
|------|------|---------|
| 检索决策 | macro-F1、over-retrieval rate、under-retrieval rate | Prompted gate / always retrieve |
| 证据相关性 | macro-F1、NDCG@k、保留率 | Reranker-only |
| 支持度 | full/partial/none macro-F1、ECE | Teacher/Human labels |
| 生成质量 | EM/F1、Answer Relevancy、Utility | 传统 RAG |
| 事实性 | Faithfulness、FactScore（可选） | 传统 RAG / Prompted Self-RAG |
| 引用 | Citation Precision、Citation Recall、Citation Correctness | 传统 RAG |
| 拒答 | answerable accuracy、unanswerable abstention F1 | 传统 RAG |
| 系统 | P50/P95 latency、平均检索轮次、tokens/query、cost/query | 传统 RAG |
| 稳定性 | parse success、fallback rate、timeout rate | 发布前一版本 |

首版建议门禁（在冻结 test set 前可基于 dev baseline 调整一次，并记录理由）：

- Response parse success ≥ 99.5%；
- Retrieval Decision macro-F1 ≥ 0.85；
- Relevance 与 Support macro-F1 ≥ 0.80；
- Citation Precision 与 Faithfulness 不低于传统 RAG，至少一项有统计显著提升；
- 不可回答集 Abstention F1 ≥ 0.80；
- P95 延迟不超过基线的 2 倍，或满足明确的业务 SLA；
- 平均检索轮次 ≤ 1.5，fallback rate ≤ 5%。

阈值不是简历数字。正式报告必须记录数据版本、样本数、置信区间、随机种子和对比模型版本。
