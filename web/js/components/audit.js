import { h, fmtNumber, fmtTime, statusBadge } from "../dom.js";
import { profileBars } from "./charts.js";

export function decisionModal(decision, ctx) {
  const profile = decision.profile || {};
  const candidates = decision.candidates || [];
  const validation = decision.validation || {};
  const evidence = decision.evidence || [];
  const body = h("div", { class: "col", style: { gap: "16px" } },
    h("div", { class: "row wrap" },
      h("span", { class: "badge teal", text: decision.screenId }),
      h("span", { class: "badge grey", text: `${fmtTime(decision.decidedAt)} UTC` }),
      decision.fallback ? h("span", { class: "badge amber", text: "Rule fallback" }) : h("span", { class: "badge green", text: "AI validated" }),
      h("span", { class: "badge purple", text: decision.aiModel || "mock" })
    ),
    h("div", { class: "card", style: { background: "var(--panel-2)" } },
      h("div", { class: "eyebrow", text: "Winning reason" }),
      h("p", { style: { marginTop: "6px", fontSize: "13px" }, text: decision.reason })
    ),
    h("div", { class: "grid grid-2", style: { gap: "14px" } },
      h("div", {},
        h("div", { class: "eyebrow", style: { marginBottom: "8px" }, text: "Crowd profile" }),
        profileBars(profile, 8),
        h("div", { class: "row wrap", style: { marginTop: "10px" } },
          h("span", { class: "chip" }, h("strong", { text: fmtNumber(profile.crowdSize) }), " pax"),
          h("span", { class: "chip" }, h("strong", { text: `${profile.medianDwellMinutes}m` }), " dwell"),
          h("span", { class: "chip" }, h("strong", { text: `${profile.delayMinutes}m` }), " delay")
        )
      ),
      h("div", {},
        h("div", { class: "eyebrow", style: { marginBottom: "8px" }, text: "Deterministic checks" }),
        h("div", { class: "col", style: { gap: "6px" } },
          ...(validation.checks || []).map((check) =>
            h("div", { class: "row-between", style: { fontSize: "11px" } },
              h("span", { class: "row", style: { gap: "6px" } },
                h("span", { class: check.ok ? "positive" : "negative", text: check.ok ? "✓" : "✕" }),
                h("span", { text: check.check })
              ),
              h("span", { class: "muted tiny", text: typeof check.detail === "string" ? check.detail : check.ok ? "passed" : "failed" })
            )
          )
        ),
        h("div", { class: "divider" }),
        h("div", { class: "eyebrow", style: { marginBottom: "8px" }, text: "Evidence" }),
        h("div", { class: "col", style: { gap: "6px", maxHeight: "180px", overflow: "auto" } },
          ...evidence.map((item) =>
            h("div", { class: "row-between", style: { fontSize: "10px" } },
              h("span", { class: "row", style: { gap: "6px", minWidth: 0 } },
                h("span", { class: "badge grey", text: item.source }),
                h("span", { class: "muted", style: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }, text: item.label })
              ),
              h("span", { class: "mono muted", text: `${item.ageSeconds}s` })
            )
          )
        )
      )
    ),
    h("div", {},
      h("div", { class: "eyebrow", style: { marginBottom: "8px" }, text: `Candidates (${candidates.length})` }),
      h("div", { class: "table-wrap" },
        h("table", { class: "data" },
          h("thead", {}, h("tr", {},
            h("th", { text: "Campaign" }), h("th", { text: "Status" }), h("th", { class: "num", text: "Match" }),
            h("th", { class: "num", text: "Boost" }), h("th", { class: "num", text: "Score" }), h("th", { text: "Why" })
          )),
          h("tbody", {}, ...candidates.slice(0, 15).map((candidate) =>
            h("tr", {},
              h("td", {}, h("div", { class: "strong", text: candidate.name }), h("div", { class: "sub", text: candidate.advertiser })),
              h("td", {}, candidate.passed ? h("span", { class: "badge green", text: "passed" }) : h("span", { class: "badge red", text: candidate.rejectedBy || "filtered" })),
              h("td", { class: "num", text: `${Math.round((candidate.audienceMatch || 0) * 100)}%` }),
              h("td", { class: "num", text: `${(candidate.boost || 1).toFixed(2)}×` }),
              h("td", { class: "num strong", text: (candidate.finalScore || 0).toFixed(3) }),
              h("td", { class: "sub", text: (candidate.reasons || []).slice(0, 2).join(" · ") })
            )
          ))
        )
      )
    )
  );
  ctx.modal({
    title: "Decision audit",
    subtitle: `${decision.screenId} · ${decision.zoneId} · ${fmtTime(decision.decidedAt)} UTC`,
    body,
    wide: true,
    actions: [{ label: "Close", primary: true }],
  });
}