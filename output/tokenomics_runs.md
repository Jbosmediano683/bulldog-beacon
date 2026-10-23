# Measured runs per agent (gpt-6-luna, normal caching)

| Agent | Runs | Model calls | Tool calls | Input | Cached | Output | Cached share | p50 latency | Avg cost |
|---|---|---|---|---|---|---|---|---|---|
| moderator | 14 | 1 | 0 | 1893 | 1677 | 87 | 89% | 1.65 s | $0.000082 |
| corroborator | 1 | 1 | 0 | 800 | 0 | 118 | 0% | 1.89 s | $0.000139 |
| concierge | 8 | 2.38 | 1.38 | 6418 | 5621 | 179 | 88% | 6.58 s | $0.000226 |
| responder | 3 | 1 | 0 | 776 | 0 | 187 | 0% | 2.33 s | $0.000171 |
