# Evidence Relevance — v1

逐条判断候选 Chunk 是否与问题相关。不得补充候选文本之外的常识。

输出 JSON 数组 `evidence`；每项必须原样返回 `chunk_id`，`relevance` 只能为
`relevant` 或 `irrelevant`，并给出一句 `concise_reason`。另输出 0~1 的 `confidence`。
不要输出隐藏思维链、retry、abstain 或策略动作。
