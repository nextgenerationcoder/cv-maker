// API_BASE and authFetch come from auth.js, loaded before this script.

const COLUMN_LABELS = {
  positions: "Positions",
  cv_made: "CV made",
  sop_and_cv_made: "SOP and CV made",
  applied: "Applied",
  interview: "Interview",
  rejected: "Rejected",
  ignored: "Ignored",
};

const boardEl = document.getElementById("board");
const boardStatusEl = document.getElementById("board-status");

let columns = Object.keys(COLUMN_LABELS);
let jobsByStatus = {};
let draggedJobId = null;

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return "";
  }
}

function buildCard(job) {
  const card = document.createElement("article");
  card.className = "board-card";
  card.draggable = true;
  card.dataset.jobId = job.id;

  card.addEventListener("dragstart", () => {
    draggedJobId = job.id;
    card.classList.add("dragging");
  });
  card.addEventListener("dragend", () => card.classList.remove("dragging"));

  const title = document.createElement("h4");
  title.textContent = job.title;
  card.appendChild(title);

  const meta = document.createElement("p");
  meta.className = "meta";
  meta.textContent = [job.company, job.location].filter(Boolean).join(" — ") || "No company/location";
  card.appendChild(meta);

  const badges = document.createElement("div");
  badges.className = "board-card-badges";
  if (job.has_tailored_cv) {
    const badge = document.createElement("span");
    badge.className = "board-badge";
    badge.textContent = "Tailored CV ready";
    badges.appendChild(badge);
  }
  const updated = document.createElement("span");
  updated.className = "board-card-date";
  updated.textContent = formatDate(job.updated_at);
  badges.appendChild(updated);
  card.appendChild(badges);

  const openLink = document.createElement("a");
  openLink.href = `job-detail.html?job_id=${encodeURIComponent(job.id)}`;
  openLink.textContent = "Open →";
  openLink.className = "board-card-open";
  card.appendChild(openLink);

  const moveRow = document.createElement("div");
  moveRow.className = "board-card-moves";
  const currentIndex = columns.indexOf(job.status);
  if (currentIndex > 0) {
    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "link-btn";
    prevBtn.textContent = "← " + COLUMN_LABELS[columns[currentIndex - 1]];
    prevBtn.addEventListener("click", () => moveJob(job.id, columns[currentIndex - 1]));
    moveRow.appendChild(prevBtn);
  }
  if (currentIndex < columns.length - 1 && currentIndex >= 0) {
    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "link-btn";
    nextBtn.textContent = COLUMN_LABELS[columns[currentIndex + 1]] + " →";
    nextBtn.addEventListener("click", () => moveJob(job.id, columns[currentIndex + 1]));
    moveRow.appendChild(nextBtn);
  }
  card.appendChild(moveRow);

  const notesToggle = document.createElement("button");
  notesToggle.type = "button";
  notesToggle.className = "link-btn";
  notesToggle.textContent = job.board_notes ? "Edit notes" : "+ Add notes";
  const notesArea = document.createElement("textarea");
  notesArea.className = "board-card-notes";
  notesArea.rows = 3;
  notesArea.placeholder = "Notes for this application…";
  notesArea.value = job.board_notes || "";
  notesArea.hidden = true;
  notesArea.addEventListener("blur", () => saveNotes(job.id, notesArea.value));
  notesToggle.addEventListener("click", () => {
    notesArea.hidden = !notesArea.hidden;
    if (!notesArea.hidden) notesArea.focus();
  });
  card.appendChild(notesToggle);
  card.appendChild(notesArea);

  return card;
}

function renderBoard() {
  boardEl.innerHTML = "";
  for (const status of columns) {
    const column = document.createElement("section");
    column.className = "board-column";
    column.dataset.status = status;

    const header = document.createElement("div");
    header.className = "board-column-header";
    const heading = document.createElement("h3");
    heading.textContent = COLUMN_LABELS[status] || status;
    header.appendChild(heading);
    const count = document.createElement("span");
    count.className = "board-column-count";
    const jobs = jobsByStatus[status] || [];
    count.textContent = jobs.length;
    header.appendChild(count);
    column.appendChild(header);

    const cardsWrap = document.createElement("div");
    cardsWrap.className = "board-column-cards";
    for (const job of jobs) cardsWrap.appendChild(buildCard(job));
    column.appendChild(cardsWrap);

    column.addEventListener("dragover", (event) => {
      event.preventDefault();
      column.classList.add("drag-over");
    });
    column.addEventListener("dragleave", () => column.classList.remove("drag-over"));
    column.addEventListener("drop", (event) => {
      event.preventDefault();
      column.classList.remove("drag-over");
      if (draggedJobId) moveJob(draggedJobId, status);
      draggedJobId = null;
    });

    boardEl.appendChild(column);
  }

  if (!Object.values(jobsByStatus).some((list) => list.length)) {
    boardStatusEl.textContent = "No jobs saved yet. Add one from the Tailored CVs page or Job Search.";
  } else {
    boardStatusEl.textContent = "";
  }
}

function groupJobs(jobs) {
  const grouped = {};
  for (const status of columns) grouped[status] = [];
  for (const job of jobs) {
    const status = columns.includes(job.status) ? job.status : "positions";
    grouped[status].push(job);
  }
  return grouped;
}

async function loadBoard() {
  try {
    const response = await authFetch(`${API_BASE}/api/tailoring/board`);
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    const data = await response.json();
    if (Array.isArray(data.columns) && data.columns.length) columns = data.columns;
    jobsByStatus = groupJobs(data.jobs);
    renderBoard();
  } catch (err) {
    boardStatusEl.textContent = `Error: ${err.message}`;
  }
}

async function moveJob(jobId, newStatus) {
  let movedJob = null;
  for (const status of columns) {
    const list = jobsByStatus[status] || [];
    const idx = list.findIndex((j) => j.id === jobId);
    if (idx !== -1) {
      movedJob = list[idx];
      list.splice(idx, 1);
      break;
    }
  }
  if (!movedJob) return;
  movedJob.status = newStatus;
  jobsByStatus[newStatus] = jobsByStatus[newStatus] || [];
  jobsByStatus[newStatus].unshift(movedJob);
  renderBoard();

  try {
    const response = await authFetch(`${API_BASE}/api/tailoring/jobs/${jobId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
  } catch (err) {
    boardStatusEl.textContent = `Couldn't save the move: ${err.message}. Reloading…`;
    loadBoard();
  }
}

async function saveNotes(jobId, notes) {
  try {
    await authFetch(`${API_BASE}/api/tailoring/jobs/${jobId}/notes`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: notes || null }),
    });
  } catch {
    // best-effort
  }
}

loadBoard();
