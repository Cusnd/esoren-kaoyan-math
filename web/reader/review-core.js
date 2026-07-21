export const REVIEW_STORAGE_KEY = "math1.reader.reviews.v1";
export const REVIEW_SCHEMA_VERSION = 1;
export const REVIEW_SCHEDULE_ID = "fixed-0-1-3-7-14-30-60-120-v1";
export const REVIEW_INTERVAL_DAYS = Object.freeze([0, 1, 3, 7, 14, 30, 60, 120]);

const NODE_ID = /^MATH1-KN-(?:CALC|LA|PROB)-\d{4}$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const REVIEW_ROOT_KEYS = new Set(["schemaVersion", "scheduleId", "updatedAt", "items", "exportedAt"]);
const REVIEW_ITEM_KEYS = new Set([
  "state",
  "step",
  "dueOn",
  "lastReviewedOn",
  "reviewCount",
  "snoozeCount",
  "labelSnapshot",
  "updatedAt",
  "removedAt",
]);

function plainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isTimestamp(value) {
  if (typeof value !== "string") return false;
  const date = new Date(value);
  return !Number.isNaN(date.getTime()) && date.toISOString() === value;
}

function unknownKeys(value, allowed) {
  return Object.keys(value).filter((key) => !allowed.has(key));
}

export function isLocalDate(value) {
  if (!DATE.test(String(value))) return false;
  const [year, month, day] = String(value).split("-").map(Number);
  const date = new Date(year, month - 1, day, 12, 0, 0, 0);
  return date.getFullYear() === year
    && date.getMonth() === month - 1
    && date.getDate() === day;
}

function pad(value) {
  return String(value).padStart(2, "0");
}

export function localDate(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) throw new TypeError("Invalid date");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function addLocalDays(value, days) {
  if (!isLocalDate(value)) throw new TypeError("Expected a real YYYY-MM-DD date");
  const [year, month, day] = String(value).split("-").map(Number);
  const date = new Date(year, month - 1, day, 12, 0, 0, 0);
  date.setDate(date.getDate() + Number(days));
  return localDate(date);
}

export function millisecondsUntilNextLocalMidnight(value = new Date()) {
  const now = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(now.getTime())) throw new TypeError("Invalid date");
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 0, 0);
  return Math.max(1, next.getTime() - now.getTime());
}

export function reviewDateChanged(previousDate, value = new Date()) {
  return String(previousDate ?? "") !== localDate(value);
}

function timestamp(value, fallback) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? fallback : date.toISOString();
}

export function emptyReviewState(now = new Date()) {
  return {
    schemaVersion: REVIEW_SCHEMA_VERSION,
    scheduleId: REVIEW_SCHEDULE_ID,
    updatedAt: (now instanceof Date ? now : new Date(now)).toISOString(),
    items: {},
  };
}

function normalizeItem(candidate, now) {
  const input = candidate && typeof candidate === "object" ? candidate : {};
  const state = input.state === "removed" ? "removed" : "active";
  const step = Math.max(0, Math.min(
    REVIEW_INTERVAL_DAYS.length - 1,
    Number.isInteger(input.step) ? input.step : 0,
  ));
  const dueOn = state === "active" && isLocalDate(input.dueOn)
    ? String(input.dueOn)
    : null;
  return {
    state,
    step,
    dueOn,
    lastReviewedOn: isLocalDate(input.lastReviewedOn)
      ? String(input.lastReviewedOn)
      : null,
    reviewCount: Math.max(0, Number.isInteger(input.reviewCount) ? input.reviewCount : 0),
    snoozeCount: Math.max(0, Number.isInteger(input.snoozeCount) ? input.snoozeCount : 0),
    labelSnapshot: String(input.labelSnapshot ?? "").slice(0, 200),
    updatedAt: timestamp(input.updatedAt, now),
    ...(state === "removed" ? { removedAt: timestamp(input.removedAt, timestamp(input.updatedAt, now)) } : {}),
  };
}

export function normalizeReviewState(candidate, now = new Date()) {
  const instant = (now instanceof Date ? now : new Date(now)).toISOString();
  const input = candidate && typeof candidate === "object" ? candidate : {};
  const sourceItems = input.items && typeof input.items === "object" && !Array.isArray(input.items)
    ? input.items
    : {};
  const items = {};
  for (const [id, value] of Object.entries(sourceItems)) {
    if (!NODE_ID.test(id)) continue;
    items[id] = normalizeItem(value, instant);
  }
  return {
    schemaVersion: REVIEW_SCHEMA_VERSION,
    scheduleId: REVIEW_SCHEDULE_ID,
    updatedAt: timestamp(input.updatedAt, instant),
    items,
  };
}

