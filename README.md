# CV Maker

## Accounts (sign up / log in)

Every part of the app — job search, CV storage, gap review, Skills to
Learn — requires an account, and each account only ever sees its own
data. Sign up with an email + password (min 8 characters) on
`frontend/signup.html`; the backend hashes passwords with bcrypt (never
stored in plaintext) and returns a JWT session token, which the frontend
keeps in `localStorage` and sends as `Authorization: Bearer <token>` on
every API call (see `frontend/auth.js`). Tokens last 30 days. Visiting
any page without a valid session redirects to `login.html`; a 401 from
the API (expired/invalid token) does the same.

Set `JWT_SECRET` (a long random string, e.g. `openssl rand -hex 32`) in
your `.env` — it signs the session tokens, so anyone who knows it can
forge logins. `docker-compose.yml` fails to start without it; running
the backend directly falls back to an insecure hardcoded dev value,
fine for local testing only.

### API

- `POST /api/auth/signup` — JSON body `{email, password}`. 409 if the
  email's taken, 422 if the email's invalid or the password's under 8
  characters. Returns `{access_token, token_type, email}`.
- `POST /api/auth/login` — JSON body `{email, password}`. 401 on a wrong
  email/password. Same response shape as signup.
- `GET /api/auth/me` — returns `{id, email}` for the bearer token's
  owner. 401 if the token's missing/expired/invalid.
- `POST /api/auth/forgot-password` — JSON body `{email}`. There's no
  email sending set up for this app, so this can't send a reset link —
  passwords are one-way bcrypt hashes anyway, so the *original* password
  can never be recovered by anyone, including the server. Instead this
  generates a new random 12-character password, saves it, and returns it
  directly: `{email, temporary_password}`. 404 if no account has that
  email. Note this means anyone who knows an account's email can reset
  it — an accepted trade-off for a small self-hosted app with no email
  infrastructure, not a general-purpose flow. `frontend/forgot-password.html`
  shows the new password once and links to the login page.
- `POST /api/auth/change-password` — requires auth. JSON body
  `{current_password, new_password}` (new password min 8 characters).
  401 if `current_password` is wrong, 422 if the new one's too short.
  Used from Settings to replace a temporary password with a real one.

Every other endpoint below now requires the same `Authorization: Bearer
<token>` header, and CVs, gaps, and learning items are all scoped to the
requesting user — fetching, editing, or deleting another user's data
404s as if it doesn't exist, rather than 403ing (so an id doesn't leak
whether it belongs to someone else).

## Job search (JobSpy)

