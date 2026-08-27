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
const scoreBarEl = document.getElementById("score-bar");
const scoreCvSelectEl = document.getElementById("score-cv-select");
const scoreHintEl = document.getElementById("score-hint");

let lastJobs = [];
let lastScoresByIndex = {};
let hasSavedCv = false;

async function loadCvOptions() {
  try {
    const response = await fetch(`${API_BASE}/api/cv?limit=50`);
    if (!response.ok) return [];
    const data = await response.json();
    scoreCvSelectEl.innerHTML = "";
    hasSavedCv = data.cvs.length > 0;
    if (!hasSavedCv) {
      const opt = document.createElement("option");
      opt.textContent = "No saved CV yet — add one on the Upload CV page";
      opt.disabled = true;
      opt.selected = true;
      scoreCvSelectEl.appendChild(opt);
    } else {
      for (const cv of data.cvs) {
        const opt = document.createElement("option");
        opt.value = cv.id;
        opt.textContent = cv.filename;
        scoreCvSelectEl.appendChild(opt);
      }
    }
    return data.cvs;
  } catch {
    return [];
  }
}

loadCvOptions();

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
    lastJobs = data.jobs;
    lastScoresByIndex = {};
    await loadCvOptions(); // refresh in case a CV was added/removed since page load
    scoreBarEl.hidden = lastJobs.length === 0 || !hasSavedCv;
    scoreHintEl.hidden = lastJobs.length === 0 || !hasSavedCv;
    renderResults(lastJobs);
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
});

const SCORE_BANDS = [
  { min: 75, label: "Strong match", className: "score-strong" },
  { min: 50, label: "Worth applying", className: "score-good" },
  { min: 25, label: "Stretch", className: "score-stretch" },
  { min: 0, label: "Not aligned", className: "score-weak" },
];

function bandFor(score) {
  return SCORE_BANDS.find((b) => score >= b.min);
}

function scoreBadgeHtml(score, jobIndex) {
  const band = bandFor(score.score);
  const missing = score.missing_requirements || [];
  const missingHtml = missing.length
    ? `
      <div class="missing-gaps" data-job-index="${jobIndex}">
        <p class="missing-label">Missing — check what you actually have experience with:</p>
        <ul class="missing-list">
          ${missing
            .map(
              (m) => `
            <li>
              <label>
                <input type="checkbox" class="missing-checkbox" value="${escapeAttr(m)}" checked />
                ${escapeHtml(m)}
              </label>
            </li>`
            )
            .join("")}
        </ul>
        <button type="button" class="save-gaps-btn" data-job-index="${jobIndex}">Add selected to CV gaps</button>
        <span class="gaps-status"></span>
      </div>
    `
    : "";
  return `
    <p class="score-badge ${band.className}">${score.score}/100 · ${escapeHtml(band.label)}</p>
    <p class="score-reasoning">${escapeHtml(score.reasoning)}</p>
    ${missingHtml}
  `;
}

resultsEl.addEventListener("click", async (event) => {
  const saveGapsBtn = event.target.closest(".save-gaps-btn");
  if (saveGapsBtn) {
    await saveSelectedGaps(saveGapsBtn);
    return;
  }

  const btn = event.target.closest(".check-match-btn");
  if (!btn) return;

  const index = Number(btn.dataset.index);
  const job = lastJobs[index];
  const cvId = scoreCvSelectEl.value;
  if (!cvId) {
    btn.insertAdjacentHTML("afterend", '<span class="score-error">Select a CV first.</span>');
    return;
  }

  btn.disabled = true;
  btn.textContent = "Checking…";

  const payloadJob = {
    id: index,
    title: job.title || "Untitled role",
    company: job.company || null,
    location: job.location || null,
    description: job.description || null,
    job_type: Array.isArray(job.job_type) ? job.job_type.join(", ") : job.job_type || null,
  };

  try {
    const response = await fetch(`${API_BASE}/api/jobs/score`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cv_id: cvId, jobs: [payloadJob] }),
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    const data = await response.json();
    const score = data.scores[0];
    lastScoresByIndex[index] = score;
    btn.outerHTML = scoreBadgeHtml(score, index);
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Check match?";
    btn.insertAdjacentHTML("afterend", `<span class="score-error">${escapeHtml(err.message)}</span>`);
  }
});

async function saveSelectedGaps(btn) {
  const index = Number(btn.dataset.jobIndex);
  const container = btn.closest(".missing-gaps");
  const statusEl = container.querySelector(".gaps-status");
  const checked = Array.from(container.querySelectorAll(".missing-checkbox:checked")).map((c) => c.value);

  if (!checked.length) {
    statusEl.textContent = "Select at least one item first.";
    return;
  }
  const cvId = scoreCvSelectEl.value;
  if (!cvId) {
    statusEl.textContent = "Select a CV first.";
    return;
  }

  const job = lastJobs[index];
  btn.disabled = true;
  statusEl.textContent = "Saving…";

  try {
    const response = await fetch(`${API_BASE}/api/cv/${cvId}/gaps`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: checked, source: job?.title || null }),
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    statusEl.textContent = `Added ${checked.length} to "Missing experiences" on the Upload CV page.`;
  } catch (err) {
    btn.disabled = false;
    statusEl.textContent = `Error: ${err.message}`;
  }
}

function renderResults(jobs) {
  resultsEl.innerHTML = "";
  jobs.forEach((job, index) => {
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

    const score = lastScoresByIndex[index];
    const scoreHtml = score
      ? scoreBadgeHtml(score, index)
      : hasSavedCv
      ? `<button type="button" class="check-match-btn" data-index="${index}">Check match?</button>`
      : "";

    li.innerHTML = `
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(company)}${location ? " — " + escapeHtml(location) : ""}</p>
      ${meta ? `<p class="meta">${meta}</p>` : ""}
      ${scoreHtml}
      <a href="${url}" target="_blank" rel="noopener noreferrer">View job</a>
    `;
    resultsEl.appendChild(li);
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/"/g, "&quot;");
}
