# Self-RAG Critic 数据形式与构造 Pipeline

## 当前模型与语料

- Generator：本地 `Qwen/Qwen3-4B`，Transformers + bitsandbytes NF4 4-bit；模型目录
  `artifacts/models/Qwen3-4B`。
- Teacher：`qwen3.8-27b` 为首选；账户重置后已通过实际生成探测，但批量标注触发
  `insufficient_quota`，因此回退到工作空间实际暴露的 `kimi-k2.5`。Provider 采用 OpenAI
  兼容接口；严格 Schema 不受支持时会把完整 Schema 注入 Prompt，并始终在本地校验。
- Embedding：原计划 `text-embedding-v4`，当前工作空间无权限，改用已探针通过的
  `qwen3.7-text-embedding`（1024 维）。
- Vision：`qwen3.5-ocr`。批量年报文本摄取时不做图片 caption，以控制费用；运行配置仍保留该模型。
- Reranker：本地 `BAAI/bge-reranker-v2-m3` cross-encoder，目录
  `artifacts/models/bge-reranker-v2-m3`。
- 中文语料：腾讯 2022–2025 年报及业绩公告，共 9 份 PDF。

## 一条 Critic 记录

训练集采用 JSONL，每行是一个 `TrainingSample`。下面省略了长 Chunk 文本：

```json
{
  "sample_id": "sha256:...",
  "schema_version": 1,
  "dataset_version": "selfrag-v0.1.0",
  "task_type": "grounded_generation",
  "instruction": "腾讯2024年的研发开支是多少？",
  "history": [],
  "source_group_id": "doc_sha256:...",
  "retrieval_snapshot": {
    "index_version": "chroma:selfrag_tencent@v1",
    "query": "腾讯2024年的研发开支是多少？",
    "candidates": [
      {
        "chunk_id": "chunk_001",
        "text": "二零二四年，本集团研发开支为人民币706亿元。",
        "source": "tencent_ar2024_cn.pdf",
        "dense_score": 0.82,
        "sparse_score": 7.1,
        "fusion_score": 0.031,
        "rerank_score": 0.91,
        "source_group_id": "doc_sha256:...",
        "collection": "selfrag_tencent",
        "role": "positive"
      }
    ]
  },
  "labels": {
    "retrieve": "retrieve",
    "evidence": [
      {
        "chunk_id": "chunk_001",
        "relevance": "relevant",
        "concise_reason": "该段直接给出2024年研发开支"
      }
    ],
    "segments": [
      {
        "text": "腾讯2024年研发开支为人民币706亿元。",
        "evidence_ids": ["chunk_001"],
        "support": "fully_supported",
        "utility": 5,
        "support_reason": "金额和年份均与证据一致",
        "utility_reason": "直接且完整回答问题"
      }
    ],
    "final_answer": "腾讯2024年研发开支为人民币706亿元。",
    "rewritten_query": null
  },
  "teacher": {
    "provider": "openai_compatible",
    "model": "qwen3.8-27b+kimi-k2.5",
    "prompt_version": "reflection-labels-v1",
    "prompt_hash": "sha256:...",
    "request_id": "label:...",
    "temperature": 0.0,
    "label_confidence": 0.95,
    "raw_response_hash": "sha256:..."
  },
  "quality": {
    "schema_valid": true,
    "rule_checks": ["evidence_ids_exist", "known_label_enums"],
    "agreement": "single_teacher",
    "review_status": "accepted",
    "quarantine_reason": null
  },
  "split": "train",
  "created_at": "2026-09-08T00:00:00+00:00"
}
```

关键点：`retrieval_snapshot` 保存可复现索引版本和 dense/sparse/fusion/rerank 全部分数；
所有 `evidence_ids` 必须存在于该快照；Teacher 原始正文不写入训练集，只保存哈希。

## 构造流程

```text
9 份中文 PDF（只读快照、授权信息、SHA-256）
  → 文本切块 + qwen3.7 embedding + BM25 建索引
  → 六类合成 Query（精确配额、来源绑定、去重）
  → Hybrid Retrieval → 本地 BGE Cross-Encoder
  → 正证据 / 难负例 / 冲突证据候选快照
  → Teacher 五次独立结构化判定
       Retrieval → Relevance → Grounded Answer → Support → Utility
  → JSON Schema、枚举、引用与来源检查
  → accepted JSONL / quarantine JSONL / manifest
  → Critic Dataset 在训练时投影为对应 Reflection Token 目标
```

五类判断拆成独立 Prompt，避免一次错误同时污染所有标签。Teacher 只给出标签、置信度和
一句短理由，不保存隐藏思维链。

当前真实预览位于 `data/training/preview/`（运行产物，不提交 Git）：30 条候选中 25 条进入
`critic.jsonl`，5 条因跨标签业务规则冲突进入 `quarantine.jsonl`。25 条 accepted 的
`sample_id` 全部唯一，证据引用均可解析到同条记录的检索快照，且序列化结果不含 retry 或
abstain 字段。该预览只验证 K1-K6 链路；低置信度过滤、完整质量门禁与正式切分由后续 K7-K9
任务实现。

## Reflection Token 边界

Critic 只训练 12 个判断 Token：

```text
<RET_YES> <RET_NO>
<REL_YES> <REL_NO>
<SUP_FULL> <SUP_PARTIAL> <SUP_NONE>
<UTIL_1> <UTIL_2> <UTIL_3> <UTIL_4> <UTIL_5>
```

不存在 RETRY 或 ABSTAIN Token。Query 是否重写、是否开始下一轮检索、以及最终是否拒答，
均由外部 `SelfRAGPolicy` 根据上述判断、阈值和预算作出。
