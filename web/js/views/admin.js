import { api, qs } from "../api.js";
import {
  clear, copyText, debounce, fmtCompact, fmtMoney, fmtNumber, fmtPct, fmtTime,
  h, icon, modal, statusBadge, titleCase, toast,
} from "../dom.js";
import { lineChart, terminalMap } from "../components/charts.js";
import { decisionModal } from "../components/audit.js";

const TABS = [
  ["overview", "Overview"],
  ["incidents", "Incidents"],
  ["master", "Master data"],
  ["rules", "Rule engine"],
  ["log", "Decision log"],
];

export async function mount(ctx) {
  const { root, ui } = ctx;
  let data;
  try {
    data = await api.get("/api/admin/overview");
  } catch (error) {
    root.appendChild(errorCard(error));
    return {};
  }
  if (ctx.compact) {
    ui.tab = ui.tab || "overview";
  }
  root.appendChild(pageHead(ctx, data));
  root.appendChild(tabs(ctx));
  const content = h("div", {});
  root.appendChild(content);

  if (ui.tab === "overview") renderOverview(ctx, content, data);
  else if (ui.tab === "incidents") renderIncidents(ctx, content, data);
  else if (ui.tab === "master") await renderMaster(ctx, content);
  else if (ui.tab === "rules") await renderRules(ctx, content);
  else if (ui.tab === "log") await renderLog(ctx, content);

  const refresh = debounce(() => {
    if (["overview", "incidents"].includes(ui.tab)) ctx.rerender();
  }, 2800);
  return {
    onEvent(name) {
      if (["decisions", "incident", "screen", "flight", "kpi"].includes(name)) refresh();
    },
    destroy() {
      refresh.cancel?.();
    },
  };
}

function pageHead(ctx, data) {
  const kpi = data.kpi;
  return h("div", { class: "page-head" },
    h("div", {},
      h("div", { class: "eyebrow", text: "Platform Admin · operator console" }),
      h("h1", { text: ctx.t("admin.title") }),
      h("p", { class: "lede", text: ctx.t("admin.lede") })
    ),
    h("div", { class: "head-actions" },
      h("span", { class: "chip" }, h("strong", { text: fmtNumber(kpi.screensTotal) }), " screens"),
      h("span", { class: "chip" }, h("strong", { text: fmtNumber(kpi.decisionsToday) }), " decisions today"),
      h("a", { class: "btn small", href: "/openapi.yaml", target: "_blank", rel: "noreferrer" }, icon("external", 12), " OpenAPI"),
      h("a", { class: "btn small", href: "/architecture.svg", target: "_blank", rel: "noreferrer" }, "Architecture")
    )
  );
}

function tabs(ctx) {
  const nav = h("div", { class: "tabs", role: "tablist" });
  for (const [key, label] of TABS) {
    nav.appendChild(h("button", {
      class: "tab", role: "tab", "aria-selected": String(ctx.ui.tab === key),
      onClick: () => { ctx.ui.tab = key; ctx.rerender(); },
    }, label));
  }
  return nav;
}

