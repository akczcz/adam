/**
 * MCP server nad Adamovou znalostní bází, běžící na Cloudflare Workers.
 *
 * Read-only. Zdrojem pravdy je knowledge/ v repu; tenhle Worker servíruje
 * build artefakt (src/knowledge.generated.ts).
 *
 * Provozní omezení, které tvaruje celý kód: Workers Free tier dává 10 ms CPU
 * na request. Čekání na I/O se nepočítá, výpočet ano. Proto se při startu
 * nic neindexuje a hledání je jen lookup v předpočítané mapě.
 */

import { createMcpHandler, McpServer } from "@modelcontextprotocol/server";
import { z } from "zod";

import { BUILT_AT, DOCS, INDEX, SECTIONS } from "./knowledge.generated.js";

interface Env {
  /**
   * Přijímané bearer tokeny, oddělené čárkou. Každý může mít štítek:
   *
   *   MCP_BEARER_TOKEN="adam:tok1,kolega-jan:tok2,tok3"
   *
   * Štítek se loguje při úspěšné autentizaci, takže je ve Workers Logs vidět,
   * kdo se připojuje – a jde odvolat jeden token, aniž by to shodilo ostatní.
   * Nastav přes: wrangler secret put MCP_BEARER_TOKEN
   */
  MCP_BEARER_TOKEN?: string;
}

const SERVER_INFO = { name: "adam-knowledge", version: "0.1.0" } as const;

/* ------------------------------------------------------------------ auth */

const encoder = new TextEncoder();

/**
 * Porovnání v konstantním čase. Workers nabízejí crypto.subtle.timingSafeEqual;
 * fallback je vlastní XOR smyčka, ať kód nespadne v jiném runtime.
 */
function secureEquals(a: string, b: string): boolean {
  const ab = encoder.encode(a);
  const bb = encoder.encode(b);
  if (ab.byteLength !== bb.byteLength) return false;

  const subtle = crypto.subtle as SubtleCrypto & {
    timingSafeEqual?: (a: ArrayBufferView, b: ArrayBufferView) => boolean;
  };
  if (typeof subtle.timingSafeEqual === "function") {
    return subtle.timingSafeEqual(ab, bb);
  }
  let diff = 0;
  for (let i = 0; i < ab.byteLength; i++) diff |= ab[i] ^ bb[i];
  return diff === 0;
}

interface Credential {
  label: string;
  token: string;
}

/**
 * Rozparsuje seznam tokenů. Tvar položky je "stitek:token" nebo holý "token".
 * Za štítek se považuje jen bezpečný prefix před první dvojtečkou – tokeny
 * z `openssl rand -base64 32 | tr -d '/+='` dvojtečku neobsahují, takže
 * nehrozí, že bychom token omylem rozsekli vejpůl.
 */
function parseCredentials(raw: string): Credential[] {
  const out: Credential[] = [];
  for (const [i, part] of raw.split(",").entries()) {
    const item = part.trim();
    if (!item) continue;

    const sep = item.indexOf(":");
    if (sep > 0) {
      const label = item.slice(0, sep);
      const token = item.slice(sep + 1).trim();
      if (token && /^[A-Za-z0-9._-]{1,32}$/.test(label)) {
        out.push({ label, token });
        continue;
      }
    }
    // Bez štítku: do logu jde jen pořadí, nikdy ne kus tokenu.
    out.push({ label: `token#${i + 1}`, token: item });
  }
  return out;
}

/** Isolate se mezi requesty recykluje, takže parsujeme jen při změně secretu. */
let credCache: { raw: string; creds: Credential[] } | null = null;

function credentialsOf(raw: string): Credential[] {
  if (credCache?.raw !== raw) credCache = { raw, creds: parseCredentials(raw) };
  return credCache.creds;
}

/**
 * Vrátí štítek odpovídajícího tokenu, jinak null.
 * Záměrně projde všechny položky i po nálezu – doba běhu tak neprozradí,
 * kolikátý token v pořadí to byl.
 */
function identify(presented: string, creds: Credential[]): string | null {
  let found: string | null = null;
  for (const cred of creds) {
    if (secureEquals(presented, cred.token)) found ??= cred.label;
  }
  return found;
}

