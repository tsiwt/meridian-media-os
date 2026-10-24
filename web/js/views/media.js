import { api, qs } from "../api.js";
import {
  clear, copyText, debounce, fmtCompact, fmtDate, fmtMoney, fmtNumber, fmtPct,
  fmtTime, h, icon, modal, statusBadge, titleCase, toast,
} from "../dom.js";
import { lineChart, profileBars } from "../components/charts.js";
import { adCreative } from "../components/creative.js";

const TABS = [
  ["inventory", "Inventory calendar"],
  ["yield", "Yield & pricing"],
  ["approvals", "Approval queue"],
  ["advertisers", "Advertisers"],
  ["packages", "Packages"],
  ["conflict", "Why A beat B"],
];

export async function mount(ctx) {
  const { root, ui } = ctx;
  const date = ui.date || new Date().toISOString().slice(0, 10);
  ui.date = date;
  const first = await api.get(`/api/media/inventory${qs({ date, screenId: ui.screenId })}`);
  if (!ui.screenId) ui.screenId = first.screen.id;
  const [inventory, yieldData, approvals, advertisers, packages] = await Promise.all([
    api.get(`/api/media/inventory${qs({ date, screenId: ui.screenId })}`),
    api.get("/api/media/yield"),
    api.get("/api/media/approvals"),
    api.get("/api/media/advertisers"),
    api.get("/api/media/packages"),
  ]);

  root.appendChild(pageHead(ctx, inventory));
  root.appendChild(tabs(ctx));
  const content = h("div", {});
  root.appendChild(content);

  if (ui.tab === "inventory") renderInventory(ctx, content, inventory);
  else if (ui.tab === "yield") renderYield(ctx, content, yieldData);
  else if (ui.tab === "approvals") renderApprovals(ctx, content, approvals);
  else if (ui.tab === "advertisers") renderAdvertisers(ctx, content, advertisers);
  else if (ui.tab === "packages") renderPackages(ctx, content, packages, inventory);
  else if (ui.tab === "conflict") await renderConflict(ctx, content, inventory);

  const refresh = debounce(() => {
    if (["inventory", "conflict"].includes(ui.tab)) ctx.rerender();
  }, 4200);
  return {
    onEvent(name) {
      if (["decisions", "approval", "kpi"].includes(name)) refresh();
    },
    destroy() { /* no timer */ },
  };
}