function renderOverview(ctx, root, data) {
  const kpi = data.kpi;
  const grid = h("div", { class: "grid grid-auto", style: { gridTemplateColumns: "repeat(auto-fit, minmax(168px, 1fr))" } },
    kpiCard(ctx.t("admin.screensOnline"), `${kpi.screensOnlinePct}%`, `${data.screens.filter((screen) => screen.status !== "online").length} attention`, "screen"),
    kpiCard(ctx.t("admin.plays"), fmtCompact(kpi.playsToday), `${fmtNumber(kpi.decisionsToday)} decisions`, "play"),
    kpiCard(ctx.t("admin.revenue"), fmtMoney(kpi.revenueToday, kpi.currency), "attributed today", "trend"),
    kpiCard(ctx.t("admin.active"), fmtNumber(kpi.activeCampaigns), `${kpi.openIncidents} open incidents`, "spark"),
    kpiCard(ctx.t("admin.latency"), `${kpi.avgLatencyMs} ms`, "screen heartbeat", "clock"),
    kpiCard(ctx.t("admin.decisions"), fmtNumber(kpi.decisionsToday), `${kpi.fallbacksToday} fallbacks`, "bolt")
  );
  root.appendChild(grid);

  const mapCard = h("div", { class: "card span-2" },
    h("div", { class: "card-head" },
      h("div", {}, h("div", { class: "card-title", text: ctx.t("admin.map") }), h("div", { class: "card-sub", text: ctx.t("admin.mapHint") })),
      h("span", { class: "badge live green", text: "LIVE" })
    ),
    terminalMap({
      zones: data.zones,
      screens: data.screens,
      presence: hasPresence(ctx.state.zonePresence) ? ctx.state.zonePresence : data.presence,
      onScreenClick: (screen) => openScreen(ctx, screen),
      onZoneClick: (zone) => openZone(ctx, zone, data),
    })
  );
  const incidentCard = h("div", { class: "card" },
    h("div", { class: "card-head" },
      h("div", { class: "card-title", text: ctx.t("admin.incidents") }),
      h("button", { class: "btn small", onClick: () => { ctx.ui.tab = "incidents"; ctx.rerender(); } }, "All")
    ),
    h("div", { class: "list" }, ...data.incidents.slice(0, 6).map((incident) => incidentRow(ctx, incident)))
  );
  root.appendChild(h("div", { class: "grid grid-3", style: { marginTop: "16px" } }, mapCard, incidentCard));

  const feedGrid = h("div", { class: "grid grid-4", style: { marginTop: "16px" } },
    ...data.feeds.map((feed) => h("div", { class: "card" },
      h("div", { class: "row-between" },
        h("div", { class: "card-title", text: feed.feed }),
        h("span", { class: feed.status === "live" ? "badge green live" : "badge amber", text: feed.status })
      ),
      h("div", { class: "tiny muted", style: { marginTop: "3px" }, text: feed.adapter }),
      h("div", { class: "grid grid-2", style: { marginTop: "10px", gap: "6px" } },
        miniStat("Last msg", feed.lastMessageAt ? fmtTime(feed.lastMessageAt) : "--"),
        miniStat("Lag", feed.lagSeconds === null ? "--" : `${feed.lagSeconds}s`),
        miniStat("Msg / min", fmtNumber(feed.messagesPerMinute)),
        miniStat("Mode", feed.mode)
      )
    ))
  );
  root.appendChild(feedGrid);

  const performance = data.performance;
  const decisionsCard = h("div", { class: "card span-2" },
    h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Recent decisions" }), h("span", { class: "badge grey", text: "audit trail" })),
    h("div", { class: "table-wrap" },
      h("table", { class: "data" },
        h("thead", {}, h("tr", {},
          h("th", { text: "Screen" }), h("th", { text: "Winner" }), h("th", { class: "num", text: "Score" }),
          h("th", { text: "Source" }), h("th", { text: "Time" })
        )),
        h("tbody", {}, ...data.decisions.map((decision) =>
          h("tr", { style: { cursor: "pointer" }, onClick: () => openDecision(ctx, decision.id) },
            h("td", {}, h("span", { class: "strong", text: decision.screenId }), h("div", { class: "sub", text: decision.zoneId })),
            h("td", { text: decision.winnerName }),
            h("td", { class: "num", text: Number(decision.winnerScore).toFixed(3) }),
            h("td", {}, decision.fallback ? h("span", { class: "badge amber", text: "rule fallback" }) : h("span", { class: "badge green", text: "AI validated" })),
            h("td", { class: "mono tiny", text: fmtTime(decision.decidedAt) })
          )
        ))
      )
    )
  );
  const perfCard = h("div", { class: "card" },
    h("div", { class: "card-head" }, h("div", { class: "card-title", text: ctx.t("admin.performance") }), h("span", { class: "badge teal", text: `${performance.latencySamples} samples` })),
    h("div", { class: "grid grid-2", style: { gap: "8px" } },
      miniStat("API p50", `${performance.p50Ms} ms`),
      miniStat("API p95", `${performance.p95Ms} ms`),
      miniStat("API p99", `${performance.p99Ms} ms`),
      miniStat("Playlist build", `${performance.playlistBuildMs} ms`),
      miniStat("Decision interval", `${performance.decisionInterval}s sim`),
      miniStat("Uptime 7d", `${performance.uptimePct7d}%`)
    ),
    h("div", { class: "divider" }),
    h("div", { class: "eyebrow", text: "Recent API latency" }),
    lineChart({ values: [performance.p50Ms, performance.p95Ms, performance.p99Ms], labels: ["p50", "p95", "p99"], height: 90, format: (value) => `${value}ms` })
  );
  root.appendChild(h("div", { class: "grid grid-3", style: { marginTop: "16px" } }, decisionsCard, perfCard));
}

