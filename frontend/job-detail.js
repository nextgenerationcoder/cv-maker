// API_BASE and authFetch come from auth.js, loaded before this script.

const params = new URLSearchParams(window.location.search);
const jobId = params.get("job_id");

const jobTitleHeading = document.getElementById("job-title-heading");
const jobMetaEl = document.getElementById("job-meta");

const matchStatusEl = document.getElementById("match-status");
const matchContentEl = document.getElementById("match-content");
const matchScoreFillEl = document.getElementById("match-score-fill");
const matchScoreLabelEl = document.getElementById("match-score-label");
const matchStrongEl = document.getElementById("match-strong");
const matchPartialEl = document.getElementById("match-partial");
const matchMissingEl = document.getElementById("match-missing");
const matchAtsEl = document.getElementById("match-ats");
const addMissingBtn = document.getElementById("add-missing-to-gaps-btn");
const gapsHintEl = document.getElementById("gaps-hint");

const evidenceSectionEl = document.getElementById("evidence-section");
const evidenceListEl = document.getElementById("evidence-list");
const toggleEvidenceBtn = document.getElementById("toggle-evidence-btn");

const generateBtn = document.getElementById("generate-btn");
const generateStatusEl = document.getElementById("generate-status");

const cvReviewSectionEl = document.getElementById("cv-review-section");
const cvPreviewEl = document.getElementById("cv-preview");
const versionSelectEl = document.getElementById("version-select");
const editToggleBtn = document.getElementById("edit-toggle-btn");
const saveCvBtn = document.getElementById("save-cv-btn");
const exportCvLink = document.getElementById("export-cv-link");
const printCvBtn = document.getElementById("print-cv-btn");
const cvSaveStatusEl = document.getElementById("cv-save-status");
const sidebarInfoEl = document.getElementById("sidebar-info");

let job = null;
let match = null;
let evidenceById = {};
let currentTailoredCv = null;
let editMode = false;

if (!jobId) {
  jobTitleHeading.textContent = "No job selected";
  matchStatusEl.textContent = "";
  generateBtn.hidden = true;
} else {
  init();
}

async function init() {
  await loadJob();
  await loadEvidence();
  await ensureMatch();
  await loadVersions();
}

async function loadJob() {
  try {
    const response = await authFetch(`${API_BASE}/api/tailoring/jobs/${jobId}`);
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    job = await response.json();
    jobTitleHeading.textContent = job.title;
    jobMetaEl.textContent = [job.company, job.location].filter(Boolean).join(" — ") || "No company/location given";
    if (job.job_url) {
      const link = document.createElement("a");
      link.href = job.job_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = " (view original posting)";
      jobMetaEl.appendChild(link);
    }
    generateBtn.disabled = false;
  } catch (err) {
    jobTitleHeading.textContent = "Couldn't load this job";
    jobMetaEl.textContent = err.message;
  }
}

async function loadEvidence() {
  try {
    const response = await authFetch(`${API_BASE}/api/tailoring/jobs/${jobId}/evidence`);
    if (!response.ok) return;
    const data = await response.json();
    evidenceById = Object.fromEntries(data.items.map((item) => [item.id, item]));
  } catch {
    // evidence review is a nice-to-have — don't block the rest of the page
  }
}

async function ensureMatch() {
  try {
    let response = await authFetch(`${API_BASE}/api/tailoring/jobs/${jobId}/match`);
    if (response.status === 404) {
      matchStatusEl.textContent = "Analyzing how your resume matches this job…";
      response = await authFetch(`${API_BASE}/api/tailoring/jobs/${jobId}/match`, { method: "POST" });
    }
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    match = await response.json();
    renderMatch(match);
  } catch (err) {
    matchStatusEl.textContent = `Error running resume match: ${err.message}`;
  }
}

