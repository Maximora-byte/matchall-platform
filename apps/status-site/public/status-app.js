export const STATUS = {
  operational: { label: "运行正常", icon: "●" },
  degraded: { label: "性能下降", icon: "△" },
  partial_outage: { label: "部分不可用", icon: "◐" },
  outage: { label: "不可用", icon: "×" },
  maintenance: { label: "维护中", icon: "◇" },
  unknown: { label: "状态未知", icon: "?" },
};
export const CATEGORY = {
  identity: "身份认证",
  content: "内容服务",
  data: "数据服务",
  distribution: "软件分发",
  network: "网络服务",
};
export const HISTORY_TIMEZONE_NOTE = "历史按 UTC 日统计";
const PRIORITY = [
  "outage",
  "partial_outage",
  "degraded",
  "maintenance",
  "unknown",
  "operational",
];
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>'"]/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[
        c
      ],
  );
const finite = (v) =>
  v === null || v === undefined || v === ""
    ? null
    : Number.isFinite(Number(v))
      ? Number(v)
      : null;
const fmt = (v) =>
  v
    ? new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date(Number(v) * 1000)) + " UTC+8"
    : "暂无数据";
const dayLabel = (v) =>
  v
    ? new Intl.DateTimeFormat("zh-CN", {
        timeZone: "UTC",
        month: "2-digit",
        day: "2-digit",
      }).format(new Date(v + "T00:00:00Z"))
    : "无数据";

