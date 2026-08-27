// Empty string = relative /api/... requests, correct when served through the
// nginx container (docker-compose), which proxies /api/ to the backend. For
// running standalone against a bare `uvicorn` on port 8000, set
// window.API_BASE = "http://localhost:8000" before this script loads.
const API_BASE = window.API_BASE || "";

const uploadForm = document.getElementById("cv-upload-form");
const fileInput = document.getElementById("cv-file");
const statusEl = document.getElementById("cv-status");
const warningsEl = document.getElementById("cv-warnings");
const downloadTemplateLink = document.getElementById("download-template-link");

const editForm = document.getElementById("cv-edit-form");
const saveStatusEl = document.getElementById("save-status");
const exportCsvLink = document.getElementById("export-csv-link");
const workEntriesEl = document.getElementById("work-entries");
const educationEntriesEl = document.getElementById("education-entries");
const languageEntriesEl = document.getElementById("language-entries");

let currentCvId = null;

downloadTemplateLink.href = `${API_BASE}/api/cv/template.csv`;

const WORK_FIELDS = [
  { key: "title", label: "Title", required: true },
  { key: "company", label: "Company", required: true },
  { key: "start_date", label: "Start date" },
  { key: "end_date", label: "End date" },
  { key: "location", label: "Location" },
  { key: "responsibilities", label: "Responsibilities (one per line)", type: "textarea", list: true },
];

const EDUCATION_FIELDS = [
  { key: "institution", label: "Institution", required: true },
  { key: "degree", label: "Degree" },
  { key: "field_of_study", label: "Field of study" },
  { key: "start_date", label: "Start date" },
  { key: "end_date", label: "End date" },
  { key: "details", label: "Details", type: "textarea" },
];

const LANGUAGE_FIELDS = [
  { key: "name", label: "Language", required: true },
  { key: "proficiency", label: "Proficiency" },
];

function makeEntryCard(fieldsSpec, values) {
  const card = document.createElement("div");
  card.className = "entry-card";
  for (const f of fieldsSpec) {
    const label = document.createElement("label");
    label.className = "field";
    const span = document.createElement("span");
    span.textContent = f.label;
    label.appendChild(span);

    const input = document.createElement(f.type === "textarea" ? "textarea" : "input");
    if (f.type !== "textarea") input.type = "text";
    const raw = values ? values[f.key] : undefined;
    input.value = f.list ? (raw || []).join("\n") : raw || "";
    input.dataset.key = f.key;
    label.appendChild(input);
    card.appendChild(label);
  }

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "remove-entry";
  removeBtn.textContent = "Remove";
  removeBtn.addEventListener("click", () => card.remove());
  card.appendChild(removeBtn);

  return card;
}

function renderEntrySection(container, fieldsSpec, entries) {
  container.innerHTML = "";
  for (const values of entries || []) {
    container.appendChild(makeEntryCard(fieldsSpec, values));
  }
}

function readEntrySection(container, fieldsSpec) {
  return Array.from(container.querySelectorAll(".entry-card")).map((card) => {
    const obj = {};
    for (const f of fieldsSpec) {
      const input = card.querySelector(`[data-key="${f.key}"]`);
      const value = input.value;
      if (f.list) {
        obj[f.key] = value
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean);
      } else {
        const trimmed = value.trim();
        obj[f.key] = trimmed || (f.required ? "" : null);
      }
    }
    return obj;
  });
}

function fillTextField(dataField, value) {
  const el = editForm.querySelector(`[data-field="${dataField}"]`);
  el.value = value || "";
}

function fillListField(dataField, values) {
  const el = editForm.querySelector(`[data-field="${dataField}"]`);
  el.value = (values || []).join("\n");
}

function readTextField(dataField) {
  const el = editForm.querySelector(`[data-field="${dataField}"]`);
  return el.value.trim() || null;
}

