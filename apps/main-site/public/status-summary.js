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
const validTime = (value) => typeof value === "number" && Number.isFinite(value) && value > 0;
const fresh = (value, now, maxAge) => validTime(value) && value <= now && now - value <= maxAge;
const summary = (status) => ({ status, label: LABELS[status] });

export function deriveStatusSummary(data, now = Date.now() / 1000) {
  if (data?.schema_version !== 2 || !fresh(data.generated_at, now, STALE_AFTER_SECONDS) ||
      !Array.isArray(data.services) || !data.services.length) return summary("unknown");
  const maxAge = typeof data.stale_after_seconds === "number" && data.stale_after_seconds > 0
    ? Math.min(data.stale_after_seconds, STALE_AFTER_SECONDS) : STALE_AFTER_SECONDS;
  const keys = data.services.map((service) => service?.key);
  const complete = REQUIRED_SERVICE_KEYS.every((key) => keys.includes(key)) &&
    keys.every((key) => typeof key === "string" && key.length > 0) && new Set(keys).size === keys.length;
  const states = data.services.map((service) =>
    service && service.stale !== true && fresh(service.last_checked_at, now, maxAge) &&
      PRIORITY.includes(service.status) ? service.status : "unknown");
  if (!complete) states.push("unknown");
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
