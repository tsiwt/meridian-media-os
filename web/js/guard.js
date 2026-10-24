(function () {
  "use strict";
  var boot = document.getElementById("boot");
  var failed = false;

  function fail(message) {
    if (failed || !boot || boot.hidden) return;
    failed = true;
    while (boot.firstChild) boot.removeChild(boot.firstChild);
    var mark = document.createElement("div");
    mark.className = "boot-mark";
    mark.textContent = "!";
    var title = document.createElement("div");
    title.style.fontSize = "15px";
    title.style.fontWeight = "700";
    title.textContent = "The demo did not finish loading";
    var detail = document.createElement("div");
    detail.style.maxWidth = "430px";
    detail.style.textAlign = "center";
    detail.style.color = "#8ea4bf";
    detail.style.fontSize = "12px";
    detail.textContent = message;
    var button = document.createElement("button");
    button.className = "btn primary";
    button.textContent = "Reload with fresh files";
    button.addEventListener("click", function () {
      location.href = location.pathname + "?fresh=" + Date.now() + location.hash;
    });
    var link = document.createElement("a");
    link.href = "/api/health";
    link.target = "_blank";
    link.rel = "noreferrer";
    link.style.fontSize = "11px";
    link.textContent = "Check server health";
    boot.appendChild(mark);
    boot.appendChild(title);
    boot.appendChild(detail);
    boot.appendChild(button);
    boot.appendChild(link);
  }

  window.addEventListener("error", function (event) {
    if (event && event.target && event.target.tagName === "SCRIPT") {
      fail("A required script failed to load. This is usually a cached old build or a network error.");
    }
  });
  window.addEventListener("unhandledrejection", function (event) {
    var reason = event && event.reason ? String(event.reason.message || event.reason) : "Unknown error";
    fail("Startup request failed: " + reason);
  });
  setTimeout(function () {
    if (boot && !boot.hidden) {
      fail("The server is taking longer than 12 seconds. It may be waking up, or the local preview process is stopped.");
    }
  }, 12000);
})();