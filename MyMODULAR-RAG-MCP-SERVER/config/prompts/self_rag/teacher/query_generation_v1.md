# Self-RAG Synthetic Query Generation v1

You generate one auditable training query from the supplied source excerpt.
Return one JSON object only. Do not return markdown, analysis, hidden reasoning,
or facts not present in the excerpt.

Inputs:

- `query_kind`: one of `factual`, `multi_hop`, `comparison`, `summary`,
  `no_retrieval`, `unanswerable`
- `language`: requested output language
- `source_group_id`: immutable source binding
- `source_text`: authorized, privacy-screened source excerpt

Output schema:

```json
{
  "instruction": "the user-facing query",
  "reference_answer": "answer grounded only in source_text, or null"
}
```

Rules:

1. `factual`, `multi_hop`, `comparison`, and `summary` must require the source.
2. `no_retrieval` must be answerable without private or document knowledge.
3. `unanswerable` must look relevant to the source but have no supported answer;
   set `reference_answer` to `null`.
4. Do not emit source IDs, labels, control tokens, contact details, or credentials.
5. Keep the query distinct from examples already supplied by the caller.
