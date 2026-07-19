import { prepareReviewImport } from "./review-core.js";

export const LEARNING_STATE_SCHEMA_VERSION = 1;
export const LEARNING_STATE_TYPE = "math1-reader-state";
export const MAX_LEARNING_STATE_BYTES = 1024 * 1024;

const allowedPreferences = {
  theme: new Set(["system", "light", "dark"]),
  fontScale: new Set(["small", "medium", "standard", "large", "1", "1.125", "1.25"]),
  contentWidth: new Set(["narrow", "standard", "wide"]),
};
const PREFERENCE_KEYS = new Set(["schemaVersion", "theme", "fontScale", "contentWidth"]);
const PROGRESS_KEYS = new Set(["schemaVersion", "recentSlug", "pages"]);
const PROGRESS_PAGE_KEYS = new Set(["maxRatio", "lastAnchor", "complete", "title", "url", "updatedAt"]);
const ENVELOPE_KEYS = new Set([
  "schemaVersion",
  "type",
  "buildId",
  "timezone",
  "exportedAt",
  "preferences",
  "progress",
  "reviews",
]);
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const ANCHOR = /^[A-Za-z0-9][A-Za-z0-9:._-]{0,255}$/;

function plainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (!plainObject(value)) return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stableValue(value[key])]));
}

function equalValue(left, right) {
  return JSON.stringify(stableValue(left)) === JSON.stringify(stableValue(right));
}

function isTimestamp(value) {
  if (typeof value !== "string") return false;
  const date = new Date(value);
  return !Number.isNaN(date.getTime()) && date.toISOString() === value;
}

function unknownKeys(value, allowed) {
  return Object.keys(value).filter((key) => !allowed.has(key));
}

function diffRecords(current, incoming) {
  const before = plainObject(current) ? current : {};
  const after = plainObject(incoming) ? incoming : {};
  const counts = { added: 0, updated: 0, removed: 0, unchanged: 0 };
  for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
    if (!(key in before)) counts.added += 1;
    else if (!(key in after)) counts.removed += 1;
    else if (equalValue(before[key], after[key])) counts.unchanged += 1;
    else counts.updated += 1;
  }
  return counts;
}

export function learningStateToken(value) {
  return JSON.stringify(stableValue(value));
}

export function validatePreferences(value) {
  const errors = [];
  if (!plainObject(value)) return ["preferences 必须是对象。"];
  for (const key of unknownKeys(value, PREFERENCE_KEYS)) errors.push(`preferences 包含不支持的字段：${key}`);
  if (value.schemaVersion !== 1) errors.push("preferences.schemaVersion 必须为 1。 ");
  for (const [key, allowed] of Object.entries(allowedPreferences)) {
    if (!allowed.has(String(value[key] ?? ""))) errors.push(`preferences.${key} 无效。`);
  }
  return errors;
}

export function validateProgress(value) {
  const errors = [];
  if (!plainObject(value)) return ["progress 必须是对象。"];
  for (const key of unknownKeys(value, PROGRESS_KEYS)) errors.push(`progress 包含不支持的字段：${key}`);
  if (value.schemaVersion !== 1) errors.push("progress.schemaVersion 必须为 1。 ");
  if (value.recentSlug !== null && (typeof value.recentSlug !== "string" || !SLUG.test(value.recentSlug))) {
    errors.push("progress.recentSlug 必须是合法 slug 或 null。 ");
  }
  if (!plainObject(value.pages)) return [...errors, "progress.pages 必须是对象。"];
  for (const [slug, page] of Object.entries(value.pages)) {
    if (!SLUG.test(slug)) errors.push(`progress.pages 的键不是合法 slug：${slug}`);
    if (!plainObject(page)) {
      errors.push(`progress.pages.${slug} 必须是对象。`);
      continue;
    }
    for (const key of unknownKeys(page, PROGRESS_PAGE_KEYS)) {
      errors.push(`progress.pages.${slug} 包含不支持的字段：${key}`);
    }
    if (!Number.isFinite(page.maxRatio) || page.maxRatio < 0 || page.maxRatio > 1) {
      errors.push(`progress.pages.${slug}.maxRatio 必须在 0 到 1 之间。`);
    }
    if (typeof page.complete !== "boolean") errors.push(`progress.pages.${slug}.complete 必须是布尔值。`);
    if (typeof page.lastAnchor !== "string" || (page.lastAnchor && !ANCHOR.test(page.lastAnchor))) {
      errors.push(`progress.pages.${slug}.lastAnchor 不是合法锚点。`);
    }
    if (typeof page.title !== "string" || !page.title.trim() || page.title.length > 200) {
      errors.push(`progress.pages.${slug}.title 必须是非空短字符串。`);
    }
    if (page.url !== `/math/${slug}`) errors.push(`progress.pages.${slug}.url 必须是对应的 /math/ 同源相对路径。`);
    if (!isTimestamp(page.updatedAt)) errors.push(`progress.pages.${slug}.updatedAt 必须是规范的 ISO 时间戳。`);
  }
  if (typeof value.recentSlug === "string" && !(value.recentSlug in value.pages)) {
    errors.push("progress.recentSlug 必须指向 pages 中的条目。 ");
  }
  return errors;
}

