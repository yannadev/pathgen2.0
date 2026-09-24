import "preline";

function initializePreline() {
  window.HSStaticMethods.autoInit();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializePreline, { once: true });
} else {
  initializePreline();
}
