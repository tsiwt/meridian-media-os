import { api, qs } from "./api.js";
import { clear, debounce, fmtTime, h, icon, modal, toast } from "./dom.js";
import { getLanguage, setLanguage, t } from "./i18n.js";
import { mount as mountAdmin } from "./views/admin.js";
import { mount as mountRetailer } from "./views/retailer.js";
import { mount as mountMedia } from "./views/media.js";
import { mount as mountAirline } from "./views/airline.js";
import { mount as mountPassenger } from "./views/passenger.js";
import { mount as mountClaim } from "./views/claim.js";

const VIEWS = {
  admin: { label: "Platform Admin", theme: "dark", mount: mountAdmin, icon: "screen" },
  retailer: { label: "Retailer", theme: "light", mount: mountRetailer, icon: "users" },
  media: { label: "Media Manager", theme: "light", mount: mountMedia, icon: "trend" },
  airline: { label: "Airline Representative", theme: "light", mount: mountAirline, icon: "bolt" },
  passenger: { label: "Passenger Screen", theme: "dark", mount: mountPassenger, icon: "qr" },
};

const ROLES = Object.keys(VIEWS);

const state = {
  config: null,
  role: "admin",
  splitRole: "retailer",
  split: false,
  lang: localStorage.getItem("mmos.lang") || "en",
  sim: null,
  simSync: null,
  zonePresence: {},
  ui: {
    admin: { tab: "overview", entity: "vendors", logQuery: "", logFallback: "" },
    retailer: { tab: "overview", advertiserId: "ADV-01", outletId: "" },
    media: { tab: "inventory", screenId: "", date: "" },
    airline: { tab: "overview", airline: "ZO" },
    passenger: { screenId: "SCR-122", why: false },
  },
};

let mounted = [];
let renderToken = 0;
let clockTimer = null;
let eventSource = null;


const dom = {};

function roleFromLocation() {
  const hash = location.hash.replace(/^#\/?/, "").split("?")[0];
  if (ROLES.includes(hash)) return hash;
  return "admin";
}

function claimCodeFromLocation() {
  const match = location.pathname.match(/^\/claim\/([^/]+)/);
  if (match) return decodeURIComponent(match[1]);
  const hash = location.hash.match(/^#\/claim\/([^/]+)/);
  return hash ? decodeURIComponent(hash[1]) : null;
}

function isClaimPage() {
  return Boolean(claimCodeFromLocation());
}

function currentSim() {
  return state.sim || state.config?.sim || { time: new Date().toISOString(), speed: 1, running: false };
}

function syncSim(sim) {
  if (!sim) return;
  state.sim = { ...state.sim, ...sim };
  state.simSync = { time: new Date(state.sim.time).getTime(), at: performance.now(), running: state.sim.running, speed: state.sim.speed };
  document.body.dataset.speed = String(state.sim.speed || 1);
  document.body.dataset.simRunning = String(Boolean(state.sim.running));
  updateClock();
  updateSimControls();
}

function displayTime() {
  const base = currentSim();
  if (!state.simSync) return base.time;
  const elapsed = state.simSync.running ? (performance.now() - state.simSync.at) * state.simSync.speed : 0;
  return new Date(state.simSync.time + elapsed).toISOString();
}

function updateClock() {
  if (!dom.clock) return;
  const iso = displayTime();
  dom.clock.textContent = `${fmtTime(iso)}:${iso.slice(17, 19)}`;
  if (dom.date) dom.date.textContent = `${iso.slice(0, 10)} UTC`;
}

function updateSimControls() {
  if (!dom.simRoot) return;
  const sim = currentSim();
  dom.playBtn.querySelector("span").textContent = sim.running ? t("sim.pause") : t("sim.play");
  dom.playBtn.querySelector("svg").replaceWith(icon(sim.running ? "pause" : "play", 14));
  dom.speedButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(Number(button.dataset.speed) === Number(sim.speed)));
  });
  dom.staleButton.classList.toggle("active", Boolean(sim.feedStale));
}

