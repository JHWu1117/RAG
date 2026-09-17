## 1. 项目概述
本项目在原有多阶段检索增强生成（RAG, Retrieval-Augmented Generation）与模型上下文协议（MCP, Model Context Protocol）基础上，升级为 **Self-Reflective Retrieval-Augmented Generation（Self-RAG）** 系统。目标是在保留原有 PDF 摄取、Hybrid Search、Rerank、MCP Tools、Dashboard 与评估体系的前提下，让模型具备 **按需检索、证据相关性判断、回答支持度检查、效用评分与受控重试** 能力，并打通从训练样本构建、强模型教师标注、知识蒸馏、参数高效微调到在线部署的完整闭环。

### 1.1 本次改造边界与兼容原则

本规格不是推翻原架构重写，而是采用“**保留基础 RAG，新增 Self-RAG 控制面**”的增量演进方式：

1. **保留原始主干**：Ingestion Pipeline、Dense/Sparse 检索、RRF、Rerank、Chroma、BM25、MCP stdio、Trace 与 Dashboard 继续作为底座。
2. **新增决策闭环**：在 QueryProcessor 与 HybridSearch/ResponseBuilder 之间新增 Self-RAG Orchestrator，负责检索门控、反思、分段生成、证据核验和有限重试。
3. **保持接口兼容**：`query_knowledge_hub` 的已有输入和基础返回字段不删除；Self-RAG 元数据作为可选扩展字段，并允许通过配置退回传统 RAG。
4. **训练与服务解耦**：训练数据构建、教师标注和微调放在独立 `src/training/` 与 `scripts/training/` 中，不让重型训练依赖污染 MCP 在线服务的最小安装集。
5. **Provider 可替换**：Teacher 默认使用 Kimi K3，DeepSeek V4 Pro 作为备选；模型 ID、API Endpoint、预算和并发度全部配置化，不在代码中写死。
6. **不蒸馏隐藏思维链**：数据集只保存结构化标签、简洁可审计的判定依据、证据 ID 和最终答案，不要求或持久化教师模型的私有/隐藏 Chain-of-Thought。
7. **可复现优先**：每条训练样本必须具备来源、Prompt 版本、Teacher 模型版本、检索快照、标签置信度和数据切分信息；每次训练必须产生 manifest、metrics、checkpoint 和 model card。

### 1.2 Self-RAG 成功标准

- 对无需外部知识的问题能够跳过检索，降低无效检索率与查询成本。
- 对知识密集型问题能够触发检索，并过滤无关证据、拒绝无支持结论。
- 模型输出能够被稳定解析为回答文本、检索决策、相关性、支持度、效用与引用关系。
- Teacher 标注任务可断点续跑、可审计、可预算控制，并支持 Kimi/DeepSeek 切换。
- Student 模型可通过 SFT/LoRA 或 QLoRA 学习 Reflection Tokens，并通过统一接口接入现有 LLM Factory。
- 与传统 RAG 基线相比，Faithfulness、Citation Precision、检索决策 F1 等指标有可量化提升，同时延迟与成本保持在配置阈值内。

### 设计理念 (Design Philosophy)

> **核心定位：自学与教学同步 (Learning by Teaching)**
> 
> 本项目是我个人技术学习、丰富简历、备战面试的实战历程，同时也是一份同步教学的开源资源。我相信"**教是最好的学**"——在整理代码、撰写文档、录制视频的过程中，我自己对 RAG 的理解也在不断深化。希望这份"边学边教"的成果能够帮助到更多同样在求职路上的朋友。

本项目不仅是一个功能完备的智能问答框架，更是一个专为 **RAG 技术学习与面试求职** 设计的实战平台：

#### 1️⃣ 实战驱动学习 (Learn by Doing)
项目架构本身就是 RAG 面试题的"**活体答案**"。我们将经典面试考点直接融入代码设计，通过动手实践来巩固理论知识：
- 分层检索 (Hierarchical Retrieval)
- Hybrid Search (BM25 + Dense Embedding)
- Rerank 重排序机制
- Embedding 策略与优化
- RAG 性能评测 (Ragas/DeepEval)

#### 2️⃣ 开箱即用与深度扩展并重 (Plug-and-Play & Extensible)
- **开箱即用**：提供 MCP 标准接口，可直接对接 Copilot/Claude，拿到项目即可运行体验。
- **深度扩展**：保留完全模块化的内部结构，方便开发者替换组件、魔改算法，作为具备深度的个人简历项目。
- **扩展指引**：文档中会明确指出各模块的扩展方向与建议，帮助你在掌握基础后继续深入迭代。

#### 3️⃣ 配套教学资源 (Comprehensive Learning Materials)
我会提供**三位一体**的配套学习资源，帮助你快速吃透项目：

| 资源类型 | 内容说明 |
|---------|---------|
| 📄 **技术文档** | 架构设计文档、技术选型说明、模块详解 |
| 💻 **代码示范** | 带详细注释的源码、关键模块的 Step-by-step 实现 |
| 🎬 **视频讲解** | RAG 核心知识点回顾、代码细节精讲、环境配置教程 |

#### 4️⃣ 学习路线与面试指南 (Study Guide & Interview Prep)
针对每个模块，我会整理：
- **📚 知识点清单**：这块涉及哪些理论知识需要提前学习（如 BM25 原理、FAISS 索引类型、Cross-Encoder vs Bi-Encoder）
- **❓ 高频面试题**：结合项目代码讲解常见面试问题及参考答案
- **📝 简历撰写建议**：如何将本项目的亮点写进简历，突出技术深度

#### 5️⃣ 社区交流与持续迭代 (Community & Iteration)
- **经验分享**：我自己的面试经历、大家使用本项目面试的反馈，都会汇总沉淀
- **问题讨论**：一起探讨"如何将本项目写进简历"、"针对本项目的面试题怎么答"
- **持续更新**：从代码 → 八股知识 → 面试技巧，形成完整的求职知识库，帮助大家更好地拿到 Offer 🎯

---
