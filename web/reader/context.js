let cachedContext;

export function getPageContext() {
  if (cachedContext !== undefined) return cachedContext;
  const element = document.getElementById("reader-page-context");
  if (!element) {
    cachedContext = {};
    return cachedContext;
  }

  try {
    cachedContext = JSON.parse(element.textContent || "{}");
  } catch {
    cachedContext = {};
  }
  return cachedContext;
}

export function canonicalPath(path = window.location.pathname) {
  const normalized = path
    .replace(/\/index\.html$/i, "/")
    .replace(/\.html$/i, "")
    .replace(/\/$/, "");
  return normalized || "/";
}
