const API_BASE = "/api/v1/admin";
const TOKEN_KEY = "ebobo_admin_token";

const loginView = document.getElementById("login-view");
const dashboardView = document.getElementById("dashboard-view");
const requestsView = document.getElementById("requests-view");
const legalFeedbackView = document.getElementById("legal-feedback-view");
const engineQualityView = document.getElementById("engine-quality-view");
const ALL_VIEWS = [loginView, dashboardView, requestsView, legalFeedbackView, engineQualityView];
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

// --- Legal Feedback ---
const lfBackBtn = document.getElementById("lf-back-btn");
const lfFilterBenefit = document.getElementById("lf-filter-benefit");
const lfFilterType = document.getElementById("lf-filter-type");
const lfFilterStatus = document.getElementById("lf-filter-status");
const lfTableBody = document.getElementById("lf-table-body");
const lfEmpty = document.getElementById("lf-empty");
const lfDetail = document.getElementById("lf-detail");
const lfDetailId = document.getElementById("lf-detail-id");
const lfDetailStatus = document.getElementById("lf-detail-status");
const lfDetailBenefit = document.getElementById("lf-detail-benefit");
const lfDetailType = document.getElementById("lf-detail-type");
const lfDetailComment = document.getElementById("lf-detail-comment");
const lfDetailExpected = document.getElementById("lf-detail-expected");
const lfDetailRulesVersion = document.getElementById("lf-detail-rules-version");
const lfDetailOriginal = document.getElementById("lf-detail-original");
const lfStatusSelect = document.getElementById("lf-status-select");
const lfStatusReason = document.getElementById("lf-status-reason");
const lfStatusSubmit = document.getElementById("lf-status-submit");
const lfStatusMessage = document.getElementById("lf-status-message");
const lfHistoryList = document.getElementById("lf-history-list");
const lfHistoryEmpty = document.getElementById("lf-history-empty");
const lfAnalyzeBtn = document.getElementById("lf-analyze-btn");
const lfAnalyzeMessage = document.getElementById("lf-analyze-message");
const lfAnalysesList = document.getElementById("lf-analyses-list");
let lfCurrentId = null;

// --- Engine Quality ---
const eqBackBtn = document.getElementById("eq-back-btn");
const eqFilterBenefit = document.getElementById("eq-filter-benefit");
const eqFilterSignal = document.getElementById("eq-filter-signal");
const eqFilterStatus = document.getElementById("eq-filter-status");
const eqFilterPriority = document.getElementById("eq-filter-priority");
const eqTableBody = document.getElementById("eq-table-body");
const eqEmpty = document.getElementById("eq-empty");
const eqDetail = document.getElementById("eq-detail");
const eqDetailId = document.getElementById("eq-detail-id");
const eqDetailSignal = document.getElementById("eq-detail-signal");
const eqDetailBenefit = document.getElementById("eq-detail-benefit");
const eqDetailRulesVersion = document.getElementById("eq-detail-rules-version");
const eqDetailProblemId = document.getElementById("eq-detail-problem-id");
const eqDetailOccurrences = document.getElementById("eq-detail-occurrences");
const eqDetailReason = document.getElementById("eq-detail-reason");
const eqDetailStatus = document.getElementById("eq-detail-status");
const eqDetailPriority = document.getElementById("eq-detail-priority");
const eqStatusSelect = document.getElementById("eq-status-select");
const eqStatusReason = document.getElementById("eq-status-reason");
const eqStatusSubmit = document.getElementById("eq-status-submit");
const eqStatusMessage = document.getElementById("eq-status-message");
const eqPrioritySelect = document.getElementById("eq-priority-select");
const eqPriorityReason = document.getElementById("eq-priority-reason");
const eqPrioritySubmit = document.getElementById("eq-priority-submit");
const eqPriorityMessage = document.getElementById("eq-priority-message");
const eqHistoryList = document.getElementById("eq-history-list");
const eqHistoryEmpty = document.getElementById("eq-history-empty");
const eqAnalyzeBtn = document.getElementById("eq-analyze-btn");
const eqAnalyzeMessage = document.getElementById("eq-analyze-message");
const eqAnalysesList = document.getElementById("eq-analyses-list");
let eqCurrentId = null;

