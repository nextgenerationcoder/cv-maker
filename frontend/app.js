// API_BASE and authFetch come from auth.js, loaded before this script.

const form = document.getElementById("search-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const urlForm = document.getElementById("url-form");
const urlStatusEl = document.getElementById("url-status");
const scoreBarEl = document.getElementById("score-bar");
const scoreCvSelectEl = document.getElementById("score-cv-select");
const scoreHintEl = document.getElementById("score-hint");
const addJobForm = document.getElementById("add-job-form");
const fetchJobUrlBtn = document.getElementById("fetch-job-url-btn");
const fetchJobStatusEl = document.getElementById("fetch-job-status");
const fetchWrongBtn = document.getElementById("fetch-wrong-btn");

let lastJobs = [];
let lastScoresByIndex = {};
let hasSavedCv = false;

async function loadCvOptions() {
  try {
    const response = await authFetch(`${API_BASE}/api/cv?limit=50`);
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
  const countryIndeed = document.getElementById("country-indeed").value.trim();

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
  if (countryIndeed) params.set("country_indeed", countryIndeed);

  try {
    const response = await authFetch(`${API_BASE}/api/jobs?${params.toString()}`);
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
        <p class="missing-label">Missing — for each one, tell us what's actually true:</p>
        <ul class="missing-list">
          ${missing
            .map(
              (m) => `
            <li class="missing-item" data-text="${escapeAttr(m)}">
              <span class="missing-text">${escapeHtml(m)}</span>
              <div class="missing-actions">
                <button type="button" class="missing-have-btn">I have this</button>
                <button type="button" class="missing-learn-btn">Track to learn</button>
                <button type="button" class="missing-ignore-btn">Not relevant to me</button>
              </div>
              <div class="missing-have-form" hidden>
                <input type="text" class="missing-have-input" value="${escapeAttr(m)}" />
                <input type="text" class="missing-have-category" placeholder="Tool category (e.g. tools)" value="tools" />
                <button type="button" class="missing-have-save-btn">Add to CV</button>
              </div>
              <span class="missing-item-status"></span>
            </li>`
            )
            .join("")}
        </ul>
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
  const haveBtn = event.target.closest(".missing-have-btn");
  if (haveBtn) {
    const li = haveBtn.closest(".missing-item");
    li.querySelector(".missing-have-form").hidden = false;
    haveBtn.closest(".missing-actions").hidden = true;
    return;
  }

  const haveSaveBtn = event.target.closest(".missing-have-save-btn");
  if (haveSaveBtn) {
    await addMissingItemToCv(haveSaveBtn.closest(".missing-item"));
    return;
  }

  const learnBtn = event.target.closest(".missing-learn-btn");
  if (learnBtn) {
    await trackMissingItemToLearn(learnBtn.closest(".missing-item"));
    return;
  }

  const ignoreBtn = event.target.closest(".missing-ignore-btn");
  if (ignoreBtn) {
    await markMissingItemIgnored(ignoreBtn.closest(".missing-item"));
    return;
  }

  const tailorBtn = event.target.closest(".tailor-cv-btn");
  if (tailorBtn) {
    await tailorCvForJob(tailorBtn);
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
    const response = await authFetch(`${API_BASE}/api/jobs/score`, {
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

async function tailorCvForJob(btn) {
  const index = Number(btn.dataset.index);
  const job = lastJobs[index];
  const cvId = scoreCvSelectEl.value;
  if (!cvId) {
    btn.insertAdjacentHTML("afterend", '<span class="score-error">Select a CV first.</span>');
    return;
  }

  btn.disabled = true;
  btn.textContent = "Saving…";

  const body = {
    cv_id: cvId,
    title: job.title || "Untitled role",
    company: job.company || null,
    location: job.location || null,
    description: job.description || null,
    job_url: job.job_url || null,
    job_type: Array.isArray(job.job_type) ? job.job_type.join(", ") : job.job_type || null,
  };

  try {
    const response = await authFetch(`${API_BASE}/api/tailoring/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    const savedJob = await response.json();
    window.location.href = `job-detail.html?job_id=${encodeURIComponent(savedJob.id)}`;
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Tailor CV for this job";
    btn.insertAdjacentHTML("afterend", `<span class="score-error">${escapeHtml(err.message)}</span>`);
  }
}

function removeMissingItem(li) {
  const list = li.closest(".missing-list");
  li.remove();
  if (list && !list.children.length) {
    list.closest(".missing-gaps").querySelector(".missing-label").textContent = "Nothing missing — nice.";
  }
}

// "I have this" — the user writes it in their own words and it's added
// straight to the CV's tools. The raw AI-flagged phrase is never
// inserted verbatim; what the user actually types is what gets saved.
async function addMissingItemToCv(li) {
  const cvId = scoreCvSelectEl.value;
  const statusEl = li.querySelector(".missing-item-status");
  const text = li.querySelector(".missing-have-input").value.trim();
  const category = li.querySelector(".missing-have-category").value.trim() || "tools";
  if (!text) return;
  if (!cvId) {
    statusEl.textContent = "Select a CV first.";
    return;
  }

  const saveBtn = li.querySelector(".missing-have-save-btn");
  saveBtn.disabled = true;
  statusEl.textContent = "Saving…";

  try {
    const cvResponse = await authFetch(`${API_BASE}/api/cv/${cvId}`);
    if (!cvResponse.ok) throw new Error(`Request failed with ${cvResponse.status}`);
    const record = await cvResponse.json();
    const profile = record.profile;
    profile.tools = profile.tools || {};
    profile.tools[category] = profile.tools[category] || [];
    profile.tools[category].push({ name: text, level: null });

    const putResponse = await authFetch(`${API_BASE}/api/cv/${cvId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, filename: record.filename }),
    });
    if (!putResponse.ok) throw new Error(`Request failed with ${putResponse.status}`);

    removeMissingItem(li);
  } catch (err) {
    saveBtn.disabled = false;
    statusEl.textContent = `Error: ${err.message}`;
  }
}

// "Track to learn" — goes on the Skills to Learn list instead of the CV.
async function trackMissingItemToLearn(li) {
  const cvId = scoreCvSelectEl.value;
  const statusEl = li.querySelector(".missing-item-status");
  if (!cvId) {
    statusEl.textContent = "Select a CV first.";
    return;
  }
  const text = li.dataset.text;
  try {
    const response = await authFetch(`${API_BASE}/api/cv/${cvId}/learning`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    removeMissingItem(li);
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
}

// "Not relevant to me" — tells future AI scoring/matching for this CV to
// stop flagging this requirement, instead of re-surfacing it every time.
async function markMissingItemIgnored(li) {
  const cvId = scoreCvSelectEl.value;
  const statusEl = li.querySelector(".missing-item-status");
  if (!cvId) {
    statusEl.textContent = "Select a CV first.";
    return;
  }
  const text = li.dataset.text;
  try {
    const response = await authFetch(`${API_BASE}/api/cv/${cvId}/ignored`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    removeMissingItem(li);
  } catch (err) {
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
    const tailorHtml = hasSavedCv
      ? `<button type="button" class="tailor-cv-btn" data-index="${index}">Tailor CV for this job</button>`
      : "";

    li.innerHTML = `
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(company)}${location ? " — " + escapeHtml(location) : ""}</p>
      ${meta ? `<p class="meta">${meta}</p>` : ""}
      ${scoreHtml}
      <div class="job-actions">
        <a href="${url}" target="_blank" rel="noopener noreferrer">View job</a>
        ${tailorHtml}
      </div>
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

// ---------- manually add a job (for boards search can't scrape) ----------

fetchJobUrlBtn.addEventListener("click", async () => {
  const url = document.getElementById("add-job-url").value.trim();
  if (!url) {
    fetchJobStatusEl.textContent = "Paste a job URL first.";
    return;
  }
  fetchJobUrlBtn.disabled = true;
  fetchJobStatusEl.textContent = "Fetching…";
  try {
    const response = await authFetch(`${API_BASE}/api/tailoring/parse-job-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    const data = await response.json();
    if (data.title) document.getElementById("add-job-title").value = data.title;
    if (data.company) document.getElementById("add-job-company").value = data.company;
    if (data.location) document.getElementById("add-job-location").value = data.location;
    if (data.description) document.getElementById("add-job-description").value = data.description;
    fetchJobStatusEl.textContent = data.description
      ? "Filled in below — review and edit before adding."
      : "Got the title, but not the description — this page likely needs a login or loads content with JavaScript. Paste the description in yourself below.";
    fetchWrongBtn.hidden = false;
  } catch (err) {
    fetchJobStatusEl.textContent = `${err.message}`;
  } finally {
    fetchJobUrlBtn.disabled = false;
  }
});

fetchWrongBtn.addEventListener("click", () => {
  document.getElementById("add-job-title").value = "";
  document.getElementById("add-job-company").value = "";
  document.getElementById("add-job-location").value = "";
  const descriptionEl = document.getElementById("add-job-description");
  descriptionEl.value = "";
  fetchJobStatusEl.textContent = "Cleared — paste the title and description in yourself below.";
  fetchWrongBtn.hidden = true;
  descriptionEl.focus();
});

addJobForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const title = document.getElementById("add-job-title").value.trim();
  if (!title) return;

  const job = {
    title,
    company: document.getElementById("add-job-company").value.trim() || null,
    location: document.getElementById("add-job-location").value.trim() || null,
    description: document.getElementById("add-job-description").value.trim() || null,
    job_url: document.getElementById("add-job-url").value.trim() || null,
    job_type: null,
    date_posted: null,
  };

  const index = lastJobs.length;
  lastJobs.push(job);
  scoreBarEl.hidden = !hasSavedCv;
  scoreHintEl.hidden = !hasSavedCv;
  renderResults(lastJobs);
  statusEl.textContent = `${lastJobs.length} job(s) — added 1 manually.`;

  addJobForm.reset();
  fetchWrongBtn.hidden = true;
  fetchJobStatusEl.textContent = "";

  const addedLi = resultsEl.children[index];
  if (addedLi) addedLi.scrollIntoView({ behavior: "smooth", block: "center" });
});
