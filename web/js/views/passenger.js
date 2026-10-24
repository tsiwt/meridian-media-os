import { api } from "../api.js";
import {
  clear, debounce, fmtNumber, fmtPct, fmtSeconds, fmtTime, h, icon, statusBadge, toast,
} from "../dom.js";
import { adCreative } from "../components/creative.js";
import { profileBars } from "../components/charts.js";

export async function mount(ctx) {
  const { root, ui } = ctx;
  const screens = await api.get("/api/passenger/screens");
  if (!screens.items.some((screen) => screen.id === ui.screenId)) ui.screenId = screens.default || screens.items[0]?.id;
  const data = await loadScreen(ctx);
  if (!data) return {};

  let currentData = data;
  let frameKey = "";
  let overlayOpen = Boolean(ui.why);
  const frameHost = h("div", {});
  const sideHost = h("div", {});

  if (!ctx.compact) {
    root.appendChild(pageHead(ctx, screens, data));
  } else {
    root.appendChild(compactControls(ctx, screens));
  }
  root.appendChild(h("div", { class: ctx.compact ? "col" : "grid", style: ctx.compact ? {} : { gridTemplateColumns: "minmax(420px, 0.9fr) minmax(0, 1.1fr)", alignItems: "start" } },
    frameHost,
    ctx.compact ? null : sideHost
  ));

  function buildFrame(force = false) {
    const key = `${currentData.decision.winnerId}|${currentData.screen.status}|${currentData.creative?.id}|${currentData.promo?.code}|${currentData.flights.map((flight) => flight.status).join(",")}`;
    if (!force && key === frameKey) {
      updateCountdowns();
      return;
    }
    frameKey = key;
    clear(frameHost);
    frameHost.appendChild(screenFrame(ctx, currentData, () => {
      overlayOpen = !overlayOpen;
      ui.why = overlayOpen;
      frameHost.querySelector(".passenger-why")?.remove();
      if (overlayOpen) frameHost.querySelector(".passenger-frame")?.appendChild(whyOverlay(currentData, () => {
        overlayOpen = false;
        ui.why = false;
        frameHost.querySelector(".passenger-why")?.remove();
      }));
    }, () => {
      overlayOpen = false;
      ui.why = false;
      requestAnimationFrame(() => buildFrame(true));
    }));
    if (overlayOpen) {
      frameHost.querySelector(".passenger-frame")?.appendChild(whyOverlay(currentData, () => {
        overlayOpen = false;
        ui.why = false;
        frameHost.querySelector(".passenger-why")?.remove();
      }));
    }
  }

  function buildSide() {
    if (ctx.compact) return;
    clear(sideHost);
    sideHost.appendChild(sidePanel(ctx, currentData));
  }

  buildFrame(true);
  buildSide();

  const ticker = setInterval(updateCountdowns, 1000);
  const refresh = debounce(async () => {
    const next = await loadScreen(ctx);
    if (!next) return;
    currentData = next;
    buildFrame();
    buildSide();
  }, 1400);

  function updateCountdowns() {
    const nodes = document.querySelectorAll("[data-passenger-countdown]");
    if (!nodes.length) return;
    const running = ctx.state.sim?.running !== false;
    const speed = Number(ctx.state.sim?.speed || 1);
    nodes.forEach((node) => {
      let remaining = Number(node.dataset.passengerCountdown || 0);
      const promo = currentData.promo;
      if (promo?.validUntil && ctx.state.sim?.time) {
        remaining = Math.max(0, Math.floor((new Date(promo.validUntil) - new Date(ctx.state.sim.time)) / 1000));
      }
      if (running) remaining = Math.max(0, remaining - speed);
      node.dataset.passengerCountdown = String(remaining);
      node.textContent = fmtSeconds(remaining);
      if (remaining <= 0) node.classList.add("negative");
    });
  }

  return {
    onEvent(name, payload) {
      if (name === "redemption" || name === "decisions" || name === "flight" || name === "screen") refresh();
      if (name === "sim" && currentData?.promo) updateCountdowns();
    },
    destroy() {
      clearInterval(ticker);
    },
  };
}

async function loadScreen(ctx) {
  try {
    return await api.get(`/api/passenger/screens/${ctx.ui.screenId}`);
  } catch (error) {
    toast(error.message, "bad");
    return null;
  }
}

