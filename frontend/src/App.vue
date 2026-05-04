<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { api, clearToken, getToken, post, put, setToken } from "./api";

type Row = Record<string, any>;

const page = ref("dashboard");
const busy = ref(false);
const error = ref("");
const output = ref<Row | Row[] | null>(null);
const userToken = ref(getToken(false));
const adminToken = ref(getToken(true));
const me = ref<Row | null>(null);
const adminDashboard = ref<Row | null>(null);
const keys = ref<Row[]>([]);
const models = ref<Row[]>([]);
const logs = ref<Row[]>([]);
const usage = ref<Row | null>(null);
const credits = ref<Row | null>(null);
const accounts = ref<Row[]>([]);
const channels = ref<Row[]>([]);
const groups = ref<Row[]>([]);

const loginForm = reactive({ email: "user@example.com", password: "password123" });
const adminForm = reactive({ email: "admin@example.com", password: "admin-password123" });
const keyForm = reactive({ name: "default-key", permissions: "All", group_id: "", quota: 0 });
const playground = reactive({ model: "deepseek-chat", prompt: "Hello OpenToken" });
const creditForm = reactive({ amount: 10, note: "manual top-up" });
const settingsForm = reactive({ default_model: "deepseek-chat", monthly_budget: 10, rate_limit_per_minute: 60, language: "English", theme: "light" });
const accountForm = reactive({ name: "DeepSeek", platform: "openai_compatible", type: "api_key", api_key: "", base_url: "https://api.deepseek.com", priority: 50, concurrency: 3, model_mapping: "{}" });
const channelForm = reactive({ name: "Default Channel", restrict_models: false, model_mapping: "{}", model_pricing: '[{"models":["deepseek-chat"],"input_price":0.000001,"output_price":0.000002}]' });
const groupForm = reactive({ name: "Default", rate_multiplier: 1, rpm_limit: 60, channel_ids: "[]" });

const nav = [
  ["dashboard", "Dashboard"],
  ["keys", "API Keys"],
  ["playground", "Playground"],
  ["usage", "Usage"],
  ["logs", "Logs"],
  ["credits", "Credits"],
  ["settings", "Settings"],
  ["admin-accounts", "Admin Accounts"],
  ["admin-channels", "Admin Channels"],
  ["admin-groups", "Admin Groups"]
];

const authed = computed(() => Boolean(userToken.value));
const adminAuthed = computed(() => Boolean(adminToken.value));

function showError(err: unknown) {
  error.value = err instanceof Error ? err.message : String(err);
}

async function run<T>(task: () => Promise<T>): Promise<T | undefined> {
  busy.value = true;
  error.value = "";
  try {
    return await task();
  } catch (err) {
    showError(err);
  } finally {
    busy.value = false;
  }
}

async function register() {
  await run(async () => {
    const res = await post<Row>("/auth/register", loginForm);
    setToken(String(res.token));
    userToken.value = String(res.token);
    output.value = res;
    await refreshUser();
  });
}

async function login() {
  await run(async () => {
    const res = await post<Row>("/auth/login", loginForm);
    setToken(String(res.token));
    userToken.value = String(res.token);
    output.value = res;
    await refreshUser();
  });
}

async function adminLogin() {
  await run(async () => {
    const res = await post<Row>("/admin/login", adminForm, true);
    setToken(String(res.token), true);
    adminToken.value = String(res.token);
    await refreshAdmin();
  });
}

async function refreshUser() {
  if (!userToken.value) return;
  await run(async () => {
    me.value = await api<Row>("/api/me");
    keys.value = await api<Row[]>("/api/keys");
    models.value = await api<Row[]>("/api/models");
    logs.value = await api<Row[]>("/api/logs");
    usage.value = await api<Row>("/api/usage");
    credits.value = await api<Row>("/api/credits");
  });
}

async function refreshAdmin() {
  if (!adminToken.value) return;
  await run(async () => {
    adminDashboard.value = await api<Row>("/admin/dashboard", {}, true);
    accounts.value = await api<Row[]>("/admin/accounts", {}, true);
    channels.value = await api<Row[]>("/admin/channels", {}, true);
    groups.value = await api<Row[]>("/admin/groups", {}, true);
  });
}

