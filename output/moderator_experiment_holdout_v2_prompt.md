# Moderator: reasoning effort vs. quality and cost

12 labelled posts x 2 rounds per setting, gpt-6-luna, gateway cache bypassed.

Accuracy = the whole pipeline (code rules, then the model; a post the model can't review is held). Token columns = calls the model actually answered.

| Effort | Accuracy | Model-only accuracy | Avg input | Avg cached | Avg output | Avg reasoning | Avg latency | p90 latency | Avg cost / post |
|---|---|---|---|---|---|---|---|---|---|
| low | 100% | 100% | 1512 | 1348 | 101 | 0 | 2.16 s | 2.46 s | $0.000080 |

Rule layer (code, 0 tokens) would block before any model call: h_tag_injection

**Misses at low:** none

Handled without a model answer at low: h_tag_injection (rule)
