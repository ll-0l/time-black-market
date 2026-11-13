// 백엔드 API 호출 모듈
export const API_BASE_URL = String(window.APP_CONFIG?.API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function detailToMessage(detail) {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI/Pydantic 422 검증 오류
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "";
        const msg = String(d.msg || "").replace(/^Value error, /, "");
        return field && field !== "body" ? `${field}: ${msg}` : msg;
      })
      .join(" / ");
  }
  return JSON.stringify(detail);
}

async function request(path, { method = "GET", body, timeout = 30000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const text = await res.text();
    const data = text ? JSON.parse(text) : null;
    if (!res.ok) throw new ApiError(detailToMessage(data?.detail) || `요청 실패 (${res.status})`, res.status);
    return data;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err.name === "AbortError") throw new ApiError("서버 응답이 너무 늦어요. 잠시 후 다시 시도하세요.", 0);
    throw new ApiError("서버에 연결할 수 없어요. 서버가 깨어나는 중일 수 있어요.", 0);
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  health: (timeout = 8000) => request("/health", { timeout }),
  summary: () => request("/api/data/summary"),
  statistics: () => request("/api/data/statistics"),
  listData: () => request("/api/data"),
  createData: (body) => request("/api/data", { method: "POST", body }),
  updateData: (id, body) => request(`/api/data/${encodeURIComponent(id)}`, { method: "PUT", body }),
  deleteData: (id) => request(`/api/data/${encodeURIComponent(id)}`, { method: "DELETE" }),
  listConversations: () => request("/api/conversations"),
  getConversation: (id) => request(`/api/conversations/${encodeURIComponent(id)}`),
  deleteConversation: (id) => request(`/api/conversations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  syncLedger: () => request("/api/tasks/sync", { method: "POST" }),
  listTasks: (status = "open", limit = 30) => request(`/api/tasks?status=${status}&limit=${limit}`),
  estimateTask: (title) => request("/api/tasks/estimate", { method: "POST", body: { title }, timeout: 60000 }),
  createTask: (body) => request("/api/tasks", { method: "POST", body }),
  updateTask: (id, body) => request(`/api/tasks/${encodeURIComponent(id)}`, { method: "PUT", body }),
  completeTask: (id, actualMinutes) =>
    request(`/api/tasks/${encodeURIComponent(id)}/complete`, { method: "POST", body: { actual_minutes: actualMinutes } }),
  reopenTask: (id) => request(`/api/tasks/${encodeURIComponent(id)}/reopen`, { method: "POST" }),
  deleteTask: (id) => request(`/api/tasks/${encodeURIComponent(id)}`, { method: "DELETE" }),
  chat: (message, conversationId) =>
    request("/api/chat", { method: "POST", body: { message, conversation_id: conversationId || null }, timeout: 90000 }),
};
