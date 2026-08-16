"""Build the in-browser reader: portal/browser-reader.html.

This is no longer a demo. A visitor picks an unread town; the site hands their
browser that town's real pages (the same document selection the installed
reader uses, served by /api/browser/plan and /api/browser/pages); a model
running inside the tab reads each prose page; records that survive the page's
own two checks are POSTed to /api/bundle, where the server re-verifies every
quoted sentence against archive.org before publishing anything. Nothing is
installed and no server does any reading.

The one-page proof is still on the page ("try it on one page first"): the
embedded Ear Falls page reads without a server, which also keeps the committed
portal/ copy meaningful away from the live site.

Generated, not hand-written, so it cannot drift: the compact small-model
instructions live beside the full concordance.extract.SYSTEM they distill, the
user-prompt template IS concordance.extract.USER_TEMPLATE, and the demo page
text is taken from the same local cache the real reader used. Regenerate after
any prompt change:

    python scripts/build_browser_reader.py

The template below is plain HTML/JS with __SENTINEL__ slots -- not a Python
format string -- because a page this size in .format braces is a page of
doubled braces, and one missed double is a parse error that takes every
handler with it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.archive import Archive                     # noqa: E402
from concordance.extract import USER_TEMPLATE               # noqa: E402

#: Compact reading instructions for browser-size models, v2 (v1's worked
#: example was a sentence from the demo page itself -- it seeded an answer;
#: v2's example is from a different document and shows the one-sentence,
#: many-records rule at the same time). The full SYSTEM
#: prompt was tuned on a 12B model and drowns 2-4B models -- observed in this
#: very page: a 1B collapsed into repetition, a 2B found values but quoted no
#: sentences, a current 3B produced two fragments. This distillation keeps
#: the load-bearing rules (the four kinds, quote-the-exact-sentence, JSON
#: only) and drops the vocabulary apparatus. UNBENCHMARKED as of 2026-08-16:
#: its accuracy against the gold pages is the next measurement, and the page
#: says so. The full prompt stays the production standard.
SMALL_SYSTEM = """You read scanned Canadian government reports and pull out every measurement.

Return ONLY a JSON array. No prose, no markdown fence. Each element:
{"kind": "...", "parameter": "...", "value": 1.23, "unit": "...",
 "source_text": "..."}

Rules, in order of importance:
1. "source_text" is the EXACT sentence from the text, copied verbatim,
   containing the value. Never paraphrase it. A record without its exact
   sentence will be rejected.
2. "value" is the number as stated. "unit" is its unit ("mg/L", "%",
   "hours", "persons").
3. "kind" is one of:
   "observation" - something actually measured ("the residual was 0.7 mg/L")
   "design"      - what equipment was built for ("design flow 0.20 MGD")
   "standard"    - a regulatory limit or objective ("must not exceed 1 mg/L")
   "conclusion"  - the author's judgement, may have no number
4. One record per measurement. A sentence with three numbers gives three
   records, each quoting that same sentence.

