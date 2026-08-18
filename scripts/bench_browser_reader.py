"""Measure the in-browser reader against the hand-read gold pages.

The reader page states that browser-size models "find roughly half of what a
page states". That figure was an estimate carried over from an Ollama run of a
different model; it has never been measured for the combination a visitor
actually runs. This builds a page that measures it.

    python scripts/bench_browser_reader.py
    # serve portal/ and open browser-bench.html, press the button, wait
    # then: python scripts/score_browser_bench.py records.json

What makes the number mean anything is that this page imports the reader's own
parser and evidence checks (``CHECKS_JS``) and its own instructions
(``SMALL_SYSTEM``) rather than a copy of them, and loads the model with the
same engine pin and the same context settings. A benchmark measuring a
reimplementation would produce a number true of code no visitor runs.

It records BOTH sets:

  * every record the model produced, so recall can be measured against what a
    person found on the page, and
  * the subset that survives the page's two checks, which is what a browser
    would actually send to a Concordance site.

The gap between them is what the checks cost in recall and buy in precision.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.archive import Archive                            # noqa: E402
from concordance.chrome import BASE_CSS, masthead                  # noqa: E402
from concordance.extract import USER_TEMPLATE                      # noqa: E402
from concordance.score import load_gold                            # noqa: E402

from build_browser_reader import CHECKS_JS, SMALL_SYSTEM           # noqa: E402


#: Candidate v3, written against a MEASURED failure rather than a guess.
#: v2 scored 17.6% recall on the gold pages; two losses dominated it.
#:
#: The magazine page returned an empty array -- 11 hand-read values, none
#: proposed -- and every one of them is a counted noun ("75 elementary
#: schools"). v2's only unit examples are mg/L, %, hours and persons, so a
#: count does not look like a measurement under it.
#:
#: The design sheet gave 6 records against 26 values. It is a specification
#: list, one measurement per line, and v2's worked example is a prose
#: sentence -- nothing tells the model that a bare line is also a reading.
#:
#: Both additions are about COMPLETENESS. The verbatim-sentence rule is
#: untouched, because precision depends on it and precision is the half of
#: this that already works.
SMALL_SYSTEM_V3 = SMALL_SYSTEM.replace(
    """2. "value" is the number as stated. "unit" is its unit ("mg/L", "%",
   "hours", "persons").""",
    """2. "value" is the number as stated. "unit" is its unit ("mg/L", "%",
   "hours", "persons"). A COUNT is a measurement: "75 elementary schools"
   is value 75, unit "schools". So is "14 pumping stations".""",
).replace(
    """4. One record per measurement. A sentence with three numbers gives three
   records, each quoting that same sentence.""",
    """4. One record per measurement. A sentence with three numbers gives three
   records, each quoting that same sentence.
5. Extract EVERY measurement on the page. Do not choose the important ones,
   do not summarise, do not stop early. A page with twenty numbers gives
   twenty records.