function hasPresence(presence) {
  return presence && Object.keys(presence).length > 0;
}

function kpiCard(label, value, meta, iconName) {
  return h("div", { class: "card kpi" },
    h("div", { class: "row-between" }, h("div", { class: "kpi-label", text: label }), h("span", { class: "muted" }, icon(iconName, 14))),
    h("div", { class: "kpi-value", text: value }),
    h("div", { class: "kpi-meta", text: meta })
  );
}

function miniStat(label, value) {
  return h("div", { class: "row-between", style: { fontSize: "10px", padding: "3px 0" } },
    h("span", { class: "muted", text: label }),
    h("span", { class: "mono", text: value })
  );
}

function incidentRow(ctx, incident) {
  return h("div", { class: "list-item" },
    h("div", { class: "list-main" },
      h("div", { class: "row", style: { gap: "7px", flexWrap: "wrap" } },
        h("span", { class: `badge ${incident.severity === "high" || incident.severity === "critical" ? "red" : incident.severity === "medium" ? "amber" : "grey"}`, text: incident.severity }),
        h("span", { class: "list-title", text: incident.title })
      ),
      h("div", { class: "list-sub", text: `${incident.kind.replaceAll("_", " ")} · ${incident.owner} · ${fmtTime(incident.createdAt)} UTC` })
    ),
    statusBadge(incident.status)
  );
}

async function openScreen(ctx, screen) {
  try {
    const list = await api.get(`/api/admin/decisions${qs({ screenId: screen.id, limit: 1 })}`);
    if (!list.items.length) {
      toast(`No decision yet for ${screen.id}`, "info");
      return;
    }
    openDecision(ctx, list.items[0].id);
  } catch (error) {
    toast(error.message, "bad");
  }
}

async function openDecision(ctx, id) {
  try {
    const decision = await api.get(`/api/admin/decisions/${id}`);
    decisionModal(decision, ctx);
  } catch (error) {
    toast(error.message, "bad");
  }
}

function openZone(ctx, zone, data) {
  const screens = data.screens.filter((screen) => screen.zone_id === zone.id);
  const presence = data.presence?.[zone.id] || {};
  const body = h("div", { class: "col" },
    h("div", { class: "row wrap" },
      h("span", { class: "chip" }, h("strong", { text: fmtNumber(presence.crowd || 0) }), " estimated pax"),
      h("span", { class: "chip" }, h("strong", { text: `${fmtPct(presence.internationalShare || 0)}` }), " international"),
      h("span", { class: "chip" }, h("strong", { text: String(screens.length) }), " screens")
    ),
    h("div", { class: "table-wrap" },
      h("table", { class: "data" },
        h("thead", {}, h("tr", {}, h("th", { text: "Screen" }), h("th", { text: "Gates" }), h("th", { text: "Status" }), h("th", { text: "Latency" }))),
        h("tbody", {}, ...screens.map((screen) =>
          h("tr", { style: { cursor: "pointer" }, onClick: () => { dialog.close(); openScreen(ctx, screen); } },
            h("td", { class: "strong", text: screen.id }),
            h("td", { class: "sub", text: (screen.nearestGates || []).join(", ") }),
            h("td", {}, statusBadge(screen.status)),
            h("td", { class: "num", text: `${screen.latency_ms} ms` })
          )
        ))
      )
    )
  );
  const dialog = ctx.modal({ title: zone.name, subtitle: `${zone.id} · ${zone.terminalId}`, body, wide: true, actions: [{ label: "Close", primary: true }] });
  return dialog;
}

