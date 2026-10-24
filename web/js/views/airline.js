import { api, qs } from "../api.js";
import {
  clear, debounce, fmtCompact, fmtDate, fmtMoney, fmtNumber, fmtPct, fmtTime,
  h, icon, modal, statusBadge, titleCase, toast,
} from "../dom.js";
import { lineChart } from "../components/charts.js";

const TABS = [
  ["overview", "Overview"],
  ["flights", "My flights"],
  ["messages", "Gate messaging"],
  ["goodwill", "Delay goodwill"],
  ["marketplace", "Marketplace"],
  ["performance", "Performance"],
];

export async function mount(ctx) {
  const { root, ui } = ctx;
  const companies = await api.get("/api/airline/companies");
  if (!companies.items.some((item) => item.iata === ui.airline)) ui.airline = companies.default || "ZO";
  const [summary, messages, marketplace] = await Promise.all([
    api.get(`/api/airline/summary${qs({ airline: ui.airline })}`),
    api.get(`/api/airline/messages${qs({ airline: ui.airline })}`),
    api.get(`/api/airline/marketplace${qs({ airline: ui.airline })}`),
  ]);
  let performance = null;
  if (ui.tab === "performance") performance = await api.get(`/api/airline/performance${qs({ airline: ui.airline })}`);

  root.appendChild(pageHead(ctx, summary, companies));
  root.appendChild(tabs(ctx));
  const content = h("div", {});
  root.appendChild(content);

  if (ui.tab === "overview") renderOverview(ctx, content, summary, messages);
  else if (ui.tab === "flights") await renderFlights(ctx, content, summary);
  else if (ui.tab === "messages") renderMessages(ctx, content, summary, messages);
  else if (ui.tab === "goodwill") await renderGoodwill(ctx, content, summary);
  else if (ui.tab === "marketplace") renderMarketplace(ctx, content, marketplace, summary);
  else if (ui.tab === "performance" && performance) renderPerformance(ctx, content, performance);

  const refresh = debounce(() => {
    if (["overview", "flights"].includes(ui.tab)) ctx.rerender();
  }, 2500);
  return {
    onEvent(name) {
      if (["flight", "goodwill", "decisions", "redemption", "marketplace"].includes(name)) refresh();
    },
  };
}

function pageHead(ctx, summary, companies) {
  const select = h("select", { class: "select", style: { width: "auto" }, onChange: (event) => {
    ctx.ui.airline = event.target.value;
    ctx.rerender();
  } }, ...companies.items.map((company) => h("option", { value: company.iata, selected: company.iata === ctx.ui.airline }, `${company.iata} · ${company.name}`)));
  return h("div", { class: "page-head" },
    h("div", {},
      h("div", { class: "eyebrow", text: "Airline Representative · station desk" }),
      h("h1", { text: summary.airline.name }),
      h("p", { class: "lede", text: `${summary.kpi.flightsToday} departures in the next window · ${summary.kpi.delayed30} delayed ≥ 30 min · every screen decision is auditable.` })
    ),
    h("div", { class: "head-actions" },
      select,
      h("span", { class: "chip" }, h("strong", { text: fmtCompact(summary.kpi.impressionsToday) }), " impressions today"),
      h("span", { class: "chip" }, h("strong", { text: fmtNumber(summary.kpi.redemptionsToday) }), " redemptions")
    )
  );
}

function tabs(ctx) {
  const nav = h("div", { class: "tabs" });
  for (const [key, label] of TABS) {
    nav.appendChild(h("button", { class: "tab", "aria-selected": String(ctx.ui.tab === key), onClick: () => { ctx.ui.tab = key; ctx.rerender(); } }, label));
  }
  return nav;
}