function pageHead(ctx, inventory) {
  return h("div", { class: "page-head" },
    h("div", {},
      h("div", { class: "eyebrow", text: "Media Manager · inventory & yield" }),
      h("h1", { text: ctx.t("media.title") }),
      h("p", { class: "lede", text: ctx.t("media.lede") })
    ),
    h("div", { class: "head-actions" },
      h("span", { class: "chip" }, h("strong", { text: `${inventory.summary.occupancyPct}%` }), " occupancy"),
      h("span", { class: "chip" }, h("strong", { text: fmtNumber(inventory.screens.length) }), " screens"),
      h("span", { class: "chip" }, h("strong", { text: fmtMoney(inventory.summary.revenueForecast, inventory.summary.currency) }), " forecast")
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

function renderInventory(ctx, root, inventory) {
  const controls = h("div", { class: "row wrap", style: { marginBottom: "12px" } },
    h("input", { class: "input", type: "date", value: inventory.date, style: { width: "auto" }, onChange: (event) => { ctx.ui.date = event.target.value || inventory.date; ctx.rerender(); } }),
    h("select", { class: "select", style: { width: "auto" }, onChange: (event) => { ctx.ui.screenId = event.target.value; ctx.rerender(); } },
      ...inventory.screens.map((screen) => h("option", { value: screen.id, selected: screen.id === inventory.screen.id }, `${screen.id} · ${screen.zoneName} · ${screen.status}`))
    ),
    h("span", { class: "badge teal", text: inventory.screen.aspect }),
    h("span", { class: "badge grey", text: `${inventory.screen.nearestGates.join(", ")}` }),
    h("div", { class: "grow" }),
    legend()
  );
  root.appendChild(controls);
  root.appendChild(h("div", { class: "card" },
    h("div", { class: "card-head" },
      h("div", {},
        h("div", { class: "card-title", text: `${inventory.date} · every screen × hour` }),
        h("div", { class: "card-sub", text: "Booked = approved campaign placement · Premium = predicted high footfall · price = base + 0.11 × live presence" })
      ),
      h("span", { class: "badge purple", text: inventory.screen.id })
    ),
    inventoryGrid(ctx, inventory)
  ));
  const selected = inventory.selectedCells;
  root.appendChild(h("div", { class: "card", style: { marginTop: "16px" } },
    h("div", { class: "card-head" },
      h("div", { class: "card-title", text: `Selected screen · ${inventory.screen.name}` }),
      h("span", { class: "badge grey", text: inventory.screen.zone_id })
    ),
    h("div", { class: "grid", style: { gridTemplateColumns: "repeat(auto-fit, minmax(92px, 1fr))" } },
      ...selected.map((cell) =>
        h("button", {
          class: "card", style: { padding: "9px", background: cellColor(cell), textAlign: "left" },
          onClick: () => cellModal(ctx, cell, inventory.screen),
        },
          h("div", { class: "mono tiny", text: `${String(cell.hour).padStart(2, "0")}:00` }),
          h("div", { class: "mono", style: { fontSize: "15px", marginTop: "3px" }, text: fmtCompact(cell.crowd) }),
          h("div", { class: "tiny muted", text: `${fmtMoney(cell.price, inventory.summary.currency)}` })
        )
      )
    )
  ));
}

function legend() {
  return h("div", { class: "legend" },
    h("span", {}, h("i", { style: { background: "var(--panel-3)", border: "1px solid var(--line)" } }), "available"),
    h("span", {}, h("i", { style: { background: "rgba(56,232,200,.6)" } }), "premium"),
    h("span", {}, h("i", { style: { background: "rgba(139,123,255,.7)" } }), "booked")
  );
}

function inventoryGrid(ctx, inventory) {
  const zones = inventory.zones;
  const columns = Array.from({ length: 24 }, (_, index) => `${String(index).padStart(2, "0")}`);
  const byKey = new Map(inventory.cells.map((cell) => [`${cell.zoneId}:${cell.hour}`, cell]));
  const grid = h("div", {
    style: {
      display: "grid",
      gridTemplateColumns: `120px repeat(24, minmax(28px, 1fr))`,
      gap: "3px",
      minWidth: "1040px",
    },
  });
  grid.appendChild(h("div", {}));
  columns.forEach((column) => grid.appendChild(h("div", { class: "tiny muted", style: { textAlign: "center" }, text: column })));
  for (const zone of zones) {
    grid.appendChild(h("div", { class: "tiny", style: { display: "flex", alignItems: "center", color: "var(--muted)" }, text: zone.name }));
    for (let hour = 0; hour < 24; hour++) {
      const cell = byKey.get(`${zone.id}:${hour}`) || { zoneId: zone.id, hour, crowd: 0, status: "available", price: 0 };
      grid.appendChild(h("div", {
        class: "heat-cell",
        title: `${zone.id} ${hour}:00 · ${cell.status} · ${fmtNumber(cell.crowd)} pax · ${fmtMoney(cell.price, inventory.summary.currency)}${cell.bookedBy ? ` · ${cell.bookedBy}` : ""}`,
        style: { background: cellColor(cell), cursor: "pointer", minWidth: "28px" },
        onClick: () => cellModal(ctx, cell, inventory.screen),
      }));
    }
  }
  return h("div", { class: "scroll-x" }, grid);
}

function cellColor(cell) {
  if (cell.status === "booked") return "rgba(139,123,255,.62)";
  if (cell.status === "premium") return "rgba(56,232,200,.42)";
  const ratio = Math.min(1, (cell.crowd || 0) / 500);
  return `color-mix(in srgb, var(--accent) ${Math.round(6 + ratio * 26)}%, var(--panel-3))`;
}

function cellModal(ctx, cell, screen) {
  ctx.modal({
    title: `${String(cell.hour).padStart(2, "0")}:00 · ${cell.zoneId}`,
    subtitle: `${screen.id} · ${screen.name}`,
    body: h("div", { class: "grid grid-2" },
      bigStat("Predicted presence", `${fmtNumber(cell.crowd)} pax`, "AODB + ACRIS"),
      bigStat("Slot price", fmtMoney(cell.price, ctx.config.theme.currency), "suggested"),
      bigStat("Status", titleCase(cell.status), cell.bookedBy || "open inventory"),
      bigStat("Inventory", cell.status === "available" ? "Sellable" : "Committed", "calendar view")
    ),
    actions: [{ label: "Close", primary: true }],
  });
}

function bigStat(label, value, meta) {
  return h("div", { class: "card", style: { background: "var(--panel-2)" } },
    h("div", { class: "kpi-label", text: label }),
    h("div", { class: "kpi-value small", style: { marginTop: "5px" }, text: value }),
    h("div", { class: "kpi-meta", text: meta })
  );
}

function renderYield(ctx, root, data) {
  root.appendChild(h("div", { class: "grid", style: { gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" } },
    ...data.zones.slice(0, 6).map((zone) =>
      h("div", { class: "card" },
        h("div", { class: "row-between" },
          h("div", {}, h("div", { class: "card-title", text: zone.zoneName }), h("div", { class: "card-sub", text: zone.zoneId })),
          zone.premium ? h("span", { class: "badge teal", text: "premium" }) : h("span", { class: "badge grey", text: "standard" })
        ),
        h("div", { class: "kpi-value small", style: { marginTop: "9px" }, text: fmtMoney(zone.suggestedPrice, data.currency) }),
        h("div", { class: "kpi-meta", text: "suggested price / slot" }),
        h("div", { class: "progress", style: { marginTop: "9px" } }, h("span", { style: { width: `${zone.occupancyPct}%` } })),
        h("div", { class: "row-between", style: { marginTop: "5px" } },
          h("span", { class: "tiny muted", text: `${zone.occupancyPct}% occupancy` }),
          h("span", { class: "tiny mono", text: `${fmtMoney(zone.revenueNext7d, data.currency)} / 7d` })
        )
      )
    )
  ));
  root.appendChild(h("div", { class: "card", style: { marginTop: "16px" } },
    h("div", { class: "card-head" },
      h("div", { class: "card-title", text: "Network revenue · 30 days" }),
      h("span", { class: "badge grey", text: data.model })
    ),
    lineChart({
      values: data.history.map((row) => row.revenue),
      labels: data.history.map((row) => fmtDate(row.day)),
      height: 190,
      format: (value) => fmtMoney(value, data.currency),
    })
  ));
}

function renderApprovals(ctx, root, data) {
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: "Approval queue" }), h("p", { class: "hint", text: "Campaigns and creatives cannot play until approved. Every approval uses the brand-safety checklist." })),
    h("span", { class: "badge amber", text: `${data.campaigns.length + data.creatives.length} waiting` })
  ));
  root.appendChild(h("div", { class: "grid grid-2" },
    h("div", { class: "card" },
      h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Campaigns" }), h("span", { class: "badge grey", text: String(data.campaigns.length) })),
      h("div", { class: "list" },
        ...(data.campaigns.length ? data.campaigns.map((campaign) =>
          h("div", { class: "list-item" },
            h("div", { class: "list-main" },
              h("div", { class: "list-title", text: campaign.name }),
              h("div", { class: "list-sub", text: `${campaign.advertiserName} · ${campaign.category} · bid ${fmtMoney(campaign.bid, ctx.config.theme.currency)} CPM` }),
              h("div", { class: "chip-row", style: { marginTop: "6px" } },
                ...Object.entries(campaign.segments || {}).slice(0, 4).map(([key, value]) => h("span", { class: "chip" }, `${titleCase(key)} ${value}`)),
                campaign.filters?.internationalOnly ? h("span", { class: "badge purple", text: "international only" }) : null
              )
            ),
            h("div", { class: "col", style: { gap: "5px" } },
              h("button", { class: "btn small primary", onClick: () => approve(ctx, "campaign", campaign.id, data.checklist) }, "Approve"),
              h("button", { class: "btn small danger", onClick: () => reject(ctx, "campaign", campaign.id) }, "Reject")
            )
          )
        ) : [h("div", { class: "empty", text: "No campaigns waiting." })])
      )
    ),
    h("div", { class: "card" },
      h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Creatives" }), h("span", { class: "badge grey", text: String(data.creatives.length) })),
      h("div", { class: "list" },
        ...(data.creatives.length ? data.creatives.map((creative) =>
          h("div", { class: "list-item" },
            h("div", { style: { width: "120px", flex: "none" } }, adCreative(creative, { compact: true, context: "REVIEW" })),
            h("div", { class: "list-main" },
              h("div", { class: "list-title", text: creative.name }),
              h("div", { class: "list-sub", text: `${creative.advertiserName} · ${creative.category}` }),
              h("div", { class: "row", style: { marginTop: "7px", gap: "5px" } },
                h("button", { class: "btn small primary", onClick: () => approve(ctx, "creative", creative.id, data.checklist) }, "Approve"),
                h("button", { class: "btn small danger", onClick: () => reject(ctx, "creative", creative.id) }, "Reject")
              )
            )
          )
        ) : [h("div", { class: "empty", text: "No creatives waiting." })])
      )
    )
  ));
  root.appendChild(h("div", { class: "card", style: { marginTop: "16px" } },
    h("div", { class: "eyebrow", text: "Brand-safety checklist" }),
    h("div", { class: "chip-row", style: { marginTop: "8px" } },
      ...data.checklist.map((item) => h("span", { class: "chip", text: item }))
    )
  ));
}

