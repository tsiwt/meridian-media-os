export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function apiUrl(path) {
  if (typeof path !== "string" || !path.startsWith("/api/")) {
    throw new Error("Unsupported API path");
  }
  const url = new URL(path, location.origin);
  if (url.origin !== location.origin) throw new Error("Cross-origin API request blocked");
  return `${url.pathname}${url.search}`;
}

async function request(path, options = {}) {
  const init = { method: options.method || "GET", headers: { Accept: "application/json" } };
  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  // Same-origin check above; path is constrained to /api/ by apiUrl().
  // nosemgrep: gitlab.nodejs_scan.javascript-ssrf-rule-node_ssrf
  const response = await fetch(apiUrl(path), init);
  const contentType = response.headers.get("Content-Type") || "";
  let payload = null;
  if (contentType.includes("application/json")) {
    payload = await response.json();
  } else {
    payload = await response.text();
  }
  if (!response.ok) {
    const message = payload && payload.message ? payload.message : `Request failed (${response.status})`;
    throw new ApiError(message, response.status, payload);
  }
  return payload;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body: body ?? {} }),
  put: (path, body) => request(path, { method: "PUT", body: body ?? {} }),
  patch: (path, body) => request(path, { method: "PATCH", body: body ?? {} }),
};

export function qs(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}