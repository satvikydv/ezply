# PRD: Real-Time Job Posting Detector & Application Assistant

## 1. Overview

A system that monitors public ATS (Applicant Tracking System) job board APIs for a curated list of target companies, detects new postings within minutes of publication, filters them for relevance against the user's profile using embeddings, scores strong matches with an LLM, and pushes an instant notification with a pre-filled draft application — leaving final submission to a human click.

**Explicitly out of scope for v1:** fully autonomous submission without human review, scraping sites that require login or violate ToS (LinkedIn, Indeed job pages), CAPTCHA-solving.

## 2. Problem Statement

Job applications submitted within the first few hours of posting get meaningfully higher response rates than those submitted days later, because many companies stop reviewing once they have enough applicants. The user needs sub-15-minute detection-to-notification latency for relevant postings at target companies, without resorting to fragile or ToS-violating scraping.

## 3. Goals

- Detect new job postings from target companies within 5 minutes of publication.
- Filter out irrelevant postings automatically (role mismatch, wrong location, wrong seniority).
- Score relevant postings for fit and surface a ranked, explained recommendation.
- Deliver notifications via Telegram (or WhatsApp) within seconds of a postingpassing the relevance filter.
- Pre-fill application data where the ATS API/form structure allows it, but require human review/submit.
- Be maintainable by one person, running on cheap/free infra.

## 4. Non-Goals

- Circumventing bot detection, CAPTCHAs, or authenticated scraping of LinkedIn/Indeed.
- Fully autonomous submission with no human in the loop (for now, may introduce later).
- Supporting every ATS on day one (start with Greenhouse + Lever, expand later).

## 5. Users

Single user (the operator) for v1. Design data models with a `user_id` field so it can be extended to multiple users later, but no auth/multi-tenant UI needed now.

## 6. System Architecture

```
[Company Registry] --> [Ingestion Worker (Celery beat)] --> [Postgres: raw_jobs]
                                                             |
                                                    [Dedup + New Job Detector]
                                                             |
                                                [Embedding Relevance Filter (FAISS)]
                                                             |
                                            (score below threshold) -> discard
                                                             |
                                              [Claude API Scoring + Extraction]
                                                             |
                                                  [Postgres: scored_jobs]
                                                             |
                                        [Notification Worker] --> [Telegram Bot]
                                                             |
                                          [Optional: Prefill Draft Generator]
```

### 6.1 Tech Stack (matches operator's existing experience)

- **Backend**: FastAPI (Python 3.11+)
- **Task queue**: Celery + Celery Beat, broker = Redis
- **Cache/dedup store**: Redis (seen job IDs, TTL-based)
- **Database**: PostgreSQL (persistent job records, scores, application status)
- **Embeddings + vector search**: FAISS (or pgvector if simpler to operationalize alongside Postgres)
- **LLM**: Claude API (Sonnet model for scoring/extraction; cheap model or embeddings-only for first-pass filter)
- **Notifications**: Telegram Bot API (simplest, no business account approval needed) — WhatsApp via WATI as a v2 option
- **Deployment**: Railway or similar single-box PaaS; Celery beat + worker + FastAPI as separate services sharing one Redis + one Postgres

## 7. Functional Requirements

### 7.1 Company Registry

- A config table/file (`companies.yaml` or `companies` Postgres table) listing target companies with:
  - `name`, `ats_type` (`greenhouse` | `lever` | `ashby` | `smartrecruiters`), `ats_slug` (the board token used in the API URL), `active` (bool), `priority` (int, affects poll frequency).
- Must support easy addition/removal without code changes (edit table or YAML + reload).
- Seed with an initial list of ~50–100 companies the operator provides.

### 7.2 Ingestion Worker

- Celery Beat schedule polls each active company's ATS API every 5 minutes (configurable per priority tier — e.g., priority 1 companies every 3 min, others every 10 min).
- Adapters per ATS type, each normalizing to a common schema:
  ```json
  {
    "external_id": "string",
    "company": "string",
    "title": "string",
    "location": "string",
    "department": "string",
    "url": "string",
    "description_raw": "string (HTML or markdown as provided)",
    "posted_at": "ISO8601 or null if not provided by ATS",
    "fetched_at": "ISO8601"
  }
  ```
- ATS adapter reference endpoints:
  - Greenhouse: `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`
  - Lever: `GET https://api.lever.co/v0/postings/{slug}?mode=json`
  - Ashby: `GET https://api.ashbyhq.com/posting-api/job-board/{slug}`
  - SmartRecruiters: `GET https://api.smartrecruiters.com/v1/companies/{slug}/postings`
- On each poll: fetch, normalize, compute a stable hash of `external_id + title + location`, check Redis set `seen:{company}` for that hash. If not present: insert into Postgres `raw_jobs`, add hash to Redis with 90-day TTL, enqueue for relevance filtering. If present: skip.
- Handle API failures gracefully: log, retry with backoff (max 3 attempts), do not crash the beat schedule; alert operator via Telegram if a company's endpoint fails repeatedly (e.g., 5 consecutive failures).

### 7.3 Relevance Filter (Embedding Pass)

