import assert from "node:assert/strict";
import test from "node:test";

import {
  LEARNING_STATE_TYPE,
  MAX_LEARNING_STATE_BYTES,
  learningStateToken,
  prepareLearningStateImport,
} from "../../web/reader/learning-state.js";
import {
  REVIEW_STORAGE_KEY,
  applyReviewAction,
  emptyReviewState,
  reviewExportPayload,
} from "../../web/reader/review-core.js";
import {
  PREFERENCES_KEY,
  PROGRESS_KEY,
  transactionalJSONWrite,
} from "../../web/reader/storage.js";

const preferences = { schemaVersion: 1, theme: "light", fontScale: "medium", contentWidth: "standard" };
const progress = { schemaVersion: 1, recentSlug: null, pages: {} };
const node = { id: "MATH1-KN-CALC-0001", title: "函数表示" };
const now = new Date("2026-07-18T12:00:00.000Z");
const reviews = applyReviewAction(emptyReviewState(now), node, "add", now);

function envelope(overrides = {}) {
  return {
    schemaVersion: 1,
    type: LEARNING_STATE_TYPE,
    buildId: "build-1",
    timezone: "Asia/Shanghai",
    exportedAt: now.toISOString(),
    preferences,
    progress,
    reviews: reviewExportPayload(reviews, now),
    ...overrides,
  };
}

function progressPage(slug, overrides = {}) {
  return {
    maxRatio: 0.2,
    lastAnchor: "",
    complete: false,
    title: `页面 ${slug}`,
    url: `/math/${slug}`,
    updatedAt: now.toISOString(),
    ...overrides,
  };
}

test("learning-state import validates the complete versioned envelope", () => {
  const prepared = prepareLearningStateImport(
    JSON.stringify(envelope()),
    { preferences, progress, reviews: emptyReviewState(now) },
    [node.id],
    now,
  );
  assert.equal(prepared.ok, true);
  assert.equal(prepared.nextState.preferences.theme, "light");
  assert.equal(prepared.nextState.reviews.items[node.id].state, "active");
});

test("boundary knowledge is rejected atomically by actions and state imports", () => {
  const boundary = { id: "MATH1-KN-CALC-0093", title: "一致连续性（教材扩展）", reviewable: false };
  assert.throws(
    () => applyReviewAction(emptyReviewState(now), boundary, "add", now),
    /Boundary knowledge/,
  );

  const boundaryItem = {
    ...reviews.items[node.id],
    labelSnapshot: boundary.title,
  };
  const incoming = envelope({
    reviews: {
      ...emptyReviewState(now),
      items: { [boundary.id]: boundaryItem },
    },
  });
  const current = { preferences, progress, reviews: emptyReviewState(now) };
  const before = structuredClone(current);
  const prepared = prepareLearningStateImport(
    JSON.stringify(incoming),
    current,
    {
      knownNodeIds: [node.id, boundary.id],
      reviewableNodeIds: [node.id],
    },
    now,
  );

  assert.equal(prepared.ok, false);
  assert.equal(prepared.nextState, null);
  assert.match(prepared.errors.join(" "), /边界知识不能导入复习状态/);
  assert.deepEqual(current, before);
});

test("future schemas and malformed preferences or progress are rejected", () => {
  for (const payload of [
    envelope({ schemaVersion: 2 }),
    envelope({ preferences: { ...preferences, theme: "sepia" } }),
    envelope({ progress: { schemaVersion: 1, recentSlug: null, pages: [] } }),
    envelope({ progress: { schemaVersion: 1, recentSlug: null, pages: { bad: { maxRatio: 2 } } } }),
  ]) {
    const result = prepareLearningStateImport(
      JSON.stringify(payload),
      { preferences, progress, reviews },
      [node.id],
      now,
    );
    assert.equal(result.ok, false);
    assert.equal(result.nextState, null);
  }
});

test("oversized learning-state imports are rejected before parsing", () => {
  const raw = `{"padding":"${"x".repeat(MAX_LEARNING_STATE_BYTES)}"}`;
  const result = prepareLearningStateImport(raw, { preferences, progress, reviews }, [node.id], now);
  assert.equal(result.ok, false);
  assert.match(result.errors.join(" "), /1 MiB/);
});

