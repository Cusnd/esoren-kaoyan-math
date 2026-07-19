import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRelationAdjacency,
  computeReaderBuildId,
} from "../../scripts/web_index_helpers.mjs";

test("relation adjacency materializes symmetric edges in both directions", () => {
  const first = "MATH1-KN-CALC-0001";
  const second = "MATH1-KN-CALC-0002";
  const third = "MATH1-KN-CALC-0003";
  const adjacency = buildRelationAdjacency([third, first, second], [
    { source: first, target: second, type: "contrasts_with" },
    { source: second, target: third, type: "prerequisite_for" },
  ]);

  assert.deepEqual(Object.keys(adjacency), [first, second, third]);
  assert.deepEqual(adjacency[first], [
    { nodeId: second, type: "contrasts_with", direction: "symmetric" },
  ]);
  assert.deepEqual(adjacency[second], [
    { nodeId: first, type: "contrasts_with", direction: "symmetric" },
    { nodeId: third, type: "prerequisite_for", direction: "outgoing" },
  ]);
  assert.deepEqual(adjacency[third], [
    { nodeId: second, type: "prerequisite_for", direction: "incoming" },
  ]);
});

test("reader build id changes when either problem registry or knowledge relations change", () => {
  const seed = {
    siteOrigin: "https://reader.example",
    siteBasePath: "/math",
    manifestSource: "pages: []",
    problemRegistrySource: "- id: MATH1-CALC-0001",
    knowledgeRegistrySource: "edges: []",
    pages: [{ slug: "calc-01", source: "chapter" }],
    assets: [{ path: "web/reader/app.js", source: Buffer.from("app") }],
  };
  const baseline = computeReaderBuildId(seed);

  assert.equal(computeReaderBuildId({
    ...seed,
    pages: seed.pages.map((page) => ({ ...page })),
    assets: seed.assets.map((asset) => ({ ...asset })),
  }), baseline);
  assert.notEqual(computeReaderBuildId({
    ...seed,
    problemRegistrySource: `${seed.problemRegistrySource}\n  title: changed`,
  }), baseline);
  assert.notEqual(computeReaderBuildId({
    ...seed,
    knowledgeRegistrySource: "edges:\n  - source: A\n    target: B\n    type: contrasts_with",
  }), baseline);
});
