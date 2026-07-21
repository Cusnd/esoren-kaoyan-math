import { sitePath } from "./site.js";

const INDEX_URL = sitePath("data/search-index.json");
let indexPromise;
let returnFocus = null;

function normalize(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .toLocaleLowerCase("zh-CN")
    .replace(/\s+/g, " ")
    .trim();
}

function stringArray(value) {
  if (Array.isArray(value)) return value.map(String);
  return value == null ? [] : [String(value)];
}

function documentsFrom(payload) {
  const documents = Array.isArray(payload)
    ? payload
    : payload?.items ?? payload?.documents ?? payload?.pages ?? [];
  return documents.map((item) => ({
    ...item,
    id: String(item.id ?? ""),
    itemType: String(item.itemType ?? item.item_type ?? "page"),
    slug: String(item.slug ?? ""),
    url: String(item.url ?? sitePath(item.slug)),
    title: String(item.title ?? "未命名页面"),
    subject: String(item.subject ?? ""),
    lecture: String(item.lecture ?? ""),
    problemIds: stringArray(item.problemIds ?? item.problem_ids ?? item.problemId ?? (item.itemType === "problem" ? item.id : [])),
    knowledgeIds: stringArray(item.knowledgeIds ?? item.knowledge_ids ?? (item.itemType === "knowledge" ? item.id : [])),
    collection: String(item.collection ?? "core"),
    chapterKey: String(item.chapterKey ?? item.chapter_key ?? ""),
    tags: stringArray(item.tags),
    reviewable: item.reviewable !== false,
    difficulty: String(item.difficulty ?? ""),
    headings: stringArray(item.headings),
    body: String(item.body ?? item.text ?? ""),
    tex: String(item.tex ?? item.source ?? ""),
  }));
}

async function loadIndex() {
  if (!indexPromise) {
    indexPromise = fetch(INDEX_URL, { credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) throw new Error(`Search index ${response.status}`);
        return response.json();
      })
      .then(documentsFrom)
      .catch((error) => {
        indexPromise = undefined;
        throw error;
      });
  }
  return indexPromise;
}

function scoreDocument(document, rawQuery) {
  const query = normalize(rawQuery);
  if (!query) return 0;
  const terms = query.split(" ").filter(Boolean);
  const title = normalize(document.title);
  const problemIds = document.problemIds.map(normalize);
  const knowledgeIds = document.knowledgeIds.map(normalize);
  const tags = normalize(document.tags.join(" "));
  const meta = normalize(
    [document.subject, document.lecture, document.difficulty, document.collection, document.chapterKey].join(" "),
  );
  const headings = normalize(document.headings.join(" "));
  const body = normalize(document.body);
  const tex = normalize(document.tex);
  const searchable = [title, document.id, problemIds.join(" "), knowledgeIds.join(" "), tags, meta, headings, body, tex].join(" ");
  if (!terms.every((term) => searchable.includes(term))) return 0;

  let score = 1;
  if (problemIds.some((id) => id === query)) score += 10000;
  else if (problemIds.some((id) => id.startsWith(query))) score += 7600;
  if (knowledgeIds.some((id) => id === query)) score += 9800;
  else if (knowledgeIds.some((id) => id.startsWith(query))) score += 7200;
  if (title === query) score += 7000;
  else if (title.startsWith(query)) score += 5200;
  else if (title.includes(query)) score += 3600;
  if (document.tags.some((tag) => normalize(tag) === query)) score += 2400;
  else if (tags.includes(query)) score += 1800;
  if (headings.includes(query)) score += 1300;
  if (meta.includes(query)) score += 900;
  if (body.includes(query)) score += 420;
  if (tex.includes(query)) score += 360;
  return score;
}

function excerptFor(document, query) {
  const source = document.body || document.tex || document.headings.join(" ");
  const normalizedSource = normalize(source);
  const normalizedQuery = normalize(query).split(" ")[0] || "";
  const index = normalizedSource.indexOf(normalizedQuery);
  const start = Math.max(0, index < 0 ? 0 : index - 42);
  const text = source.slice(start, start + 120).replace(/\s+/g, " ").trim();
  return `${start > 0 ? "…" : ""}${text}${start + 120 < source.length ? "…" : ""}`;
}