export function applyReviewAction(candidate, node, action, now = new Date()) {
  if (node?.reviewable === false) throw new TypeError("Boundary knowledge cannot enter review state.");
  const state = normalizeReviewState(candidate, now);
  const id = String(node?.id ?? node ?? "");
  if (!NODE_ID.test(id)) throw new TypeError(`Invalid knowledge node id: ${id}`);
  const instant = (now instanceof Date ? now : new Date(now)).toISOString();
  const today = localDate(now);
  const current = state.items[id] ?? normalizeItem({}, instant);
  const labelSnapshot = String(node?.title ?? current.labelSnapshot ?? "").slice(0, 200);
  let item;

  if (action === "add") {
    item = {
      ...current,
      state: "active",
      step: 0,
      dueOn: today,
      labelSnapshot,
      updatedAt: instant,
    };
    delete item.removedAt;
  } else if (action === "reviewed") {
    const step = Math.min(current.step + 1, REVIEW_INTERVAL_DAYS.length - 1);
    item = {
      ...current,
      state: "active",
      step,
      dueOn: addLocalDays(today, REVIEW_INTERVAL_DAYS[step]),
      lastReviewedOn: today,
      reviewCount: current.reviewCount + 1,
      labelSnapshot,
      updatedAt: instant,
    };
    delete item.removedAt;
  } else if (action === "still-weak") {
    item = {
      ...current,
      state: "active",
      step: 0,
      dueOn: addLocalDays(today, 1),
      lastReviewedOn: today,
      reviewCount: current.reviewCount + 1,
      labelSnapshot,
      updatedAt: instant,
    };
    delete item.removedAt;
  } else if (action === "tomorrow") {
    item = {
      ...current,
      state: "active",
      dueOn: addLocalDays(today, 1),
      snoozeCount: current.snoozeCount + 1,
      labelSnapshot,
      updatedAt: instant,
    };
    delete item.removedAt;
  } else if (action === "remove") {
    item = {
      ...current,
      state: "removed",
      dueOn: null,
      labelSnapshot,
      updatedAt: instant,
      removedAt: instant,
    };
  } else {
    throw new TypeError(`Unknown review action: ${action}`);
  }

  return {
    ...state,
    updatedAt: instant,
    items: { ...state.items, [id]: item },
  };
}

export function dueReviewIds(candidate, today = localDate()) {
  const state = normalizeReviewState(candidate);
  return Object.entries(state.items)
    .filter(([, item]) => item.state === "active" && item.dueOn && item.dueOn <= today)
    .sort((a, b) => a[1].dueOn.localeCompare(b[1].dueOn) || a[0].localeCompare(b[0]))
    .map(([id]) => id);
}

function validateImportPayload(payload) {
  const errors = [];
  if (!plainObject(payload)) {
    return ["导入文件必须是 JSON 对象。"];
  }
  for (const key of unknownKeys(payload, REVIEW_ROOT_KEYS)) errors.push(`不支持的根字段：${key}`);
  if (payload.schemaVersion !== REVIEW_SCHEMA_VERSION) errors.push("不支持的 schemaVersion。 ");
  if (payload.scheduleId !== REVIEW_SCHEDULE_ID) errors.push("不支持的 scheduleId。 ");
  if (!isTimestamp(payload.updatedAt)) errors.push("updatedAt 必须是规范的 ISO 时间戳。 ");
  if ("exportedAt" in payload && !isTimestamp(payload.exportedAt)) {
    errors.push("exportedAt 必须是规范的 ISO 时间戳。 ");
  }
  if (!plainObject(payload.items)) {
    errors.push("items 必须是对象。 ");
    return errors;
  }
  for (const [id, item] of Object.entries(payload.items)) {
    if (!NODE_ID.test(id)) errors.push(`无效知识节点 ID：${id}`);
    if (!plainObject(item)) {
      errors.push(`${id} 的状态不是对象。`);
      continue;
    }
    for (const key of unknownKeys(item, REVIEW_ITEM_KEYS)) errors.push(`${id} 包含不支持的字段：${key}`);
    if (!new Set(["active", "removed"]).has(item.state)) errors.push(`${id} 的 state 无效。`);
    if (!Number.isInteger(item.step) || item.step < 0 || item.step >= REVIEW_INTERVAL_DAYS.length) {
      errors.push(`${id} 的 step 无效。`);
    }
    if (item.state === "active" && !isLocalDate(item.dueOn)) {
      errors.push(`${id} 缺少有效 dueOn。`);
    }
    if (item.state === "removed" && item.dueOn !== null) errors.push(`${id} 的移除状态必须使用 null dueOn。`);
    if (item.lastReviewedOn !== null && !isLocalDate(item.lastReviewedOn)) {
      errors.push(`${id} 的 lastReviewedOn 无效。`);
    }
    if (!Number.isInteger(item.reviewCount) || item.reviewCount < 0) errors.push(`${id} 的 reviewCount 无效。`);
    if (!Number.isInteger(item.snoozeCount) || item.snoozeCount < 0) errors.push(`${id} 的 snoozeCount 无效。`);
    if (typeof item.labelSnapshot !== "string" || item.labelSnapshot.length > 200) {
      errors.push(`${id} 的 labelSnapshot 无效。`);
    }
    if (!isTimestamp(item.updatedAt)) errors.push(`${id} 缺少有效 updatedAt。`);
    if (item.state === "removed" && !isTimestamp(item.removedAt)) errors.push(`${id} 缺少有效 removedAt。`);
    if (item.state === "active" && "removedAt" in item) errors.push(`${id} 的活动状态不能包含 removedAt。`);
  }
  return errors;
}

