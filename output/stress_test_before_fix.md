# Stress test (virtual users, real gpt-6-luna)

2246 requests, 0 server errors (5xx or network), 200 model calls ({'ok': 200}), 603,879 tokens, $0.02833.

| Phase | Endpoint | Requests | 5xx/errors | 429 | p50 | p95 | max |
|---|---|---|---|---|---|---|---|
| A browse | /api/community | 414 | 0 | 0 | 248 ms | 334 ms | 7263 ms |
| A browse | /api/events | 393 | 0 | 0 | 207 ms | 7796 ms | 8454 ms |
| A browse | /api/incidents | 423 | 0 | 0 | 274 ms | 395 ms | 7121 ms |
| A browse | /api/places | 407 | 0 | 0 | 235 ms | 308 ms | 479 ms |
| A browse | /api/resources | 363 | 0 | 0 | 234 ms | 322 ms | 7242 ms |
| B AI wave of 15 | /api/chat | 15 | 0 | 0 | 6426 ms | 9264 ms | 13533 ms |
| B AI wave of 15 | /api/comments | 15 | 0 | 0 | 1561 ms | 2952 ms | 4187 ms |
| B AI wave of 15 | /api/community | 15 | 0 | 0 | 54 ms | 96 ms | 99 ms |
| B AI wave of 15 | /api/posts | 15 | 0 | 0 | 1746 ms | 2405 ms | 2684 ms |
| B AI wave of 30 | /api/chat | 30 | 0 | 0 | 9255 ms | 15027 ms | 26446 ms |
| B AI wave of 30 | /api/comments | 30 | 0 | 0 | 2002 ms | 7579 ms | 27496 ms |
| B AI wave of 30 | /api/community | 30 | 0 | 0 | 118 ms | 375 ms | 408 ms |
| B AI wave of 30 | /api/posts | 30 | 0 | 0 | 2476 ms | 8988 ms | 28910 ms |
| B AI wave of 5 | /api/chat | 5 | 0 | 0 | 16051 ms | 20876 ms | 20876 ms |
| B AI wave of 5 | /api/comments | 5 | 0 | 0 | 1760 ms | 4621 ms | 4621 ms |
| B AI wave of 5 | /api/community | 5 | 0 | 0 | 25 ms | 52 ms | 52 ms |
| B AI wave of 5 | /api/posts | 5 | 0 | 0 | 1872 ms | 3165 ms | 3165 ms |
| C SOS during AI load | /api/sos | 26 | 0 | 0 | 25 ms | 92 ms | 236 ms |
| D abuse: 20 chats from one NetID | /api/chat | 20 | 0 | 0 | 4524 ms | 8293 ms | 13885 ms |

AI notes: {"chats": 50, "chat_fallbacks": 0, "chat_with_action": 39, "post_status": {"published": 37, "revised": 13}, "comment_status": {"published": 50}}
Abuse: {"sent": 20, "answered_by_ai": 20, "refused_by_rate_limit": 0}
Phase timings: {"A": {"users": 50, "seconds": 17.4}, "B5": {"users": 5, "seconds": 23.9}, "B15": {"users": 15, "seconds": 14.0}, "B30": {"users": 30, "seconds": 41.9}}
Server error lines: none
