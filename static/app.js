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

function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text ?? "";
  return td;
}

function labeledDiv(title, detail) {
  const div = document.createElement("div");
  const strong = document.createElement("strong");
  const span = document.createElement("span");
  strong.textContent = title;
  span.textContent = detail;
  div.append(strong, span);
  return div;
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
    clear(list);
    list.appendChild(labeledDiv("Error", "Could not load models"));
    return;
  }
  clear(list);
  result.data.forEach((model) => {
    const row = labeledDiv(model.id, `${model.status} | in ${model.input_price} / out ${model.output_price}`);
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
  clear(rows);
  (result.data || []).forEach((key) => {
    const row = document.createElement("tr");
    const maskCell = document.createElement("td");
    const code = document.createElement("code");
    code.textContent = key.key_mask;
    maskCell.appendChild(code);
    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = key.status;
    statusCell.appendChild(badge);
    const actionCell = document.createElement("td");
    const revoke = document.createElement("button");
    revoke.textContent = "Revoke";
    revoke.dataset.keyId = key.id;
    revoke.onclick = async () => {
      await api(`/api/keys/${key.id}`, {method: "DELETE"});
      await loadKeys();
    };
    actionCell.appendChild(revoke);
    row.append(cell(key.name), maskCell, cell(key.permissions), statusCell, actionCell);
    rows.appendChild(row);
  });
}

function renderLogRows(rows) {
  const body = document.getElementById("logRows");
  clear(body);
  (rows || []).forEach((log) => {
    const row = document.createElement("tr");
    row.append(
      cell(log.date || ""),
      cell(log.model || ""),
      cell(log.provider || ""),
      cell(log.app || ""),
      cell(log.input || 0),
      cell(log.output || 0),
      cell(money(log.cost, 6)),
      cell(log.usage_type || ""),
      cell(`${log.speed || 0}ms`),
      cell(log.finish_reason || ""),
    );
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
  clear(el);
  values.forEach((item, index) => {
    const height = Math.max(12, Math.round((item.value / max) * 168));
    const color = index % 2 === 0 ? "green" : "blue";
    const bar = document.createElement("span");
    bar.className = color;
    bar.style.height = `${height}px`;
    bar.title = `${item.label}: ${item.value}`;
    el.appendChild(bar);
  });
}

function renderLegend(targetId, rows, valueKey, formatter) {
  const el = document.getElementById(targetId);
  clear(el);
  rows.forEach((row, index) => {
    const color = index % 2 === 0 ? "green" : "blue";
    const item = document.createElement("div");
    const dot = document.createElement("span");
    const name = document.createElement("strong");
    const value = document.createElement("em");
    dot.className = `legend-dot ${color}`;
    name.textContent = row.model;
    value.textContent = formatter(row[valueKey] || 0);
    item.append(dot, name, value);
    el.appendChild(item);
  });
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
  clear(body);
  result.data.transactions.forEach((tx) => {
    const row = document.createElement("tr");
    row.append(cell(tx.created_at), cell(money(tx.amount)), cell(money(tx.balance_after)), cell(tx.note));
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