function renderIncidents(ctx, root, data) {
  root.appendChild(h("div", { class: "section-head" },
    h("div", {},
      h("h2", { text: "Incident & bug tracker" }),
      h("p", { class: "hint", text: "Auto-raised from screen heartbeats, feed lag, creative failures and budget pacing. Owners and status can be changed inline." })
    ),
    h("button", { class: "btn primary small", onClick: () => incidentForm(ctx) }, icon("plus", 12), " New incident")
  ));
  const table = h("div", { class: "card flush table-wrap" },
    h("table", { class: "data" },
      h("thead", {}, h("tr", {},
        h("th", { text: "Severity" }), h("th", { text: "Incident" }), h("th", { text: "Kind" }),
        h("th", { text: "Owner" }), h("th", { text: "Created" }), h("th", { text: "Status" }), h("th", { text: "Actions" })
      )),
      h("tbody", {}, ...(data.incidents.length ? data.incidents : []).map((incident) =>
        h("tr", {},
          h("td", {}, h("span", { class: `badge ${["high", "critical"].includes(incident.severity) ? "red" : incident.severity === "medium" ? "amber" : "grey"}`, text: incident.severity })),
          h("td", {}, h("div", { class: "strong", text: incident.title }), h("div", { class: "sub", text: incident.message })),
          h("td", { class: "sub", text: titleCase(incident.kind.replaceAll("_", " ")) }),
          h("td", { class: "sub", text: incident.owner }),
          h("td", { class: "mono tiny", text: fmtTime(incident.createdAt) }),
          h("td", {}, statusBadge(incident.status)),
          h("td", {}, h("div", { class: "row", style: { gap: "5px" } },
            h("button", { class: "btn small", onClick: () => updateIncident(ctx, incident.id, { status: "investigating" }) }, "Investigate"),
            h("button", { class: "btn small", onClick: () => updateIncident(ctx, incident.id, { status: "resolved" }) }, "Resolve")
          ))
        )
      ))
    )
  );
  root.appendChild(table);
}

async function updateIncident(ctx, id, payload) {
  try {
    await api.patch(`/api/admin/incidents/${id}`, payload);
    toast("Incident updated");
    ctx.rerender();
  } catch (error) {
    toast(error.message, "bad");
  }
}

function incidentForm(ctx) {
  const form = h("form", { class: "form-grid" },
    field("Title", h("input", { class: "input", name: "title", required: true, maxlength: 160 })),
    field("Severity", select("severity", [["medium", "Medium"], ["high", "High"], ["critical", "Critical"], ["low", "Low"]])),
    field("Owner", h("input", { class: "input", name: "owner", value: "ops@mqi.example" })),
    field("Kind", h("input", { class: "input", name: "kind", value: "manual" })),
    field("Message", h("textarea", { class: "textarea full", name: "message", rows: "4" }), "full")
  );
  form.lastChild.className = "field full";
  modal({
    title: "Raise an incident",
    body: form,
    actions: [
      { label: "Cancel" },
      {
        label: "Create", primary: true,
        onClick: async () => {
          const values = Object.fromEntries(new FormData(form).entries());
          try {
            await api.post("/api/admin/incidents", values);
            toast("Incident created");
            ctx.rerender();
          } catch (error) {
            toast(error.message, "bad");
            return false;
          }
        },
      },
    ],
  });
}