function unauthorized(detail: string): Response {
  return new Response(JSON.stringify({ error: "unauthorized", detail }), {
    status: 401,
    headers: {
      "content-type": "application/json",
      // Bez tohohle klient neví, jakou autentizaci má nabídnout.
      "www-authenticate": 'Bearer realm="adam-knowledge"',
    },
  });
}

/* ---------------------------------------------------------------- search */

/** Stejná tokenizace jako v build skriptu – jinak by dotaz index netrefil. */
function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .split(/[^a-z0-9_/.-]+/)
    .filter((t) => t.length >= 3 && t.length <= 40);
}

interface Hit {
  section: number;
  score: number;
}

function search(query: string, limit: number): Hit[] {
  const tokens = [...new Set(tokenize(query))];
  if (tokens.length === 0) return [];

  const scores = new Map<number, number>();
  for (const token of tokens) {
    const postings = INDEX[token];
    if (!postings) continue;
    // Vzácnější token váží víc – hrubý idf, ale stačí to.
    const weight = 1 / Math.log2(postings.length + 2);
    for (const sec of postings) {
      scores.set(sec, (scores.get(sec) ?? 0) + weight);
    }
  }

  return [...scores.entries()]
    .map(([section, score]) => ({ section, score }))
    .sort((a, b) => b.score - a.score || a.section - b.section)
    .slice(0, limit);
}

/* -------------------------------------------------------- server factory */

/** Vytáhne obsah sekce podle nadpisu (case-insensitive, prefixová shoda). */
function sectionOf(docIndex: number, headingPrefix: string): string | null {
  const needle = headingPrefix.toLowerCase();
  const found = SECTIONS.find(
    (s) => s.doc === docIndex && s.heading.toLowerCase().startsWith(needle),
  );
  return found ? found.text : null;
}

