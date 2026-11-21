const API_BASE = "/api/v1/admin";
const TOKEN_KEY = "ebobo_admin_token";

const loginView = document.getElementById("login-view");
const dashboardView = document.getElementById("dashboard-view");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const logoutBtn = document.getElementById("logout-btn");
const welcomeText = document.getElementById("welcome-text");
const modulesContainer = document.getElementById("modules");

function getToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

function showLogin(message) {
  loginView.classList.remove("hidden");
  dashboardView.classList.add("hidden");
  logoutBtn.classList.add("hidden");
  if (message) {
    loginError.textContent = message;
    loginError.classList.remove("hidden");
  } else {
    loginError.classList.add("hidden");
  }
}

function showDashboard() {
  loginView.classList.add("hidden");
  dashboardView.classList.remove("hidden");
  logoutBtn.classList.remove("hidden");
}

async function authedFetch(path, options = {}) {
  const token = getToken();
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  });
  if (response.status === 401) {
    clearToken();
    showLogin("Sesja wygasła, zaloguj się ponownie.");
    throw new Error("unauthorized");
  }
  return response;
}

function renderModules(modules) {
  modulesContainer.innerHTML = "";
  for (const module of modules) {
    const card = document.createElement("div");
    card.className = "module-card";
    card.innerHTML = `
      <h2>${module.label}</h2>
      <span class="status-badge">${module.status}</span>
    `;
    modulesContainer.appendChild(card);
  }
}

async function loadDashboard() {
  try {
    const [meResponse, dashboardResponse] = await Promise.all([
      authedFetch("/me"),
      authedFetch("/dashboard"),
    ]);
    const me = await meResponse.json();
    const dashboard = await dashboardResponse.json();

    welcomeText.textContent = `Zalogowano jako: ${me.username}. ${dashboard.message}`;
    renderModules(dashboard.modules || []);
    showDashboard();
  } catch (err) {
    if (err.message !== "unauthorized") {
      showLogin("Nie udało się pobrać danych panelu.");
    }
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  try {
    const response = await fetch(`${API_BASE}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      showLogin(body.detail || "Nieprawidłowy login lub hasło.");
      return;
    }

    const data = await response.json();
    setToken(data.access_token);
    await loadDashboard();
  } catch (err) {
    showLogin("Błąd połączenia z API.");
  }
});

logoutBtn.addEventListener("click", () => {
  clearToken();
  showLogin();
});

if (getToken()) {
  loadDashboard();
} else {
  showLogin();
}
