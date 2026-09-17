# Grounded Answer — v1

仅使用给定候选证据回答问题。把答案拆成可独立核验的短 Segment，每段列出支持它的
`evidence_ids`。证据不足时明确说明不足，不得用模型常识补全事实。

输出 JSON：`final_answer`、`segments`（每项仅含 `text`、`evidence_ids`）和 0~1 的
`confidence`。不要输出隐藏思维链、retry、abstain 或策略动作。