function approve(ctx, type, id, checklist) {
  const checks = checklist.map((label, index) =>
    h("label", { class: "check" }, h("input", { type: "checkbox", name: `check_${index}` }), label)
  );
  const form = h("form", { class: "col" }, ...checks);
  modal({
    title: `Approve ${type}`,
    subtitle: "Confirm each brand-safety check. Approval is recorded against the campaign.",
    body: form,
    actions: [
      { label: "Cancel" },
      {
        label: "Approve", primary: true,
        onClick: async () => {
          const values = Object.fromEntries(new FormData(form).entries());
          if (Object.keys(values).length !== checklist.length) {
            toast("Complete every checklist item to approve", "bad");
            return false;
          }
          try {
            await api.post("/api/media/approvals", { type, id, decision: "approve", checklist: values });
            toast(`${titleCase(type)} approved`);
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

async function reject(ctx, type, id) {
  try {
    await api.post("/api/media/approvals", { type, id, decision: "reject" });
    toast(`${titleCase(type)} rejected`);
    ctx.rerender();
  } catch (error) {
    toast(error.message, "bad");
  }
}

function renderAdvertisers(ctx, root, data) {
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: "Advertiser overview" }), h("p", { class: "hint", text: "Top advertisers by spend, live campaign count, under-delivery flags and one-click reports." }))
  ));
  root.appendChild(h("div", { class: "card flush table-wrap" },
    h("table", { class: "data" },
      h("thead", {}, h("tr", {},
        h("th", { text: "Advertiser" }), h("th", { class: "num", text: "Campaigns" }), h("th", { class: "num", text: "Spend" }),
        h("th", { class: "num", text: "Revenue" }), h("th", { class: "num", text: "ROI" }), h("th", { class: "num", text: "Today impressions" }),
        h("th", { text: "Delivery" }), h("th", { text: "" })
      )),
      h("tbody", {}, ...data.items.map((advertiser) =>
        h("tr", {},
          h("td", {}, h("div", { class: "strong", text: advertiser.name }), h("div", { class: "sub", text: advertiser.kind })),
          h("td", { class: "num", text: fmtNumber(advertiser.campaigns) }),
          h("td", { class: "num", text: fmtMoney(advertiser.spend, data.currency) }),
          h("td", { class: "num", text: fmtMoney(advertiser.revenue, data.currency) }),
          h("td", { class: "num", text: `${(advertiser.roi * 100).toFixed(0)}%` }),
          h("td", { class: "num", text: fmtCompact(advertiser.todayImpressions) }),
          h("td", {}, advertiser.underDelivering ? h("span", { class: "badge amber", text: "under-delivering" }) : h("span", { class: "badge green", text: "on pace" })),
          h("td", {}, h("div", { class: "row", style: { gap: "5px" } },
            h("button", { class: "btn small", onClick: () => shareReport(ctx, advertiser.id) }, "Share report"),
            h("button", { class: "btn small", onClick: () => previewReport(ctx, advertiser.id) }, "Preview")
          ))
        )
      ))
    )
  ));
}

async function shareReport(ctx, advertiserId) {
  try {
    const result = await api.post("/api/media/report/share", { advertiserId });
    const url = `${location.origin}${result.url}`;
    await copyText(url);
    window.open(result.url, "_blank", "noopener");
  } catch (error) {
    toast(error.message, "bad");
  }
}

function previewReport(ctx, advertiserId) {
  window.open(`/api/media/report${qs({ advertiserId })}`, "_blank", "noopener");
}

function renderPackages(ctx, root, data, inventory) {
  root.appendChild(h("div", { class: "section-head" },
    h("div", {}, h("h2", { text: "Packages" }), h("p", { class: "hint", text: "Bundle screens into a sellable pack. Prices are suggestions, not invoices." })),
    h("button", { class: "btn primary small", onClick: () => createPackage(ctx, inventory) }, icon("plus", 12), " New package")
  ));
  root.appendChild(h("div", { class: "grid grid-3" },
    ...data.items.map((pack) =>
      h("div", { class: "card" },
        h("div", { class: "row-between" },
          h("div", { class: "card-title", text: pack.name }),
          h("span", { class: "badge purple", text: `${pack.screenIds.length} screens` })
        ),
        h("p", { class: "muted tiny", style: { marginTop: "6px" }, text: pack.description }),
        h("div", { class: "kpi-value small", style: { marginTop: "12px" }, text: fmtMoney(pack.price, ctx.config.theme.currency) }),
        h("div", { class: "kpi-meta", text: "suggested 7-day package price" }),
        h("div", { class: "chip-row", style: { marginTop: "9px" } },
          ...pack.screenIds.slice(0, 6).map((id) => h("span", { class: "chip", text: id })),
          pack.screenIds.length > 6 ? h("span", { class: "chip", text: `+${pack.screenIds.length - 6}` }) : null
        )
      )
    )
  ));
}

async function createPackage(ctx, inventory) {
  const screens = inventory.screens;
  const form = h("form", { class: "form-grid" },
    field("Name", h("input", { class: "input", name: "name", required: true })),
    field("Price", h("input", { class: "input", type: "number", name: "price", value: "12000", min: "0" })),
    field("Description", h("textarea", { class: "textarea", name: "description", rows: "3" })),
    h("div", { class: "field full" },
      h("label", { text: "Screens" }),
      h("div", { class: "chip-row", style: { maxHeight: "220px", overflow: "auto" } },
        ...screens.map((screen) =>
          h("label", { class: "check", style: { border: "1px solid var(--line)", borderRadius: "7px", padding: "4px 7px" } },
            h("input", { type: "checkbox", name: "screenIds", value: screen.id, checked: ["T2-F", "T2-DUTY"].includes(screen.zone_id) }),
            `${screen.id} · ${screen.zone_id}`
          )
        )
      )
    )
  );
  form.querySelector("textarea").parentElement.className = "field full";
  modal({
    title: "Build a package",
    body: form,
    wide: true,
    actions: [
      { label: "Cancel" },
      {
        label: "Create package", primary: true,
        onClick: async () => {
          const formData = new FormData(form);
          try {
            await api.post("/api/media/packages", {
              name: formData.get("name"),
              price: Number(formData.get("price")),
              description: formData.get("description"),
              screenIds: formData.getAll("screenIds"),
            });
            toast("Package created");
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

async function renderConflict(ctx, root, inventory) {
  const screenId = ctx.ui.screenId || inventory.screen.id;
  const conflict = await api.get(`/api/media/conflict${qs({ screenId })}`);
  root.appendChild(h("div", { class: "row wrap", style: { marginBottom: "14px" } },
    h("select", { class: "select", style: { width: "auto" }, onChange: (event) => { ctx.ui.screenId = event.target.value; ctx.rerender(); } },
      ...inventory.screens.map((screen) => h("option", { value: screen.id, selected: screen.id === screenId }, `${screen.id} · ${screen.zoneName}`))
    ),
    h("span", { class: "badge grey", text: conflict.decidedAt ? `${fmtTime(conflict.decidedAt)} UTC` : "no decision" }),
    h("span", { class: "badge purple", text: `winner ${conflict.winnerId || "none"}` })
  ));
  if (!conflict.candidates?.length) {
    root.appendChild(h("div", { class: "empty", text: "No decision has been recorded for this screen yet." }));
    return;
  }
  const winner = conflict.candidates[0];
  root.appendChild(h("div", { class: "grid grid-2" },
    h("div", { class: "card accent" },
      h("div", { class: "eyebrow", text: "Winner" }),
      h("h2", { style: { marginTop: "5px" }, text: winner.name }),
      h("p", { class: "muted", style: { marginTop: "6px" }, text: conflict.reason }),
      h("div", { class: "grid grid-2", style: { marginTop: "12px" } },
        bigStat("Audience match", `${Math.round(winner.audienceMatch * 100)}%`, "weighted segments"),
        bigStat("Boost", `${winner.boost.toFixed(2)}×`, "business rules"),
        bigStat("Final score", winner.finalScore.toFixed(3), "reproducible"),
        bigStat("Executed", conflict.validation?.executed || "ai", "evidence check")
      )
    ),
    h("div", { class: "card" },
      h("div", { class: "eyebrow", text: "Crowd profile" }),
      h("div", { style: { marginTop: "8px" } }, profileBars(conflict.profile, 7))
    )
  ));
  root.appendChild(h("div", { class: "card", style: { marginTop: "16px" } },
    h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Candidate scoreboard" }), h("span", { class: "badge grey", text: conflict.explanation })),
    h("div", { class: "table-wrap" },
      h("table", { class: "data" },
        h("thead", {}, h("tr", {},
          h("th", { text: "Campaign" }), h("th", { class: "num", text: "Audience match" }), h("th", { class: "num", text: "Boost" }),
          h("th", { class: "num", text: "Final" }), h("th", { text: "Why" }), h("th", { text: "Result" })
        )),
        h("tbody", {}, ...conflict.candidates.map((candidate) =>
          h("tr", {},
            h("td", {}, h("div", { class: "strong", text: candidate.name }), h("div", { class: "sub", text: candidate.advertiser })),
            h("td", { class: "num", text: `${Math.round(candidate.audienceMatch * 100)}%` }),
            h("td", { class: "num", text: `${candidate.boost.toFixed(2)}×` }),
            h("td", { class: "num strong", text: candidate.finalScore.toFixed(3) }),
            h("td", { class: "sub", text: candidate.reasons.join(" · ") }),
            h("td", {}, candidate.campaignId === conflict.winnerId ? h("span", { class: "badge green", text: "played" }) : h("span", { class: "badge grey", text: "next in rotation" }))
          )
        ))
      )
    )
  ));
}

function field(label, input) {
  return h("div", { class: "field" }, h("label", { text: label }), input);
}