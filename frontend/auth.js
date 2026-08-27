// Shared auth helpers, loaded before any other page script.
// Empty string = relative /api/... requests (see app.js for details on why).
const API_BASE = window.API_BASE || "";

const AUTH_TOKEN_KEY = "cvMakerToken";
const AUTH_EMAIL_KEY = "cvMakerEmail";

function getToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

function setSession(token, email) {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
  if (email) localStorage.setItem(AUTH_EMAIL_KEY, email);
}

function clearSession() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_EMAIL_KEY);
}

function getEmail() {
  return localStorage.getItem(AUTH_EMAIL_KEY);
}

// Redirects to the login page if there's no token, remembering where to
// come back to. Call this at the top of any page that requires a login.
function requireAuth() {
  if (!getToken()) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `login.html?next=${next}`;
    return false;
  }
  return true;
}

// Drop-in replacement for fetch() that attaches the auth token and, on a
// 401 (expired/invalid session), clears it and bounces to the login page.
async function authFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    clearSession();
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `login.html?next=${next}`;
  }
  return response;
}

// Fills in the "logged in as ... / Log out" bit of the top nav. Expects an
// element with id="account-bar" in the page's nav.
function renderAccountBar() {
  const bar = document.getElementById("account-bar");
  if (!bar) return;
  const email = getEmail();
  bar.innerHTML = "";
  if (email) {
    const span = document.createElement("span");
    span.className = "account-email";
    span.textContent = email;
    bar.appendChild(span);
  }
  const logoutBtn = document.createElement("button");
  logoutBtn.type = "button";
  logoutBtn.className = "link-btn";
  logoutBtn.textContent = "Log out";
  logoutBtn.addEventListener("click", () => {
    clearSession();
    window.location.href = "login.html";
  });
  bar.appendChild(logoutBtn);
}

document.addEventListener("DOMContentLoaded", renderAccountBar);
