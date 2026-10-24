import { api, qs } from "../api.js";
import {
  clear, copyText, debounce, fmtCompact, fmtDate, fmtMoney, fmtNumber, fmtPct,
  fmtSeconds, fmtTime, h, icon, modal, statusBadge, titleCase, toast,
} from "../dom.js";
import { lineChart } from "../components/charts.js";
import { adCreative, creativeTile } from "../components/creative.js";

const TABS = [
  ["overview", "Overview"],
  ["campaigns", "Campaigns"],
  ["creatives", "Creative library"],
  ["promos", "Promo codes"],
  ["history", "Campaign history"],
  ["triggers", "Trigger rules"],
];

const SEGMENTS = ["holiday", "family", "business", "international", "luxury", "young", "shopper"];

export async function mount(ctx) {
  const { root, ui } = ctx;
  const companies = await api.get("/api/retailer/companies");
  if (!companies.items.some((company) => company.id === ui.advertiserId)) {
    ui.advertiserId = companies.items[0]?.id || "ADV-01";
  }
  const outlets = await api.get(`/api/retailer/outlets${qs({ advertiserId: ui.advertiserId })}`);
  if (!outlets.items.some((outlet) => outlet.id === ui.outletId)) {
    ui.outletId = outlets.items[0]?.id || "";
  }
  const query = qs({ advertiserId: ui.advertiserId, outletId: ui.outletId });
  const [dashboard, flow] = await Promise.all([
    api.get(`/api/retailer/dashboard${query}`),
    api.get(`/api/retailer/flow${qs({ outletId: ui.outletId })}`),
  ]);
  const approved = dashboard.campaigns.find((campaign) => campaign.status === "approved");
  let recommendations = null;
  if (approved) {
    try {
      recommendations = await api.get(`/api/retailer/recommendations${qs({ campaignId: approved.id })}`);
    } catch {
      recommendations = null;
    }
  }

  root.appendChild(pageHead(ctx, dashboard, companies, outlets));
  root.appendChild(tabs(ctx));
  const content = h("div", {});
  root.appendChild(content);

  if (ui.tab === "overview") renderOverview(ctx, content, dashboard, flow, recommendations);
  else if (ui.tab === "campaigns") renderCampaigns(ctx, content, dashboard);
  else if (ui.tab === "creatives") await renderCreatives(ctx, content, ui.advertiserId);
  else if (ui.tab === "promos") await renderPromos(ctx, content, dashboard);
  else if (ui.tab === "history") renderHistory(ctx, content, dashboard);
  else if (ui.tab === "triggers") renderTriggers(ctx, content, dashboard);

  const timer = setInterval(tickCountdowns, 1000);
  const refresh = debounce(() => {
    if (ui.tab === "overview") ctx.rerender();
  }, 3500);

  return {
    onEvent(name) {
      if (["redemption", "decisions", "flight", "kpi", "approval"].includes(name)) refresh();
    },
    destroy() {
      clearInterval(timer);
    },
  };
}