function readListField(dataField) {
  const el = editForm.querySelector(`[data-field="${dataField}"]`);
  return el.value
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

function loadProfileIntoForm(filename, profile) {
  fillTextField("filename", filename);
  const contact = profile.contact || {};
  fillTextField("contact.name", contact.name);
  fillTextField("contact.email", contact.email);
  fillTextField("contact.phone", contact.phone);
  fillTextField("contact.location", contact.location);
  fillTextField("contact.linkedin", contact.linkedin);
  fillTextField("contact.website", contact.website);
  fillTextField("summary", profile.summary);
  fillListField("preferred_roles", profile.preferred_roles);
  fillListField("skills", profile.skills);
  fillListField("technical_knowledge", profile.technical_knowledge);
  fillListField("certifications", profile.certifications);

  renderEntrySection(workEntriesEl, WORK_FIELDS, profile.work_experience);
  renderEntrySection(educationEntriesEl, EDUCATION_FIELDS, profile.education);
  renderEntrySection(languageEntriesEl, LANGUAGE_FIELDS, profile.languages);

  editForm.hidden = false;
}

function buildProfileFromForm() {
  return {
    contact: {
      name: readTextField("contact.name"),
      email: readTextField("contact.email"),
      phone: readTextField("contact.phone"),
      location: readTextField("contact.location"),
      linkedin: readTextField("contact.linkedin"),
      website: readTextField("contact.website"),
    },
    summary: readTextField("summary"),
    preferred_roles: readListField("preferred_roles"),
    skills: readListField("skills"),
    technical_knowledge: readListField("technical_knowledge"),
    certifications: readListField("certifications"),
    work_experience: readEntrySection(workEntriesEl, WORK_FIELDS),
    education: readEntrySection(educationEntriesEl, EDUCATION_FIELDS),
    languages: readEntrySection(languageEntriesEl, LANGUAGE_FIELDS),
  };
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) {
    statusEl.textContent = "Choose a CSV file first.";
    return;
  }

  statusEl.textContent = "Importing…";
  warningsEl.hidden = true;
  warningsEl.innerHTML = "";
  editForm.hidden = true;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch(`${API_BASE}/api/cv/import-csv`, { method: "POST", body: formData });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    const data = await response.json();
    currentCvId = data.id;
    statusEl.textContent = `Imported ${data.filename}. Review and edit below, then save.`;
    if (data.warnings && data.warnings.length) {
      warningsEl.hidden = false;
      for (const w of data.warnings) {
        const li = document.createElement("li");
        li.textContent = w;
        warningsEl.appendChild(li);
      }
    }
    loadProfileIntoForm(data.filename, data.profile);
    exportCsvLink.href = `${API_BASE}/api/cv/${currentCvId}/export.csv`;
    exportCsvLink.hidden = false;
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
});

for (const btn of document.querySelectorAll(".add-entry-btn")) {
  btn.addEventListener("click", () => {
    const kind = btn.dataset.add;
    if (kind === "work") workEntriesEl.appendChild(makeEntryCard(WORK_FIELDS, {}));
    if (kind === "education") educationEntriesEl.appendChild(makeEntryCard(EDUCATION_FIELDS, {}));
    if (kind === "language") languageEntriesEl.appendChild(makeEntryCard(LANGUAGE_FIELDS, {}));
  });
}

editForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentCvId) {
    saveStatusEl.textContent = "Import a CSV first.";
    return;
  }
  saveStatusEl.textContent = "Saving…";

  const filename = readTextField("filename") || "Untitled CV";
  const profile = buildProfileFromForm();

  try {
    const response = await fetch(`${API_BASE}/api/cv/${currentCvId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, filename }),
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    saveStatusEl.textContent = "Saved.";
    exportCsvLink.href = `${API_BASE}/api/cv/${currentCvId}/export.csv`;
    exportCsvLink.hidden = false;
  } catch (err) {
    saveStatusEl.textContent = `Error: ${err.message}`;
  }
});
