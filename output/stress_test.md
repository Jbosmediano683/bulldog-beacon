# Stress test (virtual users, real gpt-6-luna)

2230 requests, 0 server errors (5xx or network), 192 model calls ({'ok': 192}), 557,045 tokens, $0.02694.

| Phase | Endpoint | Requests | 5xx/errors | 429 | p50 | p95 | max |
|---|---|---|---|---|---|---|---|
| A browse | /api/community | 414 | 0 | 0 | 227 ms | 287 ms | 418 ms |
| A browse | /api/events | 393 | 0 | 0 | 189 ms | 222 ms | 285 ms |
| A browse | /api/incidents | 423 | 0 | 0 | 246 ms | 336 ms | 438 ms |
| A browse | /api/places | 407 | 0 | 0 | 217 ms | 271 ms | 364 ms |
| A browse | /api/resources | 363 | 0 | 0 | 216 ms | 278 ms | 402 ms |
| B AI wave of 15 | /api/chat | 15 | 0 | 0 | 5806 ms | 8413 ms | 10878 ms |
| B AI wave of 15 | /api/comments | 15 | 0 | 0 | 1430 ms | 1778 ms | 2706 ms |
| B AI wave of 15 | /api/community | 15 | 0 | 0 | 22 ms | 38 ms | 40 ms |
| B AI wave of 15 | /api/posts | 15 | 0 | 0 | 2290 ms | 4615 ms | 13996 ms |
| B AI wave of 30 | /api/chat | 30 | 0 | 0 | 7780 ms | 10758 ms | 10803 ms |
| B AI wave of 30 | /api/comments | 30 | 0 | 0 | 1738 ms | 3257 ms | 3401 ms |
| B AI wave of 30 | /api/community | 30 | 0 | 0 | 63 ms | 195 ms | 203 ms |
| B AI wave of 30 | /api/posts | 30 | 0 | 0 | 2093 ms | 4485 ms | 5161 ms |
| B AI wave of 5 | /api/chat | 5 | 0 | 0 | 10653 ms | 10903 ms | 10903 ms |
| B AI wave of 5 | /api/comments | 5 | 0 | 0 | 1382 ms | 1702 ms | 1702 ms |
| B AI wave of 5 | /api/community | 5 | 0 | 0 | 25 ms | 27 ms | 27 ms |
| B AI wave of 5 | /api/posts | 5 | 0 | 0 | 1656 ms | 13552 ms | 13552 ms |
| C SOS during AI load | /api/sos | 10 | 0 | 0 | 36 ms | 233 ms | 233 ms |
| D abuse: 20 chats from one NetID | /api/chat | 20 | 0 | 0 | 271 ms | 4628 ms | 6178 ms |

Chat time by model round trips: {"2": {"n": 10, "p50_ms": 4351}, "3": {"n": 39, "p50_ms": 8194}, "4": {"n": 1, "p50_ms": 10661}}
AI notes: {"chats": 50, "chat_fallbacks": 0, "chat_with_action": 38, "post_status": {"published": 34, "revised": 16}, "comment_status": {"published": 50}}
Abuse: {"sent": 20, "answered_by_ai": 8, "refused_by_rate_limit": 12}
Phase timings: {"A": {"users": 50, "seconds": 9.1}, "B5": {"users": 5, "seconds": 24.4}, "B15": {"users": 15, "seconds": 20.1}, "B30": {"users": 30, "seconds": 15.4}}
Server error lines: none