6. A specification sheet is a list of measurements, one per line. Lines like
   "Design Flow 3.0 mgd" or "Design Population 25,000" are each a record,
   with that line as the source_text.""",
)

#: v4: v3's counted-noun clause WITHOUT its specification-sheet clause.
#:
#: The A/B decomposed cleanly. The count rule fixed the magazine page, which
#: v2 had abandoned entirely -- 0 records became 3, all correct. The
#: specification-sheet rule made the design sheet worse: told that a spec
#: sheet is a list of measurements one per line, the model read "PROJECT NO.
#: 2-0069-60" as the value 2 and "TREATMENT Primary" as the value 3, and
#: found fewer real specifications than before. Recall came out identical
#: because the two effects cancelled.
#:
#: So keep the half that worked. An instruction that tells a small model to
#: treat every line as a measurement gets exactly that, including the lines
#: that are not measurements.
SMALL_SYSTEM_V4 = SMALL_SYSTEM  # now shipped
_UNUSED_V4 = SMALL_SYSTEM.replace(
    """2. "value" is the number as stated. "unit" is its unit ("mg/L", "%",
   "hours", "persons").""",
    """2. "value" is the number as stated. "unit" is its unit ("mg/L", "%",
   "hours", "persons"). A COUNT is a measurement: "75 elementary schools"
   is value 75, unit "schools". So is "14 pumping stations".""",
)

#: v5: v4 plus a required unit.
#:
#: Measured on v4, every record that failed to match the answer key was a
#: CORRECT value with an empty unit -- "design population 25,000" against a
#: key that says 25,000 people, "200" against 200 mg/L. The scorer matches on
#: value AND unit, so each one is charged twice: once as a value the reader
#: missed, once as a record the key does not contain. Nothing was invented on
#: any of the four pages.
#:
#: That is an annotation defect, not a reading defect, and it damages the
#: published dataset rather than only the score: units.py exists in this
#: project because the same specification appeared as "180 PPM" in 1963 and
#: "180 mg/1" in 1969, and a record with no unit cannot be compared with
#: either.
SMALL_SYSTEM_V5 = SMALL_SYSTEM_V4.replace(
    """   is value 75, unit "schools". So is "14 pumping stations".""",
    """   is value 75, unit "schools". So is "14 pumping stations".
   NEVER leave "unit" empty. If the page gives no symbol, name what is being
   counted ("people", "schools", "hours"). 1960s scans print mg/L as "mg/1";
   record that as "mg/L".""",
)

PROMPTS = [("shipped", SMALL_SYSTEM)]

#: Kept, not deleted: both were measured and both made the reader worse.
#: Re-runnable by putting them back in PROMPTS.
REJECTED = [("+ spec-sheet rule", SMALL_SYSTEM_V3),
            ("+ forced units", SMALL_SYSTEM_V5)]

GOLD = sorted(Path("data/gold").glob("*.json"))
OUT = Path("portal/browser-bench.html")

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Concordance — benchmarking the browser reader</title>
<style>
__CHROME_CSS__
  * { box-sizing: border-box }
  main { max-width: 920px; margin: 0 auto; padding: 26px 18px 80px }
  h1 { font-size: 20px; margin: 0 0 4px }
  p { margin: 0 0 10px }
  .sub { color: var(--muted); margin-bottom: 18px }
  .card { background:var(--panel); border:1px solid var(--line);
          border-radius:12px; padding:14px 16px; margin:12px 0 }
  .note { color:var(--muted); font-size:12.5px }
  button { background:var(--hit); color:var(--bg); border:0; border-radius:9px;
           padding:9px 18px; font:inherit; font-weight:600; cursor:pointer }
  button:disabled { opacity:.45; cursor:default }
  #status { font-family:ui-monospace,monospace; font-size:12px;
            color:var(--muted); white-space:pre-wrap }
  progress { width:100%; height:6px; accent-color:var(--hit) }
  table { width:100%; border-collapse:collapse; font-size:13px; margin-top:8px }
  th,td { text-align:left; padding:6px 8px;
          border-bottom:1px solid rgba(255,255,255,.08) }
  th { color:var(--faint); font-size:11px; text-transform:uppercase;
       letter-spacing:.06em }
  td.n { text-align:right; font-family:ui-monospace,monospace }
  pre { white-space:pre-wrap; font-size:11px; color:var(--muted);
        max-height:320px; overflow:auto; background:rgba(0,0,0,.25);
        padding:10px; border-radius:8px }
  a { color:var(--hit) }
</style>
</head>
<body>
__MASTHEAD__
<main>
<h1>Benchmarking the browser reader</h1>
<p class="sub">The same model, instructions, parser and checks the
<a href="/browser">reader</a> runs, over the four pages a person read by hand.
Nothing here is published anywhere; the output is a JSON blob to score
offline.</p>

<div class="card">
  <div id="status">Checking whether this browser can run a model…</div>
  <progress id="bar" value="0" max="1" hidden></progress>
  <p style="margin-top:10px"><button id="go" disabled>Read all four gold pages</button></p>
  <p class="note" id="model-note"></p>
</div>

<div class="card" id="results" hidden>
  <b id="headline"></b>
  <table id="tbl">
    <thead><tr><th>document</th><th>page</th><th class="n">produced</th>
    <th class="n">passed checks</th><th class="n">refused</th><th class="n">seconds</th></tr></thead>
    <tbody></tbody>
  </table>
  <p class="note" style="margin-top:12px">Copy the JSON below to
  <code>records.json</code>, then score it:
  <code>python scripts/score_browser_bench.py records.json</code></p>
  <pre id="out"></pre>
</div>

<script type="module">
const SYSTEM_SMALL = __SYSTEM_JSON__;
const USER_TMPL = __USER_TMPL_JSON__;
const PAGES = __PAGES_JSON__;
const PROMPTS = __PROMPTS_JSON__;

const $ = id => document.getElementById(id);
const status = m => { $("status").textContent = m; };
const bar = $("bar"), go = $("go");

__CHECKS_JS__

/* The reader's own prompt assembly, so the model sees what it sees there. */
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

let engine = null, modelId = null;

async function loadEngine() {
  status("Loading the model list…");
  const webllm = await import("https://esm.run/@mlc-ai/web-llm@0.2.84");
  const list = webllm.prebuiltAppConfig.model_list;
  const prefer = [/qwen3\\.5-4b.*q4f16/i, /qwen3\\.5-4b/i, /qwen3-4b.*q4f16/i,
                  /qwen3\\.5-2b.*q4f16/i, /llama-3\\.2-3b.*q4f16/i];
  let chosen = null;
  for (const rx of prefer) { chosen = list.find(m => rx.test(m.model_id)); if (chosen) break; }
  if (!chosen) { status("No suitable browser model in the catalogue."); return; }
  modelId = chosen.model_id;
  $("model-note").textContent = "Model: " + modelId;
  status("Fetching " + modelId + " into browser cache…");
  bar.hidden = false;
  engine = await webllm.CreateMLCEngine(modelId, {
    initProgressCallback: r => { bar.value = r.progress || 0; status(r.text || "loading…"); },
  }, { context_window_size: 8192, sliding_window_size: -1 });
  bar.hidden = true;
  status("Model ready.");
}

async function readPage(userPrompt, label, systemPrompt) {
  const isThinker = /qwen3/i.test(modelId);
  const req = {
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userPrompt + (isThinker ? "\\n/no_think" : "") },
    ],
    temperature: 0,
    frequency_penalty: 0.3,
    max_tokens: 4000,
    stream: true,
  };
  if (isThinker) req.extra_body = { enable_thinking: false };
  const chunks = await engine.chat.completions.create(req);
  let raw = "";
  for await (const c of chunks) {
    raw += c.choices?.[0]?.delta?.content || "";
    status(label + " — " + raw.length + " characters");
  }
  return raw;
}

go.addEventListener("click", async () => {
  go.disabled = true;
  if (!engine) {
    try { await loadEngine(); }
    catch (e) { status("Could not load the model: " + String(e).slice(0, 140)); }
    if (!engine) { go.disabled = false; return; }
  }
  const out = { model: modelId, engine: "web-llm@0.2.84", runs: [] };
  const tbody = document.querySelector("#tbl tbody");
  tbody.innerHTML = "";
  $("results").hidden = false;

 for (const prompt of PROMPTS) {
  const run = { prompt: prompt.name, pages: [] };
  out.runs.push(run);
  for (let i = 0; i < PAGES.length; i++) {
    const p = PAGES[i];
    const label = prompt.name + " — page " + (i + 1) + "/" + PAGES.length + " — " + p.identifier + " p." + p.page;
    const t0 = performance.now();
    let raw = "";
    try { raw = await readPage(fillTemplate(p, p.page, p.text), label, prompt.system); }
    catch (e) { status(label + " failed: " + String(e).slice(0, 120)); }
    const secs = (performance.now() - t0) / 1000;

    const produced = [], passed = [];
    for (const r of parseRecords(raw)) {
      if (!r || typeof r !== "object") continue;
      const quote = String(r.source_text || "");
      const onPage = quoteOnPage(quote, p.text);
      const inQuote = valueInQuote(r.value, quote);
      /* The reader sends a record only when the sentence is on the page and
         the value is in it (or there is no value to check). Same rule here. */
      const ok = !!quote && onPage && inQuote !== false;
      const rec = { kind: r.kind, parameter: r.parameter, value: r.value,
                    unit: r.unit, source_text: quote, passed: ok };
      produced.push(rec);
      if (ok) passed.push(rec);
    }
    run.pages.push({ identifier: p.identifier, page: p.page, seconds: +secs.toFixed(1),
                     raw_chars: raw.length, raw: raw.slice(0, 600), records: produced });

    const row = document.createElement("tr");
    row.innerHTML = "<td>" + prompt.name + " · " + p.identifier + "</td><td class='n'>" + p.page +
      "</td><td class='n'>" + produced.length + "</td><td class='n'>" + passed.length +
      "</td><td class='n'>" + (produced.length - passed.length) +
      "</td><td class='n'>" + secs.toFixed(0) + "</td>";
    tbody.appendChild(row);

    window._bench = out;
    $("out").textContent = JSON.stringify(out, null, 1);
  }
 }

  const tot = out.runs.reduce((n, r) => n + r.pages.reduce((m, p) => m + p.records.length, 0), 0);
  $("headline").textContent =
    tot + " records across " + out.runs.length + " prompts x " + PAGES.length +
    " pages. Score them offline against the gold set.";
  status("Done. window._bench holds the JSON.");
  go.disabled = false;
});

if (!("gpu" in navigator)) {
  status("This browser has no WebGPU; the reader needs it.");
} else {
  status("Ready. Press the button — the model downloads once into browser cache.");
  go.disabled = false;
}
</script>
</main>
</body>
</html>
"""


