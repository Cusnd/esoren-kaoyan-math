import assert from "node:assert/strict";
import test from "node:test";

import { load } from "cheerio";
import {
  collapsePracticeSolutions,
  problemBoxForId,
  searchBodyForProblem,
  solutionForProblem,
} from "../../scripts/web_content_helpers.mjs";

test("practice solutions pair with their exact problem ids in a multi-problem chapter", () => {
  const $ = load(`<main>
    <div class="problem-box">MATH1-CALC-0101 题目一</div>
    <div class="problem-box">MATH1-CALC-0102 题目二</div>
    <a id="LWR-ht-answer:MATH1-CALC-0101"></a>
    <div class="solution-box">ANSWER_ONE_ONLY</div>
    <a id="LWR-ht-answer:MATH1-CALC-0102"></a>
    <div class="solution-box">ANSWER_TWO_ONLY</div>
  </main>`);
  const main = $("main");
  collapsePracticeSolutions($, main);

  const answers = main.find("details.reader-practice-answer");
  assert.equal(answers.length, 2);
  assert.equal(answers.eq(0).attr("data-answer-for"), "MATH1-CALC-0101");
  assert.equal(answers.eq(1).attr("data-answer-for"), "MATH1-CALC-0102");
  assert.match(answers.eq(0).text(), /ANSWER_ONE_ONLY/);
  assert.doesNotMatch(answers.eq(0).text(), /ANSWER_TWO_ONLY/);
  assert.match(answers.eq(1).text(), /ANSWER_TWO_ONLY/);
  assert.doesNotMatch(answers.eq(1).text(), /ANSWER_ONE_ONLY/);

  const problems = main.find(".problem-box");
  const first = solutionForProblem($, main, problems.eq(0), "MATH1-CALC-0101");
  const second = solutionForProblem($, main, problems.eq(1), "MATH1-CALC-0102");
  assert.equal(first.text(), "ANSWER_ONE_ONLY");
  assert.equal(second.text(), "ANSWER_TWO_ONLY");
  const firstBody = searchBodyForProblem($, main, problems.eq(0), "MATH1-CALC-0101");
  const secondBody = searchBodyForProblem($, main, problems.eq(1), "MATH1-CALC-0102");
  assert.match(firstBody, /题目一.*ANSWER_ONE_ONLY/);
  assert.doesNotMatch(firstBody, /题目二|ANSWER_TWO_ONLY/);
  assert.match(secondBody, /题目二.*ANSWER_TWO_ONLY/);
  assert.doesNotMatch(secondBody, /题目一|ANSWER_ONE_ONLY/);
});

test("problem search items use the stable box anchor when visible metadata was removed", () => {
  const $ = load(`<main>
    <div class="problem-box" id="math1-calc-0101">FIRST_PROBLEM_ONLY</div>
    <a id="LWR-ht-answer:MATH1-CALC-0101"></a>
    <div class="solution-box">FIRST_ANSWER_ONLY</div>
    <div class="problem-box" id="math1-calc-0102">SECOND_PROBLEM_ONLY</div>
    <a id="LWR-ht-answer:MATH1-CALC-0102"></a>
    <div class="solution-box">SECOND_ANSWER_ONLY</div>
  </main>`);
  const main = $("main");

  const firstBox = problemBoxForId($, main, "MATH1-CALC-0101");
  const firstBody = searchBodyForProblem($, main, firstBox, "MATH1-CALC-0101", main.text());
  assert.equal(firstBox.attr("id"), "math1-calc-0101");
  assert.match(firstBody, /FIRST_PROBLEM_ONLY.*FIRST_ANSWER_ONLY/);
  assert.doesNotMatch(firstBody, /SECOND_PROBLEM_ONLY|SECOND_ANSWER_ONLY/);
});