function pageHead(ctx, dashboard, companies, outlets) {
  const companySelect = h("select", { class: "select", style: { width: "auto" }, onChange: (event) => {
    ctx.ui.advertiserId = event.target.value;
    ctx.ui.outletId = "";
    ctx.rerender();
  } }, ...companies.items.map((company) => h("option", { value: company.id, selected: company.id === ctx.ui.advertiserId }, company.name)));
  const outletSelect = h("select", { class: "select", style: { width: "auto" }, onChange: (event) => {
    ctx.ui.outletId = event.target.value;
    ctx.rerender();
  } }, ...outlets.items.map((outlet) => h("option", { value: outlet.id, selected: outlet.id === ctx.ui.outletId }, outlet.name)));
  const kpi = dashboard.kpi;
  return h("div", { class: "page-head" },
    h("div", {},
      h("div", { class: "eyebrow", text: "Retailer · live commercial workspace" }),
      h("h1", { text: dashboard.company.name }),
      h("p", { class: "lede", text: `${dashboard.outlet?.name || "All outlets"} · ${dashboard.outlet?.zoneName || "network"} · impressions and redemptions update from the live decision feed.` })
    ),
    h("div", { class: "head-actions" },
      companySelect, outletSelect,
      h("span", { class: "chip" }, h("strong", { text: fmtNumber(kpi.activeCampaigns) }), " active"),
      h("button", { class: "btn primary small", onClick: () => openBuilder(ctx, dashboard) }, icon("plus", 12), " New campaign")
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

function renderOverview(ctx, root, dashboard, flow, recommendations) {
  const kpi = dashboard.kpi;
  root.appendChild(h("div", { class: "grid", style: { gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" } },
    kpiCard("Impressions", fmtNumber(kpi.impressions), "today · all outlets", "play"),
    kpiCard("Scans", fmtNumber(kpi.scans), "QR opens", "qr"),
    kpiCard("Redemptions", fmtNumber(kpi.redemptions), `${fmtPct(kpi.conversion, 1)} of scans`, "check"),
    kpiCard("Revenue attributed", fmtMoney(kpi.revenue, kpi.currency), "live + seeded history", "trend"),
    kpiCard("Live promos", fmtNumber(kpi.livePromos), "expiring with crowds", "clock")
  ));

  const flowCard = h("div", { class: "card span-2" },
    h("div", { class: "card-head" },
      h("div", {},
        h("div", { class: "card-title", text: ctx.t("retailer.flow") }),
        h("div", { class: "card-sub", text: `${flow.zoneName || flow.zoneId} · next 2 hours from AODB departures + ACRIS queues` })
      ),
      h("div", { class: "row" },
        h("span", { class: "badge teal", text: `${fmtNumber(flow.next60)} pax next 60 min` }),
        h("span", { class: "badge purple", text: `${fmtPct(flow.internationalShare || 0)} international` })
      )
    ),
    lineChart({
      values: flow.series.map((point) => point.crowd),
      labels: flow.series.map((point) => fmtTime(point.time)),
      height: 170,
      format: (value) => `${fmtCompact(value)}`,
    }),
    h("div", { class: "row wrap", style: { marginTop: "8px" } },
      ...(flow.topDestinations || []).map((destination) =>
        h("span", { class: "chip" }, h("strong", { text: destination.code }), ` ${Math.round(destination.share * 100)}%`)
      ),
      ...(flow.nationalities || []).slice(0, 3).map((item) =>
        h("span", { class: "chip" }, `Nationality ${item.code} · ${Math.round(item.share * 100)}%`)
      )
    )
  );
  const suggestion = h("div", { class: "card accent" },
    h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Learning loop" }), h("span", { class: "badge green", text: "suggested" })),
    h("div", { class: "eyebrow", text: "Best converting segment" }),
    h("div", { style: { fontSize: "19px", fontWeight: "700", marginTop: "5px" }, text: titleCase(dashboard.suggestion.segment || "family") }),
    h("p", { class: "muted", style: { marginTop: "7px", fontSize: "12px" }, text: dashboard.suggestion.text }),
    h("div", { class: "divider" }),
    h("div", { class: "eyebrow", text: "Best 3 slots tomorrow" }),
    recommendations
      ? h("div", { class: "col", style: { marginTop: "8px", gap: "6px" } },
          ...recommendations.best.map((slot, index) =>
            h("div", { class: "row-between", style: { fontSize: "11px" } },
              h("span", { class: "row", style: { gap: "7px" } },
                h("span", { class: "badge purple", text: `#${index + 1}` }),
                h("span", { text: slot.slot })
              ),
              h("span", { class: "mono", text: `${fmtCompact(slot.predictedImpressions)} imp` })
            )
          )
        )
      : h("p", { class: "muted tiny", style: { marginTop: "6px" }, text: "No approved campaign to forecast yet." }),
    h("p", { class: "hint", style: { marginTop: "8px" }, text: recommendations?.basis || "" })
  );
  root.appendChild(h("div", { class: "grid grid-3", style: { marginTop: "16px" } }, flowCard, suggestion));

  const campaignsCard = h("div", { class: "card span-2" },
    h("div", { class: "card-head" },
      h("div", { class: "card-title", text: "Campaign performance" }),
      h("button", { class: "btn small", onClick: () => { ctx.ui.tab = "campaigns"; ctx.rerender(); } }, "Manage")
    ),
    campaignTable(ctx, dashboard.campaigns.slice(0, 7), { compact: true })
  );
  const segmentCard = h("div", { class: "card" },
    h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Performance by segment" }), h("span", { class: "badge grey", text: "30 days" })),
    h("div", { class: "col", style: { gap: "9px" } },
      ...dashboard.segments.slice(0, 7).map((segment) => {
        const max = Math.max(1, ...dashboard.segments.map((item) => item.redemptions));
        return h("div", {},
          h("div", { class: "row-between", style: { fontSize: "11px" } },
            h("span", { text: titleCase(segment.segment) }),
            h("span", { class: "mono muted", text: `${fmtNumber(segment.redemptions)} redemptions` })
          ),
          h("div", { class: "progress", style: { marginTop: "4px" } }, h("span", { style: { width: `${(segment.redemptions / max) * 100}%` } }))
        );
      })
    )
  );
  root.appendChild(h("div", { class: "grid grid-3", style: { marginTop: "16px" } }, campaignsCard, segmentCard));

  const promoCard = h("div", { class: "card span-2" },
    h("div", { class: "card-head" },
      h("div", { class: "card-title", text: "Time-limited offers on screen" }),
      h("button", { class: "btn small", onClick: () => { ctx.ui.tab = "promos"; ctx.rerender(); } }, "All codes")
    ),
    h("div", { class: "table-wrap" },
      h("table", { class: "data" },
        h("thead", {}, h("tr", {}, h("th", { text: "Code" }), h("th", { text: "Offer" }), h("th", { text: "Uses" }), h("th", { text: "Expires" }), h("th", {}))),
        h("tbody", {}, ...dashboard.promos.filter((promo) => promo.live).slice(0, 6).map((promo) =>
          h("tr", {},
            h("td", {}, h("span", { class: "code", text: promo.code })),
            h("td", { text: promo.label }),
            h("td", { class: "mono", text: `${promo.uses}/${promo.max_uses}` }),
            h("td", {}, h("span", { class: "countdown", dataset: { remaining: String(promo.remainingSeconds) }, text: fmtSeconds(promo.remainingSeconds) })),
            h("td", {}, h("button", { class: "btn small", onClick: () => sharePromo(ctx, promo.code) }, "Share"))
          )
        ))
      )
    )
  );
  const liveCard = h("div", { class: "card" },
    h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Live redemptions" }), h("span", { class: "badge live green", text: "LIVE" })),
    h("div", { class: "list" },
      ...(dashboard.redemptions.length ? dashboard.redemptions.slice(0, 8).map((redemption) =>
        h("div", { class: "list-item" },
          h("div", { class: "list-main" },
            h("div", { class: "list-title", text: `${redemption.campaign_name} · redeemed` }),
            h("div", { class: "list-sub", text: `${redemption.destination || "MQI"} · ${redemption.segment} · ${fmtTime(redemption.ts)}` })
          ),
          h("span", { class: "mono positive", text: fmtMoney(redemption.value, "EUR") })
        )
      ) : [h("div", { class: "empty", text: "Waiting for the first claim. Open the passenger screen and scan the QR." })])
    )
  );
  root.appendChild(h("div", { class: "grid grid-3", style: { marginTop: "16px" } }, promoCard, liveCard));
}

function kpiCard(label, value, meta, iconName) {
  return h("div", { class: "card kpi" },
    h("div", { class: "row-between" }, h("div", { class: "kpi-label", text: label }), h("span", { class: "muted" }, icon(iconName, 14))),
    h("div", { class: "kpi-value small", text: value }),
    h("div", { class: "kpi-meta", text: meta })
  );
}

function campaignTable(ctx, campaigns, options = {}) {
  return h("div", { class: "table-wrap" },
    h("table", { class: "data" },
      h("thead", {}, h("tr", {},
        h("th", { text: "Campaign" }), h("th", { text: "Status" }), h("th", { class: "num", text: "Impressions" }),
        h("th", { class: "num", text: "Redemptions" }), h("th", { class: "num", text: "ROI" }),
        options.compact ? h("th", { text: "A/B" }) : h("th", { text: "Window" }), options.compact ? null : h("th", { text: "" })
      )),
      h("tbody", {}, ...campaigns.map((campaign) =>
        h("tr", {},
          h("td", {},
            h("div", { class: "strong", text: campaign.name }),
            h("div", { class: "sub", text: `${campaign.id} · ${campaign.category}` })
          ),
          h("td", {}, statusBadge(campaign.status)),
          h("td", { class: "num", text: fmtCompact(campaign.impressions) }),
          h("td", { class: "num", text: fmtNumber(campaign.redemptions) }),
          h("td", { class: "num", text: `${(campaign.roi * 100).toFixed(0)}%` }),
          options.compact
            ? h("td", {}, h("span", { class: "badge grey", text: campaign.ab_group || "A" }))
            : h("td", { class: "tiny muted", text: `${fmtDate(campaign.start)} → ${fmtDate(campaign.end)}` }),
          options.compact ? null : h("td", {}, h("div", { class: "row", style: { gap: "5px" } },
            h("button", { class: "btn small", onClick: () => duplicateCampaign(ctx, campaign.id, false) }, "Duplicate"),
            h("button", { class: "btn small", onClick: () => previewCampaign(ctx, campaign.id) }, "Preview")
          ))
        )
      ))
    )
  );
}

function renderCampaigns(ctx, root, dashboard) {
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: "Campaigns" }), h("p", { class: "hint", text: "Pending campaigns enter the Media Manager approval queue. Approved campaigns join the 15-second decision loop." })),
    h("button", { class: "btn primary small", onClick: () => openBuilder(ctx, dashboard) }, icon("plus", 12), " New campaign")
  ));
  root.appendChild(h("div", { class: "card flush" }, campaignTable(ctx, dashboard.campaigns)));
  const ab = dashboard.campaigns.filter((campaign) => campaign.ab_group);
  if (ab.length) {
    root.appendChild(h("div", { class: "card", style: { marginTop: "16px" } },
      h("div", { class: "card-head" }, h("div", { class: "card-title", text: "A/B creative comparison" }), h("span", { class: "badge grey", text: "same audience, two creatives" })),
      h("div", { class: "grid grid-2" },
        ...["A", "B"].map((group) => {
          const items = ab.filter((campaign) => campaign.ab_group === group);
          const impressions = items.reduce((sum, item) => sum + item.impressions, 0);
          const redemptions = items.reduce((sum, item) => sum + item.redemptions, 0);
          return h("div", { class: "card", style: { background: "var(--panel-2)" } },
            h("div", { class: "row-between" }, h("span", { class: "badge purple", text: `Group ${group}` }), h("span", { class: "muted tiny", text: `${items.length} campaigns` })),
            h("div", { class: "kpi-value small", style: { marginTop: "8px" }, text: fmtNumber(impressions) }),
            h("div", { class: "kpi-meta", text: `impressions · ${fmtNumber(redemptions)} redemptions` }),
            h("div", { class: "progress", style: { marginTop: "8px" } }, h("span", { style: { width: `${impressions ? Math.min(100, (redemptions / impressions) * 4000) : 0}%` } }))
          );
        })
      )
    ));
  }
}