function pageHead(ctx, screens, data) {
  const select = h("select", { class: "select", style: { width: "auto" }, onChange: (event) => {
    ctx.ui.screenId = event.target.value;
    ctx.rerender();
  } }, ...groupScreens(screens.items));
  return h("div", { class: "page-head" },
    h("div", {},
      h("div", { class: "eyebrow", text: "Passenger screen · physical display simulator" }),
      h("h1", { text: ctx.t("passenger.title") }),
      h("p", { class: "lede", text: ctx.t("passenger.lede") })
    ),
    h("div", { class: "head-actions" },
      select,
      aspectToggle(ctx, data),
      h("button", { class: "btn small", onClick: () => forceDecision(ctx) }, icon("refresh", 12), " Re-decide"),
      data.promo ? h("a", { class: "btn small primary", href: `/claim/${data.promo.code}`, target: "_blank", rel: "noreferrer" }, icon("qr", 12), " Open claim page") : null
    )
  );
}

function compactControls(ctx, screens) {
  const select = h("select", { class: "select", onChange: (event) => { ctx.ui.screenId = event.target.value; ctx.rerender(); } },
    ...groupScreens(screens.items)
  );
  return h("div", { class: "row", style: { marginBottom: "8px" } },
    select,
    h("button", { class: "btn small", onClick: () => forceDecision(ctx) }, icon("refresh", 12), " Re-plan")
  );
}

function groupScreens(items) {
  const groups = new Map();
  for (const screen of items) {
    if (!groups.has(screen.zoneId)) groups.set(screen.zoneId, []);
    groups.get(screen.zoneId).push(screen);
  }
  return [...groups.entries()].map(([zoneId, list]) =>
    h("optgroup", { label: `${zoneId} · ${list[0].zoneName}` },
      ...list.map((screen) => h("option", { value: screen.id, selected: screen.id === (window.MMOS?.state?.ui?.passenger?.screenId || "") }, `${screen.id} · ${screen.aspect} · ${screen.status}`))
    )
  );
}

function aspectToggle(ctx, data) {
  const current = window.MMOS?.state?.ui?.passenger?.aspect || data.screen.aspect;
  return h("div", { class: "screen-toggle" },
    ...["16:9", "9:16"].map((aspect) =>
      h("button", { "aria-pressed": String(current === aspect), onClick: () => {
        window.MMOS.state.ui.passenger.aspect = aspect;
        ctx.rerender();
      } }, aspect)
    )
  );
}

function screenFrame(ctx, data, onWhy, onClaim) {
  const aspect = window.MMOS?.state?.ui?.passenger?.aspect || data.screen.aspect || "16:9";
  const portrait = aspect === "9:16" || data.screen.aspect === "9:16";
  const creative = data.creative;
  const promo = data.promo;
  const flights = data.flights?.slice(0, 3) || [];
  const fids = h("div", { class: "fids-strip" },
    ...flights.map((flight) =>
      h("span", { class: "fids-flight" },
        h("strong", { text: `${flight.display}` }),
        h("span", { text: flight.destination }),
        h("span", { class: `status ${flight.delayMinutes ? "delayed" : ""}` }, flight.delayMinutes ? `+${flight.delayMinutes}m` : flight.status)
      )
    ),
    flights.length ? null : h("span", { class: "fids-flight" }, h("span", { text: "No nearby departures" })),
    h("span", { class: "fids-clock", text: `${fmtTime(ctx.state.sim?.time)} UTC` })
  );
  const stage = h("div", { class: "passenger-stage" });
  if (data.screen.status === "offline") {
    stage.appendChild(h("div", { class: "ad-page template-grid", style: { "--ad-a": "#3b4a60", "--ad-b": "#101c2f", alignItems: "center", justifyContent: "center", textAlign: "center" } },
      h("div", {},
        h("div", { class: "ad-headline", text: "Screen offline" }),
        h("div", { class: "ad-body", text: "No heartbeat. Fallback poster is active; the platform has raised an incident." })
      )
    ));
  } else if (creative) {
    stage.appendChild(adCreative(creative, {
      qrUrl: data.claimUrl,
      context: `${data.screen.zoneId} · ${fmtTime(data.decision.decidedAt)} UTC`,
      brand: data.campaign?.advertiserName || creative.advertiserName || creative.name,
    }));
  } else {
    stage.appendChild(h("div", { class: "ad-page template-paper" }, h("div", { class: "ad-headline", text: "Meridian International" }), h("div", { class: "ad-body", text: "Flight information and offers." })));
  }
  if (promo && data.screen.status !== "offline") {
    stage.appendChild(h("div", {
      style: {
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: "10px",
        marginTop: "8px", padding: "8px 10px", borderRadius: "10px",
        background: "rgba(3,10,20,.9)", border: "1px solid rgba(255,255,255,.14)", color: "#eaf3ff",
      },
    },
      h("div", {},
        h("div", { class: "tiny", style: { letterSpacing: ".12em", color: "#8ea4bf" }, text: "SCAN · CLAIM · SHARE" }),
        h("div", { class: "row", style: { gap: "8px" } },
          h("span", { class: "code", style: { color: "#c9f45b" }, text: promo.code }),
          h("span", { class: "tiny", style: { color: "#8ea4bf" }, text: promo.label })
        )
      ),
      h("div", { style: { textAlign: "right" } },
        h("div", { class: "tiny", style: { color: "#8ea4bf" }, text: "expires" }),
        h("div", { class: "countdown", dataset: { passengerCountdown: String(promo.remainingSeconds) }, text: fmtSeconds(promo.remainingSeconds) })
      )
    ));
  }
  const whyButton = h("button", { class: "btn small", style: { position: "absolute", right: "10px", top: "42px", zIndex: 4 }, onClick: onWhy }, "Why this ad?");
  const frame = h("div", { class: `passenger-frame ${portrait ? "portrait" : "landscape"}` },
    h("div", { class: "passenger-screen" }, fids, stage)
  );
  frame.appendChild(whyButton);
  return frame;
}

