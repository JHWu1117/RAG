# Segment Support — v1

逐段判断答案是否被其引用证据支持。`support` 只能为 `fully_supported`、
`partially_supported`、`not_supported`。每段返回 `segment_index` 与一句
`concise_reason`，整体返回 0~1 的 `confidence`。不要输出思维链或控制策略。
