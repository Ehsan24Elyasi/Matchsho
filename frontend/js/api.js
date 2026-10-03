export class ApiError extends Error {
  constructor(status, message, extra = {}) {
    super(message);
    this.status = status;
    Object.assign(this, extra);
  }
}
let csrfFlight, refreshFlight;
const PROTOCOL = "3";
function checkProtocol(response) {
  const serverProtocol = response.headers.get("X-Matchsho-Protocol");
  if (serverProtocol && serverProtocol !== PROTOCOL)
    throw new ApiError(
      409,
      "نسخهٔ برنامه تغییر کرده است. صفحه را دوباره بارگذاری کنید و وضعیت عملیات را بررسی کنید.",
      { protocolMismatch: true },
    );
}
const unresolvedMutations = new Map();
function csrfCookie() {
  return document.cookie
    .split("; ")
    .find((x) => x.startsWith("csrf_token="))
    ?.slice(11);
}
async function csrf() {
  const existing = csrfCookie();
  if (existing) return decodeURIComponent(existing);
  csrfFlight ??= fetch("/api/auth/csrf", {
    credentials: "include",
    cache: "no-store",
    headers: { "X-Matchsho-Protocol": PROTOCOL },
  })
    .then(async (r) => {
      checkProtocol(r);
      if (!r.ok) throw new ApiError(r.status, "دریافت اعتبار فرم ممکن نشد.");
      return (await r.json()).csrf_token;
    })
    .finally(() => (csrfFlight = null));
  return csrfFlight;
}
async function refresh() {
  if (refreshFlight) return refreshFlight;
  const start = Date.now();
  const work = async () => {
    // The marker contains no credentials; Web Locks serialize cookie rotation across tabs.
    let marker = 0;
    try {
      marker = Number(localStorage.getItem("matchsho.session-rotation") || 0);
    } catch {}
    if (marker > start) return;
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: {
        "X-CSRF-Token": await csrf(),
        "X-Matchsho-Protocol": PROTOCOL,
      },
    });
    checkProtocol(response);
    if (!response.ok)
      throw new ApiError(response.status, "نشست شما پایان یافته است.");
    try {
      localStorage.setItem("matchsho.session-rotation", String(Date.now()));
    } catch {}
  };
  refreshFlight = (
    navigator.locks
      ? navigator.locks.request("matchsho-session-refresh", work)
      : work()
  ).finally(() => (refreshFlight = null));
  return refreshFlight;
}
export async function api(
  path,
  { method = "GET", body, signal, retry = true, idempotencyKey, ...rest } = {},
) {
  if (!/^\/[a-zA-Z0-9/?=&%_.-]*$/.test(path))
    throw new Error("Invalid API route");
  const headers = {
    Accept: "application/json",
    "X-Matchsho-Protocol": PROTOCOL,
    ...rest.headers,
  };
  const intent =
    method === "GET" ? null : `${method}:${path}:${JSON.stringify(body)}`;
  if (method !== "GET") {
    headers["X-CSRF-Token"] = await csrf();
    headers["Idempotency-Key"] =
      idempotencyKey || unresolvedMutations.get(intent) || crypto.randomUUID();
    unresolvedMutations.set(intent, headers["Idempotency-Key"]);
  }
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "include",
      cache: "no-store",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError(0, "ارتباط با سرور برقرار نشد.");
  }
  checkProtocol(response);
  if (
    response.status === 401 &&
    retry &&
    !/^\/auth\/(login|register|activate|refresh|logout|reset-password|forgot-password|csrf)/.test(
      path,
    )
  ) {
    await refresh();
    return api(path, {
      method,
      body,
      signal,
      retry: false,
      idempotencyKey: headers["Idempotency-Key"],
      ...rest,
    });
  }
  let data;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    if (response.status < 500 && intent) unresolvedMutations.delete(intent);
    const detail = data?.detail;
    const fields = Array.isArray(detail)
      ? detail.map((x) => ({ name: x.loc?.at(-1), message: x.msg }))
      : [];
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? "اطلاعات واردشده معتبر نیست. فیلدهای مشخص‌شده را بررسی کنید."
          : detail?.message || "عملیات انجام نشد.";
    throw new ApiError(response.status, message, {
      fields,
      retryAfter: response.headers.get("Retry-After"),
      detail,
    });
  }
  if (intent) unresolvedMutations.delete(intent);
  return data;
}
export const post = (path, body) => api(path, { method: "POST", body });
