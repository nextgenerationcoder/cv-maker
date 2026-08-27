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

`frontend/cv.html` lets you upload a CV as a PDF; the backend sends it to
Claude (`claude-opus-5`, via native PDF document input + structured output)
to extract a structured profile — contact info, summary, skills, technical
knowledge, education, work experience, languages, likely preferred roles
(inferred from the CV's summary/trajectory if not stated outright), and
certifications. The result is stored in SQLite and returned to the page.

Requires `ANTHROPIC_API_KEY` set in the backend's environment (copy
`.env.example` to `.env` and fill in your key — `docker-compose.yml` reads
it from there automatically; for local `uvicorn` runs, `export` it or use a
tool like `direnv`).

### API

- `POST /api/cv/upload` — multipart form, field `file` (PDF, max 15MB).
  Returns `{id, filename, uploaded_at, profile}`.
- `GET /api/cv/{id}` — refetch a previously extracted profile.
- `GET /api/cv?limit=20` — list recent uploads (id/filename/uploaded_at only).

### Storage

SQLite, path from `CV_DB_PATH` (default `./cv_profiles.db`; the Docker setup
points it at `/data/cv.db` on a named volume, `cv_data`, so uploads survive
container rebuilds).
