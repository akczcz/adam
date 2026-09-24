#!/usr/bin/env node
/**
 * Zabalí knowledge/ do TypeScript modulu, který se přiloží k Workeru.
 *
 * Zdrojem pravdy zůstává knowledge/ v repu – tenhle skript z něj dělá
 * build artefakt. Index se počítá TADY, ne za běhu: Worker má na Free tieru
 * jen 10 ms CPU na request, takže hledání za běhu musí být jen lookup
 * v předpočítané mapě, ne skenování textu.
 */

import { readFileSync, writeFileSync, mkdirSync, readdirSync, statSync } from "node:fs";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..");
const KNOWLEDGE = join(REPO, "knowledge");
const OUT = join(HERE, "..", "src", "knowledge.generated.ts");

/** Minimální parser YAML frontmatteru – stačí na tvar, který používá knowledge/README.md. */
function parseFrontmatter(raw) {
  if (!raw.startsWith("---\n")) return { meta: {}, body: raw };
  const end = raw.indexOf("\n---", 4);
  if (end === -1) return { meta: {}, body: raw };

  const head = raw.slice(4, end);
  const body = raw.slice(end + 4).replace(/^\n/, "");
  const meta = {};
  let listKey = null;

  for (const line of head.split("\n")) {
    if (!line.trim()) continue;
    const item = line.match(/^\s+-\s+(.*)$/);
    if (item && listKey) {
      meta[listKey].push(item[1].trim());
      continue;
    }
    const kv = line.match(/^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$/);
    if (!kv) continue;
    const [, key, value] = kv;
    if (value.trim() === "") {
      listKey = key;
      meta[key] = [];
    } else {
      listKey = null;
      meta[key] = value.trim();
    }
  }
  return { meta, body };
}

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (entry.endsWith(".md")) out.push(full);
  }
  return out;
}

/** Rozřeže dokument na sekce podle `## nadpisů`, aby hledání vracelo pasáž, ne celý soubor. */
function splitSections(body) {
  const lines = body.split("\n");
  const sections = [];
  let heading = "(úvod)";
  let buf = [];

  const flush = () => {
    const text = buf.join("\n").trim();
    if (text) sections.push({ heading, text });
    buf = [];
  };

  for (const line of lines) {
    const h = line.match(/^(#{2,3})\s+(.*)$/);
    if (h) {
      flush();
      heading = h[2].trim();
    } else {
      buf.push(line);
    }
  }
  flush();
  return sections;
}

/** Tokenizace bez diakritiky, ať „protokol" najde i „protokolů". */
function tokenize(text) {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .split(/[^a-z0-9_/.-]+/)
    .filter((t) => t.length >= 3 && t.length <= 40);
}

const STOPWORDS = new Set([
  "the", "and", "for", "are", "not", "pro", "nebo", "ale", "což", "jako", "jsou",
  "byl", "byla", "bylo", "toho", "tom", "tak", "ten", "ta", "to", "se", "si",
  "ktere", "ktery", "ktera", "kdyz", "jen", "uz", "vsak", "tedy", "napr",
]);

const files = walk(KNOWLEDGE).sort();
const docs = [];
const sections = [];
const index = new Map();

for (const file of files) {
  const raw = readFileSync(file, "utf8");
  const { meta, body } = parseFrontmatter(raw);
  const path = relative(REPO, file).split("/").join("/");

  // knowledge/protocols/mcp.md -> protocols/mcp
  const id = path.replace(/^knowledge\//, "").replace(/\.md$/, "");
  const titleMatch = body.match(/^#\s+(.*)$/m);

  const docIndex = docs.length;
  docs.push({
    id,
    path,
    title: (titleMatch ? titleMatch[1] : meta.tema || id).trim(),
    tema: meta.tema ?? null,
    zralost: meta.zralost ?? null,
    naposledy_overeno: meta.naposledy_overeno ?? null,
    primarni_zdroje: Array.isArray(meta.primarni_zdroje) ? meta.primarni_zdroje : [],
    text: body,
  });

  for (const sec of splitSections(body)) {
    const secIndex = sections.length;
    sections.push({ doc: docIndex, heading: sec.heading, text: sec.text });

    for (const token of new Set(tokenize(sec.heading + " " + sec.text))) {
      if (STOPWORDS.has(token)) continue;
      if (!index.has(token)) index.set(token, []);
      index.get(token).push(secIndex);
    }
  }
}

// Tokeny, které jsou skoro všude, pro hledání nic neváží a jen nafukují bundle.
const tooCommon = Math.max(2, Math.ceil(sections.length * 0.6));
const prunedIndex = {};
let pruned = 0;
for (const [token, postings] of [...index.entries()].sort()) {
  if (postings.length > tooCommon) {
    pruned++;
    continue;
  }
  prunedIndex[token] = postings;
}

const out = `// VYGENEROVÁNO – needituj. Zdroj: knowledge/, generátor: scripts/bundle-knowledge.mjs
// Přegeneruj: npm run build:knowledge

export interface Doc {
  id: string;
  path: string;
  title: string;
  tema: string | null;
  zralost: string | null;
  naposledy_overeno: string | null;
  primarni_zdroje: string[];
  text: string;
}

export interface Section {
  doc: number;
  heading: string;
  text: string;
}

export const BUILT_AT = ${JSON.stringify(new Date().toISOString())};
export const DOCS: Doc[] = ${JSON.stringify(docs, null, 1)};
export const SECTIONS: Section[] = ${JSON.stringify(sections, null, 1)};
/** token -> indexy do SECTIONS. Předpočítáno při buildu kvůli 10ms CPU limitu. */
export const INDEX: Record<string, number[]> = ${JSON.stringify(prunedIndex)};
`;

mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, out, "utf8");

const kb = (Buffer.byteLength(out, "utf8") / 1024).toFixed(1);
console.log(
  `knowledge: ${docs.length} dokumentů, ${sections.length} sekcí, ` +
    `${Object.keys(prunedIndex).length} tokenů (${pruned} vyřazeno jako příliš častých) -> ${kb} kB`,
);
for (const d of docs) console.log(`  - ${d.id.padEnd(22)} ${d.zralost ?? "?"}  ${d.naposledy_overeno ?? "?"}`);