function renderMatch(m) {
  matchStatusEl.hidden = true;
  matchContentEl.hidden = false;

  matchScoreFillEl.style.width = `${m.matchScore}%`;
  matchScoreFillEl.className = "match-score-fill " + scoreBand(m.matchScore);
  matchScoreLabelEl.textContent = `${m.matchScore}% match`;

  fillList(matchStrongEl, m.strongMatches, "Nothing stands out yet.");
  fillList(matchPartialEl, m.partialMatches, "None.");
  fillList(matchMissingEl, m.missingRequirements, "Nothing missing.");

  matchAtsEl.textContent = m.atsKeywordsCovered.length
    ? `ATS keywords covered: ${m.atsKeywordsCovered.join(", ")}`
    : "No ATS keywords identified from the job posting.";

  if (m.missingRequirements.length) {
    addMissingBtn.hidden = false;
  }

  renderEvidence(m.selection);
}

function scoreBand(score) {
  if (score >= 75) return "score-strong";
  if (score >= 50) return "score-good";
  if (score >= 25) return "score-stretch";
  return "score-weak";
}

function fillList(ul, items, emptyText) {
  ul.innerHTML = "";
  if (!items.length) {
    const li = document.createElement("li");
    li.className = "hint";
    li.textContent = emptyText;
    ul.appendChild(li);
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    ul.appendChild(li);
  }
}

addMissingBtn.addEventListener("click", async () => {
  if (!job || !match) return;
  addMissingBtn.disabled = true;
  try {
    const response = await authFetch(`${API_BASE}/api/cv/${job.cv_id}/gaps`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: match.missingRequirements, source: job.title }),
    });
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    addMissingBtn.hidden = true;
    gapsHintEl.hidden = false;
  } catch (err) {
    addMissingBtn.disabled = false;
    gapsHintEl.hidden = false;
    gapsHintEl.textContent = `Error: ${err.message}`;
  }
});

function renderEvidence(selection) {
  if (!selection.length) return;
  evidenceSectionEl.hidden = false;
  evidenceListEl.innerHTML = "";

  const order = { include: 0, maybe: 1, exclude: 2 };
  const sorted = [...selection].sort((a, b) => (order[a.decision] ?? 3) - (order[b.decision] ?? 3) || b.relevanceScore - a.relevanceScore);

  for (const s of sorted) {
    const evidence = evidenceById[s.sourceId];
    const card = document.createElement("div");
    card.className = "entry-card evidence-card";

    const badge = document.createElement("span");
    badge.className = `evidence-badge evidence-${s.decision}`;
    badge.textContent = `${s.decision === "include" ? "Included" : s.decision === "maybe" ? "Maybe" : "Excluded"} · ${s.relevanceScore}%`;
    card.appendChild(badge);

    const text = document.createElement("p");
    text.className = "evidence-text";
    text.textContent = evidence ? evidence.bullet : "(original experience text unavailable)";
    card.appendChild(text);

    if (evidence) {
      const label = document.createElement("p");
      label.className = "meta";
      label.textContent = `${evidence.label}${evidence.period ? " — " + evidence.period : ""}`;
      card.appendChild(label);
    }

    if (s.matchedRequirements.length) {
      const matches = document.createElement("p");
      matches.className = "hint";
      matches.textContent = "Matches: " + s.matchedRequirements.join(", ");
      card.appendChild(matches);
    }

    const reason = document.createElement("p");
    reason.className = "hint evidence-reason";
    reason.textContent = s.reason;
    card.appendChild(reason);

    evidenceListEl.appendChild(card);
  }
}

toggleEvidenceBtn.addEventListener("click", () => {
  const showing = !evidenceListEl.hidden;
  evidenceListEl.hidden = showing;
  toggleEvidenceBtn.textContent = showing ? "Show details" : "Hide details";
});

// ---------- Generation ----------

const STAGE_MESSAGES = [
  "Analyzing job requirements…",
  "Selecting relevant experience…",
  "Building CV draft…",
  "Checking job alignment…",
  "Finalizing…",
];

function startStagedStatus() {
  let i = 0;
  generateStatusEl.textContent = STAGE_MESSAGES[0];
  return setInterval(() => {
    i = (i + 1) % STAGE_MESSAGES.length;
    generateStatusEl.textContent = STAGE_MESSAGES[i];
  }, 2500);
}

