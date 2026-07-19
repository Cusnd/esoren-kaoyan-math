import { createHash } from "node:crypto";

const SYMMETRIC_EDGE_TYPES = new Set(["contrasts_with", "same_structure_as"]);
const EDGE_TYPES = new Set([
  "prerequisite_for",
  "generalizes_to",
  ...SYMMETRIC_EDGE_TYPES,
]);

function hashField(hash, label, value) {
  const labelBytes = Buffer.from(String(label));
  const valueBytes = Buffer.isBuffer(value) ? value : Buffer.from(String(value));
  for (const bytes of [labelBytes, valueBytes]) {
    const length = Buffer.alloc(8);
    length.writeBigUInt64BE(BigInt(bytes.length));
    hash.update(length);
    hash.update(bytes);
  }
}

export function computeReaderBuildId({
  siteOrigin,
  siteBasePath,
  manifestSource,
  problemRegistrySource,
  knowledgeRegistrySource,
  pages = [],
  assets = [],
}) {
  const hash = createHash("sha256");
  hashField(hash, "site-origin", siteOrigin);
  hashField(hash, "site-base-path", siteBasePath);
  hashField(hash, "web-pages", manifestSource);
  hashField(hash, "problem-registry", problemRegistrySource);
  hashField(hash, "knowledge-registry", knowledgeRegistrySource);
  for (const page of pages) hashField(hash, `page:${page.slug}`, page.source);
  for (const asset of [...assets].sort((left, right) => (
    String(left.path).localeCompare(String(right.path))
  ))) {
    hashField(hash, `asset:${String(asset.path).replaceAll("\\", "/")}`, asset.source);
  }
  return hash.digest("hex").slice(0, 20);
}

export function buildRelationAdjacency(nodeIds, edges) {
  const ids = [...new Set(nodeIds.map(String))].sort((left, right) => left.localeCompare(right));
  const known = new Set(ids);
  const adjacency = Object.fromEntries(ids.map((id) => [id, []]));
  const append = (id, nodeId, type, direction) => {
    adjacency[id].push({ nodeId, type, direction });
  };

  for (const edge of edges) {
    const source = String(edge.source ?? "");
    const target = String(edge.target ?? "");
    const type = String(edge.type ?? "");
    if (!known.has(source) || !known.has(target)) {
      throw new TypeError(`Relation edge references an unknown node: ${source} -> ${target}`);
    }
    if (!EDGE_TYPES.has(type)) throw new TypeError(`Unknown relation edge type: ${type}`);
    if (SYMMETRIC_EDGE_TYPES.has(type)) {
      append(source, target, type, "symmetric");
      append(target, source, type, "symmetric");
    } else {
      append(source, target, type, "outgoing");
      append(target, source, type, "incoming");
    }
  }

  for (const links of Object.values(adjacency)) {
    links.sort((left, right) => (
      left.type.localeCompare(right.type)
      || left.direction.localeCompare(right.direction)
      || left.nodeId.localeCompare(right.nodeId)
    ));
  }
  return adjacency;
}
