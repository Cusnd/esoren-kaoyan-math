import assert from "node:assert/strict";
import test from "node:test";

import {
  REVIEW_INTERVAL_DAYS,
  REVIEW_SCHEDULE_ID,
  addLocalDays,
  applyReviewAction,
  dueReviewIds,
  emptyReviewState,
  isLocalDate,
  localDate,
  millisecondsUntilNextLocalMidnight,
  prepareReviewImport,
  reviewExportPayload,
  reviewDateChanged,
} from "../../web/reader/review-core.js";

const node = { id: "MATH1-KN-CALC-0001", title: "函数极限" };
const now = new Date(2026, 6, 18, 20, 30, 0);

test("review schedule uses local calendar dates and the fixed ladder", () => {
  assert.deepEqual(REVIEW_INTERVAL_DAYS, [0, 1, 3, 7, 14, 30, 60, 120]);
  assert.equal(localDate(now), "2026-07-18");
  assert.equal(addLocalDays("2026-03-08", 1), "2026-03-09");
  assert.equal(isLocalDate("2026-02-28"), true);
  assert.equal(isLocalDate("2026-02-30"), false);
  assert.equal(isLocalDate("2026-99-99"), false);
  let state = applyReviewAction(emptyReviewState(now), node, "add", now);
  assert.equal(state.items[node.id].dueOn, "2026-07-18");
  assert.deepEqual(dueReviewIds(state, "2026-07-18"), [node.id]);

  state = applyReviewAction(state, node, "reviewed", now);
  assert.equal(state.items[node.id].step, 1);
  assert.equal(state.items[node.id].dueOn, "2026-07-19");
  state = applyReviewAction(state, node, "reviewed", new Date(2026, 6, 19, 8));
  assert.equal(state.items[node.id].step, 2);
  assert.equal(state.items[node.id].dueOn, "2026-07-22");
});

test("resident pages can schedule and detect a local date rollover", () => {
  const beforeMidnight = new Date(2026, 6, 18, 23, 59, 30, 0);
  assert.equal(millisecondsUntilNextLocalMidnight(beforeMidnight), 30_000);
  assert.equal(reviewDateChanged("2026-07-18", beforeMidnight), false);
  assert.equal(reviewDateChanged("2026-07-18", new Date(2026, 6, 19, 0, 0, 1)), true);
});

test("weak, tomorrow and remove actions never claim a score or mastery", () => {
  let state = applyReviewAction(emptyReviewState(now), node, "add", now);
  state = applyReviewAction(state, node, "still-weak", now);
  assert.equal(state.items[node.id].step, 0);
  assert.equal(state.items[node.id].dueOn, "2026-07-19");
  assert.equal(state.items[node.id].reviewCount, 1);
  state = applyReviewAction(state, node, "tomorrow", now);
  assert.equal(state.items[node.id].snoozeCount, 1);
  state = applyReviewAction(state, node, "remove", now);
  assert.equal(state.items[node.id].state, "removed");
  assert.equal(state.items[node.id].dueOn, null);
  assert.deepEqual(dueReviewIds(state, "2099-12-31"), []);
  assert.equal("score" in state.items[node.id], false);
  assert.equal("mastery" in state.items[node.id], false);
});

test("import preview is atomic and an older export cannot revive a tombstone", () => {
  const added = applyReviewAction(emptyReviewState(now), node, "add", now);
  const removed = applyReviewAction(added, node, "remove", new Date(2026, 6, 20, 9));
  const oldExport = reviewExportPayload(added, new Date(2026, 6, 19, 9));
  const prepared = prepareReviewImport(
    JSON.stringify(oldExport),
    removed,
    [node.id],
    new Date(2026, 6, 21, 9),
  );
  assert.equal(prepared.ok, true);
  assert.equal(prepared.preview.keptLocal, 1);
  assert.equal(prepared.nextState.items[node.id].state, "removed");
  assert.equal(removed.items[node.id].state, "removed", "preview must not mutate current state");
});

test("invalid imports fail without a candidate state", () => {
  const invalid = prepareReviewImport(
    { schemaVersion: 1, scheduleId: REVIEW_SCHEDULE_ID, items: { nope: {} } },
    emptyReviewState(now),
    [node.id],
    now,
  );
  assert.equal(invalid.ok, false);
  assert.equal(invalid.nextState, null);
  assert.ok(invalid.errors.length > 0);
});

test("review import rejects malformed metadata atomically instead of normalizing it", () => {
  const current = applyReviewAction(emptyReviewState(now), node, "add", now);
  const before = structuredClone(current);
  const valid = reviewExportPayload(current, now);
  const invalidItems = [
    { ...valid.items[node.id], lastReviewedOn: "not-a-date" },
    { ...valid.items[node.id], reviewCount: "1" },
    { ...valid.items[node.id], snoozeCount: -1 },
    { ...valid.items[node.id], labelSnapshot: { unsafe: true } },
    { ...valid.items[node.id], updatedAt: "not-a-time" },
    { ...valid.items[node.id], unexpected: true },
  ];

  for (const item of invalidItems) {
    const result = prepareReviewImport(
      { ...valid, items: { [node.id]: item } },
      current,
      [node.id],
      now,
    );
    assert.equal(result.ok, false);
    assert.equal(result.nextState, null);
    assert.deepEqual(current, before);
  }
});
