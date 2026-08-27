const API_BASE = window.API_BASE || "";

const form = document.getElementById("cv-upload-form");
const fileInput = document.getElementById("cv-file");
const statusEl = document.getElementById("cv-status");
const profileEl = document.getElementById("cv-profile");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  profileEl.hidden = true;
  profileEl.innerHTML = "";
  statusEl.textContent = "Extracting your CV… this can take up to a minute.";

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch(`${API_BASE}/api/cv/upload`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    const data = await response.json();
    statusEl.textContent = `Extracted from ${data.filename}.`;
    renderProfile(data.profile);
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
});

function renderProfile(profile) {
  const contact = profile.contact || {};
  const contactLine = [contact.email, contact.phone, contact.location]
    .filter(Boolean)
    .map(escapeHtml)
    .join(" · ");

  profileEl.innerHTML = `
    <h2>${escapeHtml(contact.name || "Contact")}</h2>
    ${contactLine ? `<p class="meta">${contactLine}</p>` : ""}
    ${linksLine(contact)}
    ${profile.summary ? `<p>${escapeHtml(profile.summary)}</p>` : ""}

    ${taggedSection("Preferred roles", profile.preferred_roles)}
    ${taggedSection("Skills", profile.skills)}
    ${taggedSection("Technical knowledge", profile.technical_knowledge)}
    ${taggedSection("Certifications", profile.certifications)}

    ${listSection(
      "Work experience",
      (profile.work_experience || []).map(
        (job) => `
        <li>
          <h3>${escapeHtml(job.title)} — ${escapeHtml(job.company)}</h3>
          <p class="meta">${[job.start_date, job.end_date].filter(Boolean).map(escapeHtml).join(" – ")}${
            job.location ? " · " + escapeHtml(job.location) : ""
          }</p>
          ${
            (job.responsibilities || []).length
              ? `<ul>${job.responsibilities.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>`
              : ""
          }
        </li>`
      )
    )}

    ${listSection(
      "Education",
      (profile.education || []).map(
        (edu) => `
        <li>
          <h3>${escapeHtml(edu.degree || "")} ${edu.field_of_study ? "in " + escapeHtml(edu.field_of_study) : ""}</h3>
          <p class="meta">${escapeHtml(edu.institution)}${
            edu.start_date || edu.end_date
              ? " · " + [edu.start_date, edu.end_date].filter(Boolean).map(escapeHtml).join(" – ")
              : ""
          }</p>
          ${edu.details ? `<p>${escapeHtml(edu.details)}</p>` : ""}
        </li>`
      )
    )}

    ${listSection(
      "Languages",
      (profile.languages || []).map(
        (lang) => `<li>${escapeHtml(lang.name)}${lang.proficiency ? " — " + escapeHtml(lang.proficiency) : ""}</li>`
      )
    )}
  `;
  profileEl.hidden = false;
}

function linksLine(contact) {
  const links = [
    contact.linkedin && { label: "LinkedIn", url: contact.linkedin },
    contact.website && { label: "Website", url: contact.website },
  ].filter(Boolean);
  if (!links.length) return "";
  return `<p class="meta">${links
    .map((l) => `<a href="${escapeAttr(l.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(l.label)}</a>`)
    .join(" · ")}</p>`;
}

function taggedSection(title, items) {
  if (!items || !items.length) return "";
  return `
    <h2>${escapeHtml(title)}</h2>
    <div class="tags">${items.map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}</div>
  `;
}

function listSection(title, itemsHtml) {
  if (!itemsHtml.length) return "";
  return `
    <h2>${escapeHtml(title)}</h2>
    <ul class="entry-list">${itemsHtml.join("")}</ul>
  `;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/"/g, "&quot;");
}