Example: the text "The average influent BOD and suspended solids were 104
mg/1 and 224 mg/1 respectively." gives:
[{"kind": "observation", "parameter": "influent BOD", "value": 104,
  "unit": "mg/L", "source_text": "The average influent BOD and suspended
solids were 104 mg/1 and 224 mg/1 respectively."},
 {"kind": "observation", "parameter": "influent suspended solids",
  "value": 224, "unit": "mg/L", "source_text": "The average influent BOD
and suspended solids were 104 mg/1 and 224 mg/1 respectively."}]
"""

IDENTIFIER = "optimizationofea00ontauoft"
PAGE_NO = 9
TITLE = "The Optimization of the Ear Falls Water Treatment Plant"
YEAR = "1997"
PUBLISHER = "Ontario Ministry of Environment and Energy"
OUT = Path("portal/browser-reader.html")
#: The copy the live server serves at /browser -- written by the same
#: build so the two can never drift.
SERVED = Path("concordance/static/browser-reader.html")

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Concordance — read a town in your browser</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; }
  body { background:#0b1016; color:#e8edf2; font:14px/1.55 system-ui,sans-serif;
         max-width: 920px; margin: 0 auto; padding: 28px 18px 80px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  h2 { font-size: 15px; margin: 0 0 6px; }
  .sub { color:#8b97a4; margin-bottom: 18px; }
  .card { background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.1);
          border-radius: 12px; padding: 14px 16px; margin: 12px 0; }
  .note { color:#8b97a4; font-size: 12.5px; }
  button { background:#f0a24a; color:#0b1016; border:0; border-radius:9px;
           padding:9px 18px; font:inherit; font-weight:600; cursor:pointer }
  button:disabled { opacity:.45; cursor:default }
  button.quiet { background:transparent; color:#8b97a4;
                 border:1px solid rgba(255,255,255,.2) }
  #status { font-family: ui-monospace,monospace; font-size:12px; color:#8b97a4;
            white-space: pre-wrap; }
  progress { width:100%; height:6px; accent-color:#f0a24a }
  table { width:100%; border-collapse:collapse; font-size:13px; margin-top:8px }
  th,td { text-align:left; padding:6px 8px; border-bottom:1px solid rgba(255,255,255,.08);
          vertical-align: top }
  th { color:#6d7a86; font-size:11px; text-transform:uppercase; letter-spacing:.06em }
  .q { color:#8b97a4; font-style: italic; font-size:12px }
  .ok { color:#7dc87d } .bad { color:#e08b8b }
  .v { font-family: ui-monospace,monospace; white-space:nowrap }
  a { color:#f0a24a; text-decoration: none }
  details { margin-top: 8px } summary { cursor:pointer; color:#8b97a4 }
  pre { white-space:pre-wrap; font-size:11.5px; color:#8b97a4; max-height:260px;
        overflow:auto; margin-top:6px }
  select,input[type=text] { background:#0b1016; color:#e8edf2; font:inherit;
        border:1px solid rgba(255,255,255,.2); border-radius:8px; padding:8px 10px;
        max-width:100%; }
  .doc { padding:5px 0; border-bottom:1px dashed rgba(255,255,255,.08); font-size:13px }
  .doc:last-child { border-bottom:0 }
  .verdict { margin:6px 0; font-size:13px }
</style>
</head>
<body>
<h1>The reader, in your browser</h1>
<p class="sub">Pick a town nobody has read. An AI model runs <b>inside this
browser tab</b> on your own graphics card, reads that town's scanned
government reports page by page, and sends what survives its checks to this
site — where every quoted sentence is re-verified against the archive before
anything is published. Nothing is installed; no server does any reading.</p>

<div class="card" id="pick-card" hidden>
  <h2>Pick a town nobody has read yet</h2>
  <p class="note" style="margin-bottom:8px">These are municipalities in the
  silence index with no readings yet. More surviving reports means a longer
  read and a richer record.</p>
  <p><select id="town-select"></select></p>
  <p style="margin-top:8px"><input type="text" id="town-free"
     placeholder="or any place name in the collection…" size="30">
  </p>
  <p style="margin-top:10px"><button id="town-go">Plan the read</button></p>
  <p class="note" id="pick-note"></p>
</div>

<div class="card" id="town-card" hidden>
  <h2 id="town-name"></h2>
  <div id="town-docs"></div>
  <p class="note" id="town-note" style="margin-top:8px"></p>
</div>

<div class="card" id="run-card">
  <div id="status">Checking whether this browser can run a model…</div>
  <progress id="bar" value="0" max="1" hidden></progress>
  <p style="margin-top:10px">
    <button id="go" disabled></button>
    <button id="stop" class="quiet" hidden>stop after this page</button>
  </p>
  <p class="note" id="model-note"></p>
</div>

<div class="card" id="results" hidden>
  <b id="headline"></b>
  <div id="verdicts"></div>
  <table id="tbl">
    <thead><tr><th>kind</th><th>parameter</th><th>value</th>
    <th>sentence it was read from</th><th>page</th><th>checks</th></tr></thead>
    <tbody></tbody>
  </table>
  <details><summary class="note">the model's raw output for the last page —
  check the reader's work the way the reader checks the archive's</summary>
  <pre id="raw-out"></pre></details>
  <p class="note" style="margin-top:10px" id="results-note"></p>
</div>

<div class="card" id="demo-card" hidden>
  <h2>Or try it on one page first</h2>
  <p class="note"><b id="demo-title"></b> — one real page
  (<a id="demo-link" target="_blank" rel="noopener">the scan ↗</a>,
  Internet Archive). Reads in under a minute; publishes nothing.</p>
  <details><summary class="note">the page text being read (from the archive's
  OCR layer)</summary><pre id="page-text"></pre></details>
  <p style="margin-top:10px"><button id="demo-go" disabled>Read this page in the browser</button></p>
</div>

<p class="note" id="honesty">Honest scope. The model this page runs
(Qwen3.5-4B from the official WebLLM catalogue) is a <b>partial</b> reader:
measured on this project's gold pages, models of its size find roughly half
of what a page states and invent nothing that survives the checks — on the
embedded proof page it read 12 records in 42 seconds, 9 verified, 3 refused
in the open. What your browser sends is only what passed both checks here,
and this site then re-verifies every sentence and number against the scanned
page on archive.org before publishing — the same rule applied to every
reader, human or machine. A stronger model (gemma4:e2b — 100% precision,
44% recall on the gold pages) still cannot run in any browser: all three of
its published browser builds fall silent past ~512 prompt tokens, a defect
in the shared WebGPU kernels for its architecture, documented in this
project's worklog; the day the upstream fix lands, it takes one flag to
retest. Until then: an honest partial read a stranger can start with one
press, or the installed reader for the rest.</p>

<script type="module">
const SYSTEM_SMALL = __SYSTEM_JSON__;
const USER_TMPL = __USER_TMPL_JSON__;
const DEMO = __DEMO_JSON__;
const PLACE = (new URLSearchParams(location.search).get("place") || "").trim();

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
const status = m => { $("status").textContent = m; };
const bar = $("bar"), go = $("go"), stopBtn = $("stop");

let STOP = false;
let engine = null, modelId = null;
let TOWN = null;          // {place, documents:[...]} once planned

/* ---- the same salvage parser the real extractor uses, ported ------------ */
function parseRecords(raw) {
  // Reasoning models deliberate in <think> blocks before answering, and the
  // deliberation can contain example braces. Extraction is transcription,
  // not deliberation -- discard the thinking, closed or truncated.
  raw = raw.replace(/<think>[\\s\\S]*?<\\/think>/g, "");
  const open = raw.indexOf("<think>");
  if (open >= 0) raw = raw.slice(0, open);
  raw = raw.trim().replace(/^```[a-z]*\\n?/, "").replace(/\\n?```$/, "").trim();
  try { const v = JSON.parse(raw); return Array.isArray(v) ? v : [v]; } catch (e) {}
  const a = raw.indexOf("["), b = raw.lastIndexOf("]");
  if (a >= 0 && b > a) {
    try { const v = JSON.parse(raw.slice(a, b + 1)); if (Array.isArray(v)) return v; }
    catch (e) {}
  }
  const out = []; let depth = 0, start = -1, inStr = false, escd = false;
  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    if (inStr) { if (escd) escd = false; else if (ch === "\\\\") escd = true;
                 else if (ch === '"') inStr = false; continue; }
    if (ch === '"') inStr = true;
    else if (ch === "{") { if (!depth) start = i; depth++; }
    else if (ch === "}") { if (depth && !--depth && start >= 0) {
      try { const o = JSON.parse(raw.slice(start, i + 1));
            if (o && typeof o === "object") out.push(o); } catch (e) {}
      start = -1; } }
  }
  return out;
}

/* ---- demo-grade ports of the evidence checks ---------------------------
   The browser's checks are a pre-filter so junk never leaves the tab; the
   server's verification against archive.org is the authority, and its
   verdict is shown when records are sent. */
const norm = s => String(s || "").toLowerCase().replace(/[^a-z0-9.]+/g, " ").trim();
function quoteOnPage(quote, pageText) {
  const q = norm(quote), p = norm(pageText);
  return q.length > 8 && p.includes(q.slice(0, 160));
}
function valueInQuote(value, quote) {
  if (value === null || value === undefined) return null; // nothing to check
  let canon = String(value);
  if (canon.endsWith(".0")) canon = canon.slice(0, -2);
  // Strip commas only in the three-digit thousands shape -- "8,5" stays.
  const direct = String(quote || "").replace(/(?<=\\d),(?=\\d{3}(?!\\d))/g, "");
  const rx = new RegExp("(?<![\\\\d.+-])" + canon.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")
                        + "(?![\\\\d.])");
  return rx.test(direct);
}

/* ---- one model record -> one bundle record, or a reason it cannot be --- */
const KINDS = ["observation", "standard", "design", "conclusion"];
function toBundleRecord(r, doc, pageNo, pageText) {
  const quote = String(r.source_text || "").trim();
  const kind = String(r.kind || "").trim().toLowerCase();
  const parameter = String(r.parameter || "").trim();
  if (!KINDS.includes(kind)) return { why: "unrecognised kind" };
  if (!parameter) return { why: "no parameter named" };
  if (!quote) return { why: "no sentence quoted — unprovable" };
  let value = r.value;
  if (value === undefined) value = null;
  if (typeof value === "string" && value.trim() !== "" && isFinite(Number(value)))
    value = Number(value);
  if (value !== null && (typeof value !== "number" || !isFinite(value)))
    return { why: "value is not a number" };
  if (value === null && kind !== "conclusion")
    return { why: "no value stated" };
  if (!quoteOnPage(quote, pageText)) return { why: "sentence not found on the page" };
  const inQuote = valueInQuote(value, quote);
  if (inQuote === false) return { why: "value not in its sentence" };
  if (value === null && norm(quote).split(" ").length < 4)
    return { why: "quote too short to be evidence on its own" };
  return { record: {
    kind, parameter,
    value,
    unit: String(r.unit || "").trim() || null,
    place: TOWN ? TOWN.place : null,
    facility: (doc.facility || null),
    period: (doc.year || null),
    stream: "unknown",
    provenance: {
      identifier: doc.identifier,
      page: pageNo,
      source_text: quote,
      extractor: "browser " + (modelId || "webllm"),
      path: "prose",
    },
  } };
}

/* ---- server API with polite retry -------------------------------------- */
async function api(path, body, tries) {
  tries = tries || 6;
  for (let attempt = 0; attempt < tries; attempt++) {
    let res;
    try {
      res = await fetch(path, { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) });
    } catch (e) { throw new Error("could not reach the site (" + e + ")"); }
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (res.status === 429 || res.status === 503) {
      const wait = Math.min(30, Number((data && data.retry_after) ||
                    res.headers.get("Retry-After") || 5) || 5);
      status("The site is busy; waiting " + wait + "s before retrying…");
      await new Promise(r => setTimeout(r, wait * 1000));
      continue;
    }
    if (!res.ok || (data && data.error))
      throw new Error((data && (data.error || data.why)) || (path + " failed: " + res.status));
    return data;
  }
  throw new Error("the site stayed busy; try again in a minute");
}

/* ---- the model, in this tab --------------------------------------------
   Opening the page costs nothing: boot only checks capability and arms the
   buttons. The multi-GB model fetch is behind an explicit press -- a page a
   social link lands on must not start a 2.4 GB download uninvited. */
function boot() {
  if (!("gpu" in navigator)) {
    status("This browser has no WebGPU — the in-browser reader needs it. "
         + "Recent Chrome, Edge and Firefox on a machine with a GPU all work.");
    return false;
  }
  status("Ready. The first press downloads the model into browser cache "
       + "(about 2.4 GB, once — it stays for next time), then reads "
       + "right here on your graphics card.");
  return true;
}

async function loadEngine() {
  status("Loading the model list…");
  const webllm = await import("https://esm.run/@mlc-ai/web-llm@0.2.84");
  // The benchmarked model itself, published for browsers by a third party
  // (validated by its publisher 2026-04-13). This is gemma4:e2b -- 100%
  // precision, 44% recall on the gold pages via Ollama the same day this
  // page was built -- so when this entry loads, the page runs the SAME model
  // the benchmark measured. Its published builds cannot hold a page (the
  // kernel defect the note below the fold documents), so the committed page
  // never picks it -- but the record stays enumerable for the day the
  // upstream fix lands, selected by rebuilding with --local-model.
  const E2B_REPO = new URL(__E2B_BASE_JSON__, location.href).href.replace(/\\/$/, "");
  const E2B = {
    model: E2B_REPO,
    // Suffixed per packaging so the browser's model cache can never hand
    // one build's files to another.
    model_id: __E2B_ID_JSON__,
    model_lib: E2B_REPO + __E2B_LIB_JSON__,
    required_features: ["shader-f16"],
    // gemma4 is a hybrid: 512-token sliding layers interleaved with
    // full-attention layers. The engine handles that natively (it does for
    // gemma3) -- so override ONLY the context size and leave the model's
    // dual window declaration alone. Forcing a single mode breaks half the
    // layers: all-sliding caps the cache at 512 (crash on a page),
    // all-context corrupts the sliding layers (silence past 512). Both
    // were measured here before this line existed.
    overrides: { context_window_size: __E2B_CTX__,
                 // A chunk is one GPU dispatch; this model's 262k-token
                 // vocabulary makes big chunks lose the GPU device on
                 // laptop cards (observed at 8192). 1024 is the proven size.
                 prefill_chunk_size: 1024 },
  };
  const list = webllm.prebuiltAppConfig.model_list;
  // The measured class is 2-4B: gemma4's edge editions hit 100%/44% and
  // 95%/56% on the gold pages. A 1B model collapses into repetition under
  // these instructions -- observed on the proof page, not assumed -- so the
  // picker holds the class rather than taking the smallest thing available.
  const inClass = list.filter(m =>
      /instruct|it\\b|-it-/i.test(m.model_id) &&
      /(^|[^0-9.])(2b|3b|4b)\\b/i.test(m.model_id));
  // Within the class, prefer current-generation models known to follow the
  // one instruction everything hinges on: quote the sentence VERBATIM. The
  // 2024-era builds paraphrase, and the checks rightly refuse paraphrases.
  const prefer = [/qwen3\\.5-4b.*q4f16/i, /qwen3\\.5-4b/i, /qwen3-4b.*q4f16/i,
                  /qwen3\\.5-2b.*q4f16/i, /llama-3\\.2-3b.*q4f16/i];
  // Preference runs over the FULL list: Qwen3-era models dropped the word
  // "Instruct" from their names (instruction-tuned is their default), so an
  // instruct-word filter would hide exactly the models preferred most.
  let chosen = __E2B_PICK__;
  if (!chosen) {
    for (const rx of prefer) {
      chosen = list.find(m => rx.test(m.model_id));
      if (chosen) break;
    }
  }
  const pick = arr => arr.slice().sort((x, y) =>
      (y.vram_required_MB || 0) - (x.vram_required_MB || 0))[0];
  if (!chosen) chosen = pick(inClass) || pick(list.slice());
  if (!chosen) { status("No browser model available from the model index."); return; }
  modelId = chosen.model_id;
  $("model-note").textContent =
      "Model: " + modelId + " — downloads once into browser cache, then stays.";
  status("Fetching " + modelId + " into browser cache…");
  bar.hidden = false;
  const isE2B = chosen === E2B;
  const engineConfig = {
    initProgressCallback: r => {
      bar.value = r.progress || 0;
      status(r.text || "loading…");
    },
  };
  if (isE2B) engineConfig.appConfig = { model_list: [E2B, ...list] };
  try {
    // The e2b record carries its own overrides; chat options here would
    // shadow them, so only catalogue models get sized from this side.
    engine = await webllm.CreateMLCEngine(modelId, engineConfig,
      isE2B ? undefined
            : { context_window_size: 8192, sliding_window_size: -1 });
  } catch (e) {
    if (isE2B) {
      // This browser cannot carry the benchmarked model (no f16 shaders, or
      // the download failed). Fall back to the catalogue and say so -- and
      // keep the reason inspectable, because a status line scrolls away.
      window._e2bError = String(e && e.stack || e);
      console.error("e2b load failed:", e);
      status("The benchmarked model would not load here (" +
             String(e).slice(0, 80) + "); falling back to a catalogue model.");
      chosen = null;
      for (const rx of prefer) {
        chosen = list.find(m => rx.test(m.model_id));
        if (chosen) break;
      }
      if (!chosen) chosen = pick(inClass) || pick(list.slice());
      modelId = chosen.model_id;
      $("model-note").textContent =
          "Model: " + modelId + " (fallback) — downloads once into browser cache.";
      engine = await webllm.CreateMLCEngine(modelId, engineConfig,
        { context_window_size: 8192, sliding_window_size: -1 });
    } else { throw e; }
  }
  bar.hidden = true;
  window._engine = engine;   // inspectable: the reader checks its own reader
  status("Model ready on your GPU. Nothing was installed.");
}

async function ensureEngine() {
  if (engine) return true;
  try { await loadEngine(); }
  catch (e) { status("The model could not load here: " + String(e).slice(0, 120)); }
  return !!engine;
}

/* ---- reading one page --------------------------------------------------- */
function fillTemplate(doc, pageNo, text) {
  let out = USER_TMPL;
  const clean = v => String(v ?? "").replace(/[{}]/g, " ");
  const fill = { title: clean(doc.title) || "(unknown)",
                 publisher: clean(doc.publisher) || "(unknown)",
                 year: clean(doc.year) || "(unknown)",
                 page: String(pageNo) };
  for (const key of ["title", "publisher", "year", "page"])
    out = out.replace("{" + key + "}", () => fill[key]);
  return out.replace("{text}", () => text);
}

async function readPage(userPrompt, label) {
  // Reasoning-mode models (Qwen3 era) burn the whole token budget thinking
  // before they transcribe a single record. Their off switch must ride on
  // the USER message -- in the system prompt it is ignored, which cost a
  // 20,000-character thought spiral before this line moved. The engine's
  // native enable_thinking switch is set too; measured together they cut
  // the same question from 59 tokens of reasoning to 2 of answer.
  const isThinker = /qwen3/i.test(modelId);
  const noThink = isThinker ? "\\n/no_think" : "";
  const req = {
    messages: [
      // Every browser model gets the compact instructions: small models
      // drown in the full production prompt, and the compact set is the
      // one being iterated toward verified in-browser records.
      { role: "system", content: SYSTEM_SMALL },
      { role: "user", content: userPrompt + noThink },
    ],
    temperature: 0,
    // A guard against degenerate repetition in small quantized models.
    frequency_penalty: 0.3,
    max_tokens: 4000,
    stream: true,
  };
  if (isThinker) req.extra_body = { enable_thinking: false };
  const chunks = await engine.chat.completions.create(req);
  let raw = "";
  for await (const c of chunks) {
    raw += c.choices?.[0]?.delta?.content || "";
    status(label + " — " + raw.length + " characters produced");
  }
  window._raw = raw;
  $("raw-out").textContent = raw;
  return raw;
}

/* ---- rendering ---------------------------------------------------------- */
let nPassed = 0, nRefused = 0, nPagesRead = 0;
function addRow(r, doc, pageNo, passed, why) {
  const quote = String(r.source_text || "");
  const leaf = "https://archive.org/details/" + encodeURIComponent(doc.identifier)
             + "/page/n" + (pageNo - 1) + "/mode/2up";
  const checks = passed
    ? '<span class="ok">✓ sentence on page</span><br><span class="ok">✓ '
      + (r.value === null || r.value === undefined ? "conclusion, no value to check"
                                                   : "value in sentence") + "</span>"
    : '<span class="bad">✗ ' + esc(why) + "</span>";
  const row = document.createElement("tr");
  row.innerHTML =
    "<td>" + esc(r.kind || "") + "</td>" +
    "<td>" + esc(r.parameter || "") + "</td>" +
    '<td class="v">' + esc(r.value ?? "") + " " + esc(r.unit || "") + "</td>" +
    '<td class="q">“' + esc(quote.slice(0, 160)) + "”</td>" +
    '<td><a href="' + leaf + '" target="_blank" rel="noopener">p.' + pageNo + "</a></td>" +
    "<td>" + checks + "</td>";
  document.querySelector("#tbl tbody").appendChild(row);
}
function headline() {
  $("results").hidden = false;
  $("headline").textContent =
    nPagesRead + (nPagesRead === 1 ? " page" : " pages") + " read in this tab — "
    + nPassed + " records passed both checks here, " + nRefused + " refused in the open.";
}
function addVerdict(html) {
  const div = document.createElement("div");
  div.className = "verdict";
  div.innerHTML = html;
  $("verdicts").appendChild(div);
}

/* ---- publishing one document's survivors -------------------------------- */
async function publishDoc(doc, records) {
  if (!records.length) {
    addVerdict("<b>" + esc(doc.title) + "</b>: nothing survived the checks here; "
             + "nothing was sent.");
    return;
  }
  status("Sending " + records.length + " records to the site for re-verification…");
  let v;
  try {
    v = await api("/api/bundle", {
      bundle_version: 1,
      contributor: "a browser (" + (modelId || "webllm") + ")",
      note: "read in a browser tab: " + TOWN.place,
      n_records: records.length,
      identifiers: [...new Set(records.map(r => r.provenance.identifier))],
      records,
    });
  } catch (e) {
    addVerdict("<b>" + esc(doc.title) + "</b>: <span class='bad'>could not send — "
             + esc(String(e).slice(0, 140)) + "</span>. The records are still in "
             + "this tab (window._passing).");
    return;
  }
  window._verdicts = (window._verdicts || []).concat([v]);
  const bits = [];
  bits.push("<b>" + (v.merged || 0) + " published</b>");
  if (v.already_here) bits.push(v.already_here + " already here");
  if (v.refused) bits.push('<span class="bad">' + v.refused +
                           " refused by the archive check</span>");
  let h = "<b>" + esc(doc.title) + "</b>: sent " + records.length + " → " + bits.join(", ") + ".";
  if (v.why_refused && v.why_refused.length) {
    h += "<details><summary class='note'>why the archive refused some</summary><pre>"
       + esc(v.why_refused.join("\\n")) + "</pre></details>";
  }
  addVerdict(h);
}

/* ---- the whole read ----------------------------------------------------- */
async function readTown() {
  go.disabled = true;
  stopBtn.hidden = false;
  stopBtn.disabled = false;
  STOP = false;
  if (!(await ensureEngine())) { go.disabled = false; stopBtn.hidden = true; return; }
  window._passing = [];
  const t0 = performance.now();
  let totalPublished = 0, totalAlready = 0, totalRefusedByArchive = 0;
  const docs = TOWN.documents;
  for (let d = 0; d < docs.length && !STOP; d++) {
    const doc = docs[d];
    const tag = "document " + (d + 1) + "/" + docs.length;
    status(tag + " — fetching its readable pages…");
    let got;
    try { got = await api("/api/browser/pages", { identifier: doc.identifier }); }
    catch (e) {
      addVerdict("<b>" + esc(doc.title) + "</b>: <span class='bad'>could not fetch "
               + "its pages — " + esc(String(e).slice(0, 120)) + "</span>");
      continue;
    }
    const pages = got.pages || [];
    if (!pages.length) {
      addVerdict("<b>" + esc(doc.title) + "</b>: no prose pages to read "
               + "(" + (got.n_pages || 0) + " pages, none routed to prose).");
      continue;
    }
    const docRecords = [];
    for (let i = 0; i < pages.length; i++) {
      if (STOP) break;
      const page = pages[i];
      const label = tag + " · page " + (i + 1) + "/" + pages.length
                  + " (p." + page.page + ") · " + nPassed + " passed so far";
      let raw;
      try { raw = await readPage(fillTemplate(doc, page.page, page.text), label); }
      catch (e) {
        status(label + " — the model failed on this page: " + String(e).slice(0, 80));
        continue;
      }
      nPagesRead++;
      for (const r of parseRecords(raw)) {
        if (!r || typeof r !== "object") continue;
        const out = toBundleRecord(r, doc, page.page, page.text);
        if (out.record) {
          nPassed++; docRecords.push(out.record); window._passing.push(out.record);
          addRow(r, doc, page.page, true);
        } else {
          nRefused++;
          addRow(r, doc, page.page, false, out.why);
        }
      }
      headline();
    }
    if (got.omitted) {
      addVerdict("<b>" + esc(doc.title) + "</b>: this document has " + got.omitted
               + " more prose pages than one sitting hands out; the installed "
               + "reader covers the rest.");
    }
    // Publish after every document rather than once at the end: a read is
    // slow and a browser tab is mortal, and what has already survived should
    // not die with it. Re-sends deduplicate on the server, so stopping and
    // starting again costs nothing.
    const v0 = window._verdicts ? window._verdicts.length : 0;
    await publishDoc(doc, docRecords);
    const v = (window._verdicts || [])[v0];
    if (v) { totalPublished += v.merged || 0; totalAlready += v.already_here || 0;
             totalRefusedByArchive += v.refused || 0; }
  }
  const mins = ((performance.now() - t0) / 60000).toFixed(1);
  stopBtn.hidden = true;
  go.disabled = false;
  go.textContent = "Read it again";
  const town = "/#place=" + encodeURIComponent(TOWN.place);
  $("results-note").innerHTML =
    (STOP ? "Stopped. " : "Done. ") + "This tab read " + nPagesRead + " pages in "
    + mins + " min; the site verified every sent sentence against archive.org and "
    + "published <b>" + totalPublished + "</b> new readings"
    + (totalAlready ? " (" + totalAlready + " were already here)" : "")
    + (totalRefusedByArchive ? "; it refused " + totalRefusedByArchive : "") + ". "
    + (totalPublished || totalAlready
       ? '<a href="' + town + '">See ' + esc(TOWN.place) + "’s page — your read is on it.</a>"
       : "Nothing new was published this time.");
  status(STOP ? "Stopped, politely. Press the button to continue where it left off."
              : "Done. The model ran entirely on your graphics card.");
}

/* ---- the one-page proof ------------------------------------------------- */
async function readDemo() {
  $("demo-go").disabled = true;
  if (!(await ensureEngine())) { $("demo-go").disabled = false; return; }
  const t0 = performance.now();
  let raw;
  try { raw = await readPage(DEMO.user, "reading the proof page"); }
  catch (e) { status("The model failed: " + String(e).slice(0, 120));
              $("demo-go").disabled = false; return; }
  const secs = ((performance.now() - t0) / 1000).toFixed(0);
  const doc = { identifier: DEMO.identifier, title: DEMO.title,
                publisher: DEMO.publisher, year: DEMO.year, facility: "" };
  let passed = 0, refused = 0, shown = 0;
  for (const r of parseRecords(raw)) {
    if (!r || typeof r !== "object") continue;
    shown++;
    const out = toBundleRecord(r, doc, DEMO.page, DEMO.text);
    if (out.record) { passed++; addRow(r, doc, DEMO.page, true); }
    else { refused++; addRow(r, doc, DEMO.page, false, out.why); }
  }
  $("results").hidden = false;
  $("headline").textContent = shown + " records read in " + secs
    + "s, inside this browser tab, by " + modelId + " — " + passed
    + " passed both checks, " + refused + " refused in the open.";
  $("results-note").textContent =
    "This was the one-page proof; nothing is sent anywhere from it. Pick a town "
    + "above to read pages nobody has read and publish what survives.";
  status("Done. The model ran entirely on your graphics card.");
  $("demo-go").disabled = false;
}

/* ---- town selection ----------------------------------------------------- */
async function loadPlan(place) {
  $("town-card").hidden = false;
  $("town-name").textContent = place;
  $("town-docs").innerHTML = '<span class="note">asking the site which documents '
    + "this is…</span>";
  let plan;
  try { plan = await api("/api/browser/plan", { place }); }
  catch (e) {
    $("town-docs").innerHTML = '<span class="bad">' + esc(String(e).slice(0, 160))
      + "</span>";
    return;
  }
  TOWN = plan;
  const docs = plan.documents || [];
  if (!docs.length) {
    $("town-docs").innerHTML = "The collection's catalogue titles never mention “"
      + esc(place) + "”. It may still appear inside documents filed under other "
      + "names — that search needs the installed reader.";
    return;
  }
  const leaves = docs.reduce((a, x) => a + (x.leaves || 0), 0);
  $("town-docs").innerHTML = docs.map(x =>
    '<div class="doc">' + esc(x.title) + (x.year ? " — " + esc(x.year) : "")
    + (x.leaves ? ' <span class="note">(' + x.leaves + " leaves)</span>" : "")
    + "</div>").join("");
  $("town-note").textContent = docs.length + " document" + (docs.length === 1 ? "" : "s")
    + (leaves ? ", about " + leaves + " scanned leaves in all" : "")
    + ". Only the pages that read as prose are read here, at very roughly a "
    + "minute a page; you can stop at any point and keep what survived. "
    + (docs.length === plan.max_documents
       ? "This is the reader's " + plan.max_documents + "-document budget; a "
         + "town with more waits for the installed reader. " : "");
  go.textContent = "Read " + place + " in this browser & publish what survives";
  go.disabled = !("gpu" in navigator);
}

async function loadPicker() {
  let geo;
  try { geo = await (await fetch("/api/places.geojson")).json(); }
  catch (e) { return false; }
  const unread = (geo.features || [])
    .map(f => f.properties || {})
    .filter(p => p.place && !p.extracted)
    .sort((a, b) => (b.years || 0) - (a.years || 0));
  if (!unread.length) return false;
  $("pick-card").hidden = false;
  $("town-select").innerHTML = unread.map(p =>
    '<option value="' + esc(p.place) + '">' + esc(p.place) + " — "
    + (p.years || "?") + " reports, " + esc(p.first || "?") + "–"
    + esc(p.last || "?") + "</option>").join("");
  $("pick-note").textContent = unread.length
    + " municipalities are on the map with nothing read yet.";
  $("town-go").onclick = () => {
    const free = $("town-free").value.trim();
    const chosen = free || $("town-select").value;
    if (chosen) location.search = "?place=" + encodeURIComponent(chosen);
  };
  return true;
}

/* ---- boot --------------------------------------------------------------- */
$("page-text").textContent = DEMO.text;
$("demo-title").textContent = DEMO.title + " — page " + DEMO.page;
$("demo-link").href = "https://archive.org/details/" + encodeURIComponent(DEMO.identifier)
                    + "/page/n" + (DEMO.page - 1) + "/mode/2up";
go.addEventListener("click", readTown);
$("demo-go").addEventListener("click", readDemo);
stopBtn.addEventListener("click", () => {
  STOP = true;
  stopBtn.disabled = true;
  status("Finishing this page, then stopping…");
});

(async () => {
  const capable = boot();
  $("demo-go").disabled = !capable;
  if (PLACE) {
    go.textContent = "Read " + PLACE + " in this browser & publish what survives";
    $("demo-card").hidden = false;
    await loadPlan(PLACE);
  } else {
    go.textContent = "Pick a town above first";
    $("demo-card").hidden = false;
    const picked = await loadPicker();
    if (!picked) {
      // No site behind this page (opened as a file, or served statically):
      // the one-page proof still works entirely in the tab.
      $("run-card").hidden = true;
    }
  }
})();
</script>
</body>
</html>
"""


# The three published browser packagings of gemma-4-E2B-it, oldest first,
# all probed on this page 2026-08-16 and all failing the same way: correct
# answers while the whole prompt fits in ~512 tokens, silence (or a KV-cache
# crash) beyond. Two independent compile lineages -- welcoma/kirbyz's
# gemma4-webllm fork and maelstrome's build against upstream PR #3485 --
# share the failure, which places the defect in the TVM WebGPU kernels for
# this hybrid-attention architecture, not in any packaging choice. kirbyz's
# wasm additionally refuses to allocate the 8192-token cache its own config
# advertises; maelstrome's loses the GPU device if its 8192-token prefill
# chunk is not capped to 1024. Kept enumerable for retesting the day the
# upstream kernels are fixed. Local mirrors live under portal/models/
# behind HF-shaped junction aliases because the engine appends
# /resolve/main/... to every model URL.
BUILDS = {
    "welcoma": {
        "public": "https://huggingface.co/welcoma/gemma-4-E2B-it-q4f16_1-MLC",
        "local": "/models/e2b-hf",
        "lib": "/resolve/main/libs/gemma-4-E2B-it-q4f16_1-MLC-webgpu.wasm",
        "ctx": 4096,
    },
    "kirbyz": {
        "public": "https://huggingface.co/KirbyzDaShizNit/gemma-4-E2B-it-q4f16_1-MLC",
        "local": "/models/kirbyz-hf",
        "lib": "/resolve/main/libs/gemma-4-E2B-it-q4f16_1-MLC-webgpu.wasm",
        "ctx": 4096,
    },
    "maelstrome": {
        # Weights sit in the repo's google-it/ subfolder; the local alias
        # flattens that. A public URL for this build needs a root-shaped
        # copy (republished) rather than the subfolder repo. Compiled for
        # the model's full 131072-token window; the KV cache is allocated
        # at the runtime size, so ask for a laptop-sized 8192.
        "public": "https://huggingface.co/Maelstrome/wave-gemma4-E2B-q4f16_1-MLC",
        "local": "/models/mael-hf",
        "lib": "/resolve/main/gemma-4-E2B-it-q4f16_1-webgpu.wasm",
        "ctx": 8192,
    },
}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--local-model", nargs="?", const="welcoma", default=None,
                    choices=sorted(BUILDS),
                    help="point the page at a mirror under portal/models/... "
                         "served beside it (for testing without the Hugging "
                         "Face CDN); the committed page uses the public copy")
    args = ap.parse_args()
    # Three published browser packagings of the same model exist; each mirror
    # presents the HuggingFace URL shape because the engine appends
    # /resolve/main/... to every model URL regardless of host. The page joins
    # model_lib as E2B_REPO + the lib path, so both are relative to the base.
    build = BUILDS[args.local_model or "welcoma"]
    e2b_base = build["local"] if args.local_model else build["public"]

    pages = {p.page: p for p in Archive().pages(IDENTIFIER)}
    text = pages[PAGE_NO].text
    demo = {
        "identifier": IDENTIFIER,
        "page": PAGE_NO,
        "title": TITLE,
        "year": YEAR,
        "publisher": PUBLISHER,
        "text": text,
        # Prebuilt with the same template the tool fills per page, so the
        # proof and the tool cannot drift.
        "user": USER_TEMPLATE.format(
            title=TITLE, publisher=PUBLISHER, year=YEAR, page=PAGE_NO,
            text=text),
    }

    html = TEMPLATE
    for sentinel, value in {
        "__SYSTEM_JSON__": json.dumps(SMALL_SYSTEM),
        "__USER_TMPL_JSON__": json.dumps(USER_TEMPLATE),
        "__DEMO_JSON__": json.dumps(demo),
        "__E2B_BASE_JSON__": json.dumps(e2b_base),
        "__E2B_LIB_JSON__": json.dumps(build["lib"]),
        "__E2B_ID_JSON__": json.dumps(
            f"gemma-4-E2B-it-q4f16_1-MLC-{args.local_model or 'welcoma'}"),
        "__E2B_CTX__": str(build["ctx"]),
        "__E2B_PICK__": "E2B" if args.local_model else "null",
    }.items():
        assert sentinel in html, f"template lost its {sentinel} slot"
        html = html.replace(sentinel, value)

    OUT.write_text(html, encoding="utf-8")
    SERVED.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} and {SERVED} ({len(html) // 1024} KB; demo page text "
          f"{len(text)} chars, prompt imported from concordance.extract)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
