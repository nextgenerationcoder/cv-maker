// API_BASE and authFetch come from auth.js, loaded before this script.

const uploadForm = document.getElementById("cv-upload-form");
const fileInput = document.getElementById("cv-file");
const statusEl = document.getElementById("cv-status");
const downloadTemplateLink = document.getElementById("download-template-link");

const editForm = document.getElementById("cv-edit-form");
const saveStatusEl = document.getElementById("save-status");
const exportJsonLink = document.getElementById("export-json-link");
const workEntriesEl = document.getElementById("work-entries");
const educationEntriesEl = document.getElementById("education-entries");
const trainingEntriesEl = document.getElementById("training-entries");
const languageEntriesEl = document.getElementById("language-entries");
const toolsContainerEl = document.getElementById("tools-container");

let currentCvId = null;
const LAST_CV_ID_KEY = "cvMakerLastCvId";

downloadTemplateLink.href = `${API_BASE}/api/cv/template.json`;

// ---------- generic helpers ----------

function splitCommaList(value) {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function addField(card, key, label, value, type = "text") {
  const wrap = document.createElement("label");
  wrap.className = "field";
  const span = document.createElement("span");
  span.textContent = label;
  wrap.appendChild(span);
  const input = document.createElement(type === "textarea" ? "textarea" : "input");
  if (type !== "textarea") input.type = "text";
  input.dataset.key = key;
  input.value = value || "";
  wrap.appendChild(input);
  card.appendChild(wrap);
  return input;
}

function readField(card, key) {
  const el = card.querySelector(`[data-key="${key}"]`);
  return el.value.trim();
}

function addRemoveButton(el, label = "Remove") {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "remove-entry";
  btn.textContent = label;
  btn.addEventListener("click", () => el.remove());
  el.appendChild(btn);
  return btn;
}

// ---------- experience bullets (nested inside work/education/training) ----------

function makeExperienceItem(values) {
  const div = document.createElement("div");
  div.className = "experience-item";

  const bullet = document.createElement("textarea");
  bullet.className = "exp-bullet";
  bullet.rows = 2;
  bullet.placeholder = "Bullet point";
  bullet.value = values?.bullet || "";
  div.appendChild(bullet);

  const skills = document.createElement("input");
  skills.type = "text";
  skills.className = "exp-skills";
  skills.placeholder = "Skills (comma-separated)";
  skills.value = (values?.skills || []).join(", ");
  div.appendChild(skills);

  const metrics = document.createElement("input");
  metrics.type = "text";
  metrics.className = "exp-metrics";
  metrics.placeholder = "Metrics (comma-separated)";
  metrics.value = (values?.metrics || []).join(", ");
  div.appendChild(metrics);

  addRemoveButton(div, "Remove bullet");
  return div;
}

function renderExperiences(container, experiences) {
  container.innerHTML = "";
  for (const values of experiences || []) {
    container.appendChild(makeExperienceItem(values));
  }
}

function readExperiences(container) {
  return Array.from(container.querySelectorAll(".experience-item")).map((div) => ({
    bullet: div.querySelector(".exp-bullet").value.trim(),
    skills: splitCommaList(div.querySelector(".exp-skills").value),
    metrics: splitCommaList(div.querySelector(".exp-metrics").value),
  }));
}

function appendExperienceSection(card) {
  const heading = document.createElement("h4");
  heading.textContent = "Experience bullets";
  card.appendChild(heading);

  const list = document.createElement("div");
  list.className = "experiences-list";
  card.appendChild(list);

  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "add-entry-btn add-exp-btn";
  addBtn.textContent = "+ Add bullet";
  addBtn.addEventListener("click", () => list.appendChild(makeExperienceItem({})));
  card.appendChild(addBtn);

  return list;
}

// ---------- work / education / training cards ----------

function makeWorkCard(values) {
  const card = document.createElement("div");
  card.className = "entry-card";
  addField(card, "company", "Company", values?.company);
  addField(card, "role", "Role", values?.role);
  addField(card, "period", "Period", values?.period);
  addField(card, "location", "Location", values?.location);
  const expList = appendExperienceSection(card);
  renderExperiences(expList, values?.experiences);
  addRemoveButton(card);
  return card;
}

function readWorkCard(card) {
  return {
    company: readField(card, "company"),
    role: readField(card, "role"),
    period: readField(card, "period"),
    location: readField(card, "location") || null,
    experiences: readExperiences(card.querySelector(".experiences-list")),
  };
}

function makeEducationCard(values) {
  const card = document.createElement("div");
  card.className = "entry-card";
  addField(card, "institution", "Institution", values?.institution);
  addField(card, "program", "Program", values?.program);
  addField(card, "degree", "Degree", values?.degree);
  addField(card, "period", "Period", values?.period);
  addField(card, "location", "Location", values?.location);
  const expList = appendExperienceSection(card);
  renderExperiences(expList, values?.experiences);
  addRemoveButton(card);
  return card;
}

function readEducationCard(card) {
  return {
    institution: readField(card, "institution"),
    program: readField(card, "program"),
    degree: readField(card, "degree") || null,
    period: readField(card, "period"),
    location: readField(card, "location") || null,
    experiences: readExperiences(card.querySelector(".experiences-list")),
  };
}

function makeTrainingCard(values) {
  const card = document.createElement("div");
  card.className = "entry-card";
  addField(card, "title", "Title", values?.title);
  addField(card, "period", "Period", values?.period);
  addField(card, "duration", "Duration", values?.duration);
  const expList = appendExperienceSection(card);
  renderExperiences(expList, values?.experiences);
  addRemoveButton(card);
  return card;
}

function readTrainingCard(card) {
  return {
    title: readField(card, "title"),
    period: readField(card, "period"),
    duration: readField(card, "duration") || null,
    experiences: readExperiences(card.querySelector(".experiences-list")),
  };
}

function renderCards(container, makeCard, entries) {
  container.innerHTML = "";
  for (const values of entries || []) {
    container.appendChild(makeCard(values));
  }
}

function readCards(container, readCard) {
  return Array.from(container.querySelectorAll(":scope > .entry-card")).map(readCard);
}

// ---------- languages ----------

function makeLanguageCard(values) {
  const card = document.createElement("div");
  card.className = "entry-card";
  addField(card, "language", "Language", values?.language);
  addField(card, "level", "Level", values?.level);
  addRemoveButton(card);
  return card;
}

function readLanguageCard(card) {
  return {
    language: readField(card, "language"),
    level: readField(card, "level"),
  };
}

// ---------- tools (dynamic categories) ----------

function makeToolItem(values) {
  const row = document.createElement("div");
  row.className = "tool-item";

  const name = document.createElement("input");
  name.type = "text";
  name.className = "tool-name";
  name.placeholder = "Tool/skill name";
  name.value = values?.name || "";
  row.appendChild(name);

  const level = document.createElement("input");
  level.type = "text";
  level.className = "tool-level";
  level.placeholder = "Level (optional)";
  level.value = values?.level || "";
  row.appendChild(level);

  addRemoveButton(row, "✕");
  return row;
}

function makeToolCategoryBlock(categoryName, items) {
  const block = document.createElement("div");
  block.className = "entry-card tool-category";

  addField(block, "category-name", "Category name (e.g. ai_automation)", categoryName);

  const itemsList = document.createElement("div");
  itemsList.className = "tool-items-list";
  for (const item of items || []) itemsList.appendChild(makeToolItem(item));
  block.appendChild(itemsList);

  const addItemBtn = document.createElement("button");
  addItemBtn.type = "button";
  addItemBtn.className = "add-entry-btn";
  addItemBtn.textContent = "+ Add tool";
  addItemBtn.addEventListener("click", () => itemsList.appendChild(makeToolItem({})));
  block.appendChild(addItemBtn);

  addRemoveButton(block, "Remove category");
  return block;
}

function renderTools(tools) {
  toolsContainerEl.innerHTML = "";
  for (const [category, items] of Object.entries(tools || {})) {
    toolsContainerEl.appendChild(makeToolCategoryBlock(category, items));
  }
}

function readTools() {
  const tools = {};
  for (const block of toolsContainerEl.querySelectorAll(":scope > .tool-category")) {
    const name = readField(block, "category-name");
    if (!name) continue;
    const items = Array.from(block.querySelectorAll(".tool-item"))
      .map((row) => ({
        name: row.querySelector(".tool-name").value.trim(),
        level: row.querySelector(".tool-level").value.trim() || null,
      }))
      .filter((item) => item.name);
    tools[name] = items;
  }
  return tools;
}

// ---------- top-level form load/read ----------

function fillTextField(dataField, value) {
  editForm.querySelector(`[data-field="${dataField}"]`).value = value || "";
}

function readTextField(dataField) {
  const el = editForm.querySelector(`[data-field="${dataField}"]`);
  return el.value.trim() || null;
}

function loadProfileIntoForm(filename, profile) {
  fillTextField("filename", filename);
  const personal = profile.personal_information || {};
  fillTextField("personal.name", personal.name);
  fillTextField("personal.email", personal.email);
  fillTextField("personal.phone", personal.phone);
  fillTextField("personal.location", personal.location);

  renderCards(workEntriesEl, makeWorkCard, profile.work_experience);
  renderCards(educationEntriesEl, makeEducationCard, profile.education);
  renderCards(trainingEntriesEl, makeTrainingCard, profile.training_and_projects);
  renderCards(languageEntriesEl, makeLanguageCard, profile.languages);
  renderTools(profile.tools);

  editForm.hidden = false;
}

function buildProfileFromForm() {
  return {
    personal_information: {
      name: readTextField("personal.name") || "",
      email: readTextField("personal.email") || "",
      phone: readTextField("personal.phone") || "",
      location: readTextField("personal.location"),
    },
    work_experience: readCards(workEntriesEl, readWorkCard),
    education: readCards(educationEntriesEl, readEducationCard),
    training_and_projects: readCards(trainingEntriesEl, readTrainingCard),
    languages: readCards(languageEntriesEl, readLanguageCard),
    tools: readTools(),
  };
}

// ---------- events ----------

document.getElementById("add-work-btn").addEventListener("click", () => {
  workEntriesEl.appendChild(makeWorkCard({}));
});
document.getElementById("add-education-btn").addEventListener("click", () => {
  educationEntriesEl.appendChild(makeEducationCard({}));
});
document.getElementById("add-training-btn").addEventListener("click", () => {
  trainingEntriesEl.appendChild(makeTrainingCard({}));
});
document.getElementById("add-language-btn").addEventListener("click", () => {
  languageEntriesEl.appendChild(makeLanguageCard({}));
});
document.getElementById("add-tool-category-btn").addEventListener("click", () => {
  toolsContainerEl.appendChild(makeToolCategoryBlock("", []));
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) {
    statusEl.textContent = "Choose a JSON file first.";
    return;
  }

  statusEl.textContent = "Importing…";
  editForm.hidden = true;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await authFetch(`${API_BASE}/api/cv/import-json`, { method: "POST", body: formData });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    const data = await response.json();
    currentCvId = data.id;
    localStorage.setItem(LAST_CV_ID_KEY, currentCvId);
    statusEl.textContent = `Imported ${data.filename}. Review and edit below, then save.`;
    loadProfileIntoForm(data.filename, data.profile);
    exportJsonLink.href = `${API_BASE}/api/cv/${currentCvId}/export.json`;
    exportJsonLink.hidden = false;
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
});

editForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentCvId) {
    saveStatusEl.textContent = "Import a JSON file first.";
    return;
  }
  saveStatusEl.textContent = "Saving…";

  const filename = readTextField("filename") || "Untitled CV";
  const profile = buildProfileFromForm();

  try {
    const response = await authFetch(`${API_BASE}/api/cv/${currentCvId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, filename }),
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    saveStatusEl.textContent = "Saved.";
    exportJsonLink.href = `${API_BASE}/api/cv/${currentCvId}/export.json`;
    exportJsonLink.hidden = false;
  } catch (err) {
    saveStatusEl.textContent = `Error: ${err.message}`;
  }
});

// ---------- resume the last-used CV across page visits ----------

(async function resumeLastCv() {
  const lastId = localStorage.getItem(LAST_CV_ID_KEY);
  if (!lastId) return;
  try {
    const response = await authFetch(`${API_BASE}/api/cv/${lastId}`);
    if (!response.ok) {
      localStorage.removeItem(LAST_CV_ID_KEY);
      return;
    }
    const record = await response.json();
    currentCvId = record.id;
    statusEl.textContent = `Resumed "${record.filename}" from your last visit.`;
    loadProfileIntoForm(record.filename, record.profile);
    exportJsonLink.href = `${API_BASE}/api/cv/${currentCvId}/export.json`;
    exportJsonLink.hidden = false;
  } catch {
    // offline or backend unreachable — just leave the page in its default empty state
  }
})();