function showView(view) {
  for (const section of ALL_VIEWS) {
    section.classList.add("hidden");
  }
  view.classList.remove("hidden");
  logoutBtn.classList.toggle("hidden", view === loginView);
}

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
  showView(loginView);
  if (message) {
    loginError.textContent = message;
    loginError.classList.remove("hidden");
  } else {
    loginError.classList.add("hidden");
  }
}

function showDashboard() {
  showView(dashboardView);
}

function showRequestsView() {
  showView(requestsView);
  requestsDetail.classList.add("hidden");
  loadRequestsList();
}

function showLegalFeedbackView() {
  showView(legalFeedbackView);
  lfDetail.classList.add("hidden");
  loadLegalFeedbackList();
}

function showEngineQualityView() {
  showView(engineQualityView);
  eqDetail.classList.add("hidden");
  loadEngineQualityList();
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
    } else if (module.key === "legal_feedback" && module.status === "available") {
      card.classList.add("module-card--clickable");
      card.addEventListener("click", showLegalFeedbackView);
    } else if (module.key === "engine_quality" && module.status === "available") {
      card.classList.add("module-card--clickable");
      card.addEventListener("click", showEngineQualityView);
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

function renderHistoryList(listEl, emptyEl, history) {
  listEl.innerHTML = "";
  emptyEl.classList.toggle("hidden", history.length > 0);
  for (const entry of history) {
    const item = document.createElement("li");
    const reasonText = entry.reason ? ` - ${entry.reason}` : "";
    item.textContent =
      `${formatDate(entry.changed_at)}: ${entry.field_changed} ` +
      `${entry.old_value} → ${entry.new_value} (${entry.changed_by})${reasonText}`;
    listEl.appendChild(item);
  }
}

function renderAnalysesList(container, analyses) {
  container.innerHTML = "";
  for (const analysis of analyses) {
    const card = document.createElement("div");
    card.className = "analysis-card";
    if (analysis.analysis_status === "failed") {
      card.classList.add("analysis-card--failed");
      card.innerHTML = `
        <div class="analysis-card__meta">${formatDate(analysis.created_at)} - nieudana próba</div>
        <p>${analysis.error_message || "Brak dodatkowych informacji."}</p>
      `;
    } else {
      const sources = (analysis.verified_source_ids || []).join(", ") || "brak";
      const required = (analysis.required_information || []).join("; ") || "brak";
      card.innerHTML = `
        <div class="analysis-card__meta">
          ${formatDate(analysis.created_at)} - model: ${analysis.model_id || "?"}
        </div>
        <p><strong>Klasyfikacja:</strong> ${analysis.classification}</p>
        <p><strong>Podsumowanie:</strong> ${analysis.summary}</p>
        <p><strong>Potencjalny problem:</strong> ${analysis.potential_issue}</p>
        <p><strong>Brakujące informacje:</strong> ${required}</p>
        <p><strong>Zweryfikowane źródła:</strong> ${sources}</p>
        <p><strong>Sugerowane działanie:</strong> ${analysis.recommended_admin_action}</p>
      `;
    }
    container.appendChild(card);
  }
}

// --- Legal Feedback ---

async function loadLegalFeedbackList() {
  lfDetail.classList.add("hidden");
  const params = new URLSearchParams();
  if (lfFilterBenefit.value.trim()) params.set("benefit_code", lfFilterBenefit.value.trim());
  if (lfFilterType.value) params.set("feedback_type", lfFilterType.value);
  if (lfFilterStatus.value) params.set("status_filter", lfFilterStatus.value);
  const query = params.toString() ? `?${params.toString()}` : "";

  try {
    const response = await authedFetch(`/legal-feedback${query}`);
    const entries = await response.json();
    lfTableBody.innerHTML = "";
    lfEmpty.classList.toggle("hidden", entries.length > 0);
    for (const entry of entries) {
      const row = document.createElement("tr");
      row.className = "data-table__row";
      row.innerHTML = `
        <td>${formatDate(entry.created_at)}</td>
        <td>${entry.benefit_code || "-"}</td>
        <td>${entry.feedback_type}</td>
        <td>${entry.status}</td>
      `;
      row.addEventListener("click", () => loadLegalFeedbackDetail(entry.id));
      lfTableBody.appendChild(row);
    }
  } catch (err) {
    if (err.message !== "unauthorized") {
      lfTableBody.innerHTML = "";
      lfEmpty.textContent = "Nie udało się pobrać listy zgłoszeń.";
      lfEmpty.classList.remove("hidden");
    }
  }
}

async function loadLegalFeedbackDetail(feedbackId) {
  try {
    const response = await authedFetch(`/legal-feedback/${feedbackId}`);
    const entry = await response.json();
    lfCurrentId = entry.id;
    lfDetailId.textContent = entry.id;
    lfDetailStatus.textContent = entry.status;
    lfDetailBenefit.textContent = entry.benefit_code || "-";
    lfDetailType.textContent = entry.feedback_type;
    lfDetailComment.textContent = entry.user_comment;
    lfDetailExpected.textContent = entry.expected_result || "-";
    lfDetailRulesVersion.textContent = entry.rules_version ?? "-";
    lfDetailOriginal.textContent = JSON.stringify(entry.original_evaluation, null, 2);
    lfStatusSelect.value = entry.status;
    lfStatusMessage.classList.add("hidden");
    lfAnalyzeMessage.classList.add("hidden");
    renderHistoryList(lfHistoryList, lfHistoryEmpty, entry.status_history || []);
    renderAnalysesList(lfAnalysesList, entry.analyses || []);
    lfDetail.classList.remove("hidden");
  } catch (err) {
    if (err.message !== "unauthorized") {
      lfDetail.classList.add("hidden");
    }
  }
}

lfStatusSubmit.addEventListener("click", async () => {
  if (lfCurrentId === null) return;
  try {
    await authedFetch(`/legal-feedback/${lfCurrentId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: lfStatusSelect.value,
        reason: lfStatusReason.value.trim() || null,
      }),
    });
    lfStatusReason.value = "";
    lfStatusMessage.textContent = "Status zapisany.";
    lfStatusMessage.classList.remove("hidden");
    await loadLegalFeedbackDetail(lfCurrentId);
  } catch (err) {
    if (err.message !== "unauthorized") {
      lfStatusMessage.textContent = "Nie udało się zmienić statusu.";
      lfStatusMessage.classList.remove("hidden");
    }
  }
});

lfAnalyzeBtn.addEventListener("click", async () => {
  if (lfCurrentId === null) return;
  lfAnalyzeMessage.textContent = "Analizuję...";
  lfAnalyzeMessage.classList.remove("hidden");
  try {
    await authedFetch(`/legal-feedback/${lfCurrentId}/analyze`, { method: "POST" });
    lfAnalyzeMessage.classList.add("hidden");
    await loadLegalFeedbackDetail(lfCurrentId);
  } catch (err) {
    if (err.message !== "unauthorized") {
      lfAnalyzeMessage.textContent = "Analiza nie powiodła się.";
    }
  }
});

// --- Engine Quality ---

async function loadEngineQualityList() {
  eqDetail.classList.add("hidden");
  const params = new URLSearchParams();
  if (eqFilterBenefit.value.trim()) params.set("benefit_code", eqFilterBenefit.value.trim());
  if (eqFilterSignal.value) params.set("signal_type", eqFilterSignal.value);
  if (eqFilterStatus.value) params.set("status_filter", eqFilterStatus.value);
  if (eqFilterPriority.value) params.set("priority", eqFilterPriority.value);
  const query = params.toString() ? `?${params.toString()}` : "";

  try {
    const response = await authedFetch(`/engine-quality/cases${query}`);
    const entries = await response.json();
    eqTableBody.innerHTML = "";
    eqEmpty.classList.toggle("hidden", entries.length > 0);
    for (const entry of entries) {
      const row = document.createElement("tr");
      row.className = "data-table__row";
      row.innerHTML = `
        <td>${formatDate(entry.detected_at)}</td>
        <td>${entry.signal_type}</td>
        <td>${entry.benefit_code || "-"}</td>
        <td>${entry.occurrence_count}</td>
        <td>${entry.priority}</td>
        <td>${entry.status}</td>
      `;
      row.addEventListener("click", () => loadEngineQualityDetail(entry.id));
      eqTableBody.appendChild(row);
    }
  } catch (err) {
    if (err.message !== "unauthorized") {
      eqTableBody.innerHTML = "";
      eqEmpty.textContent = "Nie udało się pobrać listy spraw.";
      eqEmpty.classList.remove("hidden");
    }
  }
}

async function loadEngineQualityDetail(caseId) {
  try {
    const response = await authedFetch(`/engine-quality/cases/${caseId}`);
    const entry = await response.json();
    eqCurrentId = entry.id;
    eqDetailId.textContent = entry.id;
    eqDetailSignal.textContent = entry.signal_type;
    eqDetailBenefit.textContent = entry.benefit_code || "-";
    eqDetailRulesVersion.textContent = entry.rules_version ?? "-";
    eqDetailProblemId.textContent = entry.problem_id || "-";
    eqDetailOccurrences.textContent = entry.occurrence_count;
    eqDetailReason.textContent = entry.reason;
    eqDetailStatus.textContent = entry.status;
    eqDetailPriority.textContent = entry.priority;
    eqStatusSelect.value = entry.status;
    eqPrioritySelect.value = entry.priority;
    eqStatusMessage.classList.add("hidden");
    eqPriorityMessage.classList.add("hidden");
    eqAnalyzeMessage.classList.add("hidden");
    renderHistoryList(eqHistoryList, eqHistoryEmpty, entry.history || []);
    renderAnalysesList(eqAnalysesList, entry.analyses || []);
    eqDetail.classList.remove("hidden");
  } catch (err) {
    if (err.message !== "unauthorized") {
      eqDetail.classList.add("hidden");
    }
  }
}

eqStatusSubmit.addEventListener("click", async () => {
  if (eqCurrentId === null) return;
  try {
    await authedFetch(`/engine-quality/cases/${eqCurrentId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: eqStatusSelect.value,
        reason: eqStatusReason.value.trim() || null,
      }),
    });
    eqStatusReason.value = "";
    eqStatusMessage.textContent = "Status zapisany.";
    eqStatusMessage.classList.remove("hidden");
    await loadEngineQualityDetail(eqCurrentId);
  } catch (err) {
    if (err.message !== "unauthorized") {
      eqStatusMessage.textContent = "Nie udało się zmienić statusu.";
      eqStatusMessage.classList.remove("hidden");
    }
  }
});

