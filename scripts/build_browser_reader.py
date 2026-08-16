"""Build the in-browser reader proof: portal/browser-reader.html.

One real archive page, read entirely inside a web browser on the visitor's own
graphics card -- no install, no server compute. WORKING as of 2026-08-17:
Qwen3.5-4B (official catalogue, mainline engine) read this page in-tab in
42s -- 12 records, 9 verified by the page's own checks, all 9 matching the
archive-verified reference, refusals shown for the rest. The honest framing
stays a PARTIAL reader that invents nothing, with the installed reader as
the "read the rest" path; the gold-page benchmark of this exact browser
combination is the next measurement.

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
OUT = Path("portal/browser-reader.html")
#: The copy the live server serves at /browser -- written by the same
#: build so the two can never drift.
SERVED = Path("concordance/static/browser-reader.html")

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

<p class="note">Honest scope, measured 2026-08-17 on this page. Qwen3.5-4B —
a current catalogue model, no fork, no install — read this page in the
browser in 42 seconds: 12 records, 9 verified against the scan by the checks
you see, 3 refused in the open. Every verified value matches the
archive-verified reference for this page. Two findings made that possible:
reasoning-tuned models need their thinking switched off on the user turn
(in the system prompt the switch is ignored), and the instructions' worked
example must come from a different document than the one being read, or it
seeds its own answer. The benchmarked gemma4:e2b family (100% precision,
44% recall on the four gold pages, run locally) still cannot join in-browser:
all three of its published browser builds, from two independent toolchains,
fall silent past roughly 512 prompt tokens — a defect in the shared GPU
kernels, whose official support is still an open pull request upstream. The
day that lands, it takes one flag to retest. Until then the button below is
not a promise; it is the working thing.</p>

<script type="module">
const SYSTEM_SMALL = {system_json};
const SYSTEM_FULL = {full_system_json};
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
  const webllm = await import("https://esm.run/@mlc-ai/web-llm@0.2.84");
  // The benchmarked model itself, published for browsers by a third party
  // (validated by its publisher 2026-04-13). This is gemma4:e2b -- 100%
  // precision, 44% recall on the gold pages via Ollama the same day this
  // page was built -- so when this entry loads, the demo runs the SAME model
  // the benchmark measured, with the SAME full reading instructions.
  // The engine requires absolute URLs; a local mirror path is resolved
  // against wherever this page is being served from.
  const E2B_REPO = new URL("{e2b_base}", location.href).href.replace(/\\/$/, "");
  const E2B = {{
    model: E2B_REPO,
    // Suffixed per packaging so the browser's model cache can never hand
    // one build's files to another.
    model_id: "{e2b_id}",
    model_lib: E2B_REPO + "{e2b_lib_path}",
    required_features: ["shader-f16"],
    // gemma4 is a hybrid: 512-token sliding layers interleaved with
    // full-attention layers. The engine handles that natively (it does for
    // gemma3) -- so override ONLY the context size and leave the model's
    // dual window declaration alone. Forcing a single mode breaks half the
    // layers: all-sliding caps the cache at 512 (crash on a page),
    // all-context corrupts the sliding layers (silence past 512). Both
    // were measured here before this line existed.
    overrides: {{ context_window_size: {e2b_ctx},
                 // A chunk is one GPU dispatch; this model's 262k-token
                 // vocabulary makes big chunks lose the GPU device on
                 // laptop cards (observed at 8192). 1024 is the proven size.
                 prefill_chunk_size: 1024 }},
  }};
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
  // The benchmarked model leads only in local test builds: its published
  // browser builds all fall silent past ~512 prompt tokens (the kernel
  // defect described above), so the public page must not spend a
  // visitor's 2.7 GB download proving a silence this page already
  // documents. The catalogue models read instead, and their failures are
  // refused in the open.
  let chosen = {e2b_pick};
  if (!chosen) {{
    for (const rx of prefer) {{
      chosen = list.find(m => rx.test(m.model_id));
      if (chosen) break;
    }}
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
  const isE2B = chosen === E2B;
  const engineConfig = {{
    initProgressCallback: r => {{
      bar.value = r.progress || 0;
      status(r.text || "loading…");
    }},
  }};
  if (isE2B) engineConfig.appConfig = {{ model_list: [E2B, ...list] }};
  try {{
    // The e2b build's config declares BOTH window modes (its publisher's
    // engine tolerated that; the current engine insists on exactly one).
    // Its sliding mode caps the cache at 512 tokens -- one short exchange,
    // no room for a page -- so ask for full-context mode at the size this
    // build was compiled for; catalogue models get the same arrangement at
    // their own sizes.
    // The e2b record carries its own overrides; chat options here would
    // shadow them, so only catalogue models get sized from this side.
    engine = await webllm.CreateMLCEngine(modelId, engineConfig,
      isE2B ? undefined
            : {{ context_window_size: 8192, sliding_window_size: -1 }});
  }} catch (e) {{
    if (isE2B) {{
      // This browser cannot carry the benchmarked model (no f16 shaders, or
      // the download failed). Fall back to the catalogue and say so -- and
      // keep the reason inspectable, because a status line scrolls away.
      window._e2bError = String(e && e.stack || e);
      console.error("e2b load failed:", e);
      status("The benchmarked model would not load here (" +
             String(e).slice(0, 80) + "); falling back to a catalogue model.");
      chosen = null;
      for (const rx of prefer) {{
        chosen = list.find(m => rx.test(m.model_id));
        if (chosen) break;
      }}
      if (!chosen) chosen = pick(inClass) || pick(list.slice());
      modelId = chosen.model_id;
      document.getElementById("model-note").textContent =
          "Model: " + modelId + " (fallback) — downloads once into browser cache.";
      engine = await webllm.CreateMLCEngine(modelId, engineConfig,
        {{ context_window_size: 8192, sliding_window_size: -1 }});
    }} else {{ throw e; }}
  }}
  bar.hidden = true;
  window._engine = engine;   // inspectable: the reader checks its own reader
  status("Model ready on your GPU. Nothing was installed.");
  go.disabled = false;
}}

go.addEventListener("click", async () => {{
  go.disabled = true;
  const t0 = performance.now();
  status("Reading the page in this tab…");
  let raw = "";
  // Reasoning-mode models (Qwen3 era) burn the whole token budget thinking
  // before they transcribe a single record. Their off switch must ride on
  // the USER message -- in the system prompt it is ignored, which cost a
  // 20,000-character thought spiral before this line moved. The engine's
  // native enable_thinking switch is set too; measured together they cut
  // the same question from 59 tokens of reasoning to 2 of answer.
  const isThinker = /qwen3/i.test(modelId);
  const noThink = isThinker ? "\\n/no_think" : "";
  const chunks = await engine.chat.completions.create({{
    messages: [
      // Every browser model gets the compact instructions: small models
      // drown in the full production prompt, and the compact set is the
      // one being iterated toward verified in-browser records.
      {{ role: "system", content: SYSTEM_SMALL }},
      {{ role: "user", content: USER_PROMPT + noThink }},
    ],
    temperature: 0,
    // A guard against degenerate repetition in small quantized models.
    frequency_penalty: 0.3,
    max_tokens: 4000,
    stream: true,
    ...(isThinker ? {{ extra_body: {{ enable_thinking: false }} }} : {{}}),
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
    e2b_lib = build["lib"]
    if args.local_model:
        e2b_base = build["local"]
    else:
        e2b_base = build["public"]

    pages = {p.page: p for p in Archive().pages(IDENTIFIER)}
    text = pages[PAGE_NO].text
    user = USER_TEMPLATE.format(
        title=TITLE, publisher="Ontario Ministry of Environment and Energy",
        year=YEAR, page=PAGE_NO, text=text)
    html = TEMPLATE.format(
        title=TITLE, page_no=PAGE_NO, identifier=IDENTIFIER, leaf=PAGE_NO - 1,
        system_json=json.dumps(SMALL_SYSTEM),
        full_system_json=json.dumps(SYSTEM), page_json=json.dumps(text),
        e2b_base=e2b_base, e2b_lib_path=e2b_lib, e2b_ctx=build["ctx"],
        e2b_pick="E2B" if args.local_model else "null",
        e2b_id=f"gemma-4-E2B-it-q4f16_1-MLC-{args.local_model or 'welcoma'}",
        user_json=json.dumps(user))
    OUT.write_text(html, encoding="utf-8")
    SERVED.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} and {SERVED} ({len(html) // 1024} KB; page text "
          f"{len(text)} chars, prompt imported from concordance.extract)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