async function boot() {
  try {
    const config = await api.get("/api/config");
    state.config = config;
    state.sim = config.sim;
    state.ui.retailer.outletId = "";
    setLanguage(state.lang);
    const code = claimCodeFromLocation();
    if (code) {
      document.getElementById("boot").hidden = true;
      document.body.dataset.theme = "dark";
      mountClaimStandalone(code);
      return;
    }
    buildTopbar();
    buildSimbar();
    document.getElementById("boot").hidden = true;
    document.getElementById("topbar").hidden = false;
    document.getElementById("simbanner").hidden = false;
    document.getElementById("view").hidden = false;
    state.role = roleFromLocation();
    applyRoleTheme();
    connectStream();
    await render();
    startClock();
    window.addEventListener("hashchange", async () => {
      const role = roleFromLocation();
      if (role !== state.role) {
        state.role = role;
        if (role === "passenger") state.split = false;
        applyRoleTheme();
        updateNav();
        await render();
      }
    });
  } catch (error) {
    document.getElementById("boot").innerHTML = "";
    document.getElementById("boot").appendChild(
      h("div", { class: "card", style: { maxWidth: "460px" } },
        h("h1", { style: { fontSize: "18px" }, text: "Cannot reach the platform" }),
        h("p", { class: "muted", style: { marginTop: "8px" }, text: error.message }),
        h("button", { class: "btn primary", style: { marginTop: "14px" }, onClick: () => location.reload() }, "Retry")
      )
    );
  }
}

function applyRoleTheme() {
  document.body.dataset.theme = state.split ? "dark" : VIEWS[state.role]?.theme || "dark";
}

function buildTopbar() {
  const bar = document.getElementById("topbar");
  clear(bar);
  dom.brand = h("a", { class: "brand", href: "#/admin", style: { color: "inherit" } },
    h("div", { class: "brand-mark", text: "M" }),
    h("div", {},
      h("div", { class: "brand-name", text: state.config.theme.productName }),
      h("div", { class: "brand-sub", text: `${state.config.theme.airportCode} · ${state.config.theme.challenge}` })
    )
  );
  dom.roleSwitch = h("nav", { class: "role-switch", "aria-label": "Role switcher" });
  dom.splitButton = h("button", { class: "btn ghost small desktop-only", title: "Passenger screen + role dashboard", onClick: toggleSplit },
    icon("screen", 13), h("span", { text: t("nav.demo") })
  );
  dom.langButton = h("button", { class: "lang-btn", onClick: toggleLanguage }, state.lang === "en" ? "中文" : "EN");
  dom.livePill = h("span", { class: "live-pill" }, h("i", { class: "live-dot" }), h("span", { text: "SSE live" }));
  dom.topActions = h("div", { class: "top-actions" }, dom.splitButton, dom.langButton, dom.livePill);
  bar.append(dom.brand, dom.roleSwitch, dom.topActions);
  updateNav();
}

function updateNav() {
  if (!dom.roleSwitch) return;
  clear(dom.roleSwitch);
  for (const role of ROLES) {
    const active = state.split ? (role === state.splitRole && state.role !== "passenger") : role === state.role;
    dom.roleSwitch.appendChild(
      h("button", {
        class: "role-tab",
        "aria-selected": String(active),
        onClick: () => selectRole(role),
      }, t(`nav.${role}`))
    );
  }
  if (dom.splitButton) {
    dom.splitButton.classList.toggle("primary", state.split);
    dom.splitButton.querySelector("span").textContent = state.split ? "Exit split" : t("nav.demo");
  }
}

function selectRole(role) {
  if (role === "passenger") {
    state.split = false;
    state.role = "passenger";
    location.hash = "#/passenger";
  } else if (state.split) {
    state.splitRole = role;
    state.role = role;
    location.hash = `#/${role}`;
  } else {
    state.role = role;
    location.hash = `#/${role}`;
  }
  applyRoleTheme();
  updateNav();
  render();
}

function toggleSplit() {
  state.split = !state.split;
  if (state.split) {
    if (state.role === "passenger") state.role = "retailer";
    state.splitRole = state.role;
  }
  applyRoleTheme();
  updateNav();
  render();
}

