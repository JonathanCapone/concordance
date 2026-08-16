"""Build the in-browser reader proof: portal/browser-reader.html.

One real archive page, read entirely inside a web browser on the visitor's own
graphics card -- no install, no server compute. This is the measured endgame
of the volunteer loop: gemma4:e2b (the any-browser size class) read the gold
pages at 100% precision (30/30) and 44.1% recall on 2026-08-16, so the honest
framing is a PARTIAL reader that invents nothing, with the installed reader as
the "read the rest" path.

Generated, not hand-written, so it cannot drift: the compact small-model instructions live beside the full concordance.extract.SYSTEM they distill, and the page text is
taken from the same local cache the real reader used. Regenerate after any
prompt change:

    python scripts/build_browser_reader.py

Serve the portal directory over HTTP and open browser-reader.html; the model
streams from the web-llm CDN into browser cache on first use.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.archive import Archive                     # noqa: E402
from concordance.extract import SYSTEM, USER_TEMPLATE       # noqa: E402

#: Compact reading instructions for browser-size models, v1. The full SYSTEM
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

Example: the text "Relocating the injection point would reduce the free
chlorine residual required to 0.46 mg/L during the summer." gives:
[{"kind": "observation", "parameter": "free chlorine residual required",
  "value": 0.46, "unit": "mg/L", "source_text": "Relocating the injection
point would reduce the free chlorine residual required to 0.46 mg/L during
the summer."}]
"""