generateBtn.addEventListener("click", async () => {
  if (!job) return;
  generateBtn.disabled = true;
  const timer = startStagedStatus();
  try {
    const response = await authFetch(`${API_BASE}/api/tailoring/jobs/${jobId}/generate`, { method: "POST" });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    const tcv = await response.json();
    clearInterval(timer);
    generateStatusEl.textContent = "Done.";
    generateBtn.textContent = "Regenerate Tailored CV";
    generateBtn.disabled = false;
    await loadVersions();
    selectVersion(tcv.id);
  } catch (err) {
    clearInterval(timer);
    generateBtn.disabled = false;
    generateStatusEl.textContent = `Error: ${err.message}`;
  }
});

// ---------- Version history + CV review ----------

async function loadVersions() {
  try {
    const response = await authFetch(`${API_BASE}/api/tailoring/jobs/${jobId}/tailored-cvs`);
    if (!response.ok) return;
    const data = await response.json();
    versionSelectEl.innerHTML = "";
    if (!data.tailored_cvs.length) return;

    generateBtn.textContent = "Regenerate Tailored CV";
    for (const tcv of data.tailored_cvs) {
      const opt = document.createElement("option");
      opt.value = tcv.id;
      const date = new Date(tcv.created_at).toLocaleString();
      opt.textContent = `v${tcv.version_number} — ${date}`;
      versionSelectEl.appendChild(opt);
    }
    selectVersion(data.tailored_cvs[0].id);
  } catch {
    // history is optional
  }
}

versionSelectEl.addEventListener("change", () => selectVersion(versionSelectEl.value));

async function selectVersion(tcvId) {
  try {
    const response = await authFetch(`${API_BASE}/api/tailoring/tailored-cvs/${tcvId}`);
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    currentTailoredCv = await response.json();
    versionSelectEl.value = tcvId;
    cvReviewSectionEl.hidden = false;
    exportCvLink.href = `${API_BASE}/api/tailoring/tailored-cvs/${tcvId}/export.json`;
    editMode = false;
    renderSidebar();
    renderCvPreview();
  } catch (err) {
    cvSaveStatusEl.textContent = `Error loading this version: ${err.message}`;
  }
}

