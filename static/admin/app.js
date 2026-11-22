const API_BASE = "/api/v1/admin";
const TOKEN_KEY = "ebobo_admin_token";

const loginView = document.getElementById("login-view");
const dashboardView = document.getElementById("dashboard-view");
const requestsView = document.getElementById("requests-view");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const logoutBtn = document.getElementById("logout-btn");
const welcomeText = document.getElementById("welcome-text");
const modulesContainer = document.getElementById("modules");
const requestsBackBtn = document.getElementById("requests-back-btn");
const requestsFilter = document.getElementById("requests-filter");
const requestsTableBody = document.getElementById("requests-table-body");
const requestsEmpty = document.getElementById("requests-empty");
const requestsDetail = document.getElementById("requests-detail");
const requestsDetailId = document.getElementById("requests-detail-id");
const requestsDetailRequest = document.getElementById("requests-detail-request");
const requestsDetailResponse = document.getElementById("requests-detail-response");

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
  requestsView.classList.add("hidden");
  logoutBtn.classList.remove("hidden");
}

function showRequestsView() {
  loginView.classList.add("hidden");
  dashboardView.classList.add("hidden");
  requestsView.classList.remove("hidden");
  logoutBtn.classList.remove("hidden");
  requestsDetail.classList.add("hidden");
  loadRequestsList();
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
    if (module.key === "submissions" && module.status === "available") {
      card.classList.add("module-card--clickable");
      card.addEventListener("click", showRequestsView);
    }
    modulesContainer.appendChild(card);
  }
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleString("pl-PL");
}

async function loadRequestsList() {
  requestsDetail.classList.add("hidden");
  const benefitCode = requestsFilter.value.trim();
  const query = benefitCode ? `?benefit_code=${encodeURIComponent(benefitCode)}` : "";
  try {
    const response = await authedFetch(`/request-log${query}`);
    const entries = await response.json();
    requestsTableBody.innerHTML = "";
    requestsEmpty.classList.toggle("hidden", entries.length > 0);
    for (const entry of entries) {
      const row = document.createElement("tr");
      row.className = "requests-table__row";
      row.innerHTML = `
        <td>${formatDate(entry.created_at)}</td>
        <td>${entry.endpoint}</td>
        <td>${entry.benefit_code || "-"}</td>
        <td>${entry.status_code}</td>
      `;
      row.addEventListener("click", () => loadRequestDetail(entry.id));
      requestsTableBody.appendChild(row);
    }
  } catch (err) {
    if (err.message !== "unauthorized") {
      requestsTableBody.innerHTML = "";
      requestsEmpty.textContent = "Nie udało się pobrać listy wniosków.";
      requestsEmpty.classList.remove("hidden");
    }
  }
}

async function loadRequestDetail(entryId) {
  try {
    const response = await authedFetch(`/request-log/${entryId}`);
    const entry = await response.json();
    requestsDetailId.textContent = entry.id;
    requestsDetailRequest.textContent = JSON.stringify(entry.request_payload, null, 2);
    requestsDetailResponse.textContent = JSON.stringify(entry.response_payload, null, 2);
    requestsDetail.classList.remove("hidden");
  } catch (err) {
    if (err.message !== "unauthorized") {
      requestsDetail.classList.add("hidden");
    }
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

requestsBackBtn.addEventListener("click", () => {
  showDashboard();
});

let requestsFilterTimeout;
requestsFilter.addEventListener("input", () => {
  clearTimeout(requestsFilterTimeout);
  requestsFilterTimeout = setTimeout(loadRequestsList, 300);
});

if (getToken()) {
  loadDashboard();
} else {
  showLogin();
}