export function prepareLearningStateImport(raw, current, knownNodeIds = [], now = new Date()) {
  let payload = raw;
  if (typeof raw === "string") {
    if (new TextEncoder().encode(raw).byteLength > MAX_LEARNING_STATE_BYTES) {
      return { ok: false, errors: ["导入文件超过 1 MiB。"], warnings: [], preview: null, nextState: null };
    }
    try {
      payload = JSON.parse(raw);
    } catch {
      return { ok: false, errors: ["JSON 无法解析。"], warnings: [], preview: null, nextState: null };
    }
  }
  if (!plainObject(payload)) return { ok: false, errors: ["导入文件必须是 JSON 对象。"], warnings: [], preview: null, nextState: null };

  const envelope = payload.type === LEARNING_STATE_TYPE
    ? payload
    : { reviews: payload, preferences: current.preferences, progress: current.progress };
  const errors = [];
  if (payload.type === LEARNING_STATE_TYPE) {
    for (const key of unknownKeys(payload, ENVELOPE_KEYS)) errors.push(`导入文件包含不支持的字段：${key}`);
    if (payload.schemaVersion !== LEARNING_STATE_SCHEMA_VERSION) errors.push("不支持的学习状态 schemaVersion。 ");
    if (typeof payload.buildId !== "string" || !payload.buildId || payload.buildId.length > 200) {
      errors.push("buildId 必须是非空短字符串。 ");
    }
    if (typeof payload.timezone !== "string" || !payload.timezone || payload.timezone.length > 200) {
      errors.push("timezone 必须是非空短字符串。 ");
    }
    if (!isTimestamp(payload.exportedAt)) errors.push("exportedAt 必须是规范的 ISO 时间戳。 ");
  }
  errors.push(...validatePreferences(envelope.preferences));
  errors.push(...validateProgress(envelope.progress));
  const review = prepareReviewImport(envelope.reviews, current.reviews, knownNodeIds, now);
  errors.push(...review.errors);
  if (errors.length) return { ok: false, errors, warnings: review.warnings ?? [], preview: null, nextState: null };
  return {
    ok: true,
    errors: [],
    warnings: review.warnings,
    preview: {
      preferences: diffRecords(
        {
          theme: current.preferences.theme,
          fontScale: current.preferences.fontScale,
          contentWidth: current.preferences.contentWidth,
        },
        {
          theme: envelope.preferences.theme,
          fontScale: envelope.preferences.fontScale,
          contentWidth: envelope.preferences.contentWidth,
        },
      ),
      progress: diffRecords(
        { __recentSlug: current.progress.recentSlug, ...current.progress.pages },
        { __recentSlug: envelope.progress.recentSlug, ...envelope.progress.pages },
      ),
      reviews: review.preview,
    },
    nextState: {
      preferences: envelope.preferences,
      progress: envelope.progress,
      reviews: review.nextState,
    },
  };
}
