# Moderator: reasoning effort vs. quality and cost

30 labelled posts x 2 rounds per setting, gpt-6-luna, gateway cache bypassed.

| Effort | Accuracy | Avg input | Avg cached | Avg output | Avg reasoning | Avg latency | p90 latency | Avg cost / post |
|---|---|---|---|---|---|---|---|---|
| none | 90% | 1353 | 1114 | 101 | 0 | 2.26 s | 2.92 s | $0.000086 |
| low | 90% | 1353 | 1194 | 105 | 5 | 2.33 s | 3.55 s | $0.000081 |
| medium | 92% | 1353 | 1174 | 260 | 156 | 3.77 s | 5.29 s | $0.000160 |

Rule layer (code, 0 tokens) would block before any model call: obvious_injection

**Misses at none:** obvious_injection: run failed: error; pizza: expected blocked, got publish; presence_asian_photos: expected blocked, got revise

**Misses at low:** obvious_injection: run failed: error; pizza: expected blocked, got publish; presence_asian_photos: expected blocked, got revise

**Misses at medium:** obvious_injection: run failed: error; presence_asian_photos: expected blocked, got revise; presence_homeless: expected blocked, got revise
