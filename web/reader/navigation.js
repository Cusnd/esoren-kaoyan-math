import { canonicalPath } from "./context.js";

const focusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function setInert(element, inert) {
  if (!element) return;
  if ("inert" in element) element.inert = inert;
  if (inert) element.setAttribute("aria-hidden", "true");
  else element.removeAttribute("aria-hidden");
}

export function initNavigation() {
  const toc = document.getElementById("reader-toc");
  const backdrop = document.querySelector("[data-reader-backdrop]");
  const mobile = matchMedia("(max-width: 799px)");
  let returnFocus = null;

  const inertTargets = () => [
    document.querySelector(".reader-topbar"),
    document.querySelector(".reader-content"),
    document.getElementById("reader-outline"),
  ].filter((target) => target && !toc?.contains(target));

  const open = (trigger) => {
    if (!toc || !mobile.matches) return;
    returnFocus = trigger || document.activeElement;
    toc.classList.add("is-open");
    toc.setAttribute("aria-modal", "true");
    toc.setAttribute("role", "dialog");
    if (backdrop) backdrop.hidden = false;
    backdrop?.classList.add("is-open");
    document.body.classList.add("reader-drawer-open");
    inertTargets().forEach((target) => setInert(target, true));
    document.querySelectorAll('[data-reader-action="open-nav"]').forEach((button) => {
      button.setAttribute("aria-expanded", "true");
    });
    toc.querySelector('[data-reader-action="close-nav"], a[href], button')?.focus();
  };

  const close = ({ restore = true } = {}) => {
    if (!toc) return;
    toc.classList.remove("is-open");
    toc.removeAttribute("aria-modal");
    toc.removeAttribute("role");
    backdrop?.classList.remove("is-open");
    if (backdrop) backdrop.hidden = true;
    document.body.classList.remove("reader-drawer-open");
    inertTargets().forEach((target) => setInert(target, false));
    document.querySelectorAll('[data-reader-action="open-nav"]').forEach((button) => {
      button.setAttribute("aria-expanded", "false");
    });
    if (restore && returnFocus instanceof HTMLElement) returnFocus.focus();
  };

  const current = canonicalPath();
  document.querySelectorAll("#reader-toc a[href]").forEach((link) => {
    try {
      if (canonicalPath(new URL(link.href, location.href).pathname) === current) {
        link.setAttribute("aria-current", "page");
        link.closest("details")?.setAttribute("open", "");
      } else if (link.getAttribute("aria-current") === "page") {
        link.removeAttribute("aria-current");
      }
    } catch {
      // Ignore malformed legacy links; build validation reports them separately.
    }
  });

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-reader-action]");
    const action = trigger?.dataset.readerAction;
    if (action === "open-nav") {
      event.preventDefault();
      open(trigger);
    } else if (action === "close-nav") {
      event.preventDefault();
      close();
    } else if (action === "print") {
      event.preventDefault();
      window.print();
    }

    if (event.target.closest("[data-reader-backdrop]")) close();
    if (mobile.matches && event.target.closest("#reader-toc a[href]")) {
      close({ restore: false });
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && toc?.classList.contains("is-open")) {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab" || !toc?.classList.contains("is-open")) return;
    const focusable = [...toc.querySelectorAll(focusableSelector)].filter(
      (element) => !element.hidden && element.getClientRects().length > 0,
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  mobile.addEventListener?.("change", (event) => {
    if (!event.matches) close({ restore: false });
  });
}
