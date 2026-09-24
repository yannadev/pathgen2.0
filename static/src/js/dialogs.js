const focusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

let activeDialog = null;
let activeOpener = null;

function focusTarget(dialog) {
  return (
    dialog.querySelector("[data-error-summary]") ||
    dialog.querySelector("[data-dialog-initial-focus]") ||
    dialog.querySelector(focusableSelector)
  );
}

function openDialog(dialog, opener = document.activeElement) {
  if (!(dialog instanceof HTMLDialogElement)) return;
  activeDialog = dialog;
  activeOpener = opener instanceof HTMLElement ? opener : null;
  dialog.showModal();
  document.body.dataset.dialogOpen = "true";
  window.requestAnimationFrame(() => focusTarget(dialog)?.focus());
}

function closeDialog(dialog) {
  if (!(dialog instanceof HTMLDialogElement) || dialog.dataset.submitting === "true") return;
  dialog.close();
}

function restoreAfterClose(dialog) {
  if (activeDialog === dialog) {
    delete document.body.dataset.dialogOpen;
    activeOpener?.focus();
    activeDialog = null;
    activeOpener = null;
  }
}

function trapFocus(event, dialog) {
  if (event.key !== "Tab") return;
  const focusable = [...dialog.querySelectorAll(focusableSelector)].filter(
    (element) => element instanceof HTMLElement && element.offsetParent !== null,
  );
  if (focusable.length === 0) {
    event.preventDefault();
    dialog.focus();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function initializeDialogs() {
  document.querySelectorAll("[data-dialog-open]").forEach((opener) => {
    opener.addEventListener("click", (event) => {
      const dialog = document.getElementById(opener.dataset.dialogOpen);
      if (dialog instanceof HTMLDialogElement) {
        event.preventDefault();
        openDialog(dialog, opener);
      }
    });
  });

  document.querySelectorAll("dialog[data-dialog]").forEach((dialog) => {
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      closeDialog(dialog);
    });
    dialog.addEventListener("close", () => restoreAfterClose(dialog));
    dialog.addEventListener("keydown", (event) => trapFocus(event, dialog));
    dialog.querySelectorAll("[data-dialog-close]").forEach((closer) => {
      closer.addEventListener("click", () => closeDialog(dialog));
    });
    dialog.querySelectorAll("form").forEach((form) => {
      form.addEventListener("submit", () => {
        if (!form.checkValidity()) return;
        dialog.dataset.submitting = "true";
        form.setAttribute("aria-busy", "true");
        form.querySelectorAll("button[type='submit']").forEach((button) => {
          button.disabled = true;
        });
      });
    });
  });

  const autoOpen = document.querySelector("dialog[data-dialog-auto-open]");
  if (autoOpen instanceof HTMLDialogElement) openDialog(autoOpen, null);

  const pageSummary = document.querySelector("main [data-error-summary]");
  if (pageSummary instanceof HTMLElement && !pageSummary.closest("dialog")) {
    pageSummary.focus();
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeDialogs, { once: true });
} else {
  initializeDialogs();
}