async function renderMaster(ctx, root) {
  const entity = ctx.ui.entity || "vendors";
  const definitions = {
    vendors: { label: "Vendors & advertisers", columns: [["name", "Name"], ["kind", "Kind"], ["contact", "Contact"], ["outlets", "Outlets"]], create: "New vendor" },
    outlets: { label: "Outlets & F&B", columns: [["name", "Outlet"], ["advertiserName", "Vendor"], ["zoneName", "Zone"], ["category", "Category"], ["stock_status", "Stock"]], create: "New outlet" },
    airlines: { label: "Airlines", columns: [["iata", "IATA"], ["icao", "ICAO"], ["name", "Name"], ["market", "Market"]], create: "New airline" },
    screens: { label: "Screens", columns: [["id", "ID"], ["name", "Name"], ["zoneName", "Zone"], ["aspect", "Aspect"], ["status", "Status"]], create: "New screen" },
    locations: { label: "Locations", columns: [["id", "Zone"], ["name", "Name"], ["terminalId", "Terminal"], ["kind", "Kind"], ["gates", "Gates"]], create: "New zone" },
  };
  const def = definitions[entity];
  const data = await api.get(`/api/admin/master/${entity}`);
  const tabsRow = h("div", { class: "row wrap", style: { marginBottom: "12px" } },
    ...Object.entries(definitions).map(([key, value]) =>
      h("button", { class: `btn small ${key === entity ? "primary" : ""}`, onClick: () => { ctx.ui.entity = key; ctx.rerender(); } }, value.label)
    )
  );
  root.appendChild(tabsRow);
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: def.label }), h("p", { class: "hint", text: `${data.items.length} records · create and edit without leaving the console` })),
    h("button", { class: "btn primary small", onClick: () => masterForm(ctx, entity, null) }, icon("plus", 12), ` ${def.create}`)
  ));
  const table = h("div", { class: "card flush table-wrap" },
    h("table", { class: "data" },
      h("thead", {}, h("tr", {}, ...def.columns.map(([, label]) => h("th", { text: label })), h("th", { text: "" }))),
      h("tbody", {}, ...data.items.map((row) =>
        h("tr", {},
          ...def.columns.map(([key]) => {
            let value = row[key];
            if (key === "gates") value = (value || []).join(", ");
            if (key === "outlets") value = fmtNumber(value);
            if (key === "stock_status") return h("td", {}, statusBadge(value));
            if (key === "status") return h("td", {}, statusBadge(value));
            return h("td", { class: key === "name" ? "strong" : "" }, String(value ?? "—"));
          }),
          h("td", {}, h("button", { class: "btn small", onClick: () => masterForm(ctx, entity, row) }, "Edit"))
        )
      ))
    )
  );
  root.appendChild(table);
}

async function masterForm(ctx, entity, row) {
  let zones = null;
  let vendors = null;
  if (["outlets", "screens"].includes(entity)) {
    const [zoneData, vendorData] = await Promise.all([
      api.get("/api/admin/master/locations"),
      api.get("/api/admin/master/vendors"),
    ]);
    zones = zoneData.items;
    vendors = vendorData.items;
  }
  const values = row || {};
  let fields;
  if (entity === "vendors") {
    fields = [
      field("Name", h("input", { class: "input", name: "name", value: values.name || "", required: true })),
      field("Kind", select("kind", [["retailer", "Retailer"], ["brand", "Brand"], ["house", "House"], ["airline", "Airline"]], values.kind)),
      field("Color", h("input", { class: "input", type: "color", name: "color", value: values.color || "#38e8c8" })),
      field("Contact", h("input", { class: "input", name: "contact", value: values.contact || "" })),
    ];
  } else if (entity === "outlets") {
    fields = [
      field("Name", h("input", { class: "input", name: "name", value: values.name || "", required: true })),
      field("Vendor", select("advertiserId", vendors.map((vendor) => [vendor.id, vendor.name]), values.advertiser_id)),
      field("Zone", select("zoneId", zones.map((zone) => [zone.id, `${zone.id} · ${zone.name}`]), values.zone_id)),
      field("Category", h("input", { class: "input", name: "category", value: values.category || "retail" })),
    ];
  } else if (entity === "airlines") {
    fields = [
      field("IATA", h("input", { class: "input", name: "iata", maxlength: "2", value: values.iata || "", required: true })),
      field("ICAO", h("input", { class: "input", name: "icao", maxlength: "3", value: values.icao || "" })),
      field("Name", h("input", { class: "input", name: "name", value: values.name || "", required: true })),
      field("Market", h("input", { class: "input", name: "market", value: values.market || "International" })),
    ];
  } else if (entity === "screens") {
    fields = [
      field("Name", h("input", { class: "input", name: "name", value: values.name || "", required: true })),
      field("Zone", select("zoneId", zones.map((zone) => [zone.id, `${zone.id} · ${zone.name}`]), values.zone_id)),
      field("Aspect", select("aspect", [["16:9", "16:9 landscape"], ["9:16", "9:16 portrait"]], values.aspect)),
      field("Status", select("status", [["online", "Online"], ["degraded", "Degraded"], ["offline", "Offline"]], values.status)),
      field("Nearest gates", h("input", { class: "input", name: "nearestGates", value: (values.nearestGates || []).join(","), placeholder: "40,41,42" })),
      field("Size (in)", h("input", { class: "input", type: "number", name: "sizeInches", value: values.size_inches || 55 })),
    ];
  } else {
    fields = [
      field("Zone ID", h("input", { class: "input", name: "id", value: values.id || "", required: true, placeholder: "T2-G" })),
      field("Name", h("input", { class: "input", name: "name", value: values.name || "", required: true })),
      field("Terminal", select("terminalId", [["T1", "T1"], ["T2", "T2"]], values.terminal_id)),
      field("Kind", select("zoneKind", [["gate", "Gate zone"], ["retail", "Retail"], ["food", "Food"], ["lounge", "Lounge"], ["security", "Security"], ["arrivals", "Arrivals"]], values.kind)),
      field("Gates", h("input", { class: "input", name: "gates", value: (values.gates || []).join(","), placeholder: "40,41,42" })),
      field("Concourse", h("input", { class: "input", name: "concourse", value: values.concourse || "F" })),
    ];
  }
  const form = h("form", { class: "form-grid" }, ...fields);
  const editing = Boolean(row);
  modal({
    title: editing ? `Edit ${entity.slice(0, -1)} ${row.id || row.iata || ""}` : `Create ${entity.slice(0, -1)}`,
    subtitle: "Changes are written to the platform master data immediately.",
    body: form,
    wide: true,
    actions: [
      { label: "Cancel" },
      {
        label: editing ? "Save changes" : "Create", primary: true,
        onClick: async () => {
          const raw = Object.fromEntries(new FormData(form).entries());
          try {
            if (editing) {
              const payload = {};
              if (entity === "outlets") {
                Object.assign(payload, { name: raw.name, category: raw.category, zone_id: raw.zoneId });
              } else if (entity === "screens") {
                Object.assign(payload, { name: raw.name, status: raw.status, zone_id: raw.zoneId, aspect: raw.aspect });
              } else {
                for (const [key, value] of Object.entries(raw)) payload[key] = value;
              }
              await api.patch(`/api/admin/master/${entity}/${row.id || row.iata}`, payload);
            } else {
              if (raw.nearestGates) raw.nearestGates = raw.nearestGates.split(",").map((item) => item.trim()).filter(Boolean);
              if (raw.gates) raw.gates = raw.gates.split(",").map((item) => item.trim()).filter(Boolean);
              await api.post(`/api/admin/master/${entity}`, raw);
            }
            toast("Master data saved");
            ctx.rerender();
          } catch (error) {
            toast(error.message, "bad");
            return false;
          }
        },
      },
    ],
  });
}

