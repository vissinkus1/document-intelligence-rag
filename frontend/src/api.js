/**
 * API client for communicating with the RAG backend.
 * All requests go through this module for consistent auth header handling.
 */

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

/** Get the stored JWT token */
function getToken() {
  return localStorage.getItem("token");
}

/** Build headers with optional auth */
function headers(json = true) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  const token = getToken();
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

/** Handle response: parse JSON or throw with message */
async function handle(res) {
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const msg = data?.detail || `Request failed (${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}

// ---- Auth ----

export async function register(email, password) {
  const res = await fetch(`${API}/auth/register`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ email, password }),
  });
  return handle(res);
}

export async function login(email, password) {
  const form = new URLSearchParams();
  form.append("username", email);
  form.append("password", password);
  const res = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  });
  return handle(res);
}

export async function getMe() {
  const res = await fetch(`${API}/auth/me`, { headers: headers() });
  return handle(res);
}

export async function listUsers() {
  const res = await fetch(`${API}/auth/users`, { headers: headers() });
  return handle(res);
}

// ---- Documents ----

export async function uploadDocuments(files) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const res = await fetch(`${API}/documents`, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}` },
    body: form,
  });
  return handle(res);
}

export async function listDocuments() {
  const res = await fetch(`${API}/documents`, { headers: headers() });
  return handle(res);
}

export async function deleteDocument(docId) {
  const res = await fetch(`${API}/documents/${docId}`, {
    method: "DELETE",
    headers: headers(),
  });
  return handle(res);
}

// ---- Chat ----

export async function askQuestion(question, sessionId = null) {
  const body = { question };
  if (sessionId) body.session_id = sessionId;
  const res = await fetch(`${API}/chat/ask`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  return handle(res);
}

export async function listSessions() {
  const res = await fetch(`${API}/chat/sessions`, { headers: headers() });
  return handle(res);
}

export async function getSession(sessionId) {
  const res = await fetch(`${API}/chat/sessions/${sessionId}`, {
    headers: headers(),
  });
  return handle(res);
}

export async function deleteSession(sessionId) {
  const res = await fetch(`${API}/chat/sessions/${sessionId}`, {
    method: "DELETE",
    headers: headers(),
  });
  return handle(res);
}

export async function updateSessionTitle(sessionId, title) {
  const res = await fetch(`${API}/chat/sessions/${sessionId}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify({ title }),
  });
  return handle(res);
}