export function historyAggregate(days) {
  const valid = Array.isArray(days)
    ? days.filter((x) => finite(x.checks) > 0 && finite(x.uptime) !== null)
    : [];
  const samples = valid.reduce((s, x) => s + Number(x.checks), 0);
  const good = valid.reduce(
    (s, x) => s + (Number(x.checks) * Number(x.uptime)) / 100,
    0,
  );
  return { samples, uptime: samples ? (good * 100) / samples : null };
}
export function normalizeService(
  s,
  now = Date.now() / 1000,
  staleAfter = 180,
  days = [],
) {
  const checked = finite(s.last_checked_at),
    v2 = checked !== null && finite(s.uptime_30d) !== null,
    a = historyAggregate(days);
  let status = STATUS[s.status]
    ? s.status
    : STATUS[s.state]
      ? s.state
      : "unknown";
  const stale =
    s.stale === true || checked === null || now - checked > staleAfter;
  if (stale) status = "unknown";
  return {
    ...s,
    status,
    stale,
    compatibility: !v2,
    uptime_30d: finite(s.uptime_30d) ?? a.uptime,
    avg_latency: finite(s.avg_latency),
    sample_count_24h: finite(s.sample_count_24h) ?? 0,
    sample_count_30d: finite(s.sample_count_30d) ?? a.samples,
    coverage_ratio_30d: finite(s.coverage_ratio_30d),
  };
}
export function deriveOverall(items) {
  const states = new Set(items.map((x) => x.status));
  return PRIORITY.find((x) => states.has(x)) || "unknown";
}
export function overallHeadline(status, items) {
  const count = items.filter((item) => item.status === status).length;
  const labels = {
    outage: "服务不可用",
    partial_outage: "服务部分不可用",
    degraded: "服务性能下降",
    maintenance: "服务维护中",
    unknown: "服务状态未知",
  };
  return status === "operational"
    ? "所有服务运行正常"
    : `${count || 1} 项${labels[status] || "服务状态未知"}`;
}
function historyState(d) {
  const u = finite(d.uptime),
    n = finite(d.checks) || 0;
  if (!n && finite(d.maintenance_minutes) > 0) return "maintenance";
  if (!n || u === null) return "unknown";
  return u >= 99.9 ? "operational" : u >= 98 ? "degraded" : "outage";
}
export function historyCells(days) {
  if (!Array.isArray(days) || !days.length)
    return '<span class="history-empty">暂无历史数据</span>';
  return days
    .map((d) => {
      const state = historyState(d),
        u = finite(d.uptime),
        n = finite(d.checks) || 0,
        m = finite(d.maintenance_minutes) || 0,
        metric =
          state === "maintenance"
            ? `维护 ${m} 分钟`
            : u === null
              ? "无数据"
              : `${u.toFixed(2)}% · ${n} 次`,
        label = `${d.date} · ${metric}`;
      return `<button type="button" class="history-cell ${state}" data-history-label="${esc(label)}" title="${esc(label)}" aria-label="${esc(label)}"><span class="sr-only">${esc(label)}</span></button>`;
    })
    .join("");
}
function coverage(s) {
  if (!s.sample_count_30d) return "暂无历史样本";
  const start = s.coverage_start_at
      ? fmt(s.coverage_start_at).replace(" UTC+8", "")
      : "未知",
    end = s.coverage_end_at
      ? fmt(s.coverage_end_at).replace(" UTC+8", "")
      : "未知",
    quality = s.coverage_complete_30d
      ? "覆盖完整"
      : s.coverage_ratio_30d === null
        ? "覆盖率未知"
        : `覆盖 ${s.coverage_ratio_30d.toFixed(1)}%`;
  return `${start} 至 ${end} · ${quality}`;
}
export function uptimeLabel(service) {
  const value = finite(service.uptime_30d);
  if (value === null) return "暂无数据";
  const total = finite(service.sample_count_30d),
    good = finite(service.successful_samples_30d);
  if (
    total !== null &&
    good !== null &&
    good < total &&
    Number(value.toFixed(3)) >= 100
  )
    return "99.999%";
  return `${value.toFixed(3)}%`;
}
function serviceRow(s, days) {
  const meta = STATUS[s.status] || STATUS.unknown,
    lat =
      s.avg_latency === null || !s.sample_count_24h
        ? "暂无数据"
        : `${Math.round(s.avg_latency)} ms`,
    m = s.maintenance || {},
    first = days[0]?.date,
    last = days.at(-1)?.date,
    cells = historyCells(days);
  return `<details class="service-row ${s.status}" id="${esc(s.key)}"><summary aria-expanded="false"><span class="service-title"><span class="state-symbol" aria-hidden="true">${meta.icon}</span><span><strong>${esc(s.name)}</strong><small>${esc(s.name_en || s.key)}</small></span></span><span class="history-block"><span class="history" aria-label="每日可用率：${esc(first || "无数据")} 至 ${esc(last || "无数据")}">${cells}</span><span class="history-axis"><span>${dayLabel(first)}</span><span class="history-readout" aria-live="polite">选择日期查看指标</span><span>${dayLabel(last)}</span></span></span><span class="metric"><strong>${uptimeLabel(s)}</strong><small>${s.coverage_complete_30d ? "最近 30 个 UTC 日" : "实际覆盖期"} · ${s.sample_count_30d} 样本</small></span><span class="metric"><strong>${lat}</strong><small>24 小时成功探测均值</small></span><span class="row-state"><span class="badge ${s.status}">${meta.icon} ${meta.label}</span><span class="details-action" aria-hidden="true">详情⌄</span></span></summary><div class="service-detail"><div><h4>监测范围</h4><p>${esc(s.scope || "暂无范围说明")}</p><p class="coverage"><strong>统计覆盖：</strong>${esc(coverage(s))}</p></div><dl><div><dt>最后成功</dt><dd>${fmt(s.last_success_at)}</dd></div><div><dt>最近探测</dt><dd>${fmt(s.last_checked_at)}</dd></div><div><dt>检查类型</dt><dd>${esc(s.check_type || "HTTP")}</dd></div><div><dt>探测位置</dt><dd>${esc(s.probe_region || "未说明")}</dd></div></dl>${s.status === "maintenance" ? `<p class="maintenance-note"><strong>${esc(m.title || "计划维护")}</strong> ${esc(m.detail || "暂无公开说明")}</p>` : ""}<div class="mobile-history history-block"><h4>每日历史</h4><span class="history">${cells}</span><span class="history-axis"><span>${dayLabel(first)}</span><span class="history-readout" aria-live="polite">点击日期查看指标</span><span>${dayLabel(last)}</span></span></div><div class="row-actions"><a href="${esc(s.url)}" rel="noopener">打开服务 ↗</a><a href="${esc(s.help_url || "https://www.maximoraverse.org/contact/")}" rel="noopener">相关帮助 ↗</a></div></div></details>`;
}
export function renderGroups(items, map) {
  return Object.entries(CATEGORY)
    .map(([k, n]) => {
      const list = items.filter((x) => x.category === k);
      return list.length
        ? `<section class="service-group"><h3>${n}<span>${list.length} 项</span></h3>${list.map((x) => serviceRow(x, map.get(x.key) || [])).join("")}</section>`
        : "";
    })
    .join("");
}
function notice(s) {
  const meta = STATUS[s.status],
    m = s.maintenance || {},
    start = m.starts_at || s.last_checked_at,
    detail =
      m.detail ||
      `最近的${esc(s.check_type || "健康")}探测未达到正常条件；当前结论仅适用于所列监测范围。`;
  const impact =
    s.status === "maintenance"
      ? "计划维护；具体业务影响以维护说明为准"
      : "健康端点异常，具体业务影响待确认";
  return `<article class="notice ${s.status}"><div><span class="badge ${s.status}">${meta.icon} ${meta.label}</span><h3>${esc(m.title || s.name + " " + meta.label)}</h3></div><dl><div><dt>受影响范围</dt><dd>${esc(s.name)} · ${impact}</dd></div><div><dt>开始/发现时间</dt><dd>${fmt(start)}</dd></div><div><dt>最近进展</dt><dd>${esc(detail)}</dd></div><div><dt>临时办法</dt><dd>${esc(m.workaround || "暂无已验证的临时办法")}</dd></div><div><dt>下次更新时间</dt><dd>${m.next_update_at ? fmt(m.next_update_at) : "尚未安排；有新信息时更新"}</dd></div></dl></article>`;
}
function incidents(items) {
  if (!items.length)
    return '<article class="incident resolved"><span class="state-symbol">●</span><div><h3>近期没有已记录事件</h3><p>没有事件记录不代表所有业务流程均被探测覆盖。</p></div></article>';
  return items
    .map(
      (x) =>
        `<article class="incident"><span class="state-symbol">${x.resolved_at ? "●" : "◐"}</span><div><p class="incident-time">${fmt(x.started_at)}${x.resolved_at ? " — " + fmt(x.resolved_at) : " · 处理中"}</p><h3>${esc(x.title || "服务事件")}</h3><p>${esc(x.detail || "暂无更多公开说明")}</p></div></article>`,
    )
    .join("");
}
function bind(root) {
  root
    .querySelectorAll("details")
    .forEach((d) =>
      d.addEventListener("toggle", () =>
        d
          .querySelector("summary")
          ?.setAttribute("aria-expanded", String(d.open)),
      ),
    );
  root.querySelectorAll(".history-cell").forEach((b) => {
    const show = () => {
      const out = b
        .closest(".history-block")
        ?.querySelector(".history-readout");
      if (out) out.textContent = b.dataset.historyLabel;
    };
    b.addEventListener("mouseenter", show);
    b.addEventListener("focus", show);
    b.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      show();
    });
  });
}
export function applyPayload(data, hist, now = Date.now() / 1000) {
  const map = new Map(
      (Array.isArray(hist?.services) ? hist.services : []).map((x) => [
        x.key,
        x.days,
      ]),
    ),
    items = (Array.isArray(data.services) ? data.services : []).map((x) =>
      normalizeService(
        x,
        now,
        finite(data.stale_after_seconds) || 180,
        map.get(x.key) || [],
      ),
    );
  if (!items.length) throw new Error("服务列表为空");
  const overall = deriveOverall(items),
    meta = STATUS[overall],
    summary = document.querySelector("#summary");
  summary.className = `summary ${overall}`;
  summary.setAttribute("aria-busy", "false");
  summary.querySelector(".state-icon").textContent = meta.icon;
  summary.querySelector(".summary-state strong").textContent = overallHeadline(
    overall,
    items,
  );
  const checks = items.map((x) => finite(x.last_checked_at)).filter(Boolean);
  document.querySelector("#last-probe").textContent = checks.length
    ? fmt(Math.max(...checks))
    : "暂无探测";
  document.querySelector("#page-refresh").textContent = fmt(
    data.generated_at || now,
  );
  document.querySelector("#probe-region").textContent =
    items[0].probe_region || "未说明";
  const root = document.querySelector("#services");
  root.innerHTML = renderGroups(items, map);
  root.setAttribute("aria-busy", "false");
  bind(root);
  const unknown = items.filter((x) => x.status === "unknown").length,
    legacy = items.some((x) => x.compatibility);
  const freshness = legacy
    ? "旧版接口：当前状态无法验证，历史指标仅供参考"
    : unknown
      ? `${items.length - unknown}/${items.length} 项数据最新 · ${unknown} 项未知`
      : `${items.length}/${items.length} 项数据最新`;
  document.querySelector("#freshness").textContent =
    `${freshness} · ${HISTORY_TIMEZONE_NOTE}`;
  const active = items.filter((x) =>
      ["degraded", "partial_outage", "outage", "maintenance"].includes(
        x.status,
      ),
    ),
    section = document.querySelector("#attention-section");
  section.hidden = !active.length;
  document.querySelector("#attention").innerHTML = active.map(notice).join("");
  document.querySelector("#incidents").innerHTML = incidents(
    Array.isArray(data.incidents) ? data.incidents : [],
  );
  return { overall, services: items };
}
function unavailable(msg) {
  const s = document.querySelector("#summary");
  s.className = "summary unknown";
  s.setAttribute("aria-busy", "false");
  s.querySelector(".state-icon").textContent = "?";
  s.querySelector(".summary-state strong").textContent = "状态数据暂不可用";
  const root = document.querySelector("#services");
  root.innerHTML = `<article class="error"><strong>无法读取最新状态</strong><p>${esc(msg)}。这不等于所有服务中断，请直接打开所需服务确认。</p><button type="button" id="retry">重新获取</button></article>`;
  root.setAttribute("aria-busy", "false");
  document.querySelector("#freshness").textContent = "未取得最新探测数据";
  document.querySelector("#attention-section").hidden = true;
  document.querySelector("#incidents").innerHTML =
    '<article class="incident unknown"><span class="state-symbol">?</span><div><h3>事件数据暂不可用</h3><p>状态接口请求失败；这不表示所有服务发生故障，请稍后重试。</p></div></article>';
  document.querySelector("#retry")?.addEventListener("click", refreshStatus);
}
let controller;
export async function refreshStatus() {
  controller?.abort();
  controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 6000);
  try {
    const [r, h] = await Promise.all([
      fetch("/api/status", {
        headers: { accept: "application/json" },
        cache: "no-store",
        signal: controller.signal,
      }),
      fetch("/api/status/history?days=30", {
        headers: { accept: "application/json" },
        cache: "no-store",
        signal: controller.signal,
      }).catch(() => null),
    ]);
    if (!r.ok) throw new Error(`状态 API 返回 ${r.status}`);
    applyPayload(await r.json(), h?.ok ? await h.json() : { services: [] });
  } catch (e) {
    unavailable(e.name === "AbortError" ? "请求超时" : e.message);
  } finally {
    clearTimeout(timeout);
  }
}
if (typeof document !== "undefined") {
  refreshStatus();
  setInterval(() => {
    if (!document.hidden) refreshStatus();
  }, 60000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshStatus();
  });
}
