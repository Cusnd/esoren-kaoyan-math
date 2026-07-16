export const SITE_BASE_PATH = "/math";
export const SITE_ROOT = `${SITE_BASE_PATH}/`;

export function sitePath(value = "") {
  const input = String(value);
  if (!input || input === "/") return SITE_ROOT;
  if (input === SITE_BASE_PATH
    || input.startsWith(`${SITE_BASE_PATH}/`)
    || input.startsWith(`${SITE_BASE_PATH}?`)
    || input.startsWith(`${SITE_BASE_PATH}#`)) return input;
  if (input.startsWith("#") || input.startsWith("?")) return `${SITE_ROOT}${input}`;
  return `${SITE_ROOT}${input.replace(/^\/+/, "")}`;
}

export function isSitePath(pathname) {
  return pathname === SITE_BASE_PATH || pathname.startsWith(SITE_ROOT);
}