async function renderCreatives(ctx, root, advertiserId) {
  const data = await api.get(`/api/retailer/creatives${qs({ advertiserId })}`);
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: "Creative library" }), h("p", { class: "hint", text: "Reuse a page, upload an image, or generate an on-brand layout offline in English + 中文." })),
    h("div", { class: "row" },
      h("button", { class: "btn small", onClick: () => openCreativeStudio(ctx, advertiserId) }, icon("spark", 12), " GenAI assistant"),
      h("button", { class: "btn primary small", onClick: () => openCreativeForm(ctx, advertiserId) }, icon("plus", 12), " New creative")
    )
  ));
  root.appendChild(h("div", { class: "grid", style: { gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))" } },
    ...data.items.map((creative) =>
      creativeTile(creative, {
        actions: [
          h("button", { class: "btn small", onClick: () => openBuilder(ctx, null, creative) }, "Use in campaign"),
          h("button", { class: "btn small", onClick: () => openCreativeForm(ctx, advertiserId, creative) }, "Duplicate"),
        ],
      })
    )
  ));
}

async function renderPromos(ctx, root, dashboard) {
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: "Promo codes" }), h("p", { class: "hint", text: "Codes expire when the linked flight's boarding closes. Share-to-family creates a second code." })),
    h("button", { class: "btn primary small", onClick: () => openPromoForm(ctx, dashboard) }, icon("plus", 12), " New code")
  ));
  const items = dashboard.promos;
  root.appendChild(h("div", { class: "card flush table-wrap" },
    h("table", { class: "data" },
      h("thead", {}, h("tr", {},
        h("th", { text: "Code" }), h("th", { text: "Campaign / offer" }), h("th", { text: "Flight" }),
        h("th", { text: "Uses" }), h("th", { text: "Expires" }), h("th", { text: "Status" }), h("th", { text: "Actions" })
      )),
      h("tbody", {}, ...items.map((promo) =>
        h("tr", {},
          h("td", {}, h("span", { class: "code", text: promo.code })),
          h("td", {}, h("div", { class: "strong", text: promo.label }), h("div", { class: "sub", text: promo.campaign_name })),
          h("td", { class: "mono tiny", text: promo.flight_id }),
          h("td", { class: "mono", text: `${promo.uses}/${promo.max_uses}` }),
          h("td", {}, h("span", { class: "countdown", dataset: { remaining: String(promo.remainingSeconds) }, text: fmtSeconds(promo.remainingSeconds) })),
          h("td", {}, statusBadge(promo.live ? "live" : "ended")),
          h("td", {}, h("div", { class: "row", style: { gap: "5px" } },
            h("button", { class: "btn small", onClick: () => sharePromo(ctx, promo.code) }, "Share"),
            h("button", { class: "btn small", onClick: () => copyText(`${ctx.config.claimBase}/claim/${promo.code}`) }, "Copy link")
          ))
        )
      ))
    )
  ));
  root.appendChild(h("p", { class: "hint", style: { marginTop: "10px" }, text: `Claim URLs use ${ctx.config.claimBase || "the detected LAN address"}. On a hosted playground they use the public origin.` }));
}

