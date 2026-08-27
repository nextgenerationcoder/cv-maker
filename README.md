# CV Maker

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

## CV import (CSV)

Earlier versions tried two things that turned out badly: a local
regex/PDF-layout parser (unreliable on real-world resumes) and a blank
manual-entry form (tedious, redundant). Both are gone. The flow now:

1. Download the CSV template from `frontend/cv.html` (or `GET
   /api/cv/template.csv` directly).
2. Give the template + your resume to whatever AI assistant you like
   (ChatGPT, Claude, etc. — outside this app) and ask it to fill the
   template in. The page shows a ready-to-copy example prompt.
3. Upload the completed CSV. The backend parses it with plain
   `csv.DictReader` — no AI call, no PDF-layout guessing on our side —
   and stores the result in SQLite.

The CSV is a flat "long" table rather than one row per profile, because a
variable number of jobs/degrees/languages doesn't map onto fixed columns.
Every row has 7 columns — `type,field1,field2,field3,field4,field5,field6`
— and `type` says what the row is (`contact`, `summary`, `skill`,
`technical`, `education`, `work`, `language`, `preferred_role`,
`certification`); unused `field*` columns are left blank. Multiple values
in one cell (e.g. `work` responsibilities) are `;`-separated. This shape
is deliberately simple: any LLM can produce it reliably, and our parser
never has to guess at structure the way the old PDF parser did.

A malformed or unrecognized row doesn't fail the whole import — it's
skipped and reported back as a warning, so one mistake from your LLM
doesn't sink the rest of the file. Every field is still editable on the
page after import (fix anything, add/remove entries) before you save.

### API

- `GET /api/cv/template.csv` — downloads the blank template with example
  rows.
- `POST /api/cv/import-csv` — multipart form, field `file` (CSV, max
  2MB). Returns `{id, filename, uploaded_at, updated_at, profile,
  warnings}` — `warnings` lists any skipped rows.
- `GET /api/cv/{id}/export.csv` — re-export a stored profile back to the
  same CSV shape (round-trips through an LLM again if you want another
  editing pass).
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
isn't something regex heuristics can do) — set `ANTHROPIC_API_KEY` (copy
`.env.example` to `.env`, `docker compose` picks it up automatically).
Nothing else in the app needs this key; job search and CV upload/edit
work fine without it.

- Model: `claude-opus-5`, structured output (`CVProfile`-shaped request →
  a `JobScore` per job) via `client.messages.parse`.
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
