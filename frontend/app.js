// Empty string = relative /api/... requests, which is correct whenever this
// page is served through the nginx container (docker-compose) since it
// proxies /api/ to the backend itself. For running the frontend standalone
// against a bare `uvicorn` on port 8000 (no nginx in front), set
// window.API_BASE = "http://localhost:8000" before this script loads.
const API_BASE = window.API_BASE || "";

const form = document.getElementById("search-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const urlForm = document.getElementById("url-form");
const urlStatusEl = document.getElementById("url-status");

// Reverse of jobspy's f_JT codes (jobspy/linkedin/util.py: job_type_code)
const LINKEDIN_JOB_TYPE_CODES = {
  F: "fulltime",
  P: "parttime",
  I: "internship",
  C: "contract",
  T: "temporary",
};

urlForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const rawUrl = document.getElementById("linkedin-url").value.trim();
  if (!rawUrl) return;

  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch {
    urlStatusEl.textContent = "That doesn't look like a valid URL.";
    return;
  }
  if (!/(^|\.)linkedin\.com$/i.test(parsed.hostname)) {
    urlStatusEl.textContent = "Only LinkedIn job search URLs are supported here.";
    return;
  }

  const params = parsed.searchParams;
  const keywords = params.get("keywords");
  const location = params.get("location");
  const distance = params.get("distance");
  const jobTypeCode = params.get("f_JT");
  const isRemote = params.get("f_WT") === "2";
  const easyApply = params.get("f_AL") === "true";
  const tpr = params.get("f_TPR"); // e.g. "r18000" = seconds

  if (keywords) document.getElementById("search-term").value = keywords;
  if (location) document.getElementById("location").value = location;
  if (distance) document.getElementById("distance").value = distance;
  document.getElementById("site-name").value = "linkedin";
  document.getElementById("is-remote").checked = isRemote;
  document.getElementById("easy-apply").checked = easyApply;

  if (jobTypeCode && LINKEDIN_JOB_TYPE_CODES[jobTypeCode]) {
    document.getElementById("job-type").value = LINKEDIN_JOB_TYPE_CODES[jobTypeCode];
  }

  if (tpr && tpr.startsWith("r")) {
    const seconds = parseInt(tpr.slice(1), 10);
    if (!Number.isNaN(seconds)) {
      document.getElementById("hours-old").value = Math.round(seconds / 3600);
    }
  }

  const isSemanticSearch =
    parsed.pathname.includes("search-results") ||
    (params.get("origin") || "").toUpperCase().includes("SEMANTIC_SEARCH");

  if (!keywords && !location) {
    urlStatusEl.textContent =
      "No search filters found in that URL — form left as-is where nothing matched.";
  } else if (isSemanticSearch) {
    urlStatusEl.textContent =
      "This looks like a LinkedIn AI-search link — the full text was put in the search box, " +
      "but it'll be matched as plain keywords (things like \"less than 3 applicants\" won't be " +
      "understood as a filter). Edit the box if you want a cleaner keyword search.";
  } else {
    urlStatusEl.textContent = "Form filled from URL. Review and hit Search.";
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const searchTerm = document.getElementById("search-term").value.trim();
  const location = document.getElementById("location").value.trim();
  const siteName = document.getElementById("site-name").value;
  const hoursOld = document.getElementById("hours-old").value;
  const jobType = document.getElementById("job-type").value;
  const distance = document.getElementById("distance").value;
  const isRemote = document.getElementById("is-remote").checked;
  const easyApply = document.getElementById("easy-apply").checked;
  const includeKeywords = document.getElementById("include-keywords").value.trim();
  const excludeKeywords = document.getElementById("exclude-keywords").value.trim();

  resultsEl.innerHTML = "";
  statusEl.textContent = "Searching...";

  const params = new URLSearchParams({
    search_term: searchTerm,
    site_name: siteName,
  });
  if (location) params.set("location", location);
  if (hoursOld) params.set("hours_old", hoursOld);
  if (jobType) params.set("job_type", jobType);
  if (distance) params.set("distance", distance);
  if (isRemote) params.set("is_remote", "true");
  if (easyApply) params.set("easy_apply", "true");
  if (includeKeywords) params.set("include_keywords", includeKeywords);
  if (excludeKeywords) params.set("exclude_keywords", excludeKeywords);

  try {
    const response = await fetch(`${API_BASE}/api/jobs?${params.toString()}`);
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    const data = await response.json();
    statusEl.textContent = `${data.count} job(s) found`;
    renderResults(data.jobs);
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
});

function renderResults(jobs) {
  resultsEl.innerHTML = "";
  for (const job of jobs) {
    const li = document.createElement("li");
    const title = job.title || "Untitled role";
    const company = job.company || "Unknown company";
    const location = job.location || "";
    const url = job.job_url || "#";
    const datePosted = job.date_posted || "";
    const jobType = Array.isArray(job.job_type) ? job.job_type.join(", ") : job.job_type || "";

    const meta = [datePosted && `Posted ${datePosted}`, jobType]
      .filter(Boolean)
      .map(escapeHtml)
      .join(" · ");

    li.innerHTML = `
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(company)}${location ? " — " + escapeHtml(location) : ""}</p>
      ${meta ? `<p class="meta">${meta}</p>` : ""}
      <a href="${url}" target="_blank" rel="noopener noreferrer">View job</a>
    `;
    resultsEl.appendChild(li);
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
