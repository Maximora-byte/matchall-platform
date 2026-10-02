export const STATUS_API = "https://status.maximoraverse.org/api/status";
export const STALE_AFTER_SECONDS = 180;
// Match the Hub's monitored registry, not the landing page's marketing cards.
export const REQUIRED_SERVICE_KEYS = ["home", "blog", "account", "drive", "mirrors", "network"];
const PRIORITY = ["outage", "partial_outage", "degraded", "maintenance", "unknown", "operational"];
const LABELS = {
  operational: "所有受监测服务运行正常",
  degraded: "部分受监测服务性能下降",
  partial_outage: "部分受监测服务部分不可用",
  outage: "部分受监测服务不可用",
  maintenance: "部分受监测服务维护中",
  unknown: "服务状态待确认",
};
const record = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const positiveInteger = (value) => Number.isSafeInteger(value) && value > 0;
const validTime = positiveInteger;
const fresh = (value, now, maxAge) => validTime(value) && value <= now && now - value <= maxAge;
const summary = (status) => ({ status, label: LABELS[status] });

export function deriveStatusSummary(data, now = Date.now() / 1000) {
  if (!record(data) || data.schema_version !== 2 || !positiveInteger(data.stale_after_seconds) ||
      !Number.isFinite(now) || now <= 0 ||
      !Array.isArray(data.services) || !data.services.length) return summary("unknown");
  // Accept a stricter server freshness window, but never extend our local limit.
  const maxAge = Math.min(data.stale_after_seconds, STALE_AFTER_SECONDS);
  if (!fresh(data.generated_at, now, maxAge)) return summary("unknown");
  const services = Array.from(data.services);
  // Validate the whole consumed contract before trusting even an incident status.
  // A null probe time is legitimate only for an explicitly stale/unprobed service.
  if (!services.every((service) => record(service) &&
      typeof service.key === "string" && service.key.trim() === service.key && service.key.length > 0 &&
      typeof service.stale === "boolean" && PRIORITY.includes(service.status) &&
      (service.last_checked_at === null ? service.stale :
        validTime(service.last_checked_at) && service.last_checked_at <= data.generated_at))) {
    return summary("unknown");
  }
  const keys = services.map((service) => service.key);
  const complete = REQUIRED_SERVICE_KEYS.every((key) => keys.includes(key)) &&
    new Set(keys).size === keys.length;
  if (!complete) return summary("unknown");
  const states = services.map((service) =>
    !service.stale && fresh(service.last_checked_at, now, maxAge) ? service.status : "unknown");
  // Known incidents retain the status page's priority; missing data can never turn green.
  return summary(PRIORITY.find((state) => states.includes(state)) || "unknown");
}

export async function fetchStatusPayload(fetchImpl = fetch, signal) {
  const response = await fetchImpl(STATUS_API, {
    headers: { accept: "application/json" }, cache: "no-store", credentials: "omit", signal,
  });
  if (!response.ok) throw new Error("Status API unavailable");
  return response.json();
}

export function mountStatusBadge(element) {
  const label = element.querySelector("[data-status-label]");
  let payload = null;
  let controller;
  const render = () => {
    const result = deriveStatusSummary(payload);
    element.dataset.status = result.status;
    if (label.textContent !== result.label) label.textContent = result.label;
  };
  const refresh = async () => {
    render(); // Recheck old probe timestamps immediately after tab resume.
    controller?.abort();
    const request = new AbortController();
    controller = request;
    const timeout = setTimeout(() => request.abort(), 6000);
    try {
      const data = await fetchStatusPayload(fetch, request.signal);
      if (controller === request) payload = data;
    } catch {
      if (controller === request) payload = null;
    } finally {
      clearTimeout(timeout);
      if (controller === request) render();
    }
  };
  refresh();
  // Re-evaluate freshness between requests; a healthy badge must not outlive its probes.
  const freshnessTimer = setInterval(render, 1000);
  const refreshTimer = setInterval(() => { if (!document.hidden) refresh(); }, 60000);
  const resume = () => { if (!document.hidden) refresh(); };
  document.addEventListener("visibilitychange", resume);
  return () => {
    controller?.abort();
    clearInterval(freshnessTimer);
    clearInterval(refreshTimer);
    document.removeEventListener("visibilitychange", resume);
  };
}

if (typeof document !== "undefined") {
  const badge = document.querySelector(".status-pill[data-status]");
  if (badge) mountStatusBadge(badge);
}