function whyOverlay(data, onClose) {
  const decision = data.decision;
  const profile = decision.profile;
  const passed = (decision.candidates || []).filter((candidate) => candidate.passed).slice(0, 3);
  const validation = decision.validation || {};
  return h("div", { class: "passenger-why" },
    h("div", { class: "why-panel" },
      h("div", { class: "row-between" },
        h("div", { class: "why-title", text: "Why this ad?" }),
        h("button", { class: "icon-btn", onClick: onClose }, icon("close", 14))
      ),
      h("p", { style: { fontSize: "11px", color: "#c9d7e8" }, text: decision.reason }),
      h("div", { class: "eyebrow", text: "Measured crowd profile" }),
      profileBars(profile, 6),
      h("div", { class: "row wrap" },
        h("span", { class: "evidence-chip", text: `${fmtNumber(profile.crowdSize)} pax` }),
        h("span", { class: "evidence-chip", text: `${profile.medianDwellMinutes} min dwell` }),
        h("span", { class: "evidence-chip", text: `${fmtPct(profile.internationalShare)} intl` }),
        h("span", { class: "evidence-chip", text: `${profile.delayMinutes} min delay` })
      ),
      h("div", { class: "eyebrow", style: { marginTop: "4px" }, text: "Top 3 candidates" }),
      ...passed.map((candidate, index) =>
        h("div", { class: "candidate-row" },
          h("div", {},
            h("div", { style: { fontWeight: "650" }, text: `${index + 1}. ${candidate.name}` }),
            h("div", { style: { color: "#8ea4bf", fontSize: "9px" }, text: (candidate.reasons || [])[0] })
          ),
          h("span", { class: "score", text: candidate.finalScore.toFixed(2) })
        )
      ),
      h("div", { class: "eyebrow", style: { marginTop: "4px" }, text: "Winning rule" }),
      h("p", { style: { fontSize: "10px", color: "#c9d7e8" }, text: `AI proposed ${validation.aiProposed || "—"}; ${validation.executed === "ai" ? "deterministic checks passed." : "fallback executed: " + (validation.executed || "rule_default")}` }),
      h("div", { class: "row wrap" },
        ...(decision.evidence || []).slice(0, 5).map((item) =>
          h("span", { class: "evidence-chip", text: `${item.source} · ${item.ageSeconds}s` })
        )
      ),
      h("p", { style: { fontSize: "9px", color: "#7f94ad" }, text: "No personal data is used. Targeting is aggregated by flight, zone and 5-minute window." })
    )
  );
}