async function renderRules(ctx, root) {
  const rules = await api.get("/api/admin/rules");
  const weights = rules.globalWeights || {};
  const form = h("form", { class: "grid grid-2" },
    h("div", { class: "card" },
      h("div", { class: "card-title", text: "Global scoring weights" }),
      h("p", { class: "card-sub", text: "Deterministic weights applied after AI proposes a ranking." }),
      h("div", { class: "grid grid-2", style: { marginTop: "12px", gap: "10px" } },
        ...["audience", "business", "freshness", "exploration", "bid"].map((key) =>
          field(key, h("input", { class: "input", type: "number", step: "0.01", min: "0", max: "1", name: `w_${key}`, value: weights[key] ?? 0 }))
        )
      )
    ),
    h("div", { class: "card" },
      h("div", { class: "card-title", text: "Business guards" }),
      h("p", { class: "card-sub", text: "Applied to every screen slot, before and after AI scoring." }),
      h("div", { class: "grid grid-2", style: { marginTop: "12px", gap: "10px" } },
        field("Exploration %", h("input", { class: "input", type: "number", min: "0", max: "100", step: "0.5", name: "explorationPct", value: rules.explorationPct ?? 5 })),
        field("Frequency cap (min)", h("input", { class: "input", type: "number", min: "0", name: "frequencyCapMin", value: rules.frequencyCapMin ?? 20 })),
        field("Competitor separation (min)", h("input", { class: "input", type: "number", min: "0", name: "competitorSeparationMin", value: rules.competitorSeparationMin ?? 20 })),
        field("Delay threshold (min)", h("input", { class: "input", type: "number", min: "0", name: "delayThresholdMin", value: rules.delayThresholdMin ?? 30 })),
        field("Minimum evidence confidence", h("input", { class: "input", type: "number", min: "0", max: "1", step: "0.01", name: "minEvidenceConfidence", value: rules.minEvidenceConfidence ?? 0.6 })),
        field("House fallback campaign", h("input", { class: "input", name: "houseCampaignId", value: rules.houseCampaignId || "CMP-18" }))
      )
    ),
    h("div", { class: "card span-2" },
      h("div", { class: "row-between" },
        h("div", {},
          h("div", { class: "eyebrow", text: "Segment model in use" }),
          h("div", { class: "row", style: { marginTop: "6px" } },
            h("span", { class: "badge purple", text: rules.segmentModel || "seg-2026.10-v3" }),
            h("span", { class: "muted tiny", text: `Pacing: ${rules.pacing || "even"}` })
          )
        ),
        h("button", { class: "btn primary", type: "submit" }, icon("check", 13), " Save rules")
      )
    )
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const raw = Object.fromEntries(new FormData(form).entries());
    const payload = {
      globalWeights: Object.fromEntries(Object.entries(raw).filter(([key]) => key.startsWith("w_")).map(([key, value]) => [key.slice(2), Number(value)])),
      explorationPct: Number(raw.explorationPct),
      frequencyCapMin: Number(raw.frequencyCapMin),
      competitorSeparationMin: Number(raw.competitorSeparationMin),
      delayThresholdMin: Number(raw.delayThresholdMin),
      minEvidenceConfidence: Number(raw.minEvidenceConfidence),
      houseCampaignId: raw.houseCampaignId,
    };
    try {
      await api.put("/api/admin/rules", payload);
      toast("Rule engine updated — next decision cycle uses it");
      ctx.rerender();
    } catch (error) {
      toast(error.message, "bad");
    }
  });
  root.appendChild(form);
}

