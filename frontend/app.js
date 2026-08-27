const API_BASE = window.API_BASE || "http://localhost:8000";

const form = document.getElementById("search-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const searchTerm = document.getElementById("search-term").value.trim();
  const location = document.getElementById("location").value.trim();
  const siteName = document.getElementById("site-name").value;

  resultsEl.innerHTML = "";
  statusEl.textContent = "Searching...";

  const params = new URLSearchParams({
    search_term: searchTerm,
    site_name: siteName,
  });
  if (location) params.set("location", location);

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

    li.innerHTML = `
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(company)}${location ? " — " + escapeHtml(location) : ""}</p>
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