function toggleLanguage() {
  state.lang = state.lang === "en" ? (state.config?.theme.secondLanguage || "zh") : "en";
  localStorage.setItem("mmos.lang", state.lang);
  setLanguage(state.lang);
  dom.langButton.textContent = state.lang === "en" ? "中文" : "EN";
  render();
}

function buildSimbar() {
  const bar = document.getElementById("simbanner");
  clear(bar);
  dom.clock = h("span", { class: "sim-clock", text: "--:--:--" });
  dom.date = h("span", { class: "tiny muted", text: "" });
  dom.playBtn = h("button", { class: "sim-btn", onClick: controlPlay }, icon("pause", 13), h("span", { text: t("sim.pause") }));
  const speeds = h("div", { class: "sim-group" });
  dom.speedButtons = [];
  for (const speed of [1, 10, 60]) {
    const button = h("button", { class: "sim-btn", dataset: { speed }, "aria-pressed": "false", onClick: () => controlSpeed(speed) }, `${speed}×`);
    dom.speedButtons.push(button);
    speeds.appendChild(button);
  }
  const jump = h("form", { class: "row", style: { gap: "5px" }, onSubmit: jumpTo },
    h("input", { class: "sim-time-input", type: "time", value: fmtTime(displayTime()), title: "Jump to UTC time", name: "time" }),
    h("button", { class: "sim-btn", type: "submit", title: t("sim.jump") }, t("sim.jump"))
  );
  dom.injectButton = h("button", { class: "sim-btn", onClick: openInject }, icon("bolt", 12), h("span", { text: t("sim.inject") }));
  dom.staleButton = h("button", { class: "sim-btn", title: "Simulate a stale AODB feed", onClick: toggleStale }, "Stale feed");
  dom.simRoot = h("div", { class: "sim-inject" },
    h("span", { class: "sim-tag", text: t("sim.live") }),
    dom.clock,
    dom.date,
    h("div", { class: "sim-group" }, dom.playBtn),
    speeds,
    jump,
    dom.injectButton,
    dom.staleButton
  );
  bar.appendChild(dom.simRoot);
  syncSim(state.sim || state.config.sim);
}

async function control(action, value) {
  try {
    const result = await api.post("/api/sim/control", { action, value });
    if (result.state) syncSim(result.state);
    return result;
  } catch (error) {
    toast(error.message, "bad");
    return null;
  }
}

function controlPlay() {
  control(currentSim().running ? "pause" : "play");
}

function controlSpeed(speed) {
  control("speed", speed);
}

function jumpTo(event) {
  event.preventDefault();
  const time = new FormData(event.target).get("time");
  if (!time) return;
  const date = displayTime().slice(0, 10);
  control("jump", `${date}T${time}:00Z`);
}

async function toggleStale() {
  const active = Boolean(currentSim().feedStale);
  await control("stale-feed", !active);
  toast(active ? "Feed restored" : "AODB feed marked stale — AI decisions will fall back", active ? "good" : "bad");
}