async function renderLog(ctx, root) {
  const ui = ctx.ui;
  const query = qs({ q: ui.logQuery, fallback: ui.logFallback, limit: 40 });
  const data = await api.get(`/api/admin/decisions${query}`);
  const search = h("form", { class: "row wrap", style: { marginBottom: "12px" } },
    h("input", { class: "input", style: { maxWidth: "280px" }, placeholder: "Search screen, campaign or reason", value: ui.logQuery, name: "q" }),
    select("fallback", [["", "All decisions"], ["0", "AI validated"], ["1", "Rule fallback"]], ui.logFallback),
    h("button", { class: "btn small", type: "submit" }, icon("search", 12), " Search")
  );
  search.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = new FormData(search);
    ui.logQuery = form.get("q") || "";
    ui.logFallback = form.get("fallback") || "";
    ctx.rerender();
  });
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: ctx.t("admin.log") }), h("p", { class: "hint", text: `${fmtNumber(data.total)} decisions · click any row to audit evidence` })),
    search
  ));
  root.appendChild(h("div", { class: "card flush table-wrap" },
    h("table", { class: "data" },
      h("thead", {}, h("tr", {},
        h("th", { text: "#" }), h("th", { text: "Screen" }), h("th", { text: "Winner" }), h("th", { class: "num", text: "Score" }),
        h("th", { text: "Execution" }), h("th", { text: "Reason" }), h("th", { text: "Time" })
      )),
      h("tbody", {}, ...data.items.map((decision) =>
        h("tr", { style: { cursor: "pointer" }, onClick: () => openDecision(ctx, decision.id) },
          h("td", { class: "mono tiny", text: String(decision.id) }),
          h("td", { class: "strong", text: decision.screenId }),
          h("td", { text: decision.winnerName }),
          h("td", { class: "num", text: Number(decision.winnerScore).toFixed(3) }),
          h("td", {}, decision.fallback ? h("span", { class: "badge amber", text: "fallback" }) : h("span", { class: "badge green", text: "AI" })),
          h("td", { class: "sub", style: { maxWidth: "360px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }, text: decision.reason }),
          h("td", { class: "mono tiny", text: fmtTime(decision.decidedAt) })
        )
      ))
    )
  ));
}

function field(label, input, className = "") {
  return h("div", { class: `field ${className}` }, h("label", { text: label }), input);
}

function select(name, options, value = "") {
  return h("select", { class: "select", name },
    ...options.map(([key, label]) => h("option", { value: key, selected: String(key) === String(value ?? "") }, label))
  );
}

function errorCard(error) {
  return h("div", { class: "card danger" }, h("div", { class: "card-title", text: "Admin view unavailable" }), h("p", { class: "muted tiny", text: error.message }));
}