function renderHistory(ctx, root, dashboard) {
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: "Campaign history" }), h("p", { class: "hint", text: "30 seeded days plus today's live delivery. ROI = (attributed revenue − spend) / spend." })),
    h("span", { class: "badge grey", text: `${dashboard.campaigns.length} campaigns` })
  ));
  root.appendChild(h("div", { class: "card flush table-wrap" },
    h("table", { class: "data" },
      h("thead", {}, h("tr", {},
        h("th", { text: "Campaign" }), h("th", { text: "Status" }), h("th", { class: "num", text: "Spend" }),
        h("th", { class: "num", text: "Revenue" }), h("th", { class: "num", text: "Impressions" }),
        h("th", { class: "num", text: "Redemptions" }), h("th", { class: "num", text: "ROI" }), h("th", { text: "Actions" })
      )),
      h("tbody", {}, ...dashboard.campaigns.map((campaign) =>
        h("tr", {},
          h("td", {}, h("div", { class: "strong", text: campaign.name }), h("div", { class: "sub", text: `${fmtDate(campaign.start)} → ${fmtDate(campaign.end)}` })),
          h("td", {}, statusBadge(campaign.status)),
          h("td", { class: "num", text: fmtMoney(campaign.spend, dashboard.kpi.currency) }),
          h("td", { class: "num", text: fmtMoney(campaign.revenue, dashboard.kpi.currency) }),
          h("td", { class: "num", text: fmtCompact(campaign.impressions) }),
          h("td", { class: "num", text: fmtNumber(campaign.redemptions) }),
          h("td", { class: "num " + (campaign.roi >= 0 ? "positive" : "negative"), text: `${(campaign.roi * 100).toFixed(0)}%` }),
          h("td", {}, h("div", { class: "row", style: { gap: "5px" } },
            h("button", { class: "btn small", onClick: () => duplicateCampaign(ctx, campaign.id, true) }, "Run again"),
            h("button", { class: "btn small", onClick: () => duplicateCampaign(ctx, campaign.id, false) }, "Duplicate")
          ))
        )
      ))
    )
  ));
}