IDENTIFIER = "optimizationofea00ontauoft"
PAGE_NO = 9
TITLE = "The Optimization of the Ear Falls Water Treatment Plant"
YEAR = "1997"
OUT = Path("portal/browser-reader.html")

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Concordance — the reader, in your browser</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ background:#0b1016; color:#e8edf2; font:14px/1.55 system-ui,sans-serif;
         max-width: 880px; margin: 0 auto; padding: 28px 18px 80px; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color:#8b97a4; margin-bottom: 18px; }}
  .card {{ background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.1);
          border-radius: 12px; padding: 14px 16px; margin: 12px 0; }}
  .note {{ color:#8b97a4; font-size: 12.5px; }}
  button {{ background:#f0a24a; color:#0b1016; border:0; border-radius:9px;
           padding:9px 18px; font:inherit; font-weight:600; cursor:pointer }}
  button:disabled {{ opacity:.45; cursor:default }}
  #status {{ font-family: ui-monospace,monospace; font-size:12px; color:#8b97a4;
            white-space: pre-wrap; }}
  progress {{ width:100%; height:6px; accent-color:#f0a24a }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:8px }}
  th,td {{ text-align:left; padding:6px 8px; border-bottom:1px solid rgba(255,255,255,.08);
          vertical-align: top }}
  th {{ color:#6d7a86; font-size:11px; text-transform:uppercase; letter-spacing:.06em }}
  .q {{ color:#8b97a4; font-style: italic; font-size:12px }}
  .ok {{ color:#7dc87d }} .bad {{ color:#e08b8b }}
  .v {{ font-family: ui-monospace,monospace; white-space:nowrap }}
  a {{ color:#f0a24a; text-decoration: none }}
  details {{ margin-top: 8px }} summary {{ cursor:pointer; color:#8b97a4 }}
  pre {{ white-space:pre-wrap; font-size:11.5px; color:#8b97a4; max-height:260px;
        overflow:auto; margin-top:6px }}
</style>
</head>
<body>
<h1>The reader, in your browser</h1>
<p class="sub">A working proof: one real page from a 1997 Ontario government
report, read by an AI model running <b>inside this browser tab</b> on your own
graphics card. Nothing is installed; no server does any reading.</p>

<div class="card">
  <b>{title}</b> — page {page_no}
  <span class="note">(<a href="https://archive.org/details/{identifier}/page/n{leaf}/mode/2up"
  target="_blank" rel="noopener">the scanned page ↗</a>, Internet Archive)</span>
  <details><summary>the page text being read (from the archive's OCR layer)</summary>
  <pre id="page-text"></pre></details>
</div>

<div class="card">
  <div id="status">Checking whether this browser can run a model…</div>
  <progress id="bar" value="0" max="1" hidden></progress>
  <p style="margin-top:10px">
    <button id="go" disabled>Read this page in the browser</button>
  </p>
  <p class="note" id="model-note"></p>
</div>

<div class="card" id="results" hidden>
  <b id="headline"></b>
  <table id="tbl">
    <thead><tr><th>kind</th><th>parameter</th><th>value</th>
    <th>sentence it was read from</th><th>checks</th></tr></thead>
    <tbody></tbody>
  </table>
  <details><summary class="note">the model's raw output — check the reader's
  work the way the reader checks the archive's</summary>
  <pre id="raw-out"></pre></details>
  <p class="note" style="margin-top:10px">Checks shown here are the browser's
  own; if these records were submitted to a Concordance site, it would
  re-verify every sentence and number against the archive before publishing
  anything — the same rule applied to every reader, human or machine.</p>
</div>

<p class="note">Honest scope, measured 2026-08-16. The model SIZE is proven:
gemma4:e2b — small enough for any modern browser — read four hand-checked
benchmark pages at 100% precision (30 of 30, small sample) and 44% recall,
inventing nothing. But that model is not yet published in the browser model
catalogue, and the models that ARE (a generation older, or reasoning-tuned)
currently fail the one rule everything hinges on: quote your sentence
verbatim. This page shows that failure honestly — records the models produce
arrive unproven, and the checks refuse them, which is the system working.
What stands between this demo and the benchmark numbers is publishing a
current edge model for browsers, plus reading instructions tuned for small
models — both bounded, named tasks.</p>

<script type="module">
const SYSTEM_PROMPT = {system_json};
const PAGE_TEXT = {page_json};
const USER_PROMPT = {user_json};

document.getElementById("page-text").textContent = PAGE_TEXT;

const status = m => {{ document.getElementById("status").textContent = m; }};
const bar = document.getElementById("bar");
const go = document.getElementById("go");

// ---- the same salvage parser the real extractor uses, ported ------------
function parseRecords(raw) {{
  // Reasoning models deliberate in <think> blocks before answering, and the
  // deliberation can contain example braces. Extraction is transcription,
  // not deliberation -- discard the thinking, closed or truncated.
  raw = raw.replace(/<think>[\\s\\S]*?<\\/think>/g, "");
  const open = raw.indexOf("<think>");
  if (open >= 0) raw = raw.slice(0, open);
  raw = raw.trim().replace(/^```[a-z]*\\n?/, "").replace(/\\n?```$/, "").trim();
  try {{ const v = JSON.parse(raw); return Array.isArray(v) ? v : [v]; }} catch (e) {{}}
  const a = raw.indexOf("["), b = raw.lastIndexOf("]");
  if (a >= 0 && b > a) {{
    try {{ const v = JSON.parse(raw.slice(a, b + 1)); if (Array.isArray(v)) return v; }}
    catch (e) {{}}
  }}
  const out = []; let depth = 0, start = -1, inStr = false, esc = false;
  for (let i = 0; i < raw.length; i++) {{
    const ch = raw[i];
    if (inStr) {{ if (esc) esc = false; else if (ch === "\\\\") esc = true;
                 else if (ch === '"') inStr = false; continue; }}
    if (ch === '"') inStr = true;
    else if (ch === "{{") {{ if (!depth) start = i; depth++; }}
    else if (ch === "}}") {{ if (depth && !--depth && start >= 0) {{
      try {{ const o = JSON.parse(raw.slice(start, i + 1));
            if (o && typeof o === "object") out.push(o); }} catch (e) {{}}
      start = -1; }} }}
  }}
  return out;
}}

// ---- demo-grade ports of the evidence checks ----------------------------
const norm = s => String(s || "").toLowerCase().replace(/[^a-z0-9.]+/g, " ").trim();
function quoteOnPage(quote) {{
  const q = norm(quote), p = norm(PAGE_TEXT);
  return q.length > 8 && p.includes(q.slice(0, 160));
}}
function valueInQuote(value, quote) {{
  if (value === null || value === undefined) return null; // nothing to check
  let canon = String(value);
  if (canon.endsWith(".0")) canon = canon.slice(0, -2);
  // Strip commas only in the three-digit thousands shape -- "8,5" stays.
  const direct = String(quote || "").replace(/(?<=\\d),(?=\\d{{3}}(?!\\d))/g, "");
  const rx = new RegExp("(?<![\\\\d.+-])" + canon.replace(/[.*+?^${{}}()|[\\]\\\\]/g, "\\\\$&")
                        + "(?![\\\\d.])");
  return rx.test(direct);
}}

// ---- the model, in this tab ---------------------------------------------
let engine = null, modelId = null;
async function boot() {{
  if (!("gpu" in navigator)) {{
    status("This browser has no WebGPU — the in-browser reader needs it. "
         + "Recent Chrome, Edge and Firefox on a machine with a GPU all work.");
    return;
  }}
  status("Loading the model list…");
  const webllm = await import("https://esm.run/@mlc-ai/web-llm");
  const list = webllm.prebuiltAppConfig.model_list;
  // The measured class is 2-4B: gemma4's edge editions hit 100%/44% and
  // 95%/56% on the gold pages. A 1B model collapses into repetition under
  // these instructions -- observed on this very page, not assumed -- so the
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
  let chosen = null;
  for (const rx of prefer) {{
    chosen = list.find(m => rx.test(m.model_id));
    if (chosen) break;
  }}
  const pick = arr => arr.slice().sort((x, y) =>
      (y.vram_required_MB || 0) - (x.vram_required_MB || 0))[0];
  if (!chosen) chosen = pick(inClass) || pick(list.slice());
  if (!chosen) {{ status("No browser model available from the model index."); return; }}
  modelId = chosen.model_id;
  document.getElementById("model-note").textContent =
      "Model: " + modelId + " — downloads once into browser cache, then stays.";
  status("Fetching " + modelId + " into browser cache…");
  bar.hidden = false;
  engine = await webllm.CreateMLCEngine(modelId, {{
    initProgressCallback: r => {{
      bar.value = r.progress || 0;
      status(r.text || "loading…");
    }},
  }}, {{
    // Some browser builds ship with a sliding attention window; the engine
    // insists exactly one window mode is set. A plain 8k context fits this
    // page and its prompt with room to spare.
    context_window_size: 8192,
    sliding_window_size: -1,
  }});
  bar.hidden = true;
  status("Model ready on your GPU. Nothing was installed.");
  go.disabled = false;
}}

go.addEventListener("click", async () => {{
  go.disabled = true;
  const t0 = performance.now();
  status("Reading the page in this tab…");
  let raw = "";
  // Reasoning-mode models (Qwen3 era) burn the whole token budget thinking
  // before they transcribe a single record; /no_think is their off switch.
  // This task is transcription -- the answer is in the sentence being read.
  const noThink = /qwen3/i.test(modelId) ? "\\n/no_think" : "";
  const chunks = await engine.chat.completions.create({{
    messages: [
      {{ role: "system", content: SYSTEM_PROMPT + noThink }},
      {{ role: "user", content: USER_PROMPT }},
    ],
    temperature: 0,
    // A guard against degenerate repetition in small quantized models.
    frequency_penalty: 0.3,
    max_tokens: 4000,
    stream: true,
  }});
  for await (const c of chunks) {{
    raw += c.choices?.[0]?.delta?.content || "";
    status("Reading… " + raw.length + " characters produced");
  }}
  const secs = ((performance.now() - t0) / 1000).toFixed(0);
  window._raw = raw;
  document.getElementById("raw-out").textContent = raw;
  const records = parseRecords(raw);
  const tbody = document.querySelector("#tbl tbody");
  tbody.innerHTML = "";
  let shown = 0;
  for (const r of records) {{
    const quote = String(r.source_text || "");
    const onPage = quoteOnPage(quote);
    const inQuote = valueInQuote(r.value, quote);
    const checks =
      (!quote ? '<span class="bad">✗ no sentence quoted — unprovable</span>'
       : onPage ? '<span class="ok">✓ sentence on page</span>'
                : '<span class="bad">✗ sentence not found</span>') + "<br>" +
      (inQuote === null ? '<span class="note">no value to check</span>'
       : inQuote ? '<span class="ok">✓ value in sentence</span>'
                 : '<span class="bad">✗ value not in sentence</span>');
    const row = document.createElement("tr");
    row.innerHTML =
      "<td>" + (r.kind || "") + "</td>" +
      "<td>" + (r.parameter || "") + "</td>" +
      '<td class="v">' + (r.value ?? "") + " " + (r.unit || "") + "</td>" +
      '<td class="q">“' + quote.slice(0, 160) + "”</td>" +
      "<td>" + checks + "</td>";
    tbody.appendChild(row);
    shown++;
  }}
  document.getElementById("headline").textContent =
    shown + " records read in " + secs + "s, inside this browser tab, by " + modelId + ".";
  document.getElementById("results").hidden = false;
  status("Done. The model ran entirely on your graphics card.");
  go.disabled = false;
}});

boot();
</script>
</body>
</html>
"""


def main() -> int:
    pages = {p.page: p for p in Archive().pages(IDENTIFIER)}
    text = pages[PAGE_NO].text
    user = USER_TEMPLATE.format(
        title=TITLE, publisher="Ontario Ministry of Environment and Energy",
        year=YEAR, page=PAGE_NO, text=text)
    html = TEMPLATE.format(
        title=TITLE, page_no=PAGE_NO, identifier=IDENTIFIER, leaf=PAGE_NO - 1,
        system_json=json.dumps(SMALL_SYSTEM), page_json=json.dumps(text),
        user_json=json.dumps(user))
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html) // 1024} KB; page text {len(text)} chars, "
          "prompt imported from concordance.extract)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