The `backend/` folder exposes a small FastAPI service that wraps
[JobSpy](https://github.com/speedyapply/JobSpy) to scrape job postings from
Indeed, LinkedIn, ZipRecruiter, Glassdoor, and Google.

### Run the backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### API

`GET /api/jobs`

| Param | Description |
| --- | --- |
| `search_term` | Job title or keywords (required) |
| `location` | City, state, or "remote" |
| `site_name` | Repeatable: `indeed`, `linkedin`, `zip_recruiter`, `glassdoor`, `google` |
| `results_wanted` | Max results per site (default 20) |
| `hours_old` | Only jobs posted within this many hours |
| `is_remote` | Filter to remote jobs |
| `job_type` | One of `fulltime`, `parttime`, `contract`, `temporary`, `internship`, `perdiem`, `nights`, `other`, `summer`, `volunteer` |
| `distance` | Search radius in miles from `location` |
| `easy_apply` | Only jobs with an easy-apply option (LinkedIn/Indeed) |
| `country_indeed` | Country for Indeed/Glassdoor search (default `USA`) |
| `include_keywords` | Comma-separated; keep only jobs matching at least one, in title/description/company |
| `exclude_keywords` | Comma-separated; drop jobs matching any one, in title/description/company |

`include_keywords`/`exclude_keywords` are applied here, after scraping —
not sent to the job board itself. Job boards don't support this
consistently (some accept boolean search syntax in `search_term`, most
don't), so filtering our side works the same regardless of site.
`description` isn't always populated for every source (e.g. LinkedIn only
includes it when its full-description fetch is on), so matching falls
back to title + company when it's missing.

Note: JobSpy does not expose applicant counts — job boards generally don't
publish that in their public listings, so it isn't something this API can
filter or return.

### Fill the form from a LinkedIn search URL

Instead of retyping filters, paste a LinkedIn job search URL (e.g. from
`linkedin.com/jobs/search/?keywords=...`) into the "Fill from URL" box at
the top of the page. The frontend parses `keywords`, `location`,
`distance`, `f_JT` (job type), `f_WT` (remote), `f_AL` (easy apply), and
`f_TPR` (posted-within window) straight out of the URL's query string and
populates the search form — the actual search still runs through the same
JobSpy-backed `/api/jobs` endpoint above. This only reads LinkedIn's
classic keyword-search URL format; it doesn't call LinkedIn or use its
newer AI search.

Example:

```
GET /api/jobs?search_term=software+engineer&location=Remote&site_name=indeed&site_name=linkedin
```

### Frontend

`frontend/index.html` is a minimal static page that calls the API and lists
results. Open it directly in a browser (with the backend running on
`localhost:8000`), or serve it with any static file server.

## CV import (JSON)

Earlier versions tried a local regex/PDF-layout parser (unreliable on
real-world resumes), a blank manual-entry form (tedious), and a flat CSV
format — all replaced. The data model now matches a "source of truth"
JSON schema (personal info, work/education/training entries each with
per-bullet skills and metrics, languages, and free-form tool categories)
that `cv_models.py`'s `CVProfile` mirrors field-for-field, including
`extra="forbid"` so a typo'd key from a hand-edited or LLM-produced file
is caught as a clear validation error rather than silently dropped. The
flow:

1. Download the JSON template from `frontend/cv.html` (or `GET
   /api/cv/template.json` directly).
2. Give the template + your resume to whatever AI assistant you like
   (ChatGPT, Claude, etc. — outside this app) and ask it to fill the
   template in, keeping the same keys/nesting. The page shows a
   ready-to-copy example prompt.
3. Upload the completed JSON. The backend validates it against
   `CVProfile` (Pydantic) — no AI call, no layout-guessing on our side —
   and stores the result in SQLite.

Every field is still editable on the page after import (fix anything,
add/remove work/education/training entries, add/remove bullets within
an entry, add/remove tool categories) before you save. A validation
failure names the exact field and problem (e.g.
`work_experience.0.role: Field required`) rather than a generic error.

### API

- `GET /api/cv/template.json` — downloads the blank template.
- `POST /api/cv/import-json` — multipart form, field `file` (JSON, max
  2MB). Returns `{id, filename, uploaded_at, updated_at, profile}`. 422
  with a field-level message on a schema mismatch.
- `GET /api/cv/{id}/export.json` — re-export a stored profile back to
  the same JSON shape (round-trips through an LLM again if you want
  another editing pass).
- `PUT /api/cv/{id}` — JSON body `{filename?, profile}`, overwrites a
  stored entry (saves edits made on the page). 404 if the id doesn't
  exist.
- `GET /api/cv/{id}` — refetch a stored profile.
- `GET /api/cv?limit=20` — list recent entries (id/filename/uploaded_at/
  updated_at only).

### Storage

SQLite, path from `CV_DB_PATH` (default `./cv_profiles.db`; the Docker setup
points it at `/data/cv.db` on a named volume, `cv_data`, so uploads survive
container rebuilds).

## AI job scoring

On the Job Search page, once you have at least one saved CV, every job
card gets a "Check match?" button: click it on a job you're actually
interested in and only that one job gets scored — a 0-100 fit score, a
short reasoning, and (when relevant) a list of concrete missing
requirements, grounded only in what's actually in the CV profile, not
assumptions. Nothing is scored automatically; scoring is opt-in per job
so you're not spending tokens on results you'd skip anyway.

Unlike CV extraction, this one genuinely needs an LLM (job-fit judgment
isn't something regex heuristics can do). It uses whichever provider is
configured on the [Settings](#settings-ai-provider) page for the logged-in
user — falling back to this deployment's own `ANTHROPIC_API_KEY` (copy
`.env.example` to `.env`) if the user hasn't set one. Nothing else in the
app needs an LLM key; job search and CV upload/edit work fine without it.

- Anthropic: `claude-opus-5`, structured output (`CVProfile`-shaped
  request → a `JobScore` per job) via `client.messages.parse`. DeepSeek:
  JSON mode with the schema in the prompt, validated and retried
  server-side.
- The API endpoint accepts up to 25 jobs in one request (so a "score all
  visible results" flow is possible later), but the frontend only ever
  sends one job per click, matching the per-job button.
- A job with no `description` (JobSpy doesn't always populate it — see
  above) is judged on title/company/location alone, and the model is
  told to flag when that isn't enough to be confident.

### API

- `POST /api/jobs/score` — JSON body `{cv_id, jobs: [{id, title, company?,
  location?, description?, job_type?}, ...]}` (max 25 jobs). Returns
  `{scores: [{id, score, reasoning, missing_requirements}, ...]}`, keyed
  back to the `id` you sent so the frontend can match by array index
  rather than relying on response order.

## Missing requirements — resolve inline, per item

Each `missing_requirements` item from a job check (Job Search's "Check
match?" and the tailoring job-detail page's resume match both surface
these) gets three actions right where it's shown — no separate review
page, no batch step:

1. **"I have this"** — reveals an editable text box, pre-filled with the
   raw flagged phrase, so you describe it in your own words (real detail
   — dates, scale, tools used) before picking a tool category and adding
   it straight to the CV's `tools`. The raw AI-generated phrase is never
   saved verbatim; what you actually type is what gets added. This calls
   `GET`/`PUT /api/cv/{id}` directly (fetch the profile, append the tool,
   save it back) — it is a real, immediate CV edit, not a draft.
2. **"Track to learn"** — sends it straight to the
   [Skills to Learn](#skills-to-learn) list (`POST /api/cv/{id}/learning`)
   instead of the CV.
3. **"Not relevant to me"** — tells the app to stop flagging this
   requirement (or a close variant of it) for this CV in future AI job
   scoring and resume matching, rather than re-surfacing it every time.
   Stored per-CV and threaded into both the job-scoring prompt
   (`backend/job_scoring.py`) and the tailoring resume-match prompt
   (`backend/tailoring_llm_steps.py`), with a case-insensitive substring
   match as a server-side safety net in case a model doesn't fully honor
   the instruction.

Whichever action you pick, the item disappears from the list immediately
— there's no separate "save" step for this part.

### API

- `POST /api/cv/{id}/ignored` — JSON body `{text: string}`. Idempotent —
  marking the same text twice (case/whitespace-insensitive) is a no-op,
  not a duplicate row. Returns `{id, cv_id, text, created_at}`.
- `GET /api/cv/{id}/ignored` — list a CV's ignored requirements.
- `DELETE /api/cv/{id}/ignored/{item_id}` — un-ignore one. 404 if it
  doesn't exist.

## Skills to Learn

A standalone page (`frontend/learning.html`) for everything you flagged as
"don't have it yet" instead of adding to your CV. It's not just a wishlist
— the same skill getting flagged again from a different job (an identical
gap, matched case/whitespace-insensitively) bumps an occurrence count
instead of creating a duplicate row, so recurring gaps float to the top
and are the ones worth actually prioritizing. Each item shows how many
times it's been seen and when it was first/last flagged. "Learned it —
add to CV" promotes an item straight into a tool category on your CV (and
removes it from the learning list); "Remove" just drops it.

### API

- `POST /api/cv/{id}/learning` — JSON body `{text: string}`. Adds a new
  item, or bumps `occurrences` on an existing one (case/whitespace-
  insensitive match) and updates `last_flagged_at`. Returns
  `{id, cv_id, text, occurrences, first_flagged_at, last_flagged_at}`.
  404 if the CV doesn't exist; 400 if `text` is empty after trimming.
- `GET /api/cv/{id}/learning` — list items for a CV, ordered by
  `occurrences` desc then `last_flagged_at` desc.
- `DELETE /api/cv/{id}/learning/{item_id}` — remove an item. 404 if it
  doesn't exist.

## Settings (AI provider)

`frontend/settings.html` — every AI feature (job scoring, job analysis,
resume matching, CV generation) goes through one provider choice per
account: **Anthropic** (Claude) or **DeepSeek**. Pick a provider and
optionally save your own API key; without a saved key, Anthropic falls
back to this deployment's own `ANTHROPIC_API_KEY`, while DeepSeek always
needs a personal key (there's no shared DeepSeek key). Keys are encrypted
at rest (`backend/crypto_util.py`, a key derived from `JWT_SECRET`) and
only ever shown back masked (`sk-d••••••7890`), never in full.

Swapping in a new provider means adding one class to
`backend/llm_provider.py` — `LLMProvider` is the interface every pipeline
step and job-scoring call goes through (`structured_call(system_blocks,
content_blocks, output_model) → (parsed, usage)`); nothing else in the
codebase talks to an SDK directly. `AnthropicProvider` uses Claude's
native structured output; `DeepSeekProvider` uses the (OpenAI-compatible)
`openai` SDK pointed at `https://api.deepseek.com`, asks for JSON mode
with the target schema embedded in the prompt, and validates + retries
once server-side since DeepSeek doesn't enforce a JSON schema itself.

### API

- `GET /api/settings` — `{llm_provider, has_api_key, api_key_preview,
  available_providers}`.
- `PUT /api/settings` — JSON body `{llm_provider, api_key?}`.
  `llm_provider` must be `"anthropic"` or `"deepseek"`. `api_key`:
  omit to leave the saved key unchanged, `""` to remove it, or a new
  value to replace it.

## CV tailoring

Given a saved CV and a specific job, generate a CV tailored to that job —
never inventing facts. The resume database (`CVProfile`) is the single
source of truth: the AI may select, prioritize, exclude, rewrite, shorten,
and improve wording, but company names, roles, employment dates,
locations, degrees, and institutions are always copied verbatim from the
database by the backend — the model is never asked to reproduce them, so
they can't drift. Every generated bullet must cite the resume item(s) it's
based on; a bullet whose sourceIds don't check out, or whose text contains
a number not present in its cited source, is dropped before the CV is
returned rather than shown as a fact.

Pipeline (`backend/tailoring_orchestrator.py`, `tailoring_llm_steps.py`):
job analysis → evidence selection + resume match → CV draft (wording
only — structural facts filled in separately) → evaluation (score 0-100,
`TAILOR_PASS_SCORE`, default 75) → up to `TAILOR_MAX_REVISIONS` (default
2) targeted revisions if it doesn't pass → final wording-only polish pass
→ grounding validation → stored as a new version. Each stage is a
separate, narrowly-scoped LLM call through whichever provider is set on
the [Settings](#settings-ai-provider) page for the requesting user
(`backend/llm_provider.py`; Anthropic defaults to `TAILOR_LLM_MODEL`,
default `claude-opus-5`). On Anthropic, prompts put the candidate's
resume evidence behind a `cache_control` breakpoint ahead of job-specific
content, so repeated calls in one generation (and regenerations of the
same CV) can hit Anthropic's prompt cache — DeepSeek calls skip this
(no equivalent client-controlled breakpoint), so caching there is
whatever DeepSeek's own automatic prompt caching picks up.

Resume items get stable IDs derived from their own content (not stored in
the DB), so appending new experience needs no migration or rewrite —
existing items keep their ID unless their own text is edited.

### Flow

1. **Job Search** page: click "Tailor CV for this job" on a result — this
   saves the job and runs job analysis. For boards Job Search can't scrape
   (Indeed/Glassdoor often block search requests from a VPS IP — see
   below), use the **Tailored CVs** page instead: paste the listing's URL
   ("Fetch details" auto-fills title/company/location/description from
   the page's structured job data — works on most boards and ATSs, not
   just Indeed/Glassdoor) or just paste the text by hand.
2. **Job detail** page: resume match runs automatically (score, strong/
   partial/missing requirements, ATS keyword coverage), with an
   expandable review of exactly which resume items were included/maybe/
   excluded and why. Each missing requirement has three actions right
   there (see [Missing requirements](#missing-requirements--resolve-inline-per-item))
   — tailoring never asks you to invent something to satisfy a job.
3. Click **Generate Tailored CV** to run the full pipeline. The result is
   a versioned, editable document-style CV with a provenance note under
   each bullet ("Based on N experiences"), a sidebar with match/
   generation info, Edit/Save (edits only change this tailored CV, never
   the resume database), Export JSON, Print/Save-as-PDF, a version
   history dropdown, and Regenerate.

### API (`/api/tailoring/*`, all require auth, all scoped to the caller)

- `POST /parse-job-url` — `{url}` → best-effort scrape of a single job
  page (not a board search — a specific listing's URL), for boards that
  block JobSpy's search scraping. Looks for a `JobPosting` JSON-LD block
  (used by Indeed, Glassdoor, LinkedIn, Greenhouse, Lever, Workday, and
  most other boards/ATSs for SEO) first, falls back to Open Graph meta
  tags, then raw page text. Returns `{title, company, location,
  description, job_url}` — any field can be `null`. 422 with a clear
  message if the page couldn't be fetched or nothing was found (the page
  blocks bots, uses heavy client-side rendering, etc.) — paste the details
  by hand in that case. `frontend/jobs.js`'s "Fetch details" button calls
  this to prefill the manual add-job form, which stays fully editable
  either way.
- `POST /jobs` — `{cv_id, title, company?, location?, description?,
  job_url?, job_type?}` → saves the job and runs job analysis. Returns
  the job with `job_analysis` populated.
- `GET /jobs`, `GET /jobs/{id}`, `DELETE /jobs/{id}`
- `GET /jobs/{id}/evidence` — the CV's evidence pool (id, type, company/
  role/institution, period, bullet, skills) for building an evidence
  review UI.
- `POST /jobs/{id}/match` / `GET /jobs/{id}/match` — run/fetch resume
  match: `{matchScore, strongMatches, partialMatches, missingRequirements,
  atsKeywordsCovered, selection: [{sourceId, relevanceScore, decision,
  matchedRequirements, matchedKeywords, reason}]}`.
- `POST /jobs/{id}/generate` — runs the full pipeline (running match
  first if it hasn't been run yet) and stores a new version. Returns
  `{id, version_number, cv, selection, provenance, evaluation,
  generation}`.
- `GET /jobs/{id}/tailored-cvs` — version history for a job.
- `GET /tailored-cvs/{id}`, `PATCH /tailored-cvs/{id}` (body `{cv}`,
  edits presentation only), `POST /tailored-cvs/{id}/regenerate`,
  `GET /tailored-cvs/{id}/export.json`.