async function createKey() {
  await run(async () => {
    const body: Row = { name: keyForm.name, permissions: keyForm.permissions, quota: keyForm.quota };
    if (keyForm.group_id) body.group_id = Number(keyForm.group_id);
    output.value = await post<Row>("/api/keys", body);
    await refreshUser();
  });
}

async function sendPrompt() {
  await run(async () => {
    output.value = await post<Row>("/api/playground", {
      model: playground.model,
      messages: [{ role: "user", content: playground.prompt }]
    });
    await refreshUser();
  });
}

async function topUp() {
  await run(async () => {
    output.value = await post<Row>("/api/credits/top-up", creditForm);
    await refreshUser();
  });
}

async function saveSettings() {
  await run(async () => {
    output.value = await put<Row>("/api/settings", settingsForm);
  });
}

function parseJson(text: string, fallback: any) {
  try {
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

async function createAccount() {
  await run(async () => {
    output.value = await post<Row>("/admin/accounts", { ...accountForm, model_mapping: parseJson(accountForm.model_mapping, {}) }, true);
    await refreshAdmin();
  });
}

async function testAccount(id: number) {
  await run(async () => {
    output.value = await post<Row>(`/admin/accounts/${id}/test`, {}, true);
  });
}

async function createChannel() {
  await run(async () => {
    output.value = await post<Row>("/admin/channels", { ...channelForm, model_mapping: parseJson(channelForm.model_mapping, {}), model_pricing: parseJson(channelForm.model_pricing, []) }, true);
    await refreshAdmin();
  });
}

async function createGroup() {
  await run(async () => {
    output.value = await post<Row>("/admin/groups", { ...groupForm, channel_ids: parseJson(groupForm.channel_ids, []) }, true);
    await refreshAdmin();
  });
}

function logout(admin = false) {
  clearToken(admin);
  if (admin) adminToken.value = "";
  else userToken.value = "";
}

onMounted(async () => {
  await refreshUser();
  await refreshAdmin();
});
</script>

<template>
  <div class="shell">
    <aside>
      <div class="brand">
        <div class="logo">OT</div>
        <div>
          <strong>OpenToken</strong>
          <span>Gateway Console</span>
        </div>
      </div>
      <button v-for="[id, label] in nav" :key="id" :class="{ active: page === id }" @click="page = id">{{ label }}</button>
    </aside>

    <main>
      <header>
        <div>
          <p class="eyebrow">Sub2API-style Gateway</p>
          <h1>{{ nav.find((item) => item[0] === page)?.[1] }}</h1>
        </div>
        <div class="header-actions">
          <span class="pill">User: {{ authed ? "signed in" : "guest" }}</span>
          <span class="pill">Admin: {{ adminAuthed ? "signed in" : "locked" }}</span>
          <button @click="refreshUser(); refreshAdmin()">Refresh</button>
        </div>
      </header>

      <div v-if="error" class="alert">{{ error }}</div>
      <div v-if="busy" class="muted">Loading...</div>

      <section v-if="page === 'dashboard'" class="grid">
        <div class="card">
          <h2>User Login / Register</h2>
          <label>Email <input v-model="loginForm.email" /></label>
          <label>Password <input v-model="loginForm.password" type="password" /></label>
          <div class="row"><button @click="login">Login</button><button @click="register">Register</button><button @click="logout()">Logout</button></div>
          <pre>{{ me }}</pre>
        </div>
        <div class="card">
          <h2>Admin Login</h2>
          <label>Email <input v-model="adminForm.email" /></label>
          <label>Password <input v-model="adminForm.password" type="password" /></label>
          <div class="row"><button @click="adminLogin">Admin Login</button><button @click="logout(true)">Logout Admin</button></div>
          <pre>{{ adminDashboard }}</pre>
        </div>
      </section>

      <section v-if="page === 'keys'" class="card">
        <h2>Create API Key</h2>
        <div class="form-grid">
          <label>Name <input v-model="keyForm.name" /></label>
          <label>Permissions <input v-model="keyForm.permissions" /></label>
          <label>Group ID <input v-model="keyForm.group_id" placeholder="optional" /></label>
          <label>Quota <input v-model.number="keyForm.quota" type="number" /></label>
        </div>
        <button @click="createKey">Create Key</button>
        <table><tbody><tr v-for="key in keys" :key="key.id"><td>{{ key.name }}</td><td>{{ key.key_mask }}</td><td>{{ key.permissions }}</td><td>{{ key.status }}</td></tr></tbody></table>
      </section>

      <section v-if="page === 'playground'" class="grid wide">
        <div class="card">
          <h2>Chat Completions</h2>
          <label>Model <select v-model="playground.model"><option v-for="model in models" :key="model.id || model.model" :value="model.model">{{ model.model }}</option></select></label>
          <label>Prompt <textarea v-model="playground.prompt" rows="12" /></label>
          <button @click="sendPrompt">Send</button>
        </div>
        <div class="card dark"><h2>Response</h2><pre>{{ output }}</pre></div>
      </section>

      <section v-if="page === 'usage'" class="grid">
        <div class="card"><h2>Usage</h2><pre>{{ usage }}</pre></div>
        <div class="card"><h2>Models</h2><pre>{{ models }}</pre></div>
      </section>

      <section v-if="page === 'logs'" class="card">
        <h2>Usage Logs</h2>
        <table>
          <thead><tr><th>Date</th><th>Model</th><th>Provider</th><th>Input</th><th>Output</th><th>Cost</th><th>Speed</th><th>Finish</th></tr></thead>
          <tbody><tr v-for="log in logs" :key="log.id"><td>{{ log.created_at }}</td><td>{{ log.model }}</td><td>{{ log.provider }}</td><td>{{ log.input_tokens }}</td><td>{{ log.output_tokens }}</td><td>{{ log.cost || log.total_cost }}</td><td>{{ log.latency_ms || log.duration_ms }}ms</td><td>{{ log.finish_reason }}</td></tr></tbody>
        </table>
      </section>

      <section v-if="page === 'credits'" class="card">
        <h2>Credits</h2>
        <div class="form-grid"><label>Amount <input v-model.number="creditForm.amount" type="number" /></label><label>Note <input v-model="creditForm.note" /></label></div>
        <button @click="topUp">Top Up</button>
        <pre>{{ credits }}</pre>
      </section>

      <section v-if="page === 'settings'" class="card">
        <h2>Settings</h2>
        <div class="form-grid">
          <label>Default model <input v-model="settingsForm.default_model" /></label>
          <label>Monthly budget <input v-model.number="settingsForm.monthly_budget" type="number" /></label>
          <label>RPM <input v-model.number="settingsForm.rate_limit_per_minute" type="number" /></label>
          <label>Theme <input v-model="settingsForm.theme" /></label>
        </div>
        <button @click="saveSettings">Save Settings</button>
      </section>

      <section v-if="page === 'admin-accounts'" class="card">
        <h2>Accounts</h2>
        <div class="form-grid">
          <label>Name <input v-model="accountForm.name" /></label>
          <label>Platform <input v-model="accountForm.platform" /></label>
          <label>Type <input v-model="accountForm.type" /></label>
          <label>Base URL <input v-model="accountForm.base_url" /></label>
          <label>API Key <input v-model="accountForm.api_key" type="password" /></label>
          <label>Mapping JSON <textarea v-model="accountForm.model_mapping" /></label>
        </div>
        <button @click="createAccount">Create Account</button>
        <table><tbody><tr v-for="account in accounts" :key="account.id"><td>{{ account.id }}</td><td>{{ account.name }}</td><td>{{ account.platform }}</td><td>{{ account.status }}</td><td><button @click="testAccount(account.id)">Test</button></td></tr></tbody></table>
      </section>

      <section v-if="page === 'admin-channels'" class="card">
        <h2>Channels</h2>
        <label>Name <input v-model="channelForm.name" /></label>
        <label>Model Mapping JSON <textarea v-model="channelForm.model_mapping" /></label>
        <label>Pricing JSON <textarea v-model="channelForm.model_pricing" /></label>
        <button @click="createChannel">Create Channel</button>
        <pre>{{ channels }}</pre>
      </section>

      <section v-if="page === 'admin-groups'" class="card">
        <h2>Groups</h2>
        <div class="form-grid">
          <label>Name <input v-model="groupForm.name" /></label>
          <label>Channel IDs JSON <input v-model="groupForm.channel_ids" /></label>
          <label>RPM <input v-model.number="groupForm.rpm_limit" type="number" /></label>
          <label>Rate multiplier <input v-model.number="groupForm.rate_multiplier" type="number" /></label>
        </div>
        <button @click="createGroup">Create Group</button>
        <pre>{{ groups }}</pre>
      </section>
    </main>
  </div>
</template>
