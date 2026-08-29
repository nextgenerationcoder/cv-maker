// API_BASE and authFetch come from auth.js, loaded before this script.

const jobsListEl = document.getElementById("jobs-list");
const jobsStatusEl = document.getElementById("jobs-status");
const addJobForm = document.getElementById("add-job-form");
const addJobCvSelect = document.getElementById("add-job-cv-select");
const addJobStatusEl = document.getElementById("add-job-status");

async function loadCvOptions() {
  try {
    const response = await authFetch(`${API_BASE}/api/cv?limit=50`);
    if (!response.ok) return;
    const data = await response.json();
    addJobCvSelect.innerHTML = "";
    if (!data.cvs.length) {
      const opt = document.createElement("option");
      opt.textContent = "No saved CV yet — add one on the Upload CV page";
      opt.disabled = true;
      opt.selected = true;
      addJobCvSelect.appendChild(opt);
      return;
    }
    for (const cv of data.cvs) {
      const opt = document.createElement("option");
      opt.value = cv.id;
      opt.textContent = cv.filename;
      addJobCvSelect.appendChild(opt);
    }
  } catch {
    // ignore — form just won't have options
  }
}

function renderJobs(jobs) {
  jobsListEl.innerHTML = "";
  if (!jobs.length) {
    jobsStatusEl.textContent = "No jobs saved yet. Add one above, or use \"Tailor CV for this job\" on the Job Search page.";
    return;
  }
  jobsStatusEl.textContent = "";
  for (const job of jobs) {
    const li = document.createElement("li");
    li.className = "entry-card";
    const title = document.createElement("h3");
    title.textContent = job.title;
    li.appendChild(title);

    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = [job.company, job.location].filter(Boolean).join(" — ") || "No company/location given";
    li.appendChild(meta);

    const controls = document.createElement("div");
    controls.className = "gap-controls";

    const openLink = document.createElement("a");
    openLink.href = `job-detail.html?job_id=${encodeURIComponent(job.id)}`;
    openLink.textContent = "Open";
    openLink.className = "add-entry-btn";
    controls.appendChild(openLink);

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "remove-entry";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", () => deleteJob(job.id, li));
    controls.appendChild(deleteBtn);

    li.appendChild(controls);
    jobsListEl.appendChild(li);
  }
}

async function loadJobs() {
  try {
    const response = await authFetch(`${API_BASE}/api/tailoring/jobs`);
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    const data = await response.json();
    renderJobs(data.jobs);
  } catch (err) {
    jobsStatusEl.textContent = `Error: ${err.message}`;
  }
}

async function deleteJob(jobId, li) {
  try {
    await authFetch(`${API_BASE}/api/tailoring/jobs/${jobId}`, { method: "DELETE" });
  } catch {
    // best-effort
  }
  li.remove();
  if (!jobsListEl.children.length) jobsStatusEl.textContent = "No jobs saved yet.";
}

addJobForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const cvId = addJobCvSelect.value;
  if (!cvId) {
    addJobStatusEl.textContent = "Choose a CV first.";
    return;
  }
  const body = {
    cv_id: cvId,
    title: document.getElementById("add-job-title").value.trim(),
    company: document.getElementById("add-job-company").value.trim() || null,
    location: document.getElementById("add-job-location").value.trim() || null,
    job_url: document.getElementById("add-job-url").value.trim() || null,
    description: document.getElementById("add-job-description").value.trim() || null,
  };
  addJobStatusEl.textContent = "Analyzing job posting…";
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
    const job = await response.json();
    window.location.href = `job-detail.html?job_id=${encodeURIComponent(job.id)}`;
  } catch (err) {
    addJobStatusEl.textContent = `Error: ${err.message}`;
  }
});

loadCvOptions();
loadJobs();