eqPrioritySubmit.addEventListener("click", async () => {
  if (eqCurrentId === null) return;
  try {
    await authedFetch(`/engine-quality/cases/${eqCurrentId}/priority`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        priority: eqPrioritySelect.value,
        reason: eqPriorityReason.value.trim() || null,
      }),
    });
    eqPriorityReason.value = "";
    eqPriorityMessage.textContent = "Priorytet zapisany.";
    eqPriorityMessage.classList.remove("hidden");
    await loadEngineQualityDetail(eqCurrentId);
  } catch (err) {
    if (err.message !== "unauthorized") {
      eqPriorityMessage.textContent = "Nie udało się zmienić priorytetu.";
      eqPriorityMessage.classList.remove("hidden");
    }
  }
});

eqAnalyzeBtn.addEventListener("click", async () => {
  if (eqCurrentId === null) return;
  eqAnalyzeMessage.textContent = "Analizuję...";
  eqAnalyzeMessage.classList.remove("hidden");
  try {
    await authedFetch(`/engine-quality/cases/${eqCurrentId}/analyze`, { method: "POST" });
    eqAnalyzeMessage.classList.add("hidden");
    await loadEngineQualityDetail(eqCurrentId);
  } catch (err) {
    if (err.message !== "unauthorized") {
      eqAnalyzeMessage.textContent = "Analiza nie powiodła się.";
    }
  }
});

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

lfBackBtn.addEventListener("click", () => {
  showDashboard();
});

let lfFilterTimeout;
lfFilterBenefit.addEventListener("input", () => {
  clearTimeout(lfFilterTimeout);
  lfFilterTimeout = setTimeout(loadLegalFeedbackList, 300);
});
lfFilterType.addEventListener("change", loadLegalFeedbackList);
lfFilterStatus.addEventListener("change", loadLegalFeedbackList);

eqBackBtn.addEventListener("click", () => {
  showDashboard();
});

let eqFilterTimeout;
eqFilterBenefit.addEventListener("input", () => {
  clearTimeout(eqFilterTimeout);
  eqFilterTimeout = setTimeout(loadEngineQualityList, 300);
});
eqFilterSignal.addEventListener("change", loadEngineQualityList);
eqFilterStatus.addEventListener("change", loadEngineQualityList);
eqFilterPriority.addEventListener("change", loadEngineQualityList);

if (getToken()) {
  loadDashboard();
} else {
  showLogin();
}
