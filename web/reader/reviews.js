import { getPageContext } from "./context.js";
import {
  PREFERENCES_KEY,
  PROGRESS_KEY,
  readJSON,
  subscribeJSON,
  writeJSON,
  writeJSONBatch,
} from "./storage.js";
import { sitePath } from "./site.js";
import {
  LEARNING_STATE_SCHEMA_VERSION,
  LEARNING_STATE_TYPE,
  MAX_LEARNING_STATE_BYTES,
  learningStateToken,
  prepareLearningStateImport,
} from "./learning-state.js";
import {
  REVIEW_SCHEDULE_ID,
  REVIEW_SCHEMA_VERSION,
  REVIEW_STORAGE_KEY,
  applyReviewAction,
  dueReviewIds,
  emptyReviewState,
  localDate,
  millisecondsUntilNextLocalMidnight,
  normalizeReviewState,
  reviewDateChanged,
  reviewExportPayload,
} from "./review-core.js";

const RELATION_INDEX_URL = sitePath("data/relation-index.json");
const CONTENT_MANIFEST_URL = sitePath("data/content-manifest.json");
let relationPromise;
let manifestPromise;
let rowSequence = 0;
const DEFAULT_PREFERENCES = Object.freeze({
  schemaVersion: 1,
  theme: "light",
  fontScale: "medium",
  contentWidth: "standard",
});
const DEFAULT_PROGRESS = Object.freeze({ schemaVersion: 1, recentSlug: null, pages: {} });

function stringArray(value) {
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  return value == null ? [] : [String(value)].filter(Boolean);
}

function normalizeRelations(payload) {
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const edges = Array.isArray(payload?.edges) ? payload.edges : [];
  const adjacency = payload?.adjacency && typeof payload.adjacency === "object" && !Array.isArray(payload.adjacency)
    ? Object.fromEntries(Object.entries(payload.adjacency).map(([id, links]) => [
      String(id),
      (Array.isArray(links) ? links : []).map((link) => ({
        nodeId: String(link.nodeId ?? ""),
        type: String(link.type ?? ""),
        direction: String(link.direction ?? ""),
      })).filter((link) => link.nodeId && link.type && ["incoming", "outgoing", "symmetric"].includes(link.direction)),
    ]))
    : {};
  return {
    schemaVersion: Number(payload?.schemaVersion ?? payload?.schema_version ?? 1),
    buildId: String(payload?.buildId ?? ""),
    nodes: nodes.map((node) => ({
      ...node,
      id: String(node.id ?? ""),
      title: String(node.title ?? node.id ?? "未命名知识节点"),
      kind: String(node.kind ?? "concept"),
      subject: String(node.subject ?? ""),
      chapterKey: String(node.chapterKey ?? node.chapter_key ?? ""),
      aliases: stringArray(node.aliases),
      reviewable: node.reviewable !== false,
      url: String(node.url ?? ""),
    })).filter((node) => node.id),
    edges: edges.map((edge) => ({
      source: String(edge.source ?? ""),
      target: String(edge.target ?? ""),
      type: String(edge.type ?? ""),
    })).filter((edge) => edge.source && edge.target && edge.type),
    adjacency,
    problemLinks: (Array.isArray(payload?.problemLinks) ? payload.problemLinks : []).map((link) => ({
      problemId: String(link.problemId ?? link.problem_id ?? ""),
      title: String(link.title ?? link.problemId ?? link.problem_id ?? "未命名题目"),
      collection: String(link.collection ?? "core"),
      url: String(link.url ?? ""),
      knowledgeIds: stringArray(link.knowledgeIds ?? link.knowledge_ids),
      methodIds: stringArray(link.methodIds ?? link.method_ids),
      pitfallIds: stringArray(link.pitfallIds ?? link.pitfall_ids),
    })).filter((link) => link.problemId),
  };
}

async function loadRelations() {
  if (!relationPromise) {
    relationPromise = fetch(RELATION_INDEX_URL, { credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) throw new Error(`Relation index ${response.status}`);
        return response.json();
      })
      .then(normalizeRelations)
      .catch((error) => {
        relationPromise = undefined;
        throw error;
      });
  }
  return relationPromise;
}