async function openInject() {
  const kind = await new Promise((resolve) => {
    modal({
      title: "Inject a live event",
      subtitle: "The event enters as an AIDX-shaped message, is parsed by the adapter, then re-plans affected screens.",
      body: h("div", { class: "grid grid-2" },
        injectOption("Delay a flight", "Updates AIDX, gate presence, retailer delay rules and goodwill.", "delay", resolve),
        injectOption("Change a gate", "Moves the flight and re-plans both gate areas.", "gate", resolve),
        injectOption("Take a screen offline", "Raises an incident after 5 simulated minutes.", "offline", resolve),
        injectOption("Restore a screen", "Resolves the offline incident.", "online", resolve)
      ),
      actions: [{ label: "Cancel", onClick: () => resolve(null) }],
    });
  });
  if (!kind) return;
  if (kind === "offline" || kind === "online") {
    const screens = await api.get("/api/passenger/screens");
    const screenId = await pickFromList(kind === "offline" ? "Take screen offline" : "Restore screen", screens.items.map((screen) => ({
      value: screen.id,
      label: `${screen.id} · ${screen.zoneName} · ${screen.status}`,
    })));
    if (screenId) {
      const result = await control("inject", { kind: "screen_offline", screenId });
      if (kind === "online" && screenId) await control("inject", { kind: "screen_online", screenId });
      if (result) toast(`Screen ${screenId} ${kind === "offline" ? "offline" : "restored"}`, kind === "offline" ? "bad" : "good");
    }
    return;
  }
  const flights = await api.get("/api/flights");
  const flightOptions = flights.items.slice(0, 80).map((flight) => ({
    value: flight.flight_id,
    label: `${flight.display} → ${flight.destination} · Gate ${flight.gate} · ${flight.status}${flight.delayMinutes ? ` +${flight.delayMinutes}m` : ""}`,
  }));
  if (kind === "delay") {
    const form = h("form", { class: "form-grid", id: "inject-form" },
      h("div", { class: "field full" }, h("label", { text: "Flight" }), selectInput("flightId", flightOptions)),
      h("div", { class: "field" }, h("label", { text: "Delay minutes" }), h("input", { class: "input", type: "number", name: "minutes", value: "45", min: "5", max: "240" })),
      h("div", { class: "field" }, h("label", { text: "Adapter path" }), h("input", { class: "input", value: "IATA AIDX → canonical FlightEvent", readOnly: true }))
    );
    const values = await modalForm("Delay flight", form);
    if (values) {
      const result = await control("inject", { kind: "delay", flightId: values.flightId, minutes: Number(values.minutes) });
      if (result) toast(`${result.flight} delayed ${result.minutes} min · ${result.goodwill ? "goodwill auto-pushed" : "screens re-planned"}`, "bad");
    }
  } else {
    const form = h("form", { class: "form-grid", id: "inject-form" },
      h("div", { class: "field full" }, h("label", { text: "Flight" }), selectInput("flightId", flightOptions)),
      h("div", { class: "field" }, h("label", { text: "New gate" }), h("input", { class: "input", name: "gate", value: "45", maxlength: "4" }))
    );
    const values = await modalForm("Change gate", form);
    if (values) {
      const result = await control("inject", { kind: "gate_change", flightId: values.flightId, gate: values.gate });
      if (result) toast(`${result.flight} moved to Gate ${result.gate}`, "good");
    }
  }
}

function injectOption(title, text, kind, resolve) {
  return h("button", {
    class: "card", type: "button", style: { textAlign: "left" }, onClick: () => resolve(kind),
  }, h("div", { class: "card-title", text: title }), h("p", { class: "muted tiny", style: { marginTop: "5px" }, text }));
}

function selectInput(name, options, value = "") {
  return h("select", { class: "select", name }, ...options.map((option) =>
    h("option", { value: option.value, selected: option.value === value }, option.label)
  ));
}

function pickFromList(title, options) {
  return new Promise((resolve) => {
    const form = h("form", { class: "form-grid" },
      h("div", { class: "field full" }, h("label", { text: title }), selectInput("value", options))
    );
    modalForm(title, form).then((values) => resolve(values?.value || null));
  });
}

function modalForm(title, form) {
  return new Promise((resolve) => {
    const dialog = modal({
      title,
      body: form,
      actions: [
        { label: t("common.cancel"), onClick: () => { resolve(null); } },
        {
          label: "Inject event", primary: true,
          onClick: () => {
            const values = Object.fromEntries(new FormData(form).entries());
            resolve(values);
          },
        },
      ],
      onClose: () => resolve(null),
    });
  });
}

function startClock() {
  if (clockTimer) clearInterval(clockTimer);
  clockTimer = setInterval(updateClock, 500);
}

