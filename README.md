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

## CV upload & extraction

`frontend/cv.html` lets you upload a CV as a PDF; the backend parses it
locally (`cv_parser.py`) — no external API, no API key, no cost — to
extract a structured profile: contact info, summary, skills, technical
knowledge, education, work experience, languages, preferred roles, and
certifications. The result is stored in SQLite and returned to the page.

This is a rule-based parser (PDF text extraction via `pdfplumber` in
layout-preserving mode, then section-header detection + regex/keyword
heuristics), not an LLM — it works well on CVs with clear, conventional
section headers (English or German) and date-anchored entries, but will
do noticeably worse on unusual layouts, free-flowing prose, or
scanned/image-only PDFs (no embedded text to read). Tested end-to-end
against a real multi-column resume; known rough edges found there:

- `preferred_roles` falls back to the most recent job title(s) when
  there's no explicit "target role" section — it's a guess, not real
  inference.
- An entry whose date range uses a shared year across two months (e.g.
  "March – May 2026") isn't recognized as an entry boundary and merges
  into the previous entry — only a range with a year on both ends is.
- A skill/tool value that word-wraps across two lines inside an inline
  "Label: item, item, item" block (rather than its own bullet line) can
  split awkwardly at the wrap point.
- `work_experience[].company` is `"Unknown"` when an entry has no
  separate company line to detect (e.g. a project title that already
  names the organization).

Given those, every field on the page is editable after upload — fix
anything the parser got wrong, add/remove entries, then save. You can
also skip uploading entirely and click "Or start manually" to fill out
a CV from a blank form.

### API

- `POST /api/cv/upload` — multipart form, field `file` (PDF, max 15MB).
  Returns `{id, filename, uploaded_at, updated_at, profile}`.
- `POST /api/cv/manual` — JSON body `{filename?, profile}`, creates a new
  entry without a PDF. Same response shape as `/upload`.
- `PUT /api/cv/{id}` — JSON body `{filename?, profile}`, overwrites a
  stored entry (used to save edits to either an uploaded or manual CV).
  404 if the id doesn't exist.
- `GET /api/cv/{id}` — refetch a stored profile.
- `GET /api/cv?limit=20` — list recent entries (id/filename/uploaded_at/
  updated_at only).

### Storage

SQLite, path from `CV_DB_PATH` (default `./cv_profiles.db`; the Docker setup
points it at `/data/cv.db` on a named volume, `cv_data`, so uploads survive
container rebuilds).
