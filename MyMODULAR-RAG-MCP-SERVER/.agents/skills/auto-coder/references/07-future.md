## 7. 可扩展性与未来展望

### 7.1 云端部署与后端架构学习
虽然当前阶段我们主要采用“本地运行”模式，但本项目的架构设计完全支持向云端迁移。这也是一个极佳的学习后端工程化的切入点。
- **Server 容器化**：计划编写 Dockerfile，将 MCP Server 打包为容器。这让我们有机会深入理解 Python 环境隔离、依赖管理以及 Docker 的最佳实践。
- **云端接入**：未来可以将 Server 部署至 Azure Container Apps 或 AWS Lambda。
    - **挑战与学习点**：处理网络延时、配置 API Gateway、增加 AuthN/AuthZ 鉴权机制（保护私有数据不被公开访问）。
- **多租户与并发**：从单用户本地服务转变为支持团队共享的服务。
    - **学习点**：在 Chroma 中实现 Namespace 隔离、处理并发请求锁、优化 embedding 缓存策略。

### 7.2 业务深耕：从"通用"到"垂直" (Vertical Domain Adaptation)
RAG 系统的上限取决于其对特定业务数据的理解深度。未来的核心扩展方向是将通用的技术框架与具体的业务场景深度结合。在将本项目应用到实际生产环境时，识别并解决以下“最后一公里”的难题，将是提升系统价值的关键：

- **多源异构数据的复杂适配**：
    - 现实业务中不仅有 PDF，还大量存在 PPTX, DOCX, XLSX 甚至 HTML 数据。
    - **挑战**：如何处理不同格式的特有语义？例如 PPT 中的演讲者备注往往比正文更关键，Excel 中的公式逻辑与跨行关联如何保留？目前的通用处理方式容易丢失这些“隐性知识”，未来需要针对每种格式探索更深度的解析能力。

- **复杂结构化数据的精确理解**：
    - 简单的文本切分（Chunking）在处理表格、层级列表时往往会破坏语义。
    - **挑战**：
        - **表格理解**：如何处理跨页长表格、合并单元格以及含有复杂表头的财务报表？如果切分不当，检索时只能找到数字却不知道对应的列名（指标含义）。
        - **上下文断裂**：当一个完整的逻辑段落（如合同条款）被切分到两个 chunk 时，如何保证检索其中一段时能感知到整体的上下文约束？

- **业务逻辑驱动的生成控制**：
    - 仅仅根据“相似度”召回文档在企业级场景中往往不够。
    - **挑战**：
        - **时效性与版本管理**：当知识库中同时存在“2023版”和“2024版”规章时，如何确保系统不会混淆历史数据与最新标准？
        - **权限与受众适配**：面对内部员工与外部客户，如何控制生成答案的详略程度与敏感信息披露？
        - **拒答机制**：当召回内容的置信度不足时，如何让系统诚实地回答“不知道”而不是基于相关性较低的片段强行拼凑答案（幻觉问题）？

### 7.3 从 Self-RAG 迈向 Agentic RAG

完成本规格后，系统已经能够在单次请求内部按需检索、批判证据并有限重试。下一阶段不应继续无限扩大内部循环，而是把经过验证的原子能力暴露给上层 Agent：

- **原子化工具**：`keyword_search`、`semantic_search`、`preview_document`、`verify_claim`、`compare_sources`；
- **显式计划**：由 Agent 为跨文档问题生成可观察的子问题图，而不是让模型在隐藏上下文里无限反思；
- **工具级预算**：每个 Agent Run 设置查询次数、Token、延迟和费用预算；
- **跨步骤证据账本**：所有子问题结论必须绑定 source/chunk/version，最终答案只引用已验证证据；
- **Self-RAG 作为工具内核**：每个知识检索子任务仍由本项目的 Self-RAG Policy 保证相关性、支持度和拒答边界；
- **独立评估**：Agentic 任务用 task success、计划效率和跨步骤引用一致性评估，不与单轮 Self-RAG 指标混为一谈。

### 7.4 持续蒸馏与数据治理

模型上线后可构建周期性离线改进循环，但不做未经审核的在线自学习：

1. 收集低置信度、fallback、用户纠错和评估失败 Trace；
2. 完成脱敏、授权、采样和人工优先级审核；
3. 使用当前 Teacher 重新标注，并与现役 Student 输出做差异分析；
4. 生成新 Dataset 版本，在冻结回归集上训练与评估；
5. 只有通过发布门禁的模型才能进入 Model Registry 的 deployable 状态；
6. 保留数据删除、模型回滚、Prompt 回滚和 Provider 更换能力。

未来可研究 Active Learning、Weak-to-Strong、RLAIF/GRPO 等方法，但必须以可审计标签、离线对照实验和数据许可为前提，不能仅因为 Teacher 更强就默认其所有标签正确。

### 7.5 关键参考资料

- Akari Asai et al., [Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection](https://arxiv.org/abs/2310.11511)
- AkariAsai, [Self-RAG Official Implementation](https://github.com/AkariAsai/self-rag)
- Moonshot AI, [Kimi API Overview](https://www.kimi.ai/help/kimi-api/api-overview)
- DeepSeek, [DeepSeek API Documentation](https://api-docs.deepseek.com/)
- DeepSeek, [DeepSeek V4 Model Card](https://fe-static.deepseek.com/chat/transparency/deepseek-V4-model-card-EN.pdf)