async function loadManifest() {
  if (!manifestPromise) {
    manifestPromise = fetch(CONTENT_MANIFEST_URL, { credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) throw new Error(`Content manifest ${response.status}`);
        return response.json();
      });
  }
  return manifestPromise;
}

function nodeLink(node) {
  if (!node.url) {
    const span = document.createElement("span");
    span.textContent = node.title;
    return span;
  }
  const link = document.createElement("a");
  link.href = node.url;
  link.textContent = node.title;
  return link;
}

function nodeRow(node, state, { selected = false, compact = false } = {}) {
  const row = document.createElement("article");
  row.className = `reader-review-node${compact ? " reader-review-node--compact" : ""}`;
  row.dataset.reviewNode = node.id;

  const label = document.createElement("div");
  label.append(nodeLink(node));
  const meta = document.createElement("small");
  meta.textContent = [node.id, node.subject, node.chapterKey].filter(Boolean).join(" · ");
  label.append(meta);

  if (node.reviewable === false) {
    row.classList.add("reader-review-node--boundary");
    const boundary = document.createElement("span");
    boundary.className = "reader-review-node__boundary";
    boundary.textContent = "边界知识 · 不加入复习";
    label.append(boundary);
    row.append(label);
    return row;
  }

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.name = "review-node";
  checkbox.value = node.id;
  checkbox.checked = selected;
  checkbox.dataset.reviewSelect = "";
  checkbox.id = `review-node-${++rowSequence}`;

  const linkedLabel = document.createElement("label");
  linkedLabel.append(...label.childNodes);
  label.remove();
  linkedLabel.htmlFor = checkbox.id;

  const item = state.items[node.id];
  const action = document.createElement("button");
  action.type = "button";
  action.dataset.readerReviewNode = node.id;
  if (item?.state === "active") {
    action.dataset.readerReviewAction = "remove";
    action.textContent = "移出复习";
    const due = document.createElement("span");
    due.className = "reader-review-node__due";
    due.textContent = `下次：${item.dueOn}`;
    linkedLabel.append(due);
  } else {
    action.dataset.readerReviewAction = "add";
    action.textContent = "加入复习";
  }
  row.append(checkbox, linkedLabel, action);
  return row;
}

function dueRow(node, state) {
  const item = state.items[node.id];
  const row = document.createElement("article");
  row.className = "reader-review-due";
  row.dataset.reviewNode = node.id;
  const selection = document.createElement("input");
  selection.type = "checkbox";
  selection.name = "review-node";
  selection.value = node.id;
  selection.dataset.reviewSelect = "";
  selection.checked = true;
  selection.id = `review-due-${++rowSequence}`;
  const heading = document.createElement("h3");
  const label = document.createElement("label");
  label.htmlFor = selection.id;
  label.append(nodeLink(node));
  heading.append(label);
  const meta = document.createElement("p");
  meta.textContent = `到期：${item.dueOn} · 已复习 ${item.reviewCount} 次`;
  const actions = document.createElement("div");
  actions.className = "reader-review-due__actions";
  for (const [action, text] of [
    ["reviewed", "已复习"],
    ["still-weak", "仍不熟"],
    ["tomorrow", "明天提醒"],
    ["remove", "移出复习"],
  ]) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.readerReviewNode = node.id;
    button.dataset.readerReviewAction = action;
    button.textContent = text;
    actions.append(button);
  }
  row.append(selection, heading, meta, actions);
  return row;
}

function setLiveStatus(message) {
  document.querySelectorAll("[data-reader-review-status]").forEach((element) => {
    element.textContent = message;
  });
}

function selectedNodes(root, nodeMap) {
  const ids = [...root.querySelectorAll("[data-review-select]:checked")].map((input) => input.value);
  return [...new Set(ids)].map((id) => nodeMap.get(id)).filter(Boolean);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const input = document.createElement("textarea");
    input.value = text;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.append(input);
    input.select();
    const copied = document.execCommand("copy");
    input.remove();
    if (!copied) throw new Error("copy failed");
  }
}

function promptFor(kind, nodes) {
  const lines = nodes.map((node) => `- ${node.id}：${node.title}`).join("\n");
  if (kind === "practice") {
    return `请先阅读当前仓库 AGENTS.md，并加载 $kaoyan-math1-fullscore-coach。\n学习意图：围绕以下知识节点生成有区分度的练习，先查重，按 Skill 规则进入练习库并完成验证：\n${lines}`;
  }
  return `请先阅读当前仓库 AGENTS.md，并加载 $kaoyan-math1-fullscore-coach。\n学习意图：带我复习以下知识节点；先做最小诊断，再按需逐级提示，最后给一个主动回忆或迁移动作：\n${lines}`;
}