function appendHighlighted(parent, text, query) {
  const terms = [...new Set(normalize(query).split(" ").filter(Boolean))]
    .sort((a, b) => b.length - a.length);
  if (terms.length === 0) {
    parent.append(document.createTextNode(text));
    return;
  }
  const pattern = new RegExp(
    `(${terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "giu",
  );
  let offset = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > offset) parent.append(document.createTextNode(text.slice(offset, match.index)));
    const mark = document.createElement("mark");
    mark.textContent = match[0];
    parent.append(mark);
    offset = match.index + match[0].length;
  }
  if (offset < text.length) parent.append(document.createTextNode(text.slice(offset)));
}

function resultElement(item, query) {
  const li = window.document.createElement("li");
  li.className = "reader-search-result";
  const link = window.document.createElement("a");
  link.href = item.url;

  const title = window.document.createElement("span");
  title.className = "reader-search-result__title";
  appendHighlighted(title, item.title, query);

  const meta = window.document.createElement("span");
  meta.className = "reader-search-result__meta";
  meta.textContent = [
    item.collection === "practice"
      ? "练习库"
      : item.itemType === "knowledge"
        ? item.reviewable ? "知识节点" : "边界知识"
        : "主库",
    item.subject,
    item.lecture,
    ...item.problemIds.slice(0, 1),
    ...item.knowledgeIds.slice(0, 1),
  ].filter(Boolean).join(" · ");

  const excerpt = window.document.createElement("span");
  excerpt.className = "reader-search-result__excerpt";
  appendHighlighted(excerpt, excerptFor(item, query), query);
  link.append(title, meta, excerpt);
  li.append(link);
  return li;
}

function openDialog(dialog, input, trigger) {
  if (!dialog) return;
  if (dialog.open || dialog.classList.contains("is-open")) {
    input?.focus();
    return;
  }
  dialog.classList.add("reader-dialog");
  returnFocus = trigger instanceof HTMLElement ? trigger : null;
  document.body.classList.add("reader-modal-open");
  if (typeof dialog.showModal === "function") dialog.showModal();
  else {
    dialog.hidden = false;
    dialog.classList.add("is-open");
    dialog.setAttribute("aria-modal", "true");
  }
  requestAnimationFrame(() => input?.focus());
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

export function initSearch() {
  const dialog = document.getElementById("reader-search");
  const input = dialog?.querySelector("[data-reader-search-input]");
  const results = dialog?.querySelector("[data-reader-search-results]");
  const status = dialog?.querySelector("[data-reader-search-status]");
  if (!dialog || !input || !results || !status) return;
  dialog.classList.add("reader-dialog");
  input.placeholder ||= "搜索题目、知识点或公式";
  let request = 0;

  const search = async () => {
    const query = input.value.trim();
    const current = ++request;
    results.replaceChildren();
    if (!query) {
      status.textContent = "输入题号、标题、讲次、标签、正文或 TeX 源串。";
      return;
    }
    status.textContent = "正在搜索…";
    try {
      const documents = await loadIndex();
      if (current !== request) return;
      const matches = documents
        .map((document) => ({ document, score: scoreDocument(document, query) }))
        .filter(({ score }) => score > 0)
        .sort((a, b) => b.score - a.score || a.document.title.localeCompare(b.document.title, "zh-CN"))
        .slice(0, 20);
      matches.forEach(({ document }) => results.append(resultElement(document, query)));
      status.textContent = matches.length
        ? `找到 ${matches.length} 条结果。`
        : "没有找到匹配内容。";
    } catch {
      if (current !== request) return;
      status.textContent = navigator.onLine
        ? "搜索索引暂时不可用，请稍后重试。"
        : "搜索索引尚未离线保存，请联网打开一次首页。";
    }
  };

  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(search, 110);
  });

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-reader-action]");
    const action = trigger?.dataset.readerAction;
    if (action === "open-search") {
      event.preventDefault();
      openDialog(dialog, input, trigger);
      if (input.value) search();
    } else if (action === "close-search") {
      event.preventDefault();
      closeDialog(dialog);
    }
  });

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const isEditing = target instanceof HTMLInputElement
      || target instanceof HTMLTextAreaElement
      || target instanceof HTMLSelectElement
      || target?.isContentEditable;
    if (((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k")
      || (event.key === "/" && !isEditing && !event.ctrlKey && !event.metaKey && !event.altKey)) {
      event.preventDefault();
      openDialog(dialog, input, null);
    }
  });

  dialog.addEventListener("close", () => {
    document.body.classList.remove("reader-modal-open");
  });
}
