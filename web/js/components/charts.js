import { h, svg, fmtNumber, fmtCompact } from "../dom.js";

let gradientId = 0;

export function lineChart({ values = [], labels = [], height = 150, color = "var(--accent)", secondary = null, secondaryValues = [], format = fmtCompact }) {
  const width = 640;
  const pad = { left: 36, right: 10, top: 12, bottom: 20 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const all = [...values, ...secondaryValues];
  const max = Math.max(1, ...all);
  const min = 0;
  const step = values.length > 1 ? innerW / (values.length - 1) : innerW;
  const point = (value, index) => {
    const x = pad.left + step * index;
    const y = pad.top + innerH - ((value - min) / (max - min || 1)) * innerH;
    return [x, y];
  };
  const id = `grad-${++gradientId}`;
  const pathFor = (series) => series.map((value, index) => {
    const [x, y] = point(value, index);
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const line = pathFor(values);
  const area = `${line} L${pad.left + step * (values.length - 1)},${pad.top + innerH} L${pad.left},${pad.top + innerH} Z`;
  const gridLines = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const y = pad.top + innerH * ratio;
    return svg("g", {},
      svg("line", { class: "grid-line", x1: pad.left, x2: width - pad.right, y1: y, y2: y }),
      svg("text", { class: "axis", x: 0, y: y + 3 }, format(Math.round(max - (max - min) * ratio)))
    );
  });
  return svg(
    "svg",
    { class: "chart", viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "trend chart" },
    svg("defs", {},
      svg("linearGradient", { id, x1: "0", y1: "0", x2: "0", y2: "1" },
        svg("stop", { offset: "0%", "stop-color": color, "stop-opacity": "0.32" }),
        svg("stop", { offset: "100%", "stop-color": color, "stop-opacity": "0" })
      )
    ),
    ...gridLines,
    svg("path", { d: area, fill: `url(#${id})` }),
    svg("path", { class: "line", d: line, style: { stroke: color } }),
    secondary && secondaryValues.length
      ? svg("path", { class: "line secondary", d: pathFor(secondaryValues) })
      : null,
    ...values.map((value, index) => {
      if (values.length > 14 && index % 2) return null;
      const [x, y] = point(value, index);
      return svg("g", {},
        svg("circle", { class: "dot", cx: x, cy: y, r: 3, style: { fill: color } }),
        svg("title", {}, `${labels[index] || index}: ${format(value)}`)
      );
    }),
    ...(labels.length ? [
      svg("text", { class: "axis", x: pad.left, y: height - 4 }, labels[0]),
      svg("text", { class: "axis", x: width - pad.right, y: height - 4, "text-anchor": "end" }, labels[labels.length - 1]),
    ] : [])
  );
}

export function barChart({ values = [], labels = [], height = 150, color = "var(--accent)", format = fmtCompact }) {
  const width = 640;
  const pad = { left: 36, right: 8, top: 10, bottom: 22 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const max = Math.max(1, ...values);
  const slot = innerW / Math.max(1, values.length);
  const barW = Math.max(3, slot * 0.58);
  return svg("svg", { class: "chart", viewBox: `0 0 ${width} ${height}` },
    ...[0, 0.5, 1].map((ratio) => {
      const y = pad.top + innerH * ratio;
      return svg("g", {},
        svg("line", { class: "grid-line", x1: pad.left, x2: width - pad.right, y1: y, y2: y }),
        svg("text", { class: "axis", x: 0, y: y + 3 }, format(Math.round(max * (1 - ratio))))
      );
    }),
    ...values.map((value, index) => {
      const barH = max ? (value / max) * innerH : 0;
      const x = pad.left + slot * index + (slot - barW) / 2;
      const y = pad.top + innerH - barH;
      return svg("g", {},
        svg("rect", { class: "bar", x, y, width: barW, height: Math.max(1, barH), rx: 2, style: { fill: color, opacity: 0.82 } }),
        svg("title", {}, `${labels[index] || index}: ${format(value)}`)
      );
    }),
    ...labels.map((label, index) => {
      if (labels.length > 12 && index % 2) return null;
      return svg("text", { class: "axis", x: pad.left + slot * index + slot / 2, y: height - 4, "text-anchor": "middle" }, label);
    })
  );
}

export function terminalMap({ zones, screens, presence, onScreenClick, onZoneClick }) {
  const width = 1200;
  const height = 560;
  const zoneById = new Map(zones.map((zone) => [zone.id, zone]));
  const byZone = new Map();
  for (const screen of screens) {
    if (!byZone.has(screen.zone_id)) byZone.set(screen.zone_id, []);
    byZone.get(screen.zone_id).push(screen);
  }
  const maxCrowd = Math.max(1, ...Object.values(presence || {}).map((value) => value.crowd || 0));
  const terminals = [
    { id: "T1", label: "TERMINAL 1 · DOMESTIC", x: 44, y: 58, w: 508, h: 440 },
    { id: "T2", label: "TERMINAL 2 · INTERNATIONAL", x: 604, y: 58, w: 548, h: 440 },
  ];
  const nodes = [];
  for (const terminal of terminals) {
    nodes.push(svg("rect", { x: terminal.x, y: terminal.y, width: terminal.w, height: terminal.h, rx: 18, fill: "color-mix(in srgb, var(--panel) 70%, transparent)", stroke: "var(--line-strong)" }));
    nodes.push(svg("text", { class: "map-terminal-label", x: terminal.x + 16, y: terminal.y + 24 }, terminal.label));
  }
  for (const zone of zones) {
    const crowd = presence?.[zone.id]?.crowd || 0;
    const intensity = Math.min(1, crowd / maxCrowd);
    const heat = svg("circle", {
      cx: zone.x + zone.w / 2,
      cy: zone.y + zone.h / 2,
      r: Math.max(12, Math.sqrt(crowd + 1) * 2.2),
      fill: "var(--accent)",
      opacity: (0.05 + intensity * 0.22).toFixed(3),
      filter: "blur(9px)",
    });
    nodes.push(heat);
    nodes.push(svg("rect", {
      class: `map-zone ${zone.kind}`,
      x: zone.x, y: zone.y, width: zone.w, height: zone.h, rx: 8,
      onClick: onZoneClick ? () => onZoneClick(zone) : null,
      style: onZoneClick ? { cursor: "pointer" } : {},
    }, svg("title", {}, `${zone.name} · ${fmtNumber(crowd)} pax`)));
    nodes.push(svg("text", { class: "map-label", x: zone.x + 7, y: zone.y + 15 }, zone.id));
    nodes.push(svg("text", { class: "map-label", x: zone.x + 7, y: zone.y + 27, style: { opacity: 0.65 } }, `${fmtCompact(crowd)} pax`));
    const list = byZone.get(zone.id) || [];
    const cols = Math.max(1, Math.ceil(Math.sqrt(list.length)));
    list.forEach((screen, index) => {
      const col = index % cols;
      const row = Math.floor(index / cols);
      const cellW = (zone.w - 20) / cols;
      const cellH = Math.max(12, (zone.h - 38) / Math.max(1, Math.ceil(list.length / cols)));
      const cx = zone.x + 10 + cellW * (col + 0.5);
      const cy = zone.y + 36 + cellH * (row + 0.5);
      const color = screen.status === "offline" ? "#ff647c" : screen.status === "degraded" ? "#ffb454" : "#38e8c8";
      nodes.push(svg("circle", {
        class: "map-screen",
        cx, cy, r: screen.status === "offline" ? 4.5 : 3.4,
        fill: color,
        opacity: screen.status === "offline" ? 0.95 : 0.85,
        onClick: onScreenClick ? (event) => { event.stopPropagation(); onScreenClick(screen); } : null,
      }, svg("title", {}, `${screen.id} · ${screen.name} · ${screen.status}`)));
    });
  }
  nodes.push(svg("text", { x: 44, y: 530, class: "map-label" }, "Heat = measured passenger presence · dot colour = screen health · click a dot for the decision"));
  return svg("svg", { class: "terminal-map", viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Live terminal map" }, ...nodes);
}

export function profileBars(profile, limit = 7) {
  const preferred = [
    ["Holiday", "holiday"], ["Family", "family"], ["Business", "business"], ["International", "international"],
    ["Luxury", "luxury"], ["Young", "young"], ["Senior", "senior"], ["Shopper", "shopper"],
  ];
  const shares = profile?.shares || {};
  const rows = preferred
    .map(([label, key]) => ({ label, value: shares[key] || 0 }))
    .filter((row) => row.value > 0.02)
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
  return h("div", { class: "profile-bars" },
    ...rows.map((row) => h("div", { class: "profile-bar" },
      h("span", { text: row.label }),
      h("span", { class: "track" }, h("i", { style: { width: `${Math.round(row.value * 100)}%` } })),
      h("span", { class: "mono", text: `${Math.round(row.value * 100)}%` })
    ))
  );
}

export function heatGrid({ rows, columns, values, format = (v) => fmtNumber(v), onCell }) {
  const flat = values.flat();
  const max = Math.max(1, ...flat);
  return h("div", { class: "scroll-x" },
    h("div", {
      style: {
        display: "grid",
        gridTemplateColumns: `92px repeat(${columns.length}, minmax(30px, 1fr))`,
        gap: "3px",
        minWidth: `${92 + columns.length * 34}px`,
      },
    },
      h("div", {}),
      ...columns.map((column) => h("div", { class: "tiny muted", style: { textAlign: "center" } }, column)),
      ...rows.flatMap((row, rowIndex) => [
        h("div", { class: "tiny", style: { display: "flex", alignItems: "center", color: "var(--muted)" }, text: row.label }),
        ...columns.map((column, columnIndex) => {
          const value = values[rowIndex][columnIndex];
          const ratio = value / max;
          return h("div", {
            class: "heat-cell",
            title: `${row.label} ${column}: ${format(value)}`,
            style: {
              background: `color-mix(in srgb, var(--accent) ${Math.round(8 + ratio * 82)}%, var(--panel-3))`,
              cursor: onCell ? "pointer" : "default",
            },
            onClick: onCell ? () => onCell(row, column, value) : null,
          });
        }),
      ])
    )
  );
}