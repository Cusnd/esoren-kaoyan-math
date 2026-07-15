import { getPageContext } from "./context.js";
import {
  PROGRESS_KEY,
  readJSON,
  subscribeJSON,
  writeJSON,
} from "./storage.js";

const emptyProgress = Object.freeze({ schemaVersion: 1, recentSlug: null, pages: {} });

function validate(candidate) {
  const input = candidate && typeof candidate === "object" ? candidate : {};
  const pages = input.pages && typeof input.pages === "object" ? input.pages : {};
  return {
    schemaVersion: 1,
    recentSlug: typeof input.recentSlug === "string" ? input.recentSlug : null,
    pages,
  };
}

function anchorRecords(context) {
  const configured = Array.isArray(context.anchors) ? context.anchors : [];
  const records = configured.map((anchor) => {
    const id = typeof anchor === "string" ? anchor.replace(/^#/, "") : String(anchor.id ?? anchor.anchor ?? "").replace(/^#/, "");
    const label = typeof anchor === "string" ? anchor : String(anchor.label ?? anchor.title ?? id);
    return { id, label, element: document.getElementById(id) };
  });
  const discovered = [...document.querySelectorAll(
    "#reader-main [data-reader-anchor-target][id], #reader-main .problem-box[id], #reader-main .solution-box[id], #reader-main .knowledge-box[id], #reader-main .mistake-box[id], #reader-main h2[id], #reader-main h3[id]",
  )].map((element) => ({
    id: element.id,
    label: element.dataset.readerAnchorTarget || element.textContent?.trim().slice(0, 60) || element.id,
    element,
  }));
  const seen = new Set();
  return [...records, ...discovered].filter(({ id, element }) => {
    if (!id || !element || seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

function updateProgressElements(elements, ratio) {
  const percent = Math.round(Math.min(1, Math.max(0, ratio)) * 100);
  elements.forEach((element) => {
    if (element instanceof HTMLProgressElement) {
      element.max = 100;
      element.value = percent;
    } else {
      element.style.setProperty("--reader-progress", `${percent}%`);
      element.setAttribute("aria-valuemin", "0");
      element.setAttribute("aria-valuemax", "100");
      element.setAttribute("aria-valuenow", String(percent));
    }
    element.setAttribute("aria-valuetext", `已阅读 ${percent}%`);
  });
  document.querySelectorAll("[data-reader-progress-label]").forEach((label) => {
    label.textContent = `${percent}%`;
  });
}

function setContinueLink(progress) {
  const link = document.querySelector("[data-reader-continue]");
  if (!link) return;
  const entry = progress.recentSlug && progress.pages[progress.recentSlug];
  if (!entry) {
    link.hidden = true;
    return;
  }
  const base = entry.url || `/${progress.recentSlug}`;
  link.href = entry.lastAnchor ? `${base}#${encodeURIComponent(entry.lastAnchor)}` : base;
  const label = link.querySelector("[data-reader-continue-title]");
  if (label) label.textContent = entry.title || progress.recentSlug;
  link.hidden = false;
}

export function initProgress() {
  const context = getPageContext();
  const slug = String(context.slug ?? "");
  let progress = validate(readJSON(PROGRESS_KEY, emptyProgress));
  const isHome = context.isHome === true || !slug || slug === "index";

  if (isHome) {
    setContinueLink(progress);
    subscribeJSON(PROGRESS_KEY, (value) => setContinueLink(validate(value)));
    return;
  }

  const elements = [...document.querySelectorAll("[data-reader-progress]")];
  const anchors = anchorRecords(context);
  const stored = progress.pages[slug] && typeof progress.pages[slug] === "object"
    ? progress.pages[slug]
    : {};
  let maximum = Math.min(1, Math.max(0, Number(stored.maxRatio) || 0));
  let lastAnchor = typeof stored.lastAnchor === "string" ? stored.lastAnchor : "";
  let timer;

  updateProgressElements(elements, maximum);

  const save = () => {
    const height = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    const ratio = Math.min(1, Math.max(0, window.scrollY / height));
    maximum = Math.max(maximum, ratio);
    const latest = validate(readJSON(PROGRESS_KEY, progress));
    progress = {
      ...latest,
      schemaVersion: 1,
      recentSlug: slug,
      pages: {
        ...latest.pages,
        [slug]: {
          ...latest.pages[slug],
          maxRatio: Number(maximum.toFixed(4)),
          lastAnchor,
          complete: maximum >= 0.92,
          title: String(context.title ?? document.title),
          url: String(context.canonicalUrl ?? `/${slug}`),
          updatedAt: new Date().toISOString(),
        },
      },
    };
    updateProgressElements(elements, maximum);
    writeJSON(PROGRESS_KEY, progress);
  };

  const schedule = () => {
    clearTimeout(timer);
    timer = setTimeout(save, 500);
  };
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("pagehide", save);

  if ("IntersectionObserver" in window && anchors.length) {
    const visible = new Map();
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) visible.set(entry.target.id, entry.boundingClientRect.top);
        else visible.delete(entry.target.id);
      });
      const nearest = [...visible.entries()].sort((a, b) => Math.abs(a[1]) - Math.abs(b[1]))[0];
      if (!nearest) return;
      lastAnchor = nearest[0];
      document.querySelectorAll("[data-reader-anchor], #reader-outline a[href^='#']").forEach((link) => {
        const current = decodeURIComponent(link.hash.slice(1)) === lastAnchor;
        if (current) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
      });
      schedule();
    }, { rootMargin: "-18% 0px -68% 0px", threshold: [0, 0.01] });
    anchors.forEach(({ element: target }) => observer.observe(target));
  }

  // A deep link is authoritative: progress is observed but never auto-restored here.
  if (window.location.hash) {
    lastAnchor = decodeURIComponent(window.location.hash.slice(1));
  }
  save();
}
