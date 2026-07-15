(function readerPreflight() {
  const root = document.documentElement;
  const defaults = {
    theme: "light",
    fontScale: "medium",
    contentWidth: "standard",
  };

  let preferences = defaults;
  try {
    const stored = JSON.parse(
      localStorage.getItem("math1.reader.preferences.v1") || "{}",
    );
    preferences = { ...defaults, ...stored };
  } catch {
    // Storage is an enhancement; the reader remains usable without it.
  }

  const themes = new Set(["system", "light", "dark"]);
  const fontScales = new Set(["small", "medium", "standard", "large", "1", "1.125", "1.25"]);
  const widths = new Set(["narrow", "standard", "wide"]);
  const theme = themes.has(preferences.theme) ? preferences.theme : defaults.theme;
  const fontScale = fontScales.has(String(preferences.fontScale))
    ? String(preferences.fontScale)
    : defaults.fontScale;
  const contentWidth = widths.has(preferences.contentWidth)
    ? preferences.contentWidth
    : defaults.contentWidth;
  const resolvedTheme =
    theme === "system"
      ? matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : theme;

  root.dataset.themePreference = theme;
  root.dataset.theme = resolvedTheme;
  root.dataset.fontScale = fontScale;
  root.dataset.contentWidth = contentWidth;
})();