function normalizeNodePolicy(value) {
  if (value && typeof value === "object" && !Array.isArray(value) && !(value instanceof Set)) {
    const known = new Set([...(value.knownNodeIds ?? [])].map(String));
    const reviewableSource = value.reviewableNodeIds ?? value.knownNodeIds ?? [];
    return { known, reviewable: new Set([...reviewableSource].map(String)) };
  }
  const known = new Set([...(value ?? [])].map(String));
  return { known, reviewable: new Set(known) };
}

export function prepareReviewImport(rawPayload, currentCandidate, nodePolicy = [], now = new Date()) {
  let payload = rawPayload;
  if (typeof rawPayload === "string") {
    try {
      payload = JSON.parse(rawPayload);
    } catch {
      return { ok: false, errors: ["JSON 无法解析。"], warnings: [], preview: null, nextState: null };
    }
  }
  const errors = validateImportPayload(payload);
  if (errors.length) return { ok: false, errors, warnings: [], preview: null, nextState: null };

  const current = normalizeReviewState(currentCandidate, now);
  const incoming = normalizeReviewState(payload, now);
  const { known, reviewable } = normalizeNodePolicy(nodePolicy);
  const blocked = Object.keys(incoming.items)
    .filter((id) => known.has(id) && !reviewable.has(id));
  if (blocked.length) {
    return {
      ok: false,
      errors: [`边界知识不能导入复习状态：${blocked.sort().join("、")}。`],
      warnings: [],
      preview: null,
      nextState: null,
    };
  }
  const warnings = Object.keys(incoming.items)
    .filter((id) => known.size && !known.has(id))
    .map((id) => `知识网络中暂时没有 ${id}，状态将保留但不会出现在今日列表。`);
  const items = { ...current.items };
  const preview = { added: 0, updated: 0, keptLocal: 0, unchanged: 0, removed: 0 };

  for (const [id, imported] of Object.entries(incoming.items)) {
    const local = current.items[id];
    if (!local) {
      items[id] = imported;
      if (imported.state === "removed") preview.removed += 1;
      else preview.added += 1;
      continue;
    }
    const importedTime = Date.parse(imported.updatedAt);
    const localTime = Date.parse(local.updatedAt);
    if (importedTime > localTime) {
      items[id] = imported;
      if (imported.state === "removed" && local.state !== "removed") preview.removed += 1;
      else preview.updated += 1;
    } else if (importedTime < localTime) {
      preview.keptLocal += 1;
    } else {
      preview.unchanged += 1;
    }
  }

  const instant = (now instanceof Date ? now : new Date(now)).toISOString();
  return {
    ok: true,
    errors: [],
    warnings,
    preview,
    nextState: { ...current, updatedAt: instant, items },
  };
}

export function reviewExportPayload(candidate, now = new Date()) {
  const state = normalizeReviewState(candidate, now);
  return {
    ...state,
    exportedAt: (now instanceof Date ? now : new Date(now)).toISOString(),
  };
}