function downloadJSON(filename, payload) {
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function relationGroups(currentIds, index, nodeMap) {
  const selected = new Set(currentIds);
  const groups = new Map([
    ["前置知识", []],
    ["可继续推广", []],
    ["后续知识", []],
    ["对比辨析", []],
    ["同构结构", []],
  ]);
  const add = (label, id) => {
    const node = nodeMap.get(id);
    if (!node || selected.has(id) || groups.get(label).some((item) => item.id === id)) return;
    groups.get(label).push(node);
  };
  for (const id of selected) {
    for (const link of index.adjacency[id] ?? []) {
      if (link.type === "prerequisite_for") {
        add(link.direction === "incoming" ? "前置知识" : "后续知识", link.nodeId);
      } else if (link.type === "generalizes_to") {
        add(link.direction === "incoming" ? "前置知识" : "可继续推广", link.nodeId);
      } else if (link.type === "contrasts_with" && link.direction === "symmetric") {
        add("对比辨析", link.nodeId);
      } else if (link.type === "same_structure_as" && link.direction === "symmetric") {
        add("同构结构", link.nodeId);
      }
    }
  }
  return groups;
}

function availableMethods(currentIds, index, nodeMap) {
  const selected = new Set(currentIds);
  const methods = new Map();
  const add = (id) => {
    const node = nodeMap.get(id);
    if (node?.kind === "method") methods.set(node.id, node);
  };
  currentIds.forEach(add);
  for (const id of selected) (index.adjacency[id] ?? []).forEach((link) => add(link.nodeId));
  return [...methods.values()];
}

function problemEvidence(currentIds, index) {
  const selected = new Set(currentIds);
  const links = index.problemLinks.filter((link) => [
    ...link.knowledgeIds,
    ...link.methodIds,
    ...link.pitfallIds,
  ].some((id) => selected.has(id)));
  return {
    core: links.filter((link) => link.collection === "core"),
    practice: links.filter((link) => link.collection === "practice"),
  };
}

function problemEvidenceSection(title, links, emptyText) {
  const section = document.createElement("section");
  const heading = document.createElement("h3");
  heading.textContent = title;
  const list = document.createElement("ul");
  if (links.length === 0) {
    const item = document.createElement("li");
    item.textContent = emptyText;
    list.append(item);
  } else {
    for (const link of links) {
      const item = document.createElement("li");
      if (link.url) {
        const anchor = document.createElement("a");
        anchor.href = link.url;
        anchor.textContent = `${link.problemId} · ${link.title}`;
        item.append(anchor);
      } else {
        item.textContent = `${link.problemId} · ${link.title}`;
      }
      list.append(item);
    }
  }
  section.append(heading, list);
  return section;
}

function renderRelations(index, state) {
  const context = getPageContext();
  const ids = stringArray(context.knowledgeIds ?? context.knowledge_ids);
  if (context.isHome || ids.length === 0) return;
  const nodeMap = new Map(index.nodes.map((node) => [node.id, node]));
  const current = ids.map((id) => nodeMap.get(id)).filter(Boolean);
  if (current.length === 0) return;

  let section = document.querySelector("[data-reader-relations]");
  if (!section) {
    section = document.createElement("section");
    section.className = "reader-relations";
    section.dataset.readerRelations = "";
    section.setAttribute("aria-labelledby", "reader-relations-title");
    document.querySelector(".reader-page-nav")?.before(section);
  }
  section.replaceChildren();
  const heading = document.createElement("h2");
  heading.id = "reader-relations-title";
  heading.textContent = "知识关系与复习";
  const intro = document.createElement("p");
  intro.textContent = "这里只展示一跳关系；边界知识可查阅但不加入本地复习，阅读进度也不会自动改变复习状态。";
  const currentGroup = document.createElement("div");
  currentGroup.className = "reader-relations__current";
  current.forEach((node) => currentGroup.append(nodeRow(node, state, { selected: true, compact: true })));
  section.append(heading, intro, currentGroup);

  const groups = relationGroups(ids, index, nodeMap);
  const methods = availableMethods(ids, index, nodeMap);
  const evidence = problemEvidence(ids, index);
  const methodsSection = document.createElement("section");
  methodsSection.className = "reader-relations__methods";
  const methodsHeading = document.createElement("h3");
  methodsHeading.textContent = "可用方法";
  const methodsList = document.createElement("div");
  if (methods.length) methods.forEach((node) => methodsList.append(nodeRow(node, state, { compact: true })));
  else methodsList.textContent = "当前显式关系中暂无方法节点。";
  methodsSection.append(methodsHeading, methodsList);
  section.append(methodsSection);
  const grid = document.createElement("div");
  grid.className = "reader-relations__grid";
  for (const [label, nodes] of groups) {
    if (nodes.length === 0) continue;
    const group = document.createElement("section");
    const groupHeading = document.createElement("h3");
    groupHeading.textContent = label;
    const list = document.createElement("div");
    nodes.forEach((node) => list.append(nodeRow(node, state, { compact: true })));
    group.append(groupHeading, list);
    grid.append(group);
  }
  section.append(grid);
  const evidenceGrid = document.createElement("div");
  evidenceGrid.className = "reader-relations__evidence";
  evidenceGrid.append(
    problemEvidenceSection("关联主库题", evidence.core, "暂无关联主库题。"),
    problemEvidenceSection("关联练习题", evidence.practice, "暂无已验证关联练习题。"),
  );
  section.append(evidenceGrid);
  const promptActions = document.createElement("div");
  promptActions.className = "reader-review-prompts";
  promptActions.innerHTML = '<button type="button" data-reader-review-copy="review">复制复习提示词</button><button type="button" data-reader-review-copy="practice">复制出题提示词</button><span data-reader-review-status aria-live="polite"></span>';
  section.append(promptActions);
}

function renderReviewSurfaces(index, state) {
  const nodeMap = new Map(index.nodes.map((node) => [node.id, node]));
  const due = dueReviewIds(state).map((id) => nodeMap.get(id)).filter((node) => node?.reviewable !== false);
  document.querySelectorAll("[data-reader-review-count]").forEach((element) => {
    element.textContent = String(due.length);
    element.hidden = due.length === 0;
  });
  const home = document.querySelector("[data-reader-review-home]");
  if (home) {
    const summary = home.querySelector("[data-reader-review-home-summary]");
    if (summary) summary.textContent = due.length ? `今天有 ${due.length} 个知识节点需要复习。` : "今天没有到期节点。";
  }
  const dueContainer = document.querySelector("[data-reader-review-due]");
  if (dueContainer) {
    dueContainer.replaceChildren();
    if (due.length === 0) {
      const empty = document.createElement("p");
      empty.textContent = "今天没有到期节点。可以从下方知识网络加入复习。";
      dueContainer.append(empty);
    } else {
      due.forEach((node) => dueContainer.append(dueRow(node, state)));
    }
  }
  const allContainer = document.querySelector("[data-reader-review-all]");
  if (allContainer) {
    allContainer.replaceChildren();
    index.nodes.filter((node) => node.reviewable !== false).forEach((node) => allContainer.append(nodeRow(node, state)));
  }
  renderRelations(index, state);
}

function openDialog(dialog, trigger) {
  if (!dialog) return;
  dialog.dataset.returnFocus = trigger?.id ?? "";
  document.body.classList.add("reader-modal-open");
  if (typeof dialog.showModal === "function") dialog.showModal();
  else {
    dialog.hidden = false;
    dialog.classList.add("is-open");
    dialog.setAttribute("aria-modal", "true");
  }
  dialog.querySelector("button, input")?.focus();
}

function closeDialog(dialog) {
  if (!dialog) return;
  if (typeof dialog.close === "function" && dialog.open) dialog.close();
  else {
    dialog.hidden = true;
    dialog.classList.remove("is-open");
  }
  document.body.classList.remove("reader-modal-open");
  const returnFocus = dialog.dataset.returnFocus && document.getElementById(dialog.dataset.returnFocus);
  returnFocus?.focus();
}

function previewLine(label, counts) {
  return `${label}：新增 ${counts.added}，更新 ${counts.updated}，移除 ${counts.removed}，未变 ${counts.unchanged}${counts.keptLocal ? `，保留本地较新 ${counts.keptLocal}` : ""}。`;
}

export function initReviews() {
  const dialog = document.getElementById("reader-review");
  if (dialog) dialog.classList.add("reader-dialog", "reader-review-dialog");
  let state = normalizeReviewState(readJSON(REVIEW_STORAGE_KEY, emptyReviewState()));
  let index;
  let pendingImport = null;
  let renderedDate = localDate();
  let midnightTimer;
  let clockInterval;
  const previewElement = dialog?.querySelector("[data-reader-review-import-preview]");
  const applyButton = dialog?.querySelector('[data-reader-action="apply-review-import"]');

  const currentBundle = () => ({
    preferences: readJSON(PREFERENCES_KEY, DEFAULT_PREFERENCES),
    progress: readJSON(PROGRESS_KEY, DEFAULT_PROGRESS),
    reviews: state,
  });

  const invalidatePendingImport = (message = "本地状态已变化，导入预览已失效；请重新选择文件。") => {
    if (!pendingImport) return;
    pendingImport = null;
    if (applyButton) applyButton.hidden = true;
    if (previewElement) previewElement.textContent = message;
  };

  const renderForCurrentDate = () => {
    const now = new Date();
    if (reviewDateChanged(renderedDate, now)) {
      renderedDate = localDate(now);
      if (index) renderReviewSurfaces(index, state);
    }
    clearTimeout(midnightTimer);
    midnightTimer = setTimeout(renderForCurrentDate, millisecondsUntilNextLocalMidnight(now) + 50);
  };

  const startClockRefresh = () => {
    renderForCurrentDate();
    clearInterval(clockInterval);
    clockInterval = setInterval(renderForCurrentDate, 60_000);
  };

  const ready = loadRelations().then((loaded) => {
    index = loaded;
    renderReviewSurfaces(index, state);
    return loaded;
  }).catch(() => {
    setLiveStatus(navigator.onLine ? "知识关系索引暂时不可用。" : "知识关系索引尚未离线保存。 ");
    return null;
  });

  subscribeJSON(REVIEW_STORAGE_KEY, (value) => {
    state = normalizeReviewState(value);
    invalidatePendingImport();
    if (index) renderReviewSurfaces(index, state);
  });
  subscribeJSON(PREFERENCES_KEY, () => invalidatePendingImport());
  subscribeJSON(PROGRESS_KEY, () => invalidatePendingImport());
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") renderForCurrentDate();
  });
  window.addEventListener("pageshow", startClockRefresh);
  startClockRefresh();

  document.addEventListener("click", async (event) => {
    const actionElement = event.target.closest("[data-reader-review-action]");
    if (actionElement) {
      event.preventDefault();
      const loaded = index ?? await ready;
      const node = loaded?.nodes.find((item) => item.id === actionElement.dataset.readerReviewNode);
      if (!node) return;
      if (node.reviewable === false) {
        setLiveStatus("边界知识只供检索，不进入本地复习。 ");
        return;
      }
      state = applyReviewAction(state, node, actionElement.dataset.readerReviewAction);
      const persisted = writeJSON(REVIEW_STORAGE_KEY, state);
      setLiveStatus(persisted
        ? "复习提醒已保存在当前浏览器。 "
        : "浏览器无法持久化；复习提醒仅在本次页面打开期间临时保存。 ");
      return;
    }

    const trigger = event.target.closest("[data-reader-action]");
    const action = trigger?.dataset.readerAction;
    if (action === "open-review") {
      event.preventDefault();
      if (trigger && !trigger.id) trigger.id = `reader-review-trigger-${++rowSequence}`;
      openDialog(dialog, trigger);
    } else if (action === "close-review") {
      event.preventDefault();
      closeDialog(dialog);
    } else if (action === "export-review-state") {
      event.preventDefault();
      const manifest = await loadManifest().catch(() => ({}));
      const payload = {
        schemaVersion: LEARNING_STATE_SCHEMA_VERSION,
        type: LEARNING_STATE_TYPE,
        buildId: String(manifest.buildId ?? getPageContext().buildId ?? ""),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "local",
        exportedAt: new Date().toISOString(),
        preferences: readJSON(PREFERENCES_KEY, DEFAULT_PREFERENCES),
        progress: readJSON(PROGRESS_KEY, DEFAULT_PROGRESS),
        reviews: reviewExportPayload(state),
      };
      downloadJSON(`math1-learning-state-${localDate()}.json`, payload);
      setLiveStatus("已导出本地学习状态。 ");
    } else if (action === "apply-review-import" && pendingImport) {
      event.preventDefault();
      const loaded = index ?? await ready;
      if (!loaded) return;
      const latest = currentBundle();
      if (learningStateToken(latest) !== pendingImport.baseToken) {
        invalidatePendingImport();
        return;
      }
      const refreshed = prepareLearningStateImport(
        pendingImport.raw,
        latest,
        {
          knownNodeIds: loaded.nodes.map((node) => node.id),
          reviewableNodeIds: loaded.nodes.filter((node) => node.reviewable !== false).map((node) => node.id),
        },
      );
      if (!refreshed.ok) {
        invalidatePendingImport(`导入重新校验失败：${refreshed.errors.join(" ")} 未修改任何本地状态。`);
        return;
      }
      pendingImport = null;
      trigger.hidden = true;
      const committed = writeJSONBatch([
        [PREFERENCES_KEY, refreshed.nextState.preferences],
        [PROGRESS_KEY, refreshed.nextState.progress],
        [REVIEW_STORAGE_KEY, refreshed.nextState.reviews],
      ]);
      if (committed) {
        state = refreshed.nextState.reviews;
        setLiveStatus("导入已应用；其他已打开标签页会自动同步。 ");
      } else {
        setLiveStatus("写入失败，原有学习状态保持不变。 ");
      }
    }

    const copy = event.target.closest("[data-reader-review-copy]");
    if (copy) {
      event.preventDefault();
      const loaded = index ?? await ready;
      if (!loaded) return;
      const root = copy.closest("[data-reader-relations], #reader-review") ?? document;
      const nodes = selectedNodes(root, new Map(loaded.nodes.map((node) => [node.id, node])));
      if (nodes.length === 0) {
        setLiveStatus("请至少选择一个知识节点。 ");
        return;
      }
      try {
        await copyText(promptFor(copy.dataset.readerReviewCopy, nodes));
        setLiveStatus("提示词已复制。 ");
      } catch {
        setLiveStatus("复制失败，请检查浏览器的剪贴板权限。 ");
      }
    }
  });

  const input = dialog?.querySelector("[data-reader-review-import]");
  input?.addEventListener("change", async () => {
    const file = input.files?.[0];
    const loaded = index ?? await ready;
    pendingImport = null;
    if (applyButton) applyButton.hidden = true;
    if (!file || !loaded) return;
    try {
      if (file.size > MAX_LEARNING_STATE_BYTES) throw new Error("导入文件超过 1 MiB。 ");
      const raw = await file.text();
      const baseline = currentBundle();
      const prepared = prepareLearningStateImport(
        raw,
        baseline,
        {
          knownNodeIds: loaded.nodes.map((node) => node.id),
          reviewableNodeIds: loaded.nodes.filter((node) => node.reviewable !== false).map((node) => node.id),
        },
      );
      if (!prepared.ok) throw new Error(prepared.errors.join("\n"));
      pendingImport = { raw, baseToken: learningStateToken(baseline) };
      const counts = prepared.preview;
      previewElement.textContent = [
        previewLine("阅读偏好", counts.preferences),
        previewLine("阅读进度", counts.progress),
        previewLine("复习状态", counts.reviews),
        ...prepared.warnings,
        "确认前不会修改浏览器状态。",
      ].join("\n");
      if (applyButton) applyButton.hidden = false;
    } catch (error) {
      previewElement.textContent = `导入失败：${error.message} 未修改任何本地状态。`;
    } finally {
      input.value = "";
    }
  });

  dialog?.addEventListener("close", () => document.body.classList.remove("reader-modal-open"));
}

export const REVIEW_EXPORT_CONTRACT = Object.freeze({
  schemaVersion: LEARNING_STATE_SCHEMA_VERSION,
  type: LEARNING_STATE_TYPE,
  reviewSchemaVersion: REVIEW_SCHEMA_VERSION,
  scheduleId: REVIEW_SCHEDULE_ID,
});
