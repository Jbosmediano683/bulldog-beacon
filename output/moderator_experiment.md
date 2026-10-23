# Moderator: reasoning effort vs. quality and cost

30 labelled posts x 2 rounds per setting, gpt-6-luna, gateway cache bypassed.

Accuracy = the whole pipeline (code rules, then the model; a post the model can't review is held). Token columns = calls the model actually answered.

Severity = published posts graded on the scale info (no crime) / caution (property crime, suspicious behavior) / warning (crimes against people, a series) / urgent (violence in the last hour).

| Effort | Accuracy | Model-only accuracy | Severity | Avg input | Avg cached | Avg output | Avg reasoning | Avg latency | p90 latency | Avg cost / post |
|---|---|---|---|---|---|---|---|---|---|---|
| none | 100% | 100% | 100% | 1886 | 1661 | 92 | 0 | 2.32 s | 3.48 s | $0.000085 |
| low | 100% | 100% | 100% | 1886 | 1718 | 93 | 0 | 3.87 s | 4.28 s | $0.000080 |
| medium | 100% | 100% | 96% | 1886 | 1690 | 234 | 132 | 4.42 s | 4.97 s | $0.000154 |

Rule layer (code, 0 tokens) would block before any model call: obvious_injection

**Misses at none:** none

Severity misses at none: none

Handled without a model answer at none: obvious_injection (rule)

**Misses at low:** none

Severity misses at low: none

Handled without a model answer at low: obvious_injection (rule)

**Misses at medium:** none

Severity misses at medium: road_closed: got caution

Handled without a model answer at medium: obvious_injection (rule)