test("learning-state preview reports complete differences for every state area", () => {
  const ids = Array.from({ length: 5 }, (_, index) => `MATH1-KN-CALC-${String(index + 1).padStart(4, "0")}`);
  const item = (state, updatedAt, overrides = {}) => ({
    state,
    step: 0,
    dueOn: state === "active" ? "2026-07-18" : null,
    lastReviewedOn: null,
    reviewCount: 0,
    snoozeCount: 0,
    labelSnapshot: "fixture",
    updatedAt,
    ...(state === "removed" ? { removedAt: updatedAt } : {}),
    ...overrides,
  });
  const current = {
    preferences,
    progress: {
      schemaVersion: 1,
      recentSlug: "unchanged",
      pages: {
        unchanged: progressPage("unchanged"),
        updated: progressPage("updated", { maxRatio: 0.3 }),
        removed: progressPage("removed", { maxRatio: 0.4 }),
      },
    },
    reviews: {
      ...emptyReviewState(now),
      items: {
        [ids[0]]: item("active", "2026-07-18T10:00:00.000Z"),
        [ids[1]]: item("active", "2026-07-18T12:00:00.000Z"),
        [ids[2]]: item("active", "2026-07-18T10:00:00.000Z"),
        [ids[4]]: item("removed", "2026-07-18T14:00:00.000Z"),
      },
    },
  };
  const incomingProgress = {
    schemaVersion: 1,
    recentSlug: "updated",
    pages: {
      unchanged: progressPage("unchanged"),
      updated: progressPage("updated", { maxRatio: 0.8 }),
      added: progressPage("added", { maxRatio: 0.1 }),
    },
  };
  const incomingReviews = {
    ...emptyReviewState(now),
    items: {
      [ids[0]]: item("active", "2026-07-18T13:00:00.000Z", { reviewCount: 1 }),
      [ids[1]]: item("active", "2026-07-18T12:00:00.000Z"),
      [ids[2]]: item("removed", "2026-07-18T13:00:00.000Z"),
      [ids[3]]: item("active", "2026-07-18T13:00:00.000Z"),
      [ids[4]]: item("active", "2026-07-18T11:00:00.000Z"),
    },
  };
  const prepared = prepareLearningStateImport(JSON.stringify(envelope({
    preferences: { ...preferences, theme: "dark", contentWidth: "wide" },
    progress: incomingProgress,
    reviews: incomingReviews,
  })), current, ids, now);

  assert.equal(prepared.ok, true);
  assert.deepEqual(prepared.preview.preferences, {
    added: 0,
    updated: 2,
    removed: 0,
    unchanged: 1,
  });
  assert.deepEqual(prepared.preview.progress, {
    added: 1,
    updated: 2,
    removed: 1,
    unchanged: 1,
  });
  assert.deepEqual(prepared.preview.reviews, {
    added: 1,
    updated: 1,
    keptLocal: 1,
    unchanged: 1,
    removed: 1,
  });
});

test("a newer cross-tab tombstone invalidates and wins over an old import preview", () => {
  const baseline = { preferences, progress, reviews };
  const oldImport = JSON.stringify(envelope());
  const preview = prepareLearningStateImport(oldImport, baseline, [node.id], now);
  assert.equal(preview.ok, true);

  const removed = applyReviewAction(reviews, node, "remove", new Date("2026-07-18T13:00:00.000Z"));
  const latest = { preferences, progress, reviews: removed };
  assert.notEqual(learningStateToken(latest), learningStateToken(baseline));

  const refreshed = prepareLearningStateImport(oldImport, latest, [node.id], new Date("2026-07-18T13:00:01.000Z"));
  assert.equal(refreshed.ok, true);
  assert.equal(refreshed.preview.reviews.keptLocal, 1);
  assert.equal(refreshed.nextState.reviews.items[node.id].state, "removed");
});

test("progress import accepts only same-origin /math/ pages and safe anchors", () => {
  const slug = "calc-01-inverse-function";
  const validProgress = {
    schemaVersion: 1,
    recentSlug: slug,
    pages: {
      [slug]: progressPage(slug, {
        lastAnchor: "LWR-ht-knowledge:MATH1-KN-CALC-0008",
      }),
    },
  };
  const accepted = prepareLearningStateImport(
    JSON.stringify(envelope({ progress: validProgress })),
    { preferences, progress, reviews },
    [node.id],
    now,
  );
  assert.equal(accepted.ok, true);

  const unsafePages = [
    progressPage(slug, { url: "javascript:alert(1)" }),
    progressPage(slug, { url: "https://evil.example/math/calc-01-inverse-function" }),
    progressPage(slug, { url: "//evil.example/math/calc-01-inverse-function" }),
    progressPage(slug, { url: `/math/${slug}?mode=evil` }),
    progressPage(slug, { url: `/math/${slug}#other` }),
    progressPage(slug, { url: "/math/other-page" }),
    progressPage(slug, { lastAnchor: `bad\" onclick=\"alert(1)` }),
    progressPage(slug, { updatedAt: "not-a-time" }),
  ];
  const current = { preferences, progress, reviews };
  const before = structuredClone(current);
  for (const page of unsafePages) {
    const result = prepareLearningStateImport(
      JSON.stringify(envelope({
        progress: { schemaVersion: 1, recentSlug: slug, pages: { [slug]: page } },
      })),
      current,
      [node.id],
      now,
    );
    assert.equal(result.ok, false);
    assert.equal(result.nextState, null);
    assert.deepEqual(current, before);
  }
});

test("transactional storage restores every key when the second write fails", () => {
  const values = new Map([
    [PREFERENCES_KEY, '{"old":"preferences"}'],
    [PROGRESS_KEY, '{"old":"progress"}'],
    [REVIEW_STORAGE_KEY, '{"old":"reviews"}'],
  ]);
  let writes = 0;
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      writes += 1;
      if (writes === 2) throw new Error("injected failure");
      values.set(key, value);
    },
    removeItem: (key) => values.delete(key),
  };
  const committed = transactionalJSONWrite(storage, [
    [PREFERENCES_KEY, '{"new":"preferences"}'],
    [PROGRESS_KEY, '{"new":"progress"}'],
    [REVIEW_STORAGE_KEY, '{"new":"reviews"}'],
  ]);
  assert.equal(committed, false);
  assert.deepEqual(Object.fromEntries(values), {
    [PREFERENCES_KEY]: '{"old":"preferences"}',
    [PROGRESS_KEY]: '{"old":"progress"}',
    [REVIEW_STORAGE_KEY]: '{"old":"reviews"}',
  });
});