function buildServer(): McpServer {
  const server = new McpServer(SERVER_INFO, {
    instructions:
      "Znalostní báze Adama Kolaříka o AI protokolech pro multiagentní platformy. " +
      "Read-only. Fakta mají uvedený zdroj a datum ověření – u verzí a termínů " +
      "vždy zkontroluj pole naposledy_overeno, protokoly se mění rychle.",
  });

  // --- resources: každý dokument pod knowledge://<id> ---
  DOCS.forEach((doc, i) => {
    server.registerResource(
      doc.id,
      `knowledge://${doc.id}`,
      {
        title: doc.title,
        description:
          `${doc.tema ?? doc.title}` +
          (doc.zralost ? ` · zralost: ${doc.zralost}` : "") +
          (doc.naposledy_overeno ? ` · ověřeno ${doc.naposledy_overeno}` : ""),
        mimeType: "text/markdown",
      },
      async (uri) => ({
        contents: [{ uri: uri.href, mimeType: "text/markdown", text: DOCS[i].text }],
      }),
    );
  });

  // --- tool: hledání v bázi ---
  server.registerTool(
    "search_knowledge",
    {
      title: "Hledat ve znalostní bázi",
      description:
        "Fulltextové hledání napříč znalostní bází. Vrací relevantní sekce " +
        "včetně dokumentu, ze kterého pocházejí. Hledá česky i anglicky.",
      inputSchema: z.object({
        query: z.string().min(2).describe("Hledaný výraz, např. 'deprecated Roots' nebo 'stateless'"),
        limit: z.number().int().min(1).max(10).default(5).describe("Kolik sekcí vrátit"),
      }),
      annotations: { readOnlyHint: true, openWorldHint: false },
    },
    async ({ query, limit }) => {
      const hits = search(query, limit ?? 5);
      if (hits.length === 0) {
        return {
          content: [
            {
              type: "text",
              text:
                `Ve znalostní bázi nic k „${query}" není.\n\n` +
                `Dostupné dokumenty: ${DOCS.map((d) => d.id).join(", ")}`,
            },
          ],
        };
      }

      const rendered = hits.map(({ section }) => {
        const sec = SECTIONS[section];
        const doc = DOCS[sec.doc];
        return (
          `## ${doc.title} → ${sec.heading}\n` +
          `_zdroj: ${doc.path}` +
          (doc.naposledy_overeno ? `, ověřeno ${doc.naposledy_overeno}` : "") +
          `_\n\n${sec.text}`
        );
      });

      return {
        content: [{ type: "text", text: rendered.join("\n\n---\n\n") }],
      };
    },
  );

  // --- tool: stav protokolu ---
  const protocolIds = DOCS.filter((d) => d.id.startsWith("protocols/")).map((d) =>
    d.id.replace("protocols/", ""),
  );

  server.registerTool(
    "protocol_status",
    {
      title: "Stav protokolu",
      description:
        "Strukturovaný přehled jednoho protokolu: aktuální verze, zralost, datum " +
        "posledního ověření, primární zdroje a otevřené otázky. " +
        `Dostupné: ${protocolIds.join(", ")}.`,
      inputSchema: z.object({
        protocol: z.string().describe(`Název protokolu, např. ${protocolIds[0] ?? "mcp"}`),
      }),
      outputSchema: z.object({
        id: z.string(),
        tema: z.string().nullable(),
        zralost: z.string().nullable(),
        naposledy_overeno: z.string().nullable(),
        primarni_zdroje: z.array(z.string()),
        aktualni_stav: z.string().nullable(),
        otevrene_otazky: z.string().nullable(),
      }),
      annotations: { readOnlyHint: true, openWorldHint: false },
    },
    async ({ protocol }) => {
      const key = protocol.toLowerCase().trim().replace(/^protocols\//, "");
      const i = DOCS.findIndex((d) => d.id === `protocols/${key}`);

      if (i === -1) {
        return {
          isError: true,
          content: [
            {
              type: "text",
              text: `Protokol „${protocol}" v bázi není. Dostupné: ${protocolIds.join(", ")}.`,
            },
          ],
        };
      }

      const doc = DOCS[i];
      const output = {
        id: doc.id,
        tema: doc.tema,
        zralost: doc.zralost,
        naposledy_overeno: doc.naposledy_overeno,
        primarni_zdroje: doc.primarni_zdroje,
        aktualni_stav: sectionOf(i, "Aktuální stav"),
        otevrene_otazky: sectionOf(i, "Otevřené otázky"),
      };

      return {
        content: [{ type: "text", text: JSON.stringify(output, null, 2) }],
        structuredContent: output,
      };
    },
  );

  return server;
}

/* ------------------------------------------------------------------ http */

const handler = createMcpHandler(() => buildServer(), {
  // Claude API connector jede zatím na 2025-11-25 (beta mcp-client-2025-11-20),
  // takže legacy éru musíme obsluhovat, ne odmítat.
  legacy: "stateless",
  onerror: (err) => console.error("mcp handler error:", err.message),
});

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Health check mimo autentizaci – ať jde ověřit nasazení bez tokenu.
    // Záměrně neprozrazuje nic o obsahu báze.
    if (url.pathname === "/health") {
      return Response.json({
        status: "ok",
        server: SERVER_INFO,
        documents: DOCS.length,
        knowledge_built_at: BUILT_AT,
      });
    }

    const raw = env.MCP_BEARER_TOKEN;
    if (!raw) {
      // Radši tvrdě spadnout než nechat bázi omylem veřejně.
      console.error("MCP_BEARER_TOKEN není nastavený – odmítám obsluhovat.");
      return new Response(
        JSON.stringify({ error: "server_misconfigured", detail: "MCP_BEARER_TOKEN not set" }),
        { status: 500, headers: { "content-type": "application/json" } },
      );
    }

    const creds = credentialsOf(raw);
    if (creds.length === 0) {
      console.error("MCP_BEARER_TOKEN je nastavený, ale prázdný – odmítám obsluhovat.");
      return new Response(
        JSON.stringify({ error: "server_misconfigured", detail: "MCP_BEARER_TOKEN is empty" }),
        { status: 500, headers: { "content-type": "application/json" } },
      );
    }

    const auth = request.headers.get("authorization") ?? "";
    const match = auth.match(/^Bearer\s+(.+)$/i);
    if (!match) return unauthorized("Chybí hlavička Authorization: Bearer <token>");

    const label = identify(match[1].trim(), creds);
    if (!label) return unauthorized("Neplatný token");

    // Kdo se připojuje – viditelné ve Workers Logs. Token samotný se neloguje.
    console.log(`mcp auth ok: ${label} ${request.method} ${url.pathname}`);

    return handler.fetch(request);
  },
} satisfies ExportedHandler<Env>;
