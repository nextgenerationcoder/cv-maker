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

// Matches each stage to an accent color used on the column's top bar and
// its cards, so status is readable at a glance without reading the label.
const COLUMN_COLORS = {
  positions: "#9ca3af",
  cv_made: "#0891b2",
  sop_and_cv_made: "#7c3aed",
  applied: "#d97706",
  interview: "#2563eb",
  rejected: "#dc2626",
  ignored: "#6b7280",
};

const boardEl = document.getElementById("board");
const boardStatusEl = document.getElementById("board-status");

let columns = Object.keys(COLUMN_LABELS);
let jobsByStatus = {};
let draggedJobId = null;
const collapsedColumns = new Set();

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
  card.style.setProperty("--accent", COLUMN_COLORS[job.status] || "#9ca3af");

  card.addEventListener("dragstart", () => {
    draggedJobId = job.id;
    card.classList.add("dragging");
  });
  card.addEventListener("dragend", () => card.classList.remove("dragging"));

  const bar = document.createElement("div");
  bar.className = "board-card-bar";
  const idChip = document.createElement("span");
  idChip.className = "board-card-id";
  idChip.textContent = job.id.slice(0, 4).toUpperCase();
  bar.appendChild(idChip);
  card.appendChild(bar);

  const body = document.createElement("div");
  body.className = "board-card-body";
  card.appendChild(body);

  const title = document.createElement("h4");
  title.textContent = job.title;
  body.appendChild(title);

  const meta = document.createElement("p");
  meta.className = "meta";
  meta.textContent = [job.company, job.location].filter(Boolean).join(" — ") || "No company/location";
  body.appendChild(meta);

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
  body.appendChild(badges);

  const moveRow = document.createElement("div");
  moveRow.className = "board-card-moves";
  const currentIndex = columns.indexOf(job.status);
  if (currentIndex > 0) {
    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "board-btn board-btn-move";
    prevBtn.title = "Move to " + COLUMN_LABELS[columns[currentIndex - 1]];
    prevBtn.innerHTML = `<span aria-hidden="true">←</span> ${COLUMN_LABELS[columns[currentIndex - 1]]}`;
    prevBtn.addEventListener("click", () => moveJob(job.id, columns[currentIndex - 1]));
    moveRow.appendChild(prevBtn);
  } else {
    moveRow.appendChild(document.createElement("span"));
  }
  if (currentIndex < columns.length - 1 && currentIndex >= 0) {
    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "board-btn board-btn-move";
    nextBtn.title = "Move to " + COLUMN_LABELS[columns[currentIndex + 1]];
    nextBtn.innerHTML = `${COLUMN_LABELS[columns[currentIndex + 1]]} <span aria-hidden="true">→</span>`;
    nextBtn.addEventListener("click", () => moveJob(job.id, columns[currentIndex + 1]));
    moveRow.appendChild(nextBtn);
  }
  body.appendChild(moveRow);

  const actionRow = document.createElement("div");
  actionRow.className = "board-card-actions";

  const notesToggle = document.createElement("button");
  notesToggle.type = "button";
  notesToggle.className = "board-btn board-btn-ghost";
  notesToggle.textContent = job.board_notes ? "📝 Notes" : "+ Notes";
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
  actionRow.appendChild(notesToggle);

  const openLink = document.createElement("a");
  openLink.href = `job-detail.html?job_id=${encodeURIComponent(job.id)}`;
  openLink.textContent = "Open";
  openLink.className = "board-btn board-btn-primary";
  actionRow.appendChild(openLink);

  body.appendChild(actionRow);
  body.appendChild(notesArea);

  return card;
}

function renderBoard() {
  boardEl.innerHTML = "";
  for (const status of columns) {
    const jobs = jobsByStatus[status] || [];
    const collapsed = collapsedColumns.has(status);
    const accent = COLUMN_COLORS[status] || "#9ca3af";

    const column = document.createElement("section");
    column.className = "board-column" + (collapsed ? " collapsed" : "");
    column.dataset.status = status;
    column.style.setProperty("--accent", accent);

    const header = document.createElement("div");
    header.className = "board-column-header";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "board-column-toggle";
    toggle.setAttribute("aria-label", collapsed ? "Expand column" : "Collapse column");
    toggle.textContent = collapsed ? "›" : "⌄";
    toggle.addEventListener("click", () => {
      if (collapsed) collapsedColumns.delete(status);
      else collapsedColumns.add(status);
      renderBoard();
    });
    header.appendChild(toggle);

    const heading = document.createElement("h3");
    heading.textContent = COLUMN_LABELS[status] || status;
    header.appendChild(heading);

    const count = document.createElement("span");
    count.className = "board-column-count";
    count.textContent = jobs.length;
    header.appendChild(count);
    column.appendChild(header);

    if (collapsed) {
      const collapsedLabel = document.createElement("button");
      collapsedLabel.type = "button";
      collapsedLabel.className = "board-column-collapsed-label";
      collapsedLabel.textContent = `${COLUMN_LABELS[status] || status} (${jobs.length})`;
      collapsedLabel.addEventListener("click", () => {
        collapsedColumns.delete(status);
        renderBoard();
      });
      column.appendChild(collapsedLabel);
    } else {
      const cardsWrap = document.createElement("div");
      cardsWrap.className = "board-column-cards";
      for (const job of jobs) cardsWrap.appendChild(buildCard(job));
      column.appendChild(cardsWrap);
    }

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
