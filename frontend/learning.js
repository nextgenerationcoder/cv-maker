// API_BASE and authFetch come from auth.js, loaded before this script.
const LAST_CV_ID_KEY = "cvMakerLastCvId";

const cvSelectEl = document.getElementById("learning-cv-select");
const statusEl = document.getElementById("learning-status");
const listEl = document.getElementById("learning-list");

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}

async function loadCvOptions() {
  try {
    const response = await authFetch(`${API_BASE}/api/cv?limit=50`);
    if (!response.ok) return [];
    const data = await response.json();
    cvSelectEl.innerHTML = "";
    if (!data.cvs.length) {
      const opt = document.createElement("option");
      opt.textContent = "No saved CV yet — add one on the Upload CV page";
      opt.disabled = true;
      opt.selected = true;
      cvSelectEl.appendChild(opt);
      return [];
    }
    for (const cv of data.cvs) {
      const opt = document.createElement("option");
      opt.value = cv.id;
      opt.textContent = cv.filename;
      cvSelectEl.appendChild(opt);
    }
    const lastId = localStorage.getItem(LAST_CV_ID_KEY);
    if (lastId && data.cvs.some((cv) => cv.id === lastId)) {
      cvSelectEl.value = lastId;
    }
    return data.cvs;
  } catch {
    return [];
  }
}

function renderList(items) {
  listEl.innerHTML = "";
  if (!items.length) {
    const li = document.createElement("li");
    li.textContent = "Nothing tracked yet — nice, or you haven't checked any job matches.";
    listEl.appendChild(li);
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");

    const h3 = document.createElement("h3");
    h3.textContent = item.text;
    li.appendChild(h3);

    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = `Seen ${item.occurrences}x — first flagged ${formatDate(
      item.first_flagged_at
    )}, last flagged ${formatDate(item.last_flagged_at)}`;
    li.appendChild(meta);

    const controls = document.createElement("div");
    controls.className = "gap-controls";

    const learnedBtn = document.createElement("button");
    learnedBtn.type = "button";
    learnedBtn.className = "add-entry-btn";
    learnedBtn.textContent = "Learned it — add to CV";
    learnedBtn.addEventListener("click", () => promoteToCv(item, li));
    controls.appendChild(learnedBtn);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "remove-entry";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => removeItem(item.id, li));
    controls.appendChild(removeBtn);

    li.appendChild(controls);
    listEl.appendChild(li);
  }
}

async function loadLearning() {
  const cvId = cvSelectEl.value;
  if (!cvId) {
    listEl.innerHTML = "";
    return;
  }
  statusEl.textContent = "Loading…";
  try {
    const response = await authFetch(`${API_BASE}/api/cv/${cvId}/learning`);
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    const data = await response.json();
    renderList(data.items);
    statusEl.textContent = "";
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
}

async function removeItem(itemId, li) {
  const cvId = cvSelectEl.value;
  try {
    await authFetch(`${API_BASE}/api/cv/${cvId}/learning/${itemId}`, { method: "DELETE" });
  } catch {
    // best-effort — remove from view regardless
  }
  li.remove();
  if (!listEl.children.length) renderList([]);
}

async function promoteToCv(item, li) {
  const cvId = cvSelectEl.value;
  const category = window.prompt(
    "Which tool category should this go under?",
    "ai_automation"
  );
  if (!category) return;

  try {
    const response = await authFetch(`${API_BASE}/api/cv/${cvId}`);
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    const record = await response.json();
    const profile = record.profile;
    profile.tools = profile.tools || {};
    profile.tools[category] = profile.tools[category] || [];
    profile.tools[category].push({ name: item.text, level: null });

    const putResponse = await authFetch(`${API_BASE}/api/cv/${cvId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, filename: record.filename }),
    });
    if (!putResponse.ok) throw new Error(`Request failed with ${putResponse.status}`);

    await removeItem(item.id, li);
    statusEl.textContent = `Added "${item.text}" to your CV under "${category}".`;
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
}

cvSelectEl.addEventListener("change", loadLearning);

(async function init() {
  await loadCvOptions();
  await loadLearning();
})();
