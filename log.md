| Date | What | Hours | Who | When |
|---|---|---|---|---|
| 11/4/2025 | Worked on initial designs | 1 | Myles & Isaac | |
| 11/6/2025 | Worked on initial designs | 1.5 | Myles & Isaac | |
| 11/18/2025| Worked on visualization code | 3 | Myles | |
| 11/29/2025| Created Docker/Postgres database connection | 7 | Myles | |
| 12/1/2025 | Got Myles' work running on my machine, added `project_instructions.txt` and `requirements.txt` | 3 | Isaac | 9AM - 12PM |
| 12/1/2025 | Added users, annotations, and making things prettier | 5 | Isaac | 7PM - 12AM |
| 12/2/2025 | Added rate limiting, input validation, Redis caching | 7 | Isaac | 8AM - 3PM |
| 12/4/2025 | Added search/filter/pagination, export/download, permissions/sharing, monitoring, observability | 3 | Isaac | 8AM - 11AM |
| | **Myles Total** | **TBD** | |
| | **Isaac Total** | **20.5** | |


<!--
Day 1 (6 hours + 3 hours = 9 hours)
Hour 1-2: Rate Limiting & Request Throttling
Add slowapi library for per-user rate limits
Limit viz generation to 5 per minute per user (authenticated) or 2 per minute (anonymous)
Add rate limit headers to responses
Why: Production-grade, prevents GPU abuse, shows you understand scalability
Hour 3-4: Input Validation & Sanitization
Add Pydantic models for request payloads with constraints
Validate model_name against HuggingFace registry (don't just trust user input)
Sanitize text input (max/min lengths, character whitelist for safety)
Add request logging middleware that tracks user, endpoint, payload size
Why: Security hardening, shows defensive programming
Hour 5-6: Redis Caching Layer (Part 1)
Set up Redis in docker-compose.yml
Implement cache_decorator for model inference results (key = model_name + hash(input_text))
Cache hit/miss metrics logged
TTL = 1 hour for cached visualizations
Why: Major performance boost, scalability story
Hour 7-9 (Evening): Search & Filter Visualizations
Add query parameters to /visualizations endpoint: ?model=gpt2&date_from=2025-12-01&search=cat
Implement database filtering with SQLModel .where() clauses
Add full-text search on input_text (PostgreSQL ILIKE)
Pagination: ?page=1&limit=20
Why: UX improvement, database query optimization skills
Day 2 (4 hours + 5 hours = 9 hours)
Hour 1-2: Export & Download Features
Add /viz/{id}/export endpoint that returns JSON of viz metadata + annotations
CSV export of all user's visualizations (model_name, input_text, date, annotation_count)
Zip download option (HTML + JSON + CSV bundled)
Why: Data portability, API design, file handling
Hour 3-4: Annotation Permissions & Sharing
Add is_public flag to Visualization model
Allow users to share private visualizations via token-based link (e.g., /viz/6?share_token=abc123)
Implement permission checks: only owner or share_token holder can see private viz
Audit log: track who accessed what when
Why: Collaboration feature, permission model complexity
Hour 5-6: Model Comparison View
New endpoint GET /compare?model1=gpt2&model2=distilgpt2&text=hello
Side-by-side attention visualization for two models
Highlight differences (e.g., which heads activate differently)
Store comparison results in new Comparison table
Why: Advanced feature, shows you can extend BertViz, complex state management
Hour 7-9 (Evening): Monitoring & Observability
Add /metrics endpoint (Prometheus-style) with:
viz_generation_time_seconds (histogram)
cache_hit_rate (gauge)
active_users_count (gauge)
model_load_failures_total (counter)
Structured JSON logging (replace print statements with logger)
Dashboard skeleton (optional): simple HTML page showing live metrics
Why: Production ops mindset, monitoring best practices
Distribution Summary
Task	Hours	Day	Why It Matters
Rate Limiting	2	1	Scalability + security
Input Validation	2	1	Security hardening
Redis Caching	2	1	Performance + architecture
Search/Filter/Pagination	3	1	UX + DB optimization
Export/Download	2	2	Data portability
Permissions & Sharing	2	2	Collaboration
Model Comparison	2	2	Advanced feature
Monitoring & Observability	3	2	Production readiness
Total: 18 hours (fits your quota exactly)

Implementation Order I Recommend
Start with Rate Limiting + Input Validation (Day 1, hours 1-4) — these are quick wins, protect your GPU
Then Redis Caching (Day 1, hours 5-6) — shows architectural thinking
Search/Filter (Day 1, evening) — polishes existing feature
Export/Permissions (Day 2, morning) — extends data model
Model Comparison (Day 2, midday) — showcases advanced skills
Monitoring (Day 2, evening) — caps it off professionally
-->