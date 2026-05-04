export type JsonRecord = Record<string, unknown>;

const tokenKey = "opentoken_user_token";
const adminTokenKey = "opentoken_admin_token";

export function getToken(admin = false): string {
  return localStorage.getItem(admin ? adminTokenKey : tokenKey) || "";
}

export function setToken(token: string, admin = false): void {
  localStorage.setItem(admin ? adminTokenKey : tokenKey, token);
}

export function clearToken(admin = false): void {
  localStorage.removeItem(admin ? adminTokenKey : tokenKey);
}

export async function api<T>(path: string, options: RequestInit = {}, admin = false): Promise<T> {
  const token = getToken(admin);
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (options.headers instanceof Headers) {
    options.headers.forEach((value, key) => {
      headers[key] = value;
    });
  } else if (Array.isArray(options.headers)) {
    for (const [key, value] of options.headers) headers[key] = value;
  } else if (options.headers) {
    Object.assign(headers, options.headers);
  }
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...options, headers });
  const text = await res.text();
  const body = text ? JSON.parse(text) : {};
  if (!res.ok) {
    const detail = body.detail || body.error || body;
    const message = typeof detail === "string" ? detail : detail.message || detail.code || res.statusText;
    throw new Error(message);
  }
  return body as T;
}

export function post<T>(path: string, body: JsonRecord, admin = false): Promise<T> {
  return api<T>(path, { method: "POST", body: JSON.stringify(body) }, admin);
}

export function put<T>(path: string, body: JsonRecord, admin = false): Promise<T> {
  return api<T>(path, { method: "PUT", body: JSON.stringify(body) }, admin);
}
