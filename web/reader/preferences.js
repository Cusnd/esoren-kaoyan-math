import {
  PREFERENCES_KEY,
  readJSON,
  subscribeJSON,
  writeJSON,
} from "./storage.js";

const defaults = Object.freeze({
  schemaVersion: 1,
  theme: "light",
  fontScale: "medium",
  contentWidth: "standard",
});

const allowed = {
  theme: new Set(["system", "light", "dark"]),
  fontScale: new Set(["small", "medium", "standard", "large", "1", "1.125", "1.25"]),
  contentWidth: new Set(["narrow", "standard", "wide"]),
};

function validate(candidate) {
  const input = candidate && typeof candidate === "object" ? candidate : {};
  return {
    schemaVersion: 1,
    theme: allowed.theme.has(input.theme) ? input.theme : defaults.theme,
    fontScale: allowed.fontScale.has(String(input.fontScale))
      ? String(input.fontScale)
      : defaults.fontScale,
    contentWidth: allowed.contentWidth.has(input.contentWidth)
      ? input.contentWidth
      : defaults.contentWidth,
  };
}

function resolvedTheme(theme, media) {
  if (theme !== "system") return theme;
  return media.matches ? "dark" : "light";
}

function updateControls(preferences) {
  document.querySelectorAll("[data-reader-preference]").forEach((control) => {
    const key = control.dataset.readerPreference;
    const selected = String(control.value) === String(preferences[key]);
    if (control instanceof HTMLInputElement) {
      if (control.type === "radio" || control.type === "checkbox") {
        control.checked = selected;
      } else if (key in preferences) {
        control.value = preferences[key];
      }
    }
    if (control instanceof HTMLButtonElement) {
      control.setAttribute("aria-pressed", String(selected));
    }
  });
}

let returnFocus = null;

function openDialog(dialog, trigger) {
  if (!dialog) return;
  returnFocus = trigger instanceof HTMLElement ? trigger : null;
  document.body.classList.add("reader-modal-open");
  if (typeof dialog.showModal === "function") dialog.showModal();
  else {
    dialog.hidden = false;
    dialog.classList.add("is-open");
    dialog.setAttribute("aria-modal", "true");
  }
  dialog.querySelector("[data-reader-preference], button")?.focus();
}

function closeDialog(dialog) {
  if (!dialog) return;
  if (typeof dialog.close === "function" && dialog.open) dialog.close();
  else {
    dialog.classList.remove("is-open");
    dialog.hidden = true;
  }
  document.body.classList.remove("reader-modal-open");
  returnFocus?.focus();
  returnFocus = null;
}

export function initPreferences() {
  const root = document.documentElement;
  const dialog = document.getElementById("reader-preferences");
  dialog?.classList.add("reader-dialog");
  const media = matchMedia("(prefers-color-scheme: dark)");
  let preferences = validate(readJSON(PREFERENCES_KEY, defaults));

  const apply = (next) => {
    preferences = validate(next);
    root.dataset.themePreference = preferences.theme;
    root.dataset.theme = resolvedTheme(preferences.theme, media);
    root.dataset.fontScale = preferences.fontScale;
    root.dataset.contentWidth = preferences.contentWidth;
    updateControls(preferences);
  };

  apply(preferences);
  subscribeJSON(PREFERENCES_KEY, apply);

  media.addEventListener?.("change", () => {
    if (preferences.theme === "system") apply(preferences);
  });

  document.addEventListener("click", (event) => {
    const action = event.target.closest("[data-reader-action]")?.dataset.readerAction;
    if (action === "open-preferences") {
      event.preventDefault();
      const trigger = event.target.closest("[data-reader-action]");
      if (trigger && !trigger.id) trigger.id = "reader-preferences-trigger";
      openDialog(dialog, trigger);
    } else if (action === "close-preferences") {
      event.preventDefault();
      closeDialog(dialog);
    }
  });

  dialog?.addEventListener("click", (event) => {
    const control = event.target.closest("[data-reader-preference]");
    if (!control) return;
    const key = control.dataset.readerPreference;
    const value = String(control.value || control.dataset.value || "");
    if (!allowed[key]?.has(value)) return;
    apply({ ...preferences, [key]: value });
    writeJSON(PREFERENCES_KEY, preferences);
  });

  dialog?.addEventListener("change", (event) => {
    const control = event.target.closest("[data-reader-preference]");
    if (!control) return;
    const key = control.dataset.readerPreference;
    const value = String(control.value || "");
    if (!allowed[key]?.has(value)) return;
    apply({ ...preferences, [key]: value });
    writeJSON(PREFERENCES_KEY, preferences);
  });

  dialog?.addEventListener("close", () => {
    document.body.classList.remove("reader-modal-open");
  });
}
