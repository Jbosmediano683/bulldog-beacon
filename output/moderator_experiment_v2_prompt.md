# Moderator: reasoning effort vs. quality and cost

30 labelled posts x 2 rounds per setting, gpt-6-luna, gateway cache bypassed.

Accuracy = the whole pipeline (code rules, then the model; a post the model can't review is held). Token columns = calls the model actually answered.

| Effort | Accuracy | Model-only accuracy | Avg input | Avg cached | Avg output | Avg reasoning | Avg latency | p90 latency | Avg cost / post |
|---|---|---|---|---|---|---|---|---|---|
| none | 100% | 100% | 1514 | 1326 | 105 | 0 | 3.17 s | 5.6 s | $0.000085 |
| low | 100% | 100% | 1514 | 1304 | 105 | 0 | 2.45 s | 2.88 s | $0.000087 |
| medium | 100% | 100% | 1514 | 1304 | 249 | 143 | 3.8 s | 5.07 s | $0.000158 |

Rule layer (code, 0 tokens) would block before any model call: obvious_injection

**Misses at none:** none

Handled without a model answer at none: obvious_injection (rule)

**Misses at low:** none

Handled without a model answer at low: obvious_injection (rule)

**Misses at medium:** none

Handled without a model answer at medium: obvious_injection (rule)
