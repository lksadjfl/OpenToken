let token = localStorage.getItem("opentoken.session") || "";

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

function money(value) {
  return `$${Number(value || 0).toFixed(4)}`;
}

function setAccount(user) {
  const account = document.getElementById("account");
  account.textContent = user ? `${user.email} | ${money(user.balance)}` : "Not signed in";
}

function setMetrics(data = {}) {
  document.getElementById("metricRequests").textContent = data.request_count || 0;
  document.getElementById("metricTokens").textContent = data.total_tokens || 0;
  document.getElementById("metricCost").textContent = money(data.total_cost);
  document.getElementById("metricBalance").textContent = money(data.balance);
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

async function loadKeys() {
  if (!token) return;
  const result = await api("/api/keys");
  const rows = document.getElementById("keyRows");
  rows.innerHTML = "";
  (result.data || []).forEach((key) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${key.name}</td>
      <td><code>${key.key_mask}</code></td>
      <td>${key.permissions}</td>
      <td><span class="badge">${key.status}</span></td>
      <td><button data-key-id="${key.id}">Revoke</button></td>
    `;
    row.querySelector("button").onclick = async () => {
      await api(`/api/keys/${key.id}`, {method: "DELETE"});
      await loadKeys();
    };
    rows.appendChild(row);
  });
}

async function loadLogs() {
  if (!token) return;
  const result = await api("/api/logs");
  show("logsOutput", result.data);
}

async function loadUsage() {
  if (!token) {
    setMetrics();
    return;
  }
  const result = await api("/api/usage");
  show("usageOutput", result.data);
  if (result.ok) {
    setMetrics(result.data);
    await loadMe();
  }
}

async function refresh() {
  await loadMe();
  await loadKeys();
  await loadUsage();
  await loadLogs();
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

document.getElementById("createKey").onclick = async () => {
  const name = document.getElementById("keyName").value;
  const permissions = document.getElementById("perm").value;
  const result = await api("/api/keys", {method: "POST", body: JSON.stringify({name, permissions})});
  show("newKey", result.data);
  await loadKeys();
};

document.getElementById("send").onclick = async () => {
  const model = document.getElementById("model").value;
  const prompt = document.getElementById("prompt").value;
  const result = await api("/api/playground", {
    method: "POST",
    body: JSON.stringify({model, messages: [{role: "user", content: prompt}]}),
  });
  show("resp", result.data);
  await loadUsage();
  await loadLogs();
};

document.getElementById("reload").onclick = async () => {
  await loadUsage();
  await loadLogs();
};

loadHealth();
refresh();