function sidePanel(ctx, data) {
  const decision = data.decision;
  const profile = decision.profile;
  const winner = decision.winner || (decision.candidates || []).find((candidate) => candidate.campaignId === decision.winnerId);
  return h("div", { class: "col", style: { gap: "14px" } },
    h("div", { class: "card" },
      h("div", { class: "card-head" },
        h("div", { class: "card-title", text: "Current decision" }),
        decision.fallback ? h("span", { class: "badge amber", text: "fallback" }) : h("span", { class: "badge green", text: "validated" })
      ),
      h("div", { class: "row-between" },
        h("div", {},
          h("div", { style: { fontSize: "16px", fontWeight: "700" }, text: winner?.name || "No campaign" }),
          h("div", { class: "sub", text: `${data.campaign?.advertiserName || ""} · ${data.creative?.category || ""}` })
        ),
        h("div", { style: { textAlign: "right" } },
          h("div", { class: "mono", style: { fontSize: "20px", color: "var(--accent)" }, text: winner ? winner.finalScore.toFixed(2) : "—" }),
          h("div", { class: "tiny muted", text: "final score" })
        )
      ),
      h("div", { class: "chip-row", style: { marginTop: "10px" } },
        h("span", { class: "chip" }, h("strong", { text: `${Math.round((winner?.audienceMatch || 0) * 100)}%` }), " match"),
        h("span", { class: "chip" }, h("strong", { text: `${(winner?.boost || 1).toFixed(2)}×` }), " boost"),
        h("span", { class: "chip" }, h("strong", { text: decision.aiModel || "mock" }), " AI"),
        h("span", { class: "chip" }, h("strong", { text: `${profile.delayMinutes}m` }), " delay")
      ),
      h("div", { class: "divider" }),
      h("div", { class: "eyebrow", text: "Evidence trail" }),
      h("div", { class: "chip-row", style: { marginTop: "6px" } },
        ...(decision.evidence || []).slice(0, 6).map((item) =>
          h("span", { class: "chip", title: item.label }, `${item.source} · ${item.ageSeconds}s`)
        )
      )
    ),
    h("div", { class: "card" },
      h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Nearby flights · FIDS" }), h("span", { class: "badge grey", text: data.screen.zoneId })),
      h("div", { class: "timeline" },
        ...(data.flights || []).slice(0, 5).map((flight) =>
          h("div", { class: "timeline-item" },
            h("div", { class: "timeline-time", text: fmtTime(flight.estimated || flight.scheduled) }),
            h("div", { class: "timeline-body" },
              h("div", { class: "row-between" },
                h("span", { class: "strong", text: `${flight.display} → ${flight.destination}` }),
                h("span", { class: "mono tiny", text: `G${flight.gate}` })
              ),
              h("div", { class: "row", style: { gap: "6px", marginTop: "2px" } },
                statusBadge(flight.status === "DEL" ? "paused" : flight.status === "DEP" ? "ended" : "online"),
                flight.delayMinutes ? h("span", { class: "badge amber", text: `+${flight.delayMinutes}m` }) : null
              )
            )
          )
        )
      )
    ),
    h("div", { class: "card" },
      h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Playlist · next candidates" }), h("span", { class: "badge grey", text: `${data.playlist.length} passed` })),
      h("div", { class: "list" },
        ...data.playlist.slice(0, 4).map((item, index) =>
          h("div", { class: "list-item" },
            h("div", { class: "list-main" },
              h("div", { class: "list-title", text: `${index + 1}. ${item.name}` }),
              h("div", { class: "list-sub", text: `${Math.round(item.audienceMatch * 100)}% match · ${item.reason}` })
            ),
            h("span", { class: "mono muted", text: item.score.toFixed(2) })
          )
        )
      )
    ),
    data.promo ? h("div", { class: "card accent" },
      h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Promo code" }), h("span", { class: "badge green", text: "live" })),
      h("div", { class: "row-between" },
        h("div", { class: "claim-code", style: { fontSize: "18px" }, text: data.promo.code }),
        h("span", { class: "countdown", dataset: { passengerCountdown: String(data.promo.remainingSeconds) }, text: fmtSeconds(data.promo.remainingSeconds) })
      ),
      h("p", { class: "muted tiny", style: { marginTop: "6px" }, text: `${data.promo.label} · valid while the linked flight boards` }),
      h("div", { class: "row", style: { marginTop: "10px", gap: "6px" } },
        h("a", { class: "btn small primary", href: `/claim/${data.promo.code}`, target: "_blank", rel: "noreferrer" }, "Open claim page"),
        h("button", { class: "btn small", onClick: () => navigator.clipboard?.writeText(data.claimUrl).then(() => toast("Claim URL copied")) }, "Copy URL")
      )
    ) : null
  );
}

async function forceDecision(ctx) {
  try {
    await api.post(`/api/passenger/screens/${ctx.ui.screenId}/decide`);
    toast("Screen re-planned from live evidence");
    ctx.rerender();
  } catch (error) {
    toast(error.message, "bad");
  }
}
