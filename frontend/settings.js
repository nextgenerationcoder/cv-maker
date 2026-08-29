// API_BASE and authFetch come from auth.js, loaded before this script.

const settingsForm = document.getElementById("settings-form");
const providerSelect = document.getElementById("provider-select");
const apiKeyInput = document.getElementById("api-key-input");
const keyStatusEl = document.getElementById("key-status");
const settingsStatusEl = document.getElementById("settings-status");
const removeKeyBtn = document.getElementById("remove-key-btn");

function renderSettings(data) {
  providerSelect.value = data.llm_provider;
  apiKeyInput.value = "";
  keyStatusEl.textContent = data.has_api_key
    ? `Saved key: ${data.api_key_preview}`
    : "No API key saved for this provider yet.";
  removeKeyBtn.hidden = !data.has_api_key;
}

async function loadSettings() {
  try {
    const response = await authFetch(`${API_BASE}/api/settings`);
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    renderSettings(await response.json());
  } catch (err) {
    settingsStatusEl.textContent = `Error: ${err.message}`;
  }
}

settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  settingsStatusEl.textContent = "Saving…";
  const body = { llm_provider: providerSelect.value };
  if (apiKeyInput.value) body.api_key = apiKeyInput.value;

  try {
    const response = await authFetch(`${API_BASE}/api/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with ${response.status}`);
    }
    renderSettings(await response.json());
    settingsStatusEl.textContent = "Saved.";
  } catch (err) {
    settingsStatusEl.textContent = `Error: ${err.message}`;
  }
});

removeKeyBtn.addEventListener("click", async () => {
  settingsStatusEl.textContent = "Removing…";
  try {
    const response = await authFetch(`${API_BASE}/api/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ llm_provider: providerSelect.value, api_key: "" }),
    });
    if (!response.ok) throw new Error(`Request failed with ${response.status}`);
    renderSettings(await response.json());
    settingsStatusEl.textContent = "Removed.";
  } catch (err) {
    settingsStatusEl.textContent = `Error: ${err.message}`;
  }
});

loadSettings();

// ---------- change password ----------

const passwordForm = document.getElementById("password-form");
const currentPasswordInput = document.getElementById("current-password-input");
const newPasswordInput = document.getElementById("new-password-input");
const passwordStatusEl = document.getElementById("password-status");

passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  passwordStatusEl.textContent = "Changing…";

  try {
    const response = await authFetch(`${API_BASE}/api/auth/change-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: currentPasswordInput.value,
        new_password: newPasswordInput.value,
      }),
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      const detail = Array.isArray(errorBody.detail)
        ? errorBody.detail.map((d) => d.msg).join(" ")
        : errorBody.detail;
      throw new Error(detail || `Request failed with ${response.status}`);
    }
    passwordForm.reset();
    passwordStatusEl.textContent = "Changed.";
  } catch (err) {
    passwordStatusEl.textContent = `Error: ${err.message}`;
  }
});