async function render() {
  const code = claimCodeFromLocation();
  if (code) {
    mountClaimStandalone(code);
    return;
  }
  const token = ++renderToken;
  destroyMounted();
  const root = document.getElementById("view");
  clear(root);
  document.body.classList.toggle("split", state.split);
  applyRoleTheme();
  updateNav();
  document.getElementById("topbar").hidden = false;
  document.getElementById("simbanner").hidden = false;

  const baseCtx = {
    state,
    config: state.config,
    sim: state.sim,
    ui: null,
    t,
    lang: state.lang,
    api,
    qs,
    rerender: debounce(() => { if (token === renderToken) render(); }, 350),
    navigate: (role) => selectRole(role),
    toast,
    modal,
  };

  if (state.split) {
    const grid = h("div", { class: "split-body" });
    const left = h("div", { class: "split-left" });
    const right = h("div", { class: "split-right" });
    grid.append(
      h("div", {}, h("div", { class: "split-label" }, "PASSENGER SCREEN · LIVE"), left),
      h("div", {}, h("div", { class: "split-label" }, `${VIEWS[state.splitRole].label.toUpperCase()} · LIVE`, splitPicker()), right)
    );
    root.appendChild(grid);
    const passengerHandle = await safeMount(mountPassenger, { ...baseCtx, ui: state.ui.passenger, role: "passenger", compact: true, root: left });
    const businessHandle = await safeMount(VIEWS[state.splitRole].mount, { ...baseCtx, ui: state.ui[state.splitRole], role: state.splitRole, compact: true, root: right });
    if (token !== renderToken) return;
    mounted = [passengerHandle, businessHandle].filter(Boolean);
  } else {
    const handle = await safeMount(VIEWS[state.role].mount, { ...baseCtx, ui: state.ui[state.role], role: state.role, root, compact: false });
    if (token !== renderToken) return;
    mounted = handle ? [handle] : [];
  }
  window.scrollTo({ top: window.scrollY });
}

function splitPicker() {
  const select = h("select", { class: "split-picker", onChange: (event) => {
    state.splitRole = event.target.value;
    state.role = event.target.value;
    location.hash = `#/${event.target.value}`;
    updateNav();
    render();
  } }, ...["retailer", "media", "airline", "admin"].map((role) =>
    h("option", { value: role, selected: role === state.splitRole }, VIEWS[role].label)
  ));
  return select;
}

async function safeMount(mountFn, ctx) {
  try {
    return await mountFn(ctx);
  } catch (error) {
    console.error(error);
    ctx.root.appendChild(h("div", { class: "card danger" },
      h("div", { class: "card-title", text: "This view could not load" }),
      h("p", { class: "muted tiny", style: { marginTop: "6px" }, text: error.message }),
      h("button", { class: "btn small", style: { marginTop: "10px" }, onClick: () => render() }, "Retry")
    ));
    return null;
  }
}

function destroyMounted() {
  for (const handle of mounted) {
    try {
      handle?.destroy?.();
    } catch (error) {
      console.error(error);
    }
  }
  mounted = [];
}

async function mountClaimStandalone(code) {
  document.getElementById("topbar").hidden = true;
  document.getElementById("simbanner").hidden = true;
  const view = document.getElementById("view");
  view.hidden = false;
  view.className = "view";
  clear(view);
  document.body.classList.remove("split");
  await mountClaim({
    root: view,
    code,
    config: state.config,
    sim: currentSim(),
    lang: state.lang,
    t,
    api,
    toast,
  });
}

function connectStream() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource("/api/stream");
  const names = ["sim", "kpi", "flight", "decisions", "redemption", "incident", "screen", "approval", "goodwill", "marketplace", "sim_error", "scan"];
  for (const name of names) {
    eventSource.addEventListener(name, (event) => {
      let data = {};
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      if (name === "sim") syncSim(data);
      if (name === "decisions" && data.zonePresence) state.zonePresence = data.zonePresence;
      if (name === "kpi") state.kpi = data;
      for (const handle of mounted) {
        try {
          handle?.onEvent?.(name, data);
        } catch (error) {
          console.error(error);
        }
      }
    });
  }
  eventSource.onerror = () => {
    dom.livePill?.querySelector("span")?.replaceChildren(document.createTextNode("reconnecting"));
  };
  eventSource.onopen = () => {
    if (dom.livePill) {
      clear(dom.livePill);
      dom.livePill.append(h("i", { class: "live-dot" }), h("span", { text: "SSE live" }));
    }
  };
}

// expose a tiny hook for the claim page to notify dashboards
window.MMOS = { state, toast, getLanguage };

boot();