function renderOverview(ctx, root, summary, messages) {
  const kpi = summary.kpi;
  root.appendChild(h("div", { class: "grid", style: { gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" } },
    kpiCard("Flights in window", fmtNumber(kpi.flightsToday), "departures near now", "clock"),
    kpiCard("Delayed ≥ 30", fmtNumber(kpi.delayed30), "goodwill candidates", "warning"),
    kpiCard("Passengers reached", fmtCompact(kpi.passengersReached), "load + delay weight", "users"),
    kpiCard("Avg load factor", fmtPct(kpi.avgLoadFactor, 1), "AODB pax / seats", "trend"),
    kpiCard("Own-campaign redemptions", fmtNumber(kpi.redemptionsToday), "today", "check")
  ));
  const timeline = h("div", { class: "card span-2" },
    h("div", { class: "card-head" },
      h("div", { class: "card-title", text: "Flight timeline" }),
      h("button", { class: "btn small", onClick: () => { ctx.ui.tab = "flights"; ctx.rerender(); } }, "All flights")
    ),
    h("div", { class: "timeline" },
      ...summary.flights.slice(0, 7).map((flight) =>
        h("div", { class: "timeline-item" },
          h("div", { class: "timeline-time", text: fmtTime(flight.estimated || flight.scheduled) }),
          h("div", { class: "timeline-body" },
            h("div", { class: "row-between" },
              h("div", { class: "row", style: { gap: "8px" } },
                h("span", { class: "strong", text: `${flight.display} → ${flight.destination}` }),
                statusBadge(flight.status === "DEP" ? "ended" : flight.status === "CNL" ? "cancelled" : flight.status === "DEL" ? "paused" : "online"),
                flight.delayMinutes ? h("span", { class: "badge amber", text: `+${flight.delayMinutes}m` }) : null
              ),
              h("span", { class: "mono tiny", text: `Gate ${flight.gate} · ${fmtPct(flight.loadFactor, 0)} load` })
            ),
            h("div", { class: "progress", style: { marginTop: "6px" } }, h("span", { style: { width: `${Math.min(100, flight.loadFactor * 100)}%` } }))
          )
        )
      )
    )
  );
  const campaigns = h("div", { class: "card" },
    h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Gate-area content" }), h("span", { class: "badge grey", text: String(messages.items.length) })),
    h("div", { class: "list" },
      ...(messages.items.length ? messages.items.slice(0, 5).map((campaign) =>
        h("div", { class: "list-item" },
          h("div", { class: "list-main" },
            h("div", { class: "list-title", text: campaign.name }),
            h("div", { class: "list-sub", text: `${campaign.status} · ${Object.keys(campaign.triggers || {}).join(", ") || "no trigger"}` })
          ),
          statusBadge(campaign.status)
        )
      ) : [h("div", { class: "empty", text: "No gate-area messages yet." })])
    ),
    h("button", { class: "btn small", style: { marginTop: "10px" }, onClick: () => { ctx.ui.tab = "messages"; ctx.rerender(); } }, icon("plus", 12), " Schedule message")
  );
  root.appendChild(h("div", { class: "grid grid-3", style: { marginTop: "16px" } }, timeline, campaigns));
  root.appendChild(h("div", { class: "grid grid-2", style: { marginTop: "16px" } },
    h("div", { class: "card" },
      h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Delay goodwill" }), h("span", { class: "badge green", text: "automation on" })),
      h("p", { class: "muted tiny", text: "Threshold and offer are configured per airline. An injected delay creates a co-funded voucher and pushes it to the gate screens." }),
      h("div", { class: "chip-row", style: { marginTop: "9px" } },
        h("span", { class: "chip" }, h("strong", { text: `${summary.goodwill.settings.threshold} min` }), " threshold"),
        h("span", { class: "chip" }, h("strong", { text: summary.goodwill.settings.offer }), "")
      ),
      h("div", { class: "divider" }),
      h("div", { class: "list" },
        ...(summary.goodwill.recent.length ? summary.goodwill.recent.slice(0, 4).map((action) =>
          h("div", { class: "row-between", style: { fontSize: "11px" } },
            h("span", { text: `${action.flight_id} · ${action.offer}` }),
            h("span", { class: "code", text: action.code })
          )
        ) : [h("p", { class: "muted tiny", text: "No goodwill actions yet. Inject a delay from the simulation bar." })])
      )
    ),
    h("div", { class: "card" },
      h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Cause and effect" }), h("span", { class: "badge teal", text: "under 2s" })),
      h("div", { class: "timeline" },
        effect("AIDX delay", "Flight event parsed by the adapter"),
        effect("Profile rebuild", "ZonePresence recalculated from pax × dwell"),
        effect("Decision", "Delay boost re-scores gate screens"),
        effect("Claim", "Passenger scans QR; retailer revenue ticks")
      )
    )
  ));
}

function effect(title, text) {
  return h("div", { class: "timeline-item" },
    h("div", { class: "timeline-time", text: "→" }),
    h("div", { class: "timeline-body" }, h("div", { class: "strong", style: { fontSize: "12px" }, text: title }), h("div", { class: "sub", text }))
  );
}

function kpiCard(label, value, meta, iconName) {
  return h("div", { class: "card kpi" },
    h("div", { class: "row-between" }, h("div", { class: "kpi-label", text: label }), h("span", { class: "muted" }, icon(iconName, 14))),
    h("div", { class: "kpi-value small", text: value }),
    h("div", { class: "kpi-meta", text: meta })
  );
}

async function renderFlights(ctx, root, summary) {
  const data = await api.get(`/api/airline/flights${qs({ airline: ctx.ui.airline })}`);
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: `${ctx.ui.airline} departures` }), h("p", { class: "hint", text: "Gate, status, delay and load factor from the AODB snapshot + live AIDX events." })),
    h("div", { class: "row" },
      h("span", { class: "badge grey", text: `${data.items.length} flights` }),
      h("span", { class: "badge purple", text: `updated ${fmtTime(data.now)} UTC` })
    )
  ));
  root.appendChild(h("div", { class: "card flush table-wrap" },
    h("table", { class: "data" },
      h("thead", {}, h("tr", {},
        h("th", { text: "Time" }), h("th", { text: "Flight" }), h("th", { text: "Destination" }), h("th", { text: "Gate" }),
        h("th", { text: "Status" }), h("th", { class: "num", text: "Delay" }), h("th", { class: "num", text: "Load" }), h("th", { class: "num", text: "Pax" })
      )),
      h("tbody", {}, ...data.items.map((flight) =>
        h("tr", {},
          h("td", { class: "mono", text: fmtTime(flight.estimated || flight.scheduled) }),
          h("td", { class: "strong", text: flight.display }),
          h("td", { text: flight.destination }),
          h("td", { class: "mono", text: flight.gate }),
          h("td", {}, statusBadge(flight.status === "DEL" ? "paused" : flight.status === "DEP" ? "ended" : "online")),
          h("td", { class: "num " + (flight.delayMinutes ? "warn-text" : ""), text: flight.delayMinutes ? `+${flight.delayMinutes}m` : "—" }),
          h("td", { class: "num", text: fmtPct(flight.loadFactor, 0) }),
          h("td", { class: "num", text: fmtNumber(flight.pax) })
        )
      ))
    )
  ));
}

