let token = localStorage.getItem("opentoken.session") || "";
let currentSettings = {theme: localStorage.getItem("opentoken.theme") || "light", language: "English"};
let lastLogs = [];

const titles = {
  dashboard: "Developer Console",
  keys: "API Keys",
  models: "Models",
  playground: "Playground",
  usage: "Activity",
  logs: "Logs",
  credits: "Credits",
  settings: "Settings",
  docs: "Docs",
};

function headers() {
  const h = {"Content-Type": "application/json"};
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

async function api(url, options = {}) {
  const response = await fetch(url, {...options, headers: {...headers(), ...(options.headers || {})}});
  const data = await response.json().catch(() => ({}));
  return {ok: response.ok, status: response.status, data};
}

function show(id, data) {
  const el = document.getElementById(id);
  if (el) el.textContent = JSON.stringify(data, null, 2);
}

function money(value, digits = 4) {
  return `$${Number(value || 0).toFixed(digits)}`;
}

function setAccount(user) {
  document.getElementById("account").textContent = user ? `${user.email} | ${money(user.balance)}` : "Not signed in";
}

function setMetrics(data = {}) {
  document.getElementById("metricRequests").textContent = data.request_count || 0;
  document.getElementById("metricTokens").textContent = data.total_tokens || 0;
  document.getElementById("metricCost").textContent = money(data.total_cost);
  document.getElementById("metricBalance").textContent = money(data.balance);
}

function setTheme(theme) {
  currentSettings.theme = theme === "dark" ? "dark" : "light";
  document.body.classList.toggle("dark", currentSettings.theme === "dark");
  localStorage.setItem("opentoken.theme", currentSettings.theme);
  document.getElementById("themeLabel").textContent = currentSettings.theme === "dark" ? "Dark" : "Light";
  document.querySelector("#themeToggle .material-symbols-outlined").textContent =
    currentSettings.theme === "dark" ? "dark_mode" : "light_mode";
}

function routeTo(page) {
  const target = titles[page] ? page : "dashboard";
  document.querySelectorAll("[data-page]").forEach((el) => el.classList.toggle("active", el.dataset.page === target));
  document.querySelectorAll("[data-route]").forEach((el) => el.classList.toggle("active", el.dataset.route === target));
  document.getElementById("pageTitle").textContent = titles[target];
  history.replaceState(null, "", `#${target}`);
  if (target === "usage") loadActivity();
  if (target === "logs") loadLogs();
  if (target === "credits") loadCredits();
}

function requireLogin() {
  if (token) return true;
  routeTo("dashboard");
  show("authResult", {error: "Please register or login first."});
  return false;
}

async function loadHealth() {
  const result = await api("/health");
  const health = document.getElementById("health");
  health.textContent = `Health: ${result.ok ? "OK" : "FAIL"}`;
  health.classList.toggle("ok", result.ok);
}

async function loadMe() {
  if (!token) return;
  const result = await api("/api/me");
  if (result.ok) setAccount(result.data);
}

async function loadModels() {
  const result = await api("/api/models");
  const list = document.getElementById("modelList");
  if (!result.ok) {
    list.innerHTML = "<div><strong>Error</strong><span>Could not load models</span></div>";
    return;
  }
  list.innerHTML = "";
  result.data.forEach((model) => {
    const row = document.createElement("div");
    row.innerHTML = `<strong>${model.id}</strong><span>${model.status} | in ${model.input_price} / out ${model.output_price}</span>`;
    row.onclick = () => {
      document.getElementById("model").value = model.id;
      document.getElementById("defaultModel").value = model.id;
      routeTo("playground");
    };
    list.appendChild(row);
  });
}

async function loadKeys() {
  if (!token) return;
  const result = await api("/api/keys");
  const rows = document.getElementById("keyRows");
  rows.innerHTML = "";
  (result.data || []).forEach((key) => {
    const row = document.createElement("tr");
    row.innerHTML = `<td>${key.name}</td><td><code>${key.key_mask}</code></td><td>${key.permissions}</td><td><span class="badge">${key.status}</span></td><td><button data-key-id="${key.id}">Revoke</button></td>`;
    row.querySelector("button").onclick = async () => {
      await api(`/api/keys/${key.id}`, {method: "DELETE"});
      await loadKeys();
    };
    rows.appendChild(row);
  });
}

function renderLogRows(rows) {
  const body = document.getElementById("logRows");
  body.innerHTML = "";
  (rows || []).forEach((log) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${log.date || ""}</td>
      <td>${log.model || ""}</td>
      <td>${log.provider || ""}</td>
      <td>${log.app || ""}</td>
      <td>${log.input || 0}</td>
      <td>${log.output || 0}</td>
      <td>${money(log.cost, 6)}</td>
      <td>${log.usage_type || ""}</td>
      <td>${log.speed || 0}ms</td>
      <td>${log.finish_reason || ""}</td>
    `;
    body.appendChild(row);
  });
}

async function loadLogs() {
  if (!token) return;
  const result = await api("/api/logs");
  lastLogs = result.ok ? result.data : [];
  renderLogRows(lastLogs);
}

async function loadUsage() {
  if (!token) {
    setMetrics();
    return;
  }
  const result = await api("/api/usage");
  if (result.ok) {
    setMetrics(result.data);
    await loadMe();
  }
}

function renderBars(targetId, values) {
  const el = document.getElementById(targetId);
  const max = Math.max(...values.map((item) => item.value), 1);
  el.innerHTML = values.map((item, index) => {
    const height = Math.max(12, Math.round((item.value / max) * 168));
    const color = index % 2 === 0 ? "green" : "blue";
    return `<span class="${color}" style="height:${height}px" title="${item.label}: ${item.value}"></span>`;
  }).join("");
}

function renderLegend(targetId, rows, valueKey, formatter) {
  const el = document.getElementById(targetId);
  el.innerHTML = rows.map((row, index) => {
    const color = index % 2 === 0 ? "green" : "blue";
    return `<div><span class="legend-dot ${color}"></span><strong>${row.model}</strong><em>${formatter(row[valueKey] || 0)}</em></div>`;
  }).join("");
}

async function loadActivity() {
  if (!token) return;
  const result = await api("/api/activity");
  if (!result.ok) return;
  const rows = result.data.by_model.length ? result.data.by_model : [{model: "No usage yet", spend: 0, requests: 0, tokens: 0}];
  document.getElementById("chartSpend").textContent = money(result.data.totals.spend, 2);
  document.getElementById("chartRequests").textContent = result.data.totals.requests || 0;
  document.getElementById("chartTokens").textContent = result.data.totals.tokens || 0;
  renderBars("spendBars", rows.map((row) => ({label: row.model, value: row.spend || 0})));
  renderBars("requestBars", rows.map((row) => ({label: row.model, value: row.requests || 0})));
  renderBars("tokenBars", rows.map((row) => ({label: row.model, value: row.tokens || 0})));
  renderLegend("spendLegend", rows, "spend", (value) => money(value, 4));
  renderLegend("requestLegend", rows, "requests", (value) => value);
  renderLegend("tokenLegend", rows, "tokens", (value) => value);
}

async function loadCredits() {
  if (!token) return;
  const result = await api("/api/credits");
  if (!result.ok) return;
  document.getElementById("creditBalance").textContent = money(result.data.balance);
  show("creditsOutput", {balance: result.data.balance});
  const body = document.getElementById("creditRows");
  body.innerHTML = "";
  result.data.transactions.forEach((tx) => {
    const row = document.createElement("tr");
    row.innerHTML = `<td>${tx.created_at}</td><td>${money(tx.amount)}</td><td>${money(tx.balance_after)}</td><td>${tx.note}</td>`;
    body.appendChild(row);
  });
}

async function loadSettings() {
  if (!token) return;
  const result = await api("/api/settings");
  show("settingsOutput", result.data);
  if (!result.ok) return;
  currentSettings = {...currentSettings, ...result.data};
  document.getElementById("defaultModel").value = result.data.default_model;
  document.getElementById("monthlyBudget").value = result.data.monthly_budget;
  document.getElementById("rateLimit").value = result.data.rate_limit_per_minute;
  document.getElementById("language").value = result.data.language;
  setTheme(result.data.theme);
}

async function refresh() {
  await loadMe();
  await loadModels();
  await loadKeys();
  await loadUsage();
  await loadActivity();
  await loadLogs();
  await loadCredits();
  await loadSettings();
}

document.getElementById("register").onclick = async () => {
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  const result = await api("/auth/register", {method: "POST", body: JSON.stringify({email, password})});
  show("authResult", result.data);
  if (result.ok) {
    token = result.data.token;
    localStorage.setItem("opentoken.session", token);
    await refresh();
  }
};

document.getElementById("login").onclick = async () => {
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  const result = await api("/auth/login", {method: "POST", body: JSON.stringify({email, password})});
  show("authResult", result.data);
  if (result.ok) {
    token = result.data.token;
    localStorage.setItem("opentoken.session", token);
    await refresh();
  }
};

document.getElementById("logout").onclick = async () => {
  if (token) await api("/auth/logout", {method: "POST"});
  token = "";
  localStorage.removeItem("opentoken.session");
  setAccount(null);
  setMetrics();
  routeTo("dashboard");
};

document.getElementById("createKey").onclick = async () => {
  if (!requireLogin()) return;
  const name = document.getElementById("keyName").value;
  const permissions = document.getElementById("perm").value;
  const result = await api("/api/keys", {method: "POST", body: JSON.stringify({name, permissions})});
  show("newKey", result.data);
  await loadKeys();
};

document.getElementById("send").onclick = async () => {
  if (!requireLogin()) return;
  const model = document.getElementById("model").value;
  const prompt = document.getElementById("prompt").value;
  const result = await api("/api/playground", {method: "POST", body: JSON.stringify({model, messages: [{role: "user", content: prompt}]})});
  show("resp", result.data);
  await loadUsage();
  await loadActivity();
  await loadLogs();
};

document.getElementById("reload").onclick = async () => {
  if (!requireLogin()) return;
  await loadLogs();
};

document.getElementById("usageRefresh").onclick = async () => {
  if (!requireLogin()) return;
  await loadUsage();
  await loadActivity();
};

document.getElementById("viewLogsFromUsage").onclick = () => routeTo("logs");

document.getElementById("topupCredits").onclick = async () => {
  if (!requireLogin()) return;
  const amount = Number(document.getElementById("topupAmount").value || 0);
  const note = document.getElementById("topupNote").value;
  const result = await api("/api/credits/top-up", {method: "POST", body: JSON.stringify({amount, note})});
  show("creditsOutput", result.data);
  await loadCredits();
  await loadUsage();
};

document.getElementById("saveSettings").onclick = async () => {
  if (!requireLogin()) return;
  const payload = {
    default_model: document.getElementById("defaultModel").value,
    monthly_budget: Number(document.getElementById("monthlyBudget").value || 0),
    rate_limit_per_minute: Number(document.getElementById("rateLimit").value || 60),
    language: document.getElementById("language").value,
    theme: currentSettings.theme,
  };
  const result = await api("/api/settings", {method: "PUT", body: JSON.stringify(payload)});
  show("settingsOutput", result.data);
  if (result.ok) await loadSettings();
};

document.getElementById("themeToggle").onclick = async () => {
  const nextTheme = currentSettings.theme === "dark" ? "light" : "dark";
  setTheme(nextTheme);
  if (token) {
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({
        default_model: document.getElementById("defaultModel").value,
        monthly_budget: Number(document.getElementById("monthlyBudget").value || 0),
        rate_limit_per_minute: Number(document.getElementById("rateLimit").value || 60),
        language: document.getElementById("language").value,
        theme: nextTheme,
      }),
    });
  }
};

document.getElementById("copyCurl").onclick = async () => {
  const text = document.getElementById("docsOutput").textContent;
  try {
    await navigator.clipboard.writeText(text);
    show("settingsOutput", {ok: true, message: "cURL copied to clipboard"});
  } catch {
    show("settingsOutput", {ok: false, message: "Clipboard permission denied", curl: text});
  }
};

document.getElementById("exportLogs").onclick = () => {
  const blob = new Blob([JSON.stringify(lastLogs, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "opentoken-logs.json";
  link.click();
  URL.revokeObjectURL(url);
};

document.querySelectorAll("[data-route]").forEach((button) => {
  button.addEventListener("click", () => routeTo(button.dataset.route));
});

setTheme(currentSettings.theme);
loadHealth();
loadModels();
routeTo(location.hash.replace("#", "") || "dashboard");
refresh();
