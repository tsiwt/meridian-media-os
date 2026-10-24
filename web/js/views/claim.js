import { api } from "../api.js";
import { clear, fmtSeconds, fmtTime, h, icon, toast } from "../dom.js";
import { adCreative } from "../components/creative.js";



export async function mount(ctx) {
  const { root, code } = ctx;
  root.classList.add("claim-view");
  document.body.classList.add("claim-mode");
  let payload;
  try {
    payload = await api.get(`/api/claim/${encodeURIComponent(code)}`);
  } catch (error) {
    root.appendChild(notFound(error.message));
    return {};
  }
  let promo = payload.promo;
  let claimed = null;
  let familyPromo = null;
  let simTime = payload.now || new Date().toISOString();
  let speed = payload.speed || 1;
  let remaining = promo.remainingSeconds;
  let scanning = false;

  const card = h("div", { class: "claim-card" });
  root.appendChild(h("div", { class: "claim-body" }, card));

  function render() {
    clear(card);
    const creative = {
      headlineEn: promo.headline_en,
      headlineZh: promo.headline_zh,
      bodyEn: promo.body_en,
      bodyZh: promo.body_zh,
      ctaEn: promo.cta_en,
      ctaZh: promo.cta_zh,
      template: promo.template,
      colors: promo.colors || ["#38e8c8", "#8b7bff"],
      name: promo.campaign_name,
    };
    card.appendChild(h("div", { class: "claim-top", style: { "--ad-a": (promo.colors || ["#38e8c8"])[0], "--ad-b": (promo.colors || ["#38e8c8", "#8b7bff"])[1] } },
      h("div", { class: "tiny", style: { letterSpacing: ".16em", textTransform: "uppercase" }, text: "MERIDIAN MEDIA OS · CLAIM" }),
      h("h1", { text: promo.headline_en || promo.campaign_name }),
      h("p", { style: { fontSize: "12px", opacity: 0.9 }, text: promo.body_en || "Show this code at the counter." })
    ));
    const inner = h("div", { class: "claim-body-inner" });
    if (familyPromo) {
      inner.appendChild(h("div", { class: "claim-meta" },
        metaBox("Your code", familyPromo.code),
        metaBox("Shared with family", "Ready")
      ));
    }
    inner.appendChild(h("div", { class: "eyebrow", text: claimed ? "Family code ready" : "Your promo code" }));
    inner.appendChild(h("div", { class: "claim-code", text: claimed ? claimed.code : promo.code, style: { letterSpacing: ".08em", fontSize: claimed ? "22px" : "24px" } }));
    inner.appendChild(h("div", { class: "claim-meta" },
      metaBox("Offer", promo.value || "—"),
      metaBox("Advertiser", promo.advertiser_name || ""),
      metaBox("Linked flight", payload.flight ? `${payload.flight.display} → ${payload.flight.destination}` : (promo.flight_id || "MQI")),
      metaBox("Expires", promo.validUntil ? fmtTime(promo.validUntil) + " UTC" : "boarding close")
    ));
    if (claimed) {
      inner.appendChild(h("div", { class: "claim-ok" },
        h("div", { class: "tick", text: "✓" }),
        h("div", { style: { fontSize: "16px", fontWeight: "700" }, text: "Offer claimed" }),
        h("p", { class: "muted tiny", text: "The redemption is already visible in the Retailer dashboard." })
      ));
      if (!familyPromo) {
        inner.appendChild(h("button", { class: "btn primary", onClick: shareFamily }, icon("users", 14), " Share a code with family"));
      }
    } else {
      const expired = remaining <= 0 || !promo.live;
      inner.appendChild(h("button", {
        class: "btn primary", disabled: expired || scanning,
        onClick: claimOffer,
        style: { minHeight: "46px", fontSize: "14px" },
      }, expired ? "This offer has expired" : "Claim this offer"));
      inner.appendChild(h("div", { class: "row-between", style: { marginTop: "2px" } },
        h("span", { class: "tiny muted", text: "Countdown follows the airport simulation clock" }),
        h("span", { class: "countdown", "data-claim-countdown": String(remaining), text: fmtSeconds(remaining) })
      ));
    }
    if (promo.parent_code) {
      inner.appendChild(h("p", { class: "hint", text: `Family code of ${promo.parent_code}.` }));
    }
    inner.appendChild(h("p", { class: "hint", text: "One code per traveller. Aggregated by flight and zone; no identity or device tracking." }));
    inner.appendChild(h("a", { class: "btn ghost small", href: "/" }, "Back to the platform"));
    card.appendChild(inner);
    const footer = h("div", { class: "card", style: { margin: "0 22px 22px", background: "rgba(255,255,255,.03)" } },
      adCreative(creative, { compact: true, context: "OFFER PREVIEW" })
    );
    card.appendChild(footer);
  }

  function metaBox(label, value) {
    return h("div", {}, h("span", { text: label }), h("strong", { text: value || "—" }));
  }

  async function claimOffer(event) {
    const button = event.target;
    scanning = true;
    button.disabled = true;
    try {
      claimed = await api.post(`/api/claim/${encodeURIComponent(code)}`, { channel: "mobile-qr" });
      toast("Offer claimed");
      render();
    } catch (error) {
      scanning = false;
      toast(error.message, "bad");
      render();
    }
  }

  async function shareFamily() {
    try {
      const result = await api.post(`/api/claim/${encodeURIComponent(code)}/share`);
      familyPromo = result.promo;
      toast(`Family code ready: ${familyPromo.code}`);
      render();
    } catch (error) {
      toast(error.message, "bad");
    }
  }

  try {
    await api.post(`/api/claim/${encodeURIComponent(code)}/scan`);
  } catch {
    // scanning is best-effort; claim is the authoritative redemption
  }
  render();

  const timer = setInterval(async () => {
    if (!claimed) {
      if (promo.validUntil) {
        remaining = Math.max(0, Math.floor((new Date(promo.validUntil) - new Date(simTime)) / 1000));
      }
      if (document.body.dataset.simRunning !== "false") simTime = new Date(new Date(simTime).getTime() + speed * 1000).toISOString();
      const node = card.querySelector("[data-claim-countdown]");
      if (node) {
        node.textContent = fmtSeconds(remaining);
        node.dataset.claimCountdown = String(remaining);
      }
    }
  }, 1000);

  const syncTimer = setInterval(async () => {
    try {
      const sim = await api.get("/api/sim");
      simTime = sim.time;
      speed = sim.speed;
      if (!claimed) {
        remaining = promo.validUntil ? Math.max(0, Math.floor((new Date(promo.validUntil) - new Date(simTime)) / 1000)) : remaining;
        render();
      }
    } catch {
      // keep local countdown
    }
  }, 6000);

  document.body.dataset.simRunning = String(payload.running !== false);
  return {
    destroy() {
      clearInterval(timer);
      clearInterval(syncTimer);
    },
  };
}

function notFound(message) {
  return h("div", { class: "claim-body" },
    h("div", { class: "claim-card" },
      h("div", { class: "claim-body-inner" },
        h("h1", { style: { fontSize: "22px" }, text: "Offer not found" }),
        h("p", { class: "muted", text: message || "This claim link is invalid or has expired." }),
        h("a", { class: "btn primary", href: "/" }, "Back to the platform")
      )
    )
  );
}