function renderMessages(ctx, root, summary, messages) {
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: "Gate-area messaging" }), h("p", { class: "hint", text: "Sponsor screens at your own gates for a boarding window. Messages are airline-approved and still pass brand safety." })),
    h("button", { class: "btn primary small", onClick: () => messageForm(ctx, summary) }, icon("plus", 12), " Schedule content")
  ));
  root.appendChild(h("div", { class: "grid grid-2" },
    ...(messages.items.length ? messages.items.map((campaign) =>
      h("div", { class: "card" },
        h("div", { class: "row-between" },
          h("div", {}, h("div", { class: "card-title", text: campaign.name }), h("div", { class: "card-sub", text: `${fmtDate(campaign.start)} → ${fmtDate(campaign.end)}` })),
          statusBadge(campaign.status)
        ),
        h("div", { class: "chip-row", style: { marginTop: "9px" } },
          h("span", { class: "chip" }, h("strong", { text: (campaign.placement?.gates || []).join(", ") || "zones" }), " gates"),
          campaign.triggers?.boarding ? h("span", { class: "badge teal", text: "boarding window" }) : null,
          h("span", { class: "chip" }, `${fmtCompact(campaign.impressions)} imp · ${fmtNumber(campaign.redemptions)} red`)
        )
      )
    ) : [h("div", { class: "empty", text: "No gate-area messages yet." })])
  ));
}