function renderTriggers(ctx, root, dashboard) {
  const items = dashboard.campaigns.filter((campaign) => Object.keys(campaign.triggers || {}).length);
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: "Trigger rules" }), h("p", { class: "hint", text: "A delay, gate change or boarding window can re-score the campaign instantly. Triggers are evaluated only against measured feed events." })),
    h("span", { class: "badge grey", text: `${items.length} configured` })
  ));
  if (!items.length) {
    root.appendChild(h("div", { class: "empty", text: "No triggers configured." }));
    return;
  }
  root.appendChild(h("div", { class: "grid grid-2" },
    ...items.map((campaign) => {
      const triggers = campaign.triggers || {};
      return h("div", { class: "card" },
        h("div", { class: "card-head" },
          h("div", {}, h("div", { class: "card-title", text: campaign.name }), h("div", { class: "card-sub", text: campaign.status })),
          h("button", { class: "btn small", onClick: () => editTriggers(ctx, campaign, dashboard) }, "Edit")
        ),
        h("div", { class: "chip-row" },
          triggers.delayOver ? h("span", { class: "badge amber", text: `Delay ≥ ${triggers.delayOver} min` }) : null,
          triggers.boarding ? h("span", { class: "badge teal", text: "Boarding window" }) : null,
          triggers.gateChange ? h("span", { class: "badge purple", text: "Gate change" }) : null,
          triggers.festival ? h("span", { class: "badge green", text: "Holiday period" }) : null
        ),
        h("p", { class: "hint", style: { marginTop: "10px" }, text: "Injected AIDX delay → ZonePresence re-planned → campaign boost applied within 2 seconds." })
      );
    })
  ));
}

