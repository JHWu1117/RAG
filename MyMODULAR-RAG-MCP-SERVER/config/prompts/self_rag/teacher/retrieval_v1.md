# Retrieval Decision — v1

判断回答用户问题是否需要检索给定企业知识库。仅依据任务类型与问题本身判断。

输出 JSON：`retrieve` 只能为 `retrieve` 或 `no_retrieve`，`confidence` 为 0~1，
`concise_reason` 为一句可审计短理由。不要输出思维链，不要输出 retry、abstain 或策略动作。
