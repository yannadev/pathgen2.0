function setSidebarCollapsed(collapsed) {
  const shell = document.querySelector("[data-app-shell]");
  if (!shell) return;
  shell.dataset.sidebarCollapsed = String(collapsed);
  document.querySelectorAll("[data-sidebar-toggle]").forEach((button) => {
    button.setAttribute("aria-expanded", String(!collapsed));
    button.setAttribute(
      "aria-label",
      collapsed ? "Expand sidebar" : "Collapse sidebar",
    );
  });
}

function initializeShell() {
  const stored = window.localStorage.getItem("pathgen:sidebar-collapsed") === "true";
  setSidebarCollapsed(stored);
  document.querySelectorAll("[data-sidebar-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const shell = document.querySelector("[data-app-shell]");
      const collapsed = shell?.dataset.sidebarCollapsed !== "true";
      setSidebarCollapsed(collapsed);
      window.localStorage.setItem("pathgen:sidebar-collapsed", String(collapsed));
    });
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeShell, { once: true });
} else {
  initializeShell();
}
