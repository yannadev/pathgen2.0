import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  GraduationCap,
  HeartPulse,
  LayoutDashboard,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  ScrollText,
  School,
  SlidersHorizontal,
  UserRound,
  Users,
  X,
  createIcons,
} from "lucide";

function initializeLucide() {
  createIcons({
    icons: {
      BookOpen,
      ChevronLeft,
      ChevronRight,
      CircleAlert,
      CircleCheck,
      GraduationCap,
      HeartPulse,
      LayoutDashboard,
      LogOut,
      Menu,
      PanelLeftClose,
      PanelLeftOpen,
      ScrollText,
      School,
      SlidersHorizontal,
      UserRound,
      Users,
      X,
    },
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeLucide, { once: true });
} else {
  initializeLucide();
}