function editTriggers(ctx, campaign, dashboard) {
  const triggers = campaign.triggers || {};
  const form = h("form", { class: "col" },
    h("label", { class: "check" }, h("input", { type: "checkbox", name: "boarding", checked: Boolean(triggers.boarding) }), " Boost during the airline's boarding window"),
    h("label", { class: "check" }, h("input", { type: "checkbox", name: "gateChange", checked: Boolean(triggers.gateChange) }), " Boost on a gate change in the catchment"),
    h("label", { class: "check" }, h("input", { type: "checkbox", name: "festival", checked: Boolean(triggers.festival) }), " Boost during the configured holiday period"),
    h("div", { class: "row" },
      h("label", { class: "check" }, h("input", { type: "checkbox", name: "delayEnabled", checked: Boolean(triggers.delayOver) }), " Boost when delay exceeds"),
      h("input", { class: "input", type: "number", name: "delayOver", min: "0", max: "240", value: triggers.delayOver || 30, style: { width: "90px" } }),
      h("span", { class: "muted tiny", text: "minutes" })
    ),
    h("p", { class: "hint", text: "All trigger inputs must be present in a trusted feed and fresh enough; otherwise the decision falls back." })
  );
  modal({
    title: "Edit trigger rules",
    subtitle: campaign.name,
    body: form,
    actions: [
      { label: "Cancel" },
      {
        label: "Save triggers", primary: true,
        onClick: async () => {
          const formData = new FormData(form);
          const payload = {
            campaignId: campaign.id,
            triggers: {
              boarding: formData.get("boarding") === "on",
              gateChange: formData.get("gateChange") === "on",
              festival: formData.get("festival") === "on",
              delayOver: formData.get("delayEnabled") === "on" ? Number(formData.get("delayOver") || 30) : 0,
            },
          };
          try {
            await api.post("/api/retailer/triggers", payload);
            toast("Trigger rules saved");
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

async function sharePromo(ctx, code) {
  try {
    const result = await api.post(`/api/retailer/promos/${code}/share`);
    toast(`Family code created: ${result.promo.code}`);
    ctx.rerender();
  } catch (error) {
    toast(error.message, "bad");
  }
}

async function duplicateCampaign(ctx, id, rerun) {
  try {
    const result = await api.post(`/api/retailer/campaigns/${id}/${rerun ? "rerun" : "duplicate"}`);
    toast(`${rerun ? "Campaign re-run" : "Campaign duplicated"} as ${result.campaignId} (pending review)`);
    ctx.rerender();
  } catch (error) {
    toast(error.message, "bad");
  }
}

async function previewCampaign(ctx, id) {
  try {
    const preview = await api.get(`/api/retailer/campaigns/preview${qs({ campaignId: id })}`);
    modal({
      title: "Audience-match preview",
      subtitle: `${preview.zones?.join(", ")} · next slot`,
      body: h("div", { class: "grid grid-2" },
        bigStat("Match", `${preview.matches}%`, "weighted audience fit"),
        bigStat("Expected impressions", fmtNumber(preview.expectedImpressions), preview.basis),
        bigStat("Expected redemptions", fmtNumber(preview.expectedRedemptions), "at current conversion"),
        bigStat("Today", fmtNumber(preview.todayImpressions || 0), "impressions recorded")
      ),
      actions: [{ label: "Close", primary: true }],
    });
  } catch (error) {
    toast(error.message, "bad");
  }
}

function bigStat(label, value, meta) {
  return h("div", { class: "card", style: { background: "var(--panel-2)" } },
    h("div", { class: "kpi-label", text: label }),
    h("div", { class: "kpi-value small", style: { marginTop: "5px" }, text: value }),
    h("div", { class: "kpi-meta", text: meta })
  );
}

async function openBuilder(ctx, dashboard, preselectedCreative = null) {
  const advertiserId = ctx.ui.advertiserId;
  const [creatives, screens] = await Promise.all([
    api.get(`/api/retailer/creatives${qs({ advertiserId })}`),
    api.get("/api/passenger/screens"),
  ]);
  const zones = [...new Map(screens.items.map((screen) => [screen.zoneId, { id: screen.zoneId, name: screen.zoneName }])).values()];
  const creativeOptions = creatives.items.filter((creative) => creative.status === "approved");
  const now = new Date();
  const startValue = new Date(now.getTime() + 3600_000).toISOString().slice(0, 16);
  const endValue = new Date(now.getTime() + 15 * 86400_000).toISOString().slice(0, 16);
  const previewBox = h("div", { class: "card", style: { background: "var(--panel-2)" } },
    h("div", { class: "kpi-label", text: "Live audience preview" }),
    h("div", { class: "muted tiny", style: { marginTop: "6px" }, text: "Choose zones and audience weights to preview the match." })
  );
  const previewCreative = h("div", {});
  const form = h("form", { class: "col", style: { gap: "14px" } });
  const creativeSelect = h("select", { class: "select", name: "creativeId" },
    ...creativeOptions.map((creative) => h("option", { value: creative.id, selected: preselectedCreative?.id === creative.id }, `${creative.name} · ${creative.category}`))
  );
  const zoneChecks = h("div", { class: "chip-row" },
    ...zones.map((zone) =>
      h("label", { class: "check", style: { border: "1px solid var(--line)", borderRadius: "8px", padding: "6px 9px" } },
        h("input", { type: "checkbox", name: "zones", value: zone.id, checked: ["T2-F", "T2-DUTY"].includes(zone.id) }),
        zone.name
      )
    )
  );
  const segmentSliders = h("div", { class: "grid grid-2", style: { gap: "9px" } },
    ...SEGMENTS.map((segment) => {
      const input = h("input", { type: "range", min: "0", max: "1", step: "0.05", name: `seg_${segment}`, value: segment === "holiday" || segment === "family" ? "0.8" : segment === "international" ? "0.6" : "0.2" });
      const label = h("span", { class: "mono tiny", text: input.value });
      input.addEventListener("input", () => { label.textContent = Number(input.value).toFixed(2); schedulePreview(); });
      return h("div", { class: "field" }, h("label", { style: { display: "flex", justifyContent: "space-between" } }, h("span", { text: titleCase(segment) }), label), input);
    })
  );
  form.append(
    h("div", { class: "form-grid" },
      field("Campaign name", h("input", { class: "input", name: "name", required: true, placeholder: "Summer fragrance boost" })),
      field("Creative", creativeSelect),
      field("Start (UTC)", h("input", { class: "input", type: "datetime-local", name: "start", value: startValue })),
      field("End (UTC)", h("input", { class: "input", type: "datetime-local", name: "end", value: endValue })),
      field("Budget (EUR)", h("input", { class: "input", type: "number", name: "budget", value: "5000", min: "0" })),
      field("Daily cap (EUR)", h("input", { class: "input", type: "number", name: "dailyCap", value: "400", min: "0" })),
      field("Frequency cap (min)", h("input", { class: "input", type: "number", name: "freqCapMin", value: "20", min: "1" })),
      field("Bid (EUR CPM)", h("input", { class: "input", type: "number", name: "bid", value: "2.5", step: "0.1", min: "0" }))
    ),
    h("div", { class: "field" }, h("label", { text: "Zones / screens" }), zoneChecks),
    h("div", { class: "field" }, h("label", { text: "Segment weights (0–1)" }), segmentSliders),
    h("div", { class: "form-grid" },
      field("Minimum dwell (min)", h("input", { class: "input", type: "number", name: "minDwell", value: "15", min: "0" })),
      field("Minimum crowd", h("input", { class: "input", type: "number", name: "minCrowd", value: "80", min: "0" })),
      field("Destinations (comma separated)", h("input", { class: "input", name: "destinations", placeholder: "DXB, SMG, LHR" })),
      h("div", { class: "field" }, h("label", { text: "Hard filters" }),
        h("label", { class: "check" }, h("input", { type: "checkbox", name: "internationalOnly" }), " International audience only"))
    ),
    h("div", { class: "field" }, h("label", { text: "Triggers" }),
      h("div", { class: "row wrap" },
        h("label", { class: "check" }, h("input", { type: "checkbox", name: "delay", checked: true }), " Delay ≥ 30 min"),
        h("label", { class: "check" }, h("input", { type: "checkbox", name: "boarding" }), " Boarding window"),
        h("label", { class: "check" }, h("input", { type: "checkbox", name: "gateChange" }), " Gate change"),
        h("label", { class: "check" }, h("input", { type: "checkbox", name: "festival", checked: true }), " Holiday period")
      )
    ),
    h("div", { class: "grid grid-2", style: { gap: "14px" } },
      h("div", { class: "col" }, h("div", { class: "eyebrow", text: "Preview on screen" }), previewCreative),
      previewBox
    )
  );
  let draftTimer = null;
  function schedulePreview() {
    clearTimeout(draftTimer);
    draftTimer = setTimeout(runPreview, 450);
  }
  function currentDraft() {
    const formData = new FormData(form);
    const selectedZones = formData.getAll("zones");
    const segments = {};
    for (const segment of SEGMENTS) segments[segment] = Number(formData.get(`seg_${segment}`) || 0);
    const destinations = String(formData.get("destinations") || "").split(",").map((item) => item.trim().toUpperCase()).filter(Boolean);
    const creative = creativeOptions.find((item) => item.id === formData.get("creativeId"));
    return {
      name: formData.get("name"),
      creativeId: formData.get("creativeId"),
      start: formData.get("start") ? `${formData.get("start")}:00Z` : undefined,
      end: formData.get("end") ? `${formData.get("end")}:00Z` : undefined,
      budget: Number(formData.get("budget")),
      dailyCap: Number(formData.get("dailyCap")),
      freqCapMin: Number(formData.get("freqCapMin")),
      bid: Number(formData.get("bid")),
      segments,
      filters: {
        internationalOnly: formData.get("internationalOnly") === "on",
        minDwell: Number(formData.get("minDwell")),
        minCrowd: Number(formData.get("minCrowd")),
        destinations,
      },
      placement: { zones: selectedZones, gates: [], screens: [] },
      triggers: {
        delayOver: formData.get("delay") === "on" ? 30 : 0,
        boarding: formData.get("boarding") === "on",
        gateChange: formData.get("gateChange") === "on",
        festival: formData.get("festival") === "on",
      },
      creative,
    };
  }
  async function runPreview() {
    const draft = currentDraft();
    previewCreative.replaceChildren(draft.creative
      ? adCreative(draft.creative, { compact: true, context: "CAMPAIGN PREVIEW" })
      : h("div", { class: "empty", text: "No approved creative yet." }));
    try {
      const result = await api.post("/api/retailer/campaigns/preview", draft);
      previewBox.replaceChildren(
        h("div", { class: "kpi-label", text: "Live audience preview" }),
        h("div", { class: "kpi-value small", style: { marginTop: "7px" }, text: `${result.matches}% match` }),
        h("div", { class: "kpi-meta", text: `${fmtNumber(result.expectedImpressions)} expected impressions · ${fmtNumber(result.expectedRedemptions)} redemptions` }),
        h("div", { class: "progress", style: { marginTop: "9px" } }, h("span", { style: { width: `${result.matches}%` } })),
        h("p", { class: "hint", style: { marginTop: "8px" }, text: `${result.basis} · zones ${result.zones.join(", ")}` })
      );
    } catch (error) {
      previewBox.replaceChildren(h("p", { class: "muted tiny", text: error.message }));
    }
  }
  form.addEventListener("change", schedulePreview);
  form.addEventListener("input", schedulePreview);
  setTimeout(runPreview, 200);
  modal({
    title: "Campaign builder",
    subtitle: "The preview uses live ZonePresence; saving sends the campaign to Media approval.",
    body: form,
    wide: true,
    actions: [
      { label: "Cancel" },
      {
        label: "Save campaign", primary: true,
        onClick: async () => {
          const draft = currentDraft();
          if (!draft.name) { toast("Campaign name is required", "bad"); return false; }
          if (!draft.creativeId) { toast("Choose an approved creative", "bad"); return false; }
          try {
            await api.post("/api/retailer/campaigns", { ...draft, advertiserId });
            toast("Campaign saved — pending Media approval");
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

function field(label, input) {
  return h("div", { class: "field" }, h("label", { text: label }), input);
}

function openCreativeForm(ctx, advertiserId, existing = null) {
  const creative = existing || {};
  const form = h("form", { class: "form-grid" },
    field("Name", h("input", { class: "input", name: "name", value: creative.name ? `${creative.name} copy` : "", required: true })),
    field("Category", h("input", { class: "input", name: "category", value: creative.category || "retail" })),
    field("Headline (EN)", h("input", { class: "input", name: "headlineEn", value: creative.headline_en || "", required: true })),
    field("Headline (中文)", h("input", { class: "input", name: "headlineZh", value: creative.headline_zh || "" })),
    field("Body (EN)", h("textarea", { class: "textarea", name: "bodyEn", rows: "3" }, creative.body_en || "")),
    field("Body (中文)", h("textarea", { class: "textarea", name: "bodyZh", rows: "3" }, creative.body_zh || "")),
    field("CTA (EN)", h("input", { class: "input", name: "ctaEn", value: creative.cta_en || "Learn more" })),
    field("CTA (中文)", h("input", { class: "input", name: "ctaZh", value: creative.cta_zh || "了解更多" })),
    field("Template", h("select", { class: "select", name: "template" },
      ...["aurora", "lumen", "grid", "wave", "paper"].map((template) => h("option", { value: template, selected: template === (creative.template || "aurora") }, template))
    )),
    field("Accent", h("input", { class: "input", type: "color", name: "colorA", value: (creative.colors || ["#38e8c8"])[0] || "#38e8c8" })),
    field("Secondary", h("input", { class: "input", type: "color", name: "colorB", value: (creative.colors || ["#38e8c8", "#8b7bff"])[1] || "#8b7bff" })),
    field("Image (optional)", h("input", { class: "input", type: "file", name: "imageFile", accept: "image/png,image/jpeg,image/webp" })),
    h("div", { class: "full", id: "creative-preview" })
  );
  let imageData = creative.image || "";
  const fileInput = form.querySelector('[name="imageFile"]');
  const previewNode = form.querySelector("#creative-preview");
  const refreshPreview = () => {
    const values = Object.fromEntries(new FormData(form).entries());
    const draft = {
      name: values.name || "Preview",
      headlineEn: values.headlineEn || "Your airport moment",
      headlineZh: values.headlineZh,
      bodyEn: values.bodyEn,
      bodyZh: values.bodyZh,
      ctaEn: values.ctaEn,
      ctaZh: values.ctaZh,
      template: values.template,
      colors: [values.colorA, values.colorB],
      category: values.category,
      image: imageData,
    };
    previewNode.replaceChildren(adCreative(draft, { context: "CREATIVE PREVIEW" }));
  };
  form.addEventListener("input", refreshPreview);
  form.addEventListener("change", refreshPreview);
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    if (file.size > 300_000) { toast("Image must be under 300 KB", "bad"); fileInput.value = ""; return; }
    const reader = new FileReader();
    reader.onload = () => { imageData = String(reader.result); refreshPreview(); };
    reader.readAsDataURL(file);
  });
  refreshPreview();
  modal({
    title: existing ? "Duplicate creative" : "New creative",
    subtitle: "Uploads are stored as data URLs; no external asset host is required.",
    body: form,
    wide: true,
    actions: [
      { label: "Cancel" },
      {
        label: "Save creative", primary: true,
        onClick: async () => {
          const values = Object.fromEntries(new FormData(form).entries());
          delete values.imageFile;
          const payload = {
            name: values.name,
            category: values.category,
            headlineEn: values.headlineEn,
            headlineZh: values.headlineZh,
            bodyEn: values.bodyEn,
            bodyZh: values.bodyZh,
            ctaEn: values.ctaEn,
            ctaZh: values.ctaZh,
            template: values.template,
            colors: [values.colorA, values.colorB],
            image: imageData,
            advertiserId,
          };
          try {
            await api.post("/api/retailer/creatives", payload);
            toast("Creative saved — pending brand-safety approval");
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

async function openCreativeStudio(ctx, advertiserId) {
  const preview = h("div", { class: "card", style: { background: "var(--panel-2)" } }, h("p", { class: "muted tiny", text: "Describe the offer; the offline provider drafts a bilingual ad page." }));
  const form = h("form", { class: "col" },
    h("div", { class: "form-grid" },
      field("Brief", h("input", { class: "input", name: "brief", placeholder: "Festive sweets, 20% off, families flying domestic" })),
      field("Language", h("select", { class: "select", name: "language" }, h("option", { value: "zh" }, "中文"), h("option", { value: "en" }, "English")))
    ),
    h("div", { class: "row" }, h("button", { class: "btn", type: "button", id: "generate-btn" }, icon("spark", 13), " Generate draft")),
    preview
  );
  let generated = null;
  form.querySelector("#generate-btn").addEventListener("click", async () => {
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      generated = await api.post("/api/retailer/creatives/generate", { brief: data.brief, language: data.language });
      preview.replaceChildren(
        adCreative({
          headlineEn: generated.headline,
          headlineZh: generated.also?.headline,
          bodyEn: generated.body,
          bodyZh: generated.also?.body,
          ctaEn: generated.cta,
          ctaZh: generated.also?.cta,
          template: generated.template,
          colors: generated.colors,
          name: "GenAI draft",
        }, { context: `OFFLINE · ${generated.language.toUpperCase()}` })
      );
    } catch (error) {
      toast(error.message, "bad");
    }
  });
  modal({
    title: "GenAI creative assistant",
    subtitle: "Mock provider by default; swap AI_PROVIDER for a real LLM without changing the UI.",
    body: form,
    wide: true,
    actions: [
      { label: "Cancel" },
      {
        label: "Save to library", primary: true,
        onClick: async () => {
          if (!generated) { toast("Generate a draft first", "bad"); return false; }
          try {
            await api.post("/api/retailer/creatives", {
              advertiserId,
              name: `GenAI · ${(generated.brief || "draft").slice(0, 40)}`,
              headlineEn: generated.headline,
              headlineZh: generated.also?.headline || generated.headline,
              bodyEn: generated.body,
              bodyZh: generated.also?.body || generated.body,
              ctaEn: generated.cta,
              ctaZh: generated.also?.cta || generated.cta,
              template: generated.template,
              colors: generated.colors,
              category: "generated",
            });
            toast("Generated creative saved");
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

async function openPromoForm(ctx, dashboard) {
  const [flights] = await Promise.all([api.get("/api/flights")]);
  const campaigns = dashboard.campaigns.filter((campaign) => campaign.status === "approved");
  const form = h("form", { class: "form-grid" },
    field("Campaign", h("select", { class: "select", name: "campaignId" },
      ...campaigns.map((campaign) => h("option", { value: campaign.id }, campaign.name))
    )),
    field("Flight", h("select", { class: "select", name: "flightId" },
      ...flights.items.slice(0, 60).map((flight) => h("option", { value: flight.flight_id }, `${flight.display} → ${flight.destination} · Gate ${flight.gate}`))
    )),
    field("Label", h("input", { class: "input", name: "label", value: "Gate offer" })),
    field("Value", h("input", { class: "input", name: "value", value: "10%" })),
    field("Minutes", h("input", { class: "input", type: "number", name: "minutes", value: "30", min: "5", max: "240" }))
  );
  modal({
    title: "Create promo code",
    subtitle: "The code expires 10 minutes before the linked flight's estimated departure.",
    body: form,
    actions: [
      { label: "Cancel" },
      {
        label: "Create code", primary: true,
        onClick: async () => {
          const values = Object.fromEntries(new FormData(form).entries());
          try {
            const result = await api.post("/api/retailer/promos", { ...values, advertiserId: ctx.ui.advertiserId });
            toast(`Promo ${result.promo.code} created`);
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

function tickCountdowns() {
  const running = document.body.dataset.simRunning === "true";
  if (!running) return;
  const speed = Number(document.body.dataset.speed || 1);
  document.querySelectorAll("[data-remaining]").forEach((node) => {
    let remaining = Number(node.dataset.remaining || 0);
    if (remaining <= 0) return;
    remaining = Math.max(0, remaining - speed);
    node.dataset.remaining = String(remaining);
    node.textContent = fmtSeconds(remaining);
  });
}