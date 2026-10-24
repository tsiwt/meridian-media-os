import { h } from "../dom.js";
import { bilingual } from "../i18n.js";

export function adCreative(creative, options = {}) {
  const colors = creative?.colors || ["#38e8c8", "#8b7bff"];
  const headline = options.headline ?? bilingual(creative, "headline");
  const body = options.body ?? bilingual(creative, "body");
  const cta = options.cta ?? bilingual(creative, "cta");
  const brand = options.brand ?? creative?.advertiserName ?? creative?.name ?? "Meridian";
  const template = creative?.template || "aurora";
  const page = h("div", {
    class: `ad-page template-${template}`,
    style: { "--ad-a": colors[0] || "#38e8c8", "--ad-b": colors[1] || "#8b7bff", minHeight: options.compact ? "150px" : "220px" },
  },
    h("div", { class: "ad-brandline" },
      h("span", { text: brand }),
      h("span", { text: options.context || "MQI · AIRPORT MEDIA" })
    ),
    h("div", {},
      h("div", { class: "ad-headline", text: headline || "A little more journey" }),
      body ? h("div", { class: "ad-body", text: body }) : null,
      h("div", { class: "ad-foot" },
        h("span", { class: "ad-cta", text: cta || "Discover" }),
        options.qrUrl
          ? h("span", { class: "ad-qr" }, h("img", { src: `/api/qr.svg?data=${encodeURIComponent(options.qrUrl)}`, alt: "Promo QR" }))
          : (options.showMark ? h("span", { style: { fontFamily: "var(--mono)", fontSize: "9px", opacity: 0.8 }, text: "MERIDIAN · POC" }) : null)
      )
    )
  );
  if (options.onClick) {
    page.style.cursor = "pointer";
    page.addEventListener("click", options.onClick);
  }
  return page;
}

export function creativeTile(creative, options = {}) {
  return h("div", { class: "card", style: { padding: "10px", overflow: "hidden" } },
    adCreative(creative, { ...options, compact: true, context: options.context || "PREVIEW · 16:9" }),
    h("div", { class: "row-between", style: { marginTop: "9px" } },
      h("div", {},
        h("div", { style: { fontSize: "12px", fontWeight: "650" }, text: creative.name }),
        h("div", { class: "sub", text: `${creative.category} · ${creative.template}` })
      ),
      h("span", { class: `badge ${creative.status === "approved" ? "green" : creative.status === "pending" ? "amber" : "red"}`, text: creative.status })
    ),
    options.actions ? h("div", { class: "row", style: { marginTop: "8px", gap: "5px" } }, ...options.actions) : null
  );
}