function renderSidebar() {
  sidebarInfoEl.innerHTML = "";
  const rows = [
    ["Target job", job ? job.title : ""],
    ["Company", job ? job.company || "—" : ""],
    ["Match score", match ? `${match.matchScore}%` : "—"],
    ["ATS keywords covered", match ? `${match.atsKeywordsCovered.length} / ${match.atsKeywordsCovered.length + match.missingRequirements.length}` : "—"],
    ["Experiences included", String(currentTailoredCv.selection.filter((s) => s.decision === "include").length)],
    ["Evaluator score", `${currentTailoredCv.evaluation.score}/100 (${currentTailoredCv.evaluation.pass ?? currentTailoredCv.evaluation.passed ? "passed" : "below threshold"})`],
    ["Revisions made", String(currentTailoredCv.generation.revisionCount)],
    ["Version", `v${currentTailoredCv.version_number}`],
    ["Generated", new Date(currentTailoredCv.created_at).toLocaleString()],
  ];
  for (const [label, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    sidebarInfoEl.appendChild(dt);
    sidebarInfoEl.appendChild(dd);
  }
}

function humanSourceText(sourceIds) {
  const texts = sourceIds.map((id) => evidenceById[id]).filter(Boolean).map((e) => e.bullet);
  if (!texts.length) return "";
  return texts.length === 1 ? `Based on: "${texts[0]}"` : `Based on ${texts.length} experiences: ` + texts.map((t) => `"${t}"`).join("; ");
}

function provenanceFor(path) {
  const entry = (currentTailoredCv.provenance || []).find((p) => p.path === path);
  return entry ? entry.sourceIds : [];
}

function renderCvPreview() {
  const cv = currentTailoredCv.cv;
  cvPreviewEl.innerHTML = "";
  cvPreviewEl.className = "cv-document" + (editMode ? " cv-document-edit" : "");

  const header = document.createElement("div");
  header.className = "cv-doc-header";
  header.innerHTML = `
    <h2>${editMode ? "" : escapeHtml(cv.name || "Unnamed candidate")}</h2>
    <p class="cv-doc-jobtitle">${editMode ? "" : escapeHtml(cv.jobTitle || "")}</p>
    <p class="cv-doc-contact">${editMode ? "" : escapeHtml([cv.location, cv.phone, cv.email].filter(Boolean).join(" · "))}</p>
  `;
  if (editMode) {
    header.innerHTML = "";
    header.appendChild(labeledInput("Name", "name", cv.name));
    header.appendChild(labeledInput("Target job title", "jobTitle", cv.jobTitle));
    header.appendChild(labeledInput("Location", "location", cv.location));
    header.appendChild(labeledInput("Phone", "phone", cv.phone));
    header.appendChild(labeledInput("Email", "email", cv.email));
  }
  cvPreviewEl.appendChild(header);

  const summarySection = document.createElement("div");
  summarySection.className = "cv-doc-section";
  const summaryHeading = document.createElement("h3");
  summaryHeading.textContent = "Profile";
  summarySection.appendChild(summaryHeading);
  if (editMode) {
    const ta = document.createElement("textarea");
    ta.rows = 3;
    ta.dataset.path = "profileSummary";
    ta.value = cv.profileSummary || "";
    summarySection.appendChild(ta);
  } else {
    const p = document.createElement("p");
    p.textContent = cv.profileSummary || "(no summary)";
    summarySection.appendChild(p);
  }
  cvPreviewEl.appendChild(summarySection);

  const jobsSection = document.createElement("div");
  jobsSection.className = "cv-doc-section";
  const jobsHeading = document.createElement("h3");
  jobsHeading.textContent = "Experience";
  jobsSection.appendChild(jobsHeading);
  cv.jobs.forEach((job_, i) => {
    const block = document.createElement("div");
    block.className = "cv-doc-entry";
    if (editMode) {
      block.appendChild(labeledInput(null, `jobs.${i}.title`, job_.title, "cv-doc-entry-title"));
      const metaRow = document.createElement("p");
      metaRow.className = "meta";
      metaRow.textContent = `${job_.company}${job_.location ? " — " + job_.location : ""} · ${job_.date}`;
      block.appendChild(metaRow);
    } else {
      const heading = document.createElement("p");
      heading.className = "cv-doc-entry-title";
      heading.textContent = `${job_.title}${job_.company ? " — " + job_.company : ""}`;
      block.appendChild(heading);
      const metaRow = document.createElement("p");
      metaRow.className = "meta";
      metaRow.textContent = `${job_.location ? job_.location + " · " : ""}${job_.date}`;
      block.appendChild(metaRow);
    }
    const ul = document.createElement(editMode ? "div" : "ul");
    job_.bullets.forEach((bullet, j) => {
      const path = `jobs[${i}].bullets[${j}]`;
      if (editMode) {
        const ta = document.createElement("textarea");
        ta.rows = 2;
        ta.dataset.path = `jobs.${i}.bullets.${j}`;
        ta.value = bullet;
        ul.appendChild(ta);
      } else {
        const li = document.createElement("li");
        li.textContent = bullet;
        li.className = "cv-doc-bullet";
        const sourceIds = provenanceFor(path);
        if (sourceIds.length) {
          const srcBtn = document.createElement("button");
          srcBtn.type = "button";
          srcBtn.className = "source-toggle";
          srcBtn.textContent = `Based on ${sourceIds.length} experience${sourceIds.length > 1 ? "s" : ""}`;
          const detail = document.createElement("p");
          detail.className = "source-detail";
          detail.hidden = true;
          detail.textContent = humanSourceText(sourceIds);
          srcBtn.addEventListener("click", () => {
            detail.hidden = !detail.hidden;
          });
          li.appendChild(srcBtn);
          li.appendChild(detail);
        }
        ul.appendChild(li);
      }
    });
    block.appendChild(ul);
    jobsSection.appendChild(block);
  });
  cvPreviewEl.appendChild(jobsSection);

  if (cv.education.length) {
    const eduSection = document.createElement("div");
    eduSection.className = "cv-doc-section";
    const eduHeading = document.createElement("h3");
    eduHeading.textContent = "Education";
    eduSection.appendChild(eduHeading);
    cv.education.forEach((edu, i) => {
      const block = document.createElement("div");
      block.className = "cv-doc-entry";
      const heading = document.createElement("p");
      heading.className = "cv-doc-entry-title";
      heading.textContent = `${edu.degree}${edu.institution ? " — " + edu.institution : ""}`;
      block.appendChild(heading);
      const metaRow = document.createElement("p");
      metaRow.className = "meta";
      metaRow.textContent = `${edu.location ? edu.location + " · " : ""}${edu.date}`;
      block.appendChild(metaRow);
      const ul = document.createElement("ul");
      edu.bullets.forEach((bullet) => {
        const li = document.createElement("li");
        li.textContent = bullet;
        ul.appendChild(li);
      });
      block.appendChild(ul);
      eduSection.appendChild(block);
    });
    cvPreviewEl.appendChild(eduSection);
  }

  const skillsSection = document.createElement("div");
  skillsSection.className = "cv-doc-section";
  const skillsHeading = document.createElement("h3");
  skillsHeading.textContent = "Skills";
  skillsSection.appendChild(skillsHeading);
  const skillLabels = { languages: "Languages", productBusiness: "Product & Business", tools: "Tools", strengths: "Strengths" };
  for (const [key, label] of Object.entries(skillLabels)) {
    if (!editMode && !cv.skills[key]) continue;
    const row = document.createElement("p");
    if (editMode) {
      const span = document.createElement("span");
      span.textContent = `${label}: `;
      const input = document.createElement("input");
      input.type = "text";
      input.dataset.path = `skills.${key}`;
      input.value = cv.skills[key] || "";
      row.appendChild(span);
      row.appendChild(input);
    } else {
      row.innerHTML = `<strong>${escapeHtml(label)}:</strong> ${escapeHtml(cv.skills[key])}`;
    }
    skillsSection.appendChild(row);
  }
  cvPreviewEl.appendChild(skillsSection);
}

function labeledInput(label, path, value, extraClass) {
  const wrap = document.createElement("label");
  wrap.className = "field" + (extraClass ? " " + extraClass : "");
  if (label) {
    const span = document.createElement("span");
    span.textContent = label;
    wrap.appendChild(span);
  }
  const input = document.createElement("input");
  input.type = "text";
  input.dataset.path = path;
  input.value = value || "";
  wrap.appendChild(input);
  return wrap;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

editToggleBtn.addEventListener("click", () => {
  editMode = !editMode;
  editToggleBtn.textContent = editMode ? "Cancel edit" : "Edit";
  saveCvBtn.hidden = !editMode;
  renderCvPreview();
});

function readEditedCv() {
  const cv = JSON.parse(JSON.stringify(currentTailoredCv.cv));
  cvPreviewEl.querySelectorAll("[data-path]").forEach((el) => {
    const path = el.dataset.path.split(".");
    let target = cv;
    for (let i = 0; i < path.length - 1; i++) {
      const key = /^\d+$/.test(path[i]) ? Number(path[i]) : path[i];
      target = target[key];
    }
    const lastKey = /^\d+$/.test(path[path.length - 1]) ? Number(path[path.length - 1]) : path[path.length - 1];
    target[lastKey] = el.value;
  });
  return cv;
}

saveCvBtn.addEventListener("click", async () => {
  const edited = readEditedCv();
  cvSaveStatusEl.textContent = "Saving…";
  try {
    const response = await authFetch(`${API_BASE}/api/tailoring/tailored-cvs/${currentTailoredCv.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cv: edited }),
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    currentTailoredCv = await response.json();
    cvSaveStatusEl.textContent = "Saved. This only changes this tailored CV — your resume database is untouched.";
    editMode = false;
    editToggleBtn.textContent = "Edit";
    saveCvBtn.hidden = true;
    renderCvPreview();
  } catch (err) {
    cvSaveStatusEl.textContent = `Error: ${err.message}`;
  }
});

printCvBtn.addEventListener("click", () => window.print());