- Maintain an embedding of the operator's target-role profile (built once from resume + a short free-text description of desired roles — e.g., "AI/ML engineering, backend, agentic systems, RAG, LLM infra, India or remote").
- On new job insert: embed `title + description_raw` (truncate description to ~2000 chars before embedding), compute cosine similarity against the profile embedding via FAISS.
- Also apply hard filters before/alongside similarity: location allowlist/denylist (e.g., exclude on-site-only roles outside India unless remote), seniority keyword denylist (e.g., exclude "Staff", "Principal", "Director" if the operator is early-career — configurable).
- Jobs scoring below a configurable similarity threshold (default 0.75, tunable) are marked `status = filtered_out` and stored but not sent to LLM scoring or notification.
- Jobs above threshold proceed to LLM scoring.

### 7.4 LLM Scoring & Extraction (Claude API)

- For each job that passes the embedding filter, call Claude with the job description and the operator's resume summary. Request structured JSON output with:
  ```json
  {
    "fit_score": 0-100,
    "reasoning": "1-2 sentence explanation",
    "key_requirements": ["..."],
    "concerns": ["e.g. requires 5+ years experience, operator has 1"],
    "suggested_resume_emphasis": ["which of operator's projects/skills to highlight"]
  }
  ```
- Store result in `scored_jobs` table linked to `raw_jobs`.
- Jobs with `fit_score >= 70` (configurable) trigger notification. Jobs 40–69 stored for a daily digest, not instant-pinged. Below 40 stored only, no notification.

### 7.5 Notification

- Telegram bot sends a message immediately for any job with `fit_score >= 70`:
  - Company, title, location, fit score, one-line reasoning, direct application URL.
  - Inline buttons: "Mark Applied", "Dismiss", "Show Full Analysis".
- A daily digest (e.g., 9am IST) summarizing all jobs scored 40–69 from the last 24 hours, batched into one message or a short list.
- Notification worker consumes from a Redis/Celery queue populated by the scoring step; must not double-notify (idempotency key = job hash).

### 7.6 Application Draft Assist (v1.5, can ship after core loop works)

- For Greenhouse/Lever postings (which expose form field structures via their API in some cases, or at minimum consistent HTML form patterns), generate a prefilled draft: name, email, phone, LinkedIn, resume file attached, and a short "why this role" paragraph generated by Claude using the job description + operator's background.
- Output the draft as a structured object (not an auto-submit action). Options for delivery:
  - Simple: post the draft text + a reminder link in the Telegram message for manual copy-paste.
  - Advanced (later phase): Playwright script that opens the application URL, fills fields, and stops before the submit click, waiting for operator confirmation in a local browser session.
- Do not implement automatic form submission in v1 or v1.5.

### 7.7 Tracking

- `applications` table: `job_id`, `status` (`not_applied`, `applied`, `rejected`, `interview`, `offer`), `applied_at`, `notes`.
- Telegram inline button "Mark Applied" updates status.
- Simple `GET /jobs?status=&min_score=` API endpoint for a future dashboard (no UI required in v1; can be queried directly or via a minimal HTML table view).

## 8. Data Model (Postgres)

```sql
companies (id, name, ats_type, ats_slug, active, priority, created_at)
raw_jobs (id, company_id, external_id, title, location, department, url,
          description_raw, posted_at, fetched_at, job_hash UNIQUE)
scored_jobs (id, raw_job_id FK, embedding_score, fit_score, reasoning,
             key_requirements JSONB, concerns JSONB, status, scored_at)
applications (id, raw_job_id FK, status, applied_at, notes, updated_at)
```

## 9. Non-Functional Requirements

- **Latency**: posting-to-notification under 15 minutes for priority-1 companies (target: under 8 min given 3-5 min poll interval + processing time).
- **Cost control**: embedding filter must run before any Claude API call to avoid scoring irrelevant postings; cap Claude calls per day with an env-configurable limit as a safety net.
- **Idempotency**: no duplicate notifications for the same job even across worker restarts (Redis-backed dedup, not in-memory).
- **Observability**: structured logs for each pipeline stage; a lightweight `/health` endpoint reporting last successful poll time per company.
- **Config-driven**: similarity threshold, fit score thresholds, poll intervals, and company list must be changeable without a redeploy (env vars or DB-backed config table).

## 10. Milestones

1. **M1 — Ingestion core**: company registry, Greenhouse + Lever adapters, dedup via Redis, raw_jobs table populated on a schedule. Verify with 10 seed companies.
2. **M2 — Relevance filter**: embed profile once, embed + compare each new job, threshold filtering working end-to-end.
3. **M3 — LLM scoring**: Claude API integration producing structured fit scores; scored_jobs table populated.
4. **M4 — Notifications**: Telegram bot wired up, instant pings for high-fit jobs, daily digest for mid-fit jobs.
5. **M5 — Tracking**: applications table + inline button status updates.
6. **M6 (stretch)** — Draft assist: generated "why this role" text delivered alongside notification.
7. **M7 (stretch)** — Ashby + SmartRecruiters adapters; expand company list to 200+.

## 11. Open Questions for Operator (to resolve before/during build)

- Exact target company list and priority tiers.
- Location/seniority hard-filter rules (fully remote only? India-based only? open to relocation?).
- Preferred notification channel: Telegram vs WhatsApp (WATI) vs both.
- Whether resume text should be embedded once statically or re-derived from the latest resume version each time it changes.