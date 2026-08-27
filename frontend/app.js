const API_BASE = window.API_BASE || "http://localhost:8000";

const form = document.getElementById("search-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");

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
