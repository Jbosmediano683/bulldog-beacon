# Moderator: reasoning effort vs. quality and cost

12 labelled posts x 2 rounds per setting, gpt-6-luna, gateway cache bypassed.

Accuracy = the whole pipeline (code rules, then the model; a post the model can't review is held). Token columns = calls the model actually answered.

Severity = published posts graded on the scale info (no crime) / caution (property crime, suspicious behavior) / warning (crimes against people, a series) / urgent (violence in the last hour).

| Effort | Accuracy | Model-only accuracy | Severity | Avg input | Avg cached | Avg output | Avg reasoning | Avg latency | p90 latency | Avg cost / post |
|---|---|---|---|---|---|---|---|---|---|---|
| low | 100% | 100% | 100% | 1884 | 1718 | 89 | 0 | 3.1 s | 4.38 s | $0.000078 |

Rule layer (code, 0 tokens) would block before any model call: h_tag_injection

**Misses at low:** none

Severity misses at low: none

Handled without a model answer at low: h_tag_injection (rule)
