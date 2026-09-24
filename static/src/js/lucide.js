import { createIcons, HeartPulse } from "lucide";

function initializeLucide() {
  createIcons({ icons: { HeartPulse } });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeLucide, { once: true });
} else {
  initializeLucide();
}