function messageForm(ctx, summary) {
  const gates = [...new Set(summary.flights.map((flight) => flight.gate))].filter(Boolean);
  const form = h("form", { class: "form-grid" },
    field("Message name", h("input", { class: "input", name: "name", required: true, placeholder: "Halcyon upgrade · Gate 43" })),
    field("Duration (hours)", h("input", { class: "input", type: "number", name: "hours", value: "3", min: "1", max: "48" })),
    field("Gates (comma separated)", h("input", { class: "input", name: "gates", value: gates.slice(0, 4).join(",") })),
    field("Budget (EUR)", h("input", { class: "input", type: "number", name: "budget", value: "3000", min: "0" }))
  );
  modal({
    title: "Schedule gate-area content",
    subtitle: "Creates an approved airline message targeting your own gates and boarding window.",
    body: form,
    actions: [
      { label: "Cancel" },
      {
        label: "Schedule", primary: true,
        onClick: async () => {
          const values = Object.fromEntries(new FormData(form).entries());
          values.airline = ctx.ui.airline;
          values.gates = String(values.gates || "").split(",").map((item) => item.trim()).filter(Boolean);
          try {
            const result = await api.post("/api/airline/messages", values);
            toast(`Message scheduled on gates ${result.gates.join(", ")}`);
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

async function renderGoodwill(ctx, root, summary) {
  const advertisers = await api.get("/api/media/advertisers");
  const partners = advertisers.items.filter((item) => ["retailer", "brand"].includes(item.kind));
  const settings = summary.goodwill.settings;
  const form = h("form", { class: "grid grid-2" },
    h("div", { class: "card" },
      h("div", { class: "card-title", text: "Automation settings" }),
      h("div", { class: "col", style: { marginTop: "12px", gap: "10px" } },
        h("label", { class: "check" }, h("input", { type: "checkbox", name: "enabled", checked: Boolean(settings.enabled) }), " Enable delay goodwill automation"),
        field("Delay threshold (min)", h("input", { class: "input", type: "number", name: "threshold", value: settings.threshold, min: "5", max: "240" })),
        field("Partner", h("select", { class: "select", name: "partner" }, ...partners.map((partner) => h("option", { value: partner.id, selected: partner.id === settings.partner }, partner.name)))),
        field("Offer", h("input", { class: "input", name: "offer", value: settings.offer })),
        field("Campaign (optional)", h("input", { class: "input", name: "campaignId", value: settings.campaignId || "", placeholder: "CMP-20" }))
      ),
      h("button", { class: "btn primary", type: "submit", style: { marginTop: "12px" } }, icon("check", 13), " Save settings")
    ),
    h("div", { class: "card" },
      h("div", { class: "card-title", text: "Recent goodwill actions" }),
      h("div", { class: "list", style: { marginTop: "6px" } },
        ...(summary.goodwill.recent.length ? summary.goodwill.recent.map((action) =>
          h("div", { class: "list-item" },
            h("div", { class: "list-main" },
              h("div", { class: "list-title", text: `${action.offer} · ${action.partner}` }),
              h("div", { class: "list-sub", text: `${action.flight_id} +${action.minutes}m · ${fmtTime(action.created)} UTC` })
            ),
            h("span", { class: "code", text: action.code })
          )
        ) : [h("div", { class: "empty", text: "No actions yet." })])
      )
    )
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form).entries());
    try {
      await api.put("/api/airline/goodwill", { ...values, enabled: values.enabled === "on", airline: ctx.ui.airline, threshold: Number(values.threshold) });
      toast("Goodwill settings saved");
      ctx.rerender();
    } catch (error) {
      toast(error.message, "bad");
    }
  });
  root.appendChild(form);
}

function renderMarketplace(ctx, root, marketplace, summary) {
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: "Co-marketing marketplace" }), h("p", { class: "hint", text: "Retailers offer deals to your passengers. Accepting creates a promo code for your next departure." }))
  ));
  root.appendChild(h("div", { class: "grid grid-2" },
    ...(marketplace.items.length ? marketplace.items.map((offer) =>
      h("div", { class: "card" },
        h("div", { class: "row-between" },
          h("div", { class: "card-title", text: offer.title }),
          statusBadge(offer.status)
        ),
        h("p", { class: "muted tiny", style: { marginTop: "6px" }, text: offer.offer }),
        h("div", { class: "row-between", style: { marginTop: "12px" } },
          h("span", { class: "chip" }, h("strong", { text: offer.retailer_name }), ""),
          offer.status === "accepted"
            ? h("span", { class: "badge green", text: "live for passengers" })
            : h("button", { class: "btn small primary", onClick: () => acceptOffer(ctx, offer.id) }, "Accept with one click")
        )
      )
    ) : [h("div", { class: "empty", text: "No offers for this airline." })])
  ));
}

async function acceptOffer(ctx, id) {
  try {
    const result = await api.post(`/api/airline/marketplace/${id}/accept`, { airline: ctx.ui.airline });
    toast(result.promo ? `Offer accepted · code ${result.promo.code}` : "Offer accepted");
    ctx.rerender();
  } catch (error) {
    toast(error.message, "bad");
  }
}

function renderPerformance(ctx, root, data) {
  const overall = data.overall;
  root.appendChild(h("div", { class: "grid", style: { gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" } },
    kpiCard("Impressions", fmtCompact(overall.impressions), "own campaigns", "play"),
    kpiCard("Redemptions", fmtNumber(overall.redemptions), `${overall.redemptionRate}% of impressions`, "check"),
    kpiCard("Revenue", fmtMoney(overall.revenue, ctx.config.theme.currency), "attributed", "trend"),
    kpiCard("Flights", fmtNumber(overall.flights), "today", "clock"),
    kpiCard("Passengers", fmtCompact(overall.passengers), "own departures", "users"),
    kpiCard("Avg load", fmtPct(overall.avgLoadFactor, 1), "AODB pax / seats", "users")
  ));
  root.appendChild(h("div", { class: "card", style: { marginTop: "16px" } },
    h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Daily impressions and redemptions" }), h("span", { class: "badge grey", text: "last 14 days" })),
    lineChart({
      values: data.daily.map((row) => row.impressions),
      secondaryValues: data.daily.map((row) => row.redemptions * 40),
      labels: data.daily.map((row) => fmtDate(row.day)),
      height: 210,
      format: (value) => fmtCompact(value),
    }),
    h("div", { class: "legend", style: { marginTop: "8px" } },
      h("span", {}, h("i", { style: { background: "var(--accent)" } }), "impressions"),
      h("span", {}, h("i", { style: { background: "var(--accent-2)" } }), "redemptions ×40")
    )
  ));
}

function field(label, input) {
  return h("div", { class: "field" }, h("label", { text: label }), input);
}