import { initNavigation } from "./navigation.js";
import { initPreferences } from "./preferences.js";
import { initProgress } from "./progress.js";
import { initPWA } from "./pwa.js";
import { initSearch } from "./search.js";

function initializeReader() {
  document.documentElement.classList.add("reader-js");
  initNavigation();
  initPreferences();
  initSearch();
  initProgress();
  initPWA();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeReader, { once: true });
} else {
  initializeReader();
}
