# Segment Utility — v1

逐段评价答案对问题的帮助程度。`utility` 必须为整数 1~5；每段返回
`segment_index` 与一句 `concise_reason`，整体返回 0~1 的 `confidence`。
评价只描述效用，不决定重试、重写、继续检索或拒答，也不输出隐藏思维链。
