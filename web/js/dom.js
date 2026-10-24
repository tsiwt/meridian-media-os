const SVG_NS = "http://www.w3.org/2000/svg";

export function h(tag, props, ...children) {
  if (props === null || props === undefined || typeof props !== "object" || Array.isArray(props) || props instanceof Node) {
    children.unshift(props);
    props = {};
  }
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class" || key === "className") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key === "style" && typeof value === "object") Object.assign(el.style, value);
    else if (key === "on" && typeof value === "object") {
      for (const [event, handler] of Object.entries(value)) el.addEventListener(event, handler);
    } else if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === "ref" && typeof value === "function") value(el);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
  append(el, children);
  return el;
}

export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    parent.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

export function svg(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "text") el.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else el.setAttribute(key, String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function qs(selector, root = document) {
  return root.querySelector(selector);
}

export function qsa(selector, root = document) {
  return [...root.querySelectorAll(selector)];
}

const icons = {
  play: "M8 5v14l11-7z",
  pause: "M6 5h4v14H6zm8 0h4v14h-4z",
  plus: "M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z",
  close: "M6.4 5L12 10.6 17.6 5 19 6.4 13.4 12 19 17.6 17.6 19 12 13.4 6.4 19 5 17.6 10.6 12 5 6.4z",
  search: "M10 4a6 6 0 104.2 10.3l4.3 4.3 1.4-1.4-4.3-4.3A6 6 0 0010 4zm0 2a4 4 0 110 8 4 4 0 010-8z",
  external: "M14 3h7v7h-2V6.4l-8.3 8.3-1.4-1.4L17.6 5H14zM5 5h6v2H7v10h10v-4h2v6H5z",
  check: "M9.5 17.5L4 12l1.4-1.4 4.1 4.1L18.6 5.6 20 7z",
  spark: "M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8z",
  bolt: "M13 2L4 14h6l-1 8 9-12h-6z",
  clock: "M12 3a9 9 0 100 18 9 9 0 000-18zm1 4h-2v6l4.2 2.5 1-1.7-3.2-1.9z",
  warning: "M12 3l9 17H3zm1 12h-2v2h2zm0-7h-2v5h2z",
  trend: "M3 17l6-6 4 4 8-9 1.5 1.3-9.4 10.5-4-4L4.4 18.5z",
  users: "M12 12a4 4 0 100-8 4 4 0 000 8zm-7 8a7 7 0 0114 0H5z",
  qr: "M3 3h8v8H3zm2 2v4h4V5zM13 3h8v8h-8zm2 2v4h4V5zM3 13h8v8H3zm2 2v4h4v-4zm8-2h3v3h-3zm5 0h3v3h-3zm-5 5h3v3h-3zm5 0h3v3h-3z",
  screen: "M3 4h18v12H3zm2 2v8h14V6zM8 18h8v2H8z",
  refresh: "M12 5a7 7 0 016.7 5h-2.1A5 5 0 007 10H9L5 6 1 10h2a9 9 0 1015.5-3.5L17 8a7 7 0 00-5-3z",
};

export function icon(name, size = 16) {
  const path = icons[name] || icons.spark;
  return svg("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "currentColor", "aria-hidden": "true" }, svg("path", { d: path }));
}

export function fmtNumber(value, digits = 0) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(Number(value) || 0);
}

export function fmtCompact(value) {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value) || 0);
}

export function fmtMoney(value, currency = "EUR") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value) || 0);
}

export function fmtPct(value, digits = 0) {
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export function fmtTime(isoString) {
  if (!isoString) return "--:--";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "--:--";
  return date.toISOString().slice(11, 16);
}

export function fmtDate(isoString) {
  if (!isoString) return "--";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toISOString().slice(0, 10);
}

export function fmtSeconds(total) {
  const seconds = Math.max(0, Math.floor(Number(total) || 0));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

export function titleCase(text) {
  return String(text || "").replace(/(^|\s|\.)([a-z])/g, (match, prefix, letter) => prefix + letter.toUpperCase());
}

export function debounce(fn, wait = 250) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function toast(message, kind = "good", timeout = 3800) {
  const root = document.getElementById("toast-root");
  const node = h("div", { class: `toast ${kind === "bad" ? "bad" : kind === "info" ? "" : "good"}`, role: "status" }, message);
  root.appendChild(node);
  setTimeout(() => {
    node.style.opacity = "0";
    node.style.transition = "opacity .2s";
    setTimeout(() => node.remove(), 220);
  }, timeout);
}

export function modal({ title, subtitle, body, actions, wide = false, onClose = null }) {
  const root = document.getElementById("modal-root");
  const backdrop = h("div", { class: "modal-backdrop", role: "dialog", "aria-modal": "true" });
  const bodyNode = h("div", {}, body);
  const actionNode = h("div", { class: "modal-actions" });
  const close = () => {
    backdrop.remove();
    document.removeEventListener("keydown", onKey);
    if (onClose) onClose();
  };
  const onKey = (event) => {
    if (event.key === "Escape") close();
  };
  for (const action of actions || []) {
    if (!action) continue;
    actionNode.appendChild(
      h("button", {
        class: `btn ${action.primary ? "primary" : ""} ${action.danger ? "danger" : ""}`,
        onClick: async () => {
          if (action.onClick) {
            const result = await action.onClick(close);
            if (result === false) return;
          }
          close();
        },
      }, action.label)
    );
  }
  const closeBtn = h("button", { class: "icon-btn", "aria-label": "Close", onClick: close }, icon("close"));
  const dialog = h(
    "div",
    { class: `modal ${wide ? "wide" : ""}` },
    h("div", { class: "modal-head" },
      h("div", {}, h("h2", { text: title }), subtitle ? h("p", { class: "muted tiny", style: { marginTop: "4px" }, text: subtitle }) : null),
      closeBtn
    ),
    bodyNode,
    actions && actions.length ? actionNode : null
  );
  backdrop.appendChild(dialog);
  backdrop.addEventListener("click", (event) => { if (event.target === backdrop) close(); });
  root.appendChild(backdrop);
  document.addEventListener("keydown", onKey);
  return { close, body: bodyNode, dialog };
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copied to clipboard");
    return true;
  } catch {
    toast("Copy failed", "bad");
    return false;
  }
}

export function confirmAction(message) {
  return new Promise((resolve) => {
    modal({
      title: "Confirm",
      body: h("p", { class: "muted", text: message }),
      actions: [
        { label: "Cancel", onClick: () => { resolve(false); } },
        { label: "Continue", primary: true, onClick: () => { resolve(true); } },
      ],
      onClose: () => resolve(false),
    });
  });
}

export function statusBadge(status) {
  const map = {
    online: ["green", "Online"],
    approved: ["green", "Approved"],
    live: ["green", "Live"],
    active: ["green", "Active"],
    resolved: ["green", "Resolved"],
    accepted: ["green", "Accepted"],
    degraded: ["amber", "Degraded"],
    pending: ["amber", "Pending"],
    investigating: ["amber", "Investigating"],
    paused: ["amber", "Paused"],
    offered: ["purple", "Offered"],
    open: ["red", "Open"],
    offline: ["red", "Offline"],
    rejected: ["red", "Rejected"],
    ended: ["grey", "Ended"],
    cancelled: ["grey", "Cancelled"],
    in_stock: ["green", "In stock"],
    out_of_stock: ["red", "Out of stock"],
  };
  const [tone, label] = map[status] || ["grey", titleCase(status || "unknown")];
  return h("span", { class: `badge ${tone}` }, label);
}