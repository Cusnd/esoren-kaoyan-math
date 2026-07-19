function answerIdFrom(value) {
  return String(value ?? "").match(/answer:(MATH1-(?:CALC|LA|PROB)-\d{4})/i)?.[1]?.toUpperCase() ?? "";
}

function precedingAnswerId($, node) {
  let cursor = $(node).prev();
  while (cursor.length) {
    const id = answerIdFrom(cursor.attr("id"));
    if (id) return id;
    if (cursor.hasClass("solution-box") || cursor.hasClass("problem-box")) break;
    cursor = cursor.prev();
  }
  return "";
}

export function collapsePracticeSolutions($, main) {
  main.find(".solution-box").each((_, node) => {
    const problemId = precedingAnswerId($, node);
    const wrapper = $('<details class="reader-practice-answer"><summary>查看答案与解析</summary></details>');
    if (problemId) wrapper.attr("data-answer-for", problemId);
    $(node).replaceWith(wrapper);
    wrapper.append(node);
  });
}

export function solutionForProblem($, root, problemBox, problemId) {
  const normalizedId = String(problemId).toUpperCase();
  const paired = root.find("details.reader-practice-answer").filter((_, node) => (
    String($(node).attr("data-answer-for") ?? "").toUpperCase() === normalizedId
  )).first().find(".solution-box").first();
  if (paired.length) return paired;

  const answerAnchor = root.find("[id]").filter((_, node) => (
    answerIdFrom($(node).attr("id")) === normalizedId
  )).first();
  if (answerAnchor.length) {
    let cursor = answerAnchor.next();
    while (cursor.length) {
      if (cursor.hasClass("solution-box")) return cursor;
      const nested = cursor.find(".solution-box").first();
      if (nested.length) return nested;
      if (answerIdFrom(cursor.attr("id"))) break;
      cursor = cursor.next();
    }
  }

  let cursor = problemBox.next();
  while (cursor.length && !cursor.hasClass("problem-box")) {
    if (cursor.hasClass("solution-box")) return cursor;
    const nested = cursor.find(".solution-box").first();
    if (nested.length) return nested;
    cursor = cursor.next();
  }
  return root.find(".__reader-no-solution__");
}

export function problemBoxForId($, root, problemId) {
  const normalizedId = String(problemId).toLowerCase();
  const anchored = root.find(".problem-box").filter((_, node) => (
    String($(node).attr("id") ?? "").toLowerCase() === normalizedId
  )).first();
  if (anchored.length) return anchored;

  const displayId = String(problemId).toUpperCase();
  return root.find(".problem-box").filter((_, node) => (
    $(node).text().toUpperCase().includes(displayId)
  )).first();
}

export function searchBodyForProblem($, root, problemBox, problemId, fallback = "") {
  const solutionBox = solutionForProblem($, root, problemBox, problemId);
  return `${problemBox.text()} ${solutionBox.text()}`.replace(/\s+/g, " ").trim() || fallback;
}