def main() -> int:
    archive = Archive()
    pages: list[dict[str, object]] = []

    for gold_path in GOLD:
        gold = load_gold(gold_path)
        ident = gold["identifier"]
        got = {p.page: p for p in archive.pages(ident)}
        for page_no_str in sorted(gold["pages"], key=int):
            page_no = int(page_no_str)
            page = got.get(page_no)
            if page is None:
                print(f"  page {page_no} of {ident} not found; skipped")
                continue
            pages.append({
                "identifier": ident,
                "title": gold.get("title", ""),
                "publisher": gold.get("publisher", ""),
                "year": str(gold.get("year", "")),
                "page": page_no,
                # The same slice extract_prose prompts with, so the model sees
                # neither more nor less of the page than the installed reader.
                "text": page.text[:12000],
            })

    html = TEMPLATE
    for sentinel, value in {
        "__CHROME_CSS__": BASE_CSS,
        "__MASTHEAD__": masthead("Benchmark", home="/"),
        "__CHECKS_JS__": CHECKS_JS,
        "__SYSTEM_JSON__": json.dumps(SMALL_SYSTEM),
        "__PROMPTS_JSON__": json.dumps([{"name": n, "system": t} for n, t in PROMPTS]),
        "__USER_TMPL_JSON__": json.dumps(USER_TEMPLATE),
        "__PAGES_JSON__": json.dumps(pages),
    }.items():
        assert sentinel in html, f"template lost its {sentinel} slot"
        html = html.replace(sentinel, value)

    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html) // 1024} KB) — {len(pages)} gold pages "
          f"from {len(GOLD)} documents")
    for p in pages:
        print(f"  {p['identifier']} p.{p['page']}  {len(str(p['text']))} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
