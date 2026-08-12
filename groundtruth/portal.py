"""The map portal, forked from the OMEGA-wave portal.

What comes across: the app shell -- header, icon nav rail, panel dock -- its
553 KB of chrome CSS, and the MapLibre setup with keyless Esri imagery and AWS
terrarium terrain.

What does not: OMEGA's `portal.js`. It is 2.3 MB bound to endpoints for mesh
routing, firmware builds, acoustic messaging and storm tracking, none of which
exist here. Forking it wholesale would produce a menu full of controls wired to
nothing, which is worse than a smaller portal that works.

So the chrome is OMEGA's and the views are this project's:

    Observe     where the measurements are
    Record      one place, read out of the scans -- every number can show a
                picture of the sentence it came from
    Silence     what stopped being measured, and when
    Rivers      who was downstream of whom, and what the method refused to link
    Verify      how accurate the reading is, against hand-checked ground truth
    Decisions   who moved what, who seconded, and how each person voted
    Disputed    measurements two readings disagree about, shown side by side
                with both crops, because nobody here adjudicates
    Ask Honu    the agent, over the whole toolset

This is the SERVING layer, and the one place allowed outside dependencies. The
core stays dependency-free: nobody should need a mapping library installed to
check whether 104 mg/L is what the page says.
"""

from __future__ import annotations

MAPLIBRE_VERSION = "5.24.0"
SAT_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
DEM_TILES = "https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png"

NAV = [
    ("observe", "Observe", "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17Zm0 4.6a3.9 3.9 0 1 1 0 7.8 3.9 3.9 0 0 1 0-7.8Z"),
    ("record", "Record", "M4 19.2V4.8h9.6l6.4 6.4v8H4Zm9.2-13.4v5.4h5.4"),
    ("silence", "Silence", "M4 12h4l3.2-5.4v10.8L8 12H4Zm12.4-3.4a6 6 0 0 1 0 6.8M19 6a9.4 9.4 0 0 1 0 12"),
    ("rivers", "Rivers", "M3.5 7.5c3 0 3 3 6 3s3-3 6-3 3 3 5 3M3.5 14c3 0 3 3 6 3s3-3 6-3 3 3 5 3"),
    ("verify", "Verify", "M5 12.6 9.8 17.4 19 6.6"),
    ("decisions", "Decisions", "M7 4.5h10v15H7Zm2.6 4h4.8m-4.8 3.6h4.8m-4.8 3.6h3"),
    ("disputed", "Disputed", "M12 4.5 3.5 19.5h17L12 4.5Zm0 5.4v4.4m0 2.6v.1"),
    ("ask", "Ask Honu", "M4.5 6.5h15v9h-8.4L6.6 19v-3.5H4.5Z"),
]


def _nav() -> str:
    out = []
    for i, (key, label, path) in enumerate(NAV):
        active = " is-active" if i == 0 else ""
        out.append(
            f'<button type="button" class="nav-button{active}" data-view="{key}" '
            f'aria-label="{label}">'
            f'<svg class="nav-glyph" viewBox="0 0 24 24" aria-hidden="true">'
            f'<path d="{path}" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round"/></svg>'
            f'<span class="nav-tip">{label}</span></button>'
        )
    return "".join(out)


def render(s: dict) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ground Truth — Canada's public record, read</title>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@{MAPLIBRE_VERSION}/dist/maplibre-gl.css">
<link rel="stylesheet" href="/static/omega-portal.css">
<style>
/* Ground Truth overrides on top of the inherited OMEGA chrome. */
:root{{--gt-hit:#f0a24a;--gt-cold:#5b7285}}
html,body{{height:100%;margin:0;background:#04080d;color:#e8edf2;
  font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}
*{{box-sizing:border-box}}
.app-shell{{display:flex;flex-direction:column;height:100vh;overflow:hidden}}
.app-header{{display:flex;align-items:center;gap:22px;padding:9px 18px;
  border-bottom:1px solid rgba(255,255,255,.09);background:rgba(8,12,17,.94);z-index:20}}
.brand-block{{display:flex;align-items:baseline;gap:10px;min-width:210px}}
.brand-wordmark{{margin:0;font-size:15px;font-weight:600;letter-spacing:.02em}}
.brand-sub{{margin:0;font-size:11px;color:#7d8996}}
.primary-nav{{display:flex;gap:4px}}
.nav-button{{background:none;border:1px solid transparent;border-radius:9px;
  color:#8b97a4;padding:7px 9px;cursor:pointer;display:flex;align-items:center;gap:7px}}
.nav-button:hover{{color:#e8edf2;border-color:rgba(255,255,255,.12)}}
.nav-button.is-active{{color:#04080d;background:var(--gt-hit);border-color:var(--gt-hit)}}
.nav-glyph{{width:17px;height:17px}}
.nav-tip{{font-size:12.5px;font-weight:500}}
.header-stats{{margin-left:auto;display:flex;gap:0;border:1px solid rgba(255,255,255,.10);
  border-radius:9px;overflow:hidden}}
.hstat{{padding:5px 13px;border-right:1px solid rgba(255,255,255,.10)}}
.hstat:last-child{{border-right:0}}
.hstat b{{display:block;font-size:15px;font-weight:600;font-variant-numeric:tabular-nums;
  line-height:1.2}}
.hstat span{{font-size:9.5px;color:#6d7a86;text-transform:uppercase;letter-spacing:.06em}}

.app-body{{flex:1;position:relative;overflow:hidden}}
.view{{position:absolute;inset:0;display:none;overflow:auto}}
.view.is-active{{display:block}}
#map{{position:absolute;inset:0}}

.dock{{position:absolute;top:0;right:0;bottom:0;width:410px;z-index:12;
  background:rgba(9,13,18,.95);border-left:1px solid rgba(255,255,255,.10);
  backdrop-filter:blur(10px);overflow-y:auto;padding:20px 22px 30px;
  transform:translateX(100%);transition:transform .2s ease}}
.dock.open{{transform:none}}
@media(max-width:860px){{.dock{{width:100%}}}}
.dock h2{{margin:0 0 3px;font-size:20px;font-weight:600;letter-spacing:-.01em}}
.dock .meta{{color:#8b97a4;font-size:12.5px;margin-bottom:15px}}
.dock-close{{position:absolute;top:15px;right:16px;width:27px;height:27px;
  background:none;border:1px solid rgba(255,255,255,.14);border-radius:7px;
  color:#8b97a4;cursor:pointer;font-size:15px;line-height:1}}
.sec{{border-top:1px solid rgba(255,255,255,.09);padding-top:12px;margin-top:14px}}
.sec h3{{margin:0 0 8px;font-size:11px;font-weight:600;color:#6d7a86;
  text-transform:uppercase;letter-spacing:.07em}}
.row{{display:grid;grid-template-columns:42px 1fr auto;gap:9px;align-items:baseline;
  padding:6px 0;border-bottom:1px solid rgba(255,255,255,.05)}}
.row .y{{font-family:ui-monospace,monospace;font-size:11.5px;color:#8b97a4}}
.row .v{{font-family:ui-monospace,monospace;font-size:12.5px;white-space:nowrap}}
.src{{grid-column:2/4;font-size:11.5px;color:#6d7a86;font-style:italic;line-height:1.45;
  margin-top:2px}}
.src a{{color:var(--gt-hit);font-style:normal;text-decoration:none;white-space:nowrap}}
.paper-btn{{background:transparent;border:0;color:var(--gt-hit);font:inherit;font-size:11px;
  font-style:normal;cursor:pointer;padding:0 0 0 8px;white-space:nowrap}}
.paper-btn:hover{{text-decoration:underline}}
.paper{{display:block}}
details input,details textarea{{background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.14);border-radius:7px;padding:7px 10px;
  color:inherit;font:inherit;font-size:12px}}
details textarea{{resize:vertical}}
#sb-out{{font-size:12px}}
.paper img{{box-shadow:0 2px 10px rgba(0,0,0,.35)}}
.spark{{width:100%;height:42px;display:block;margin:1px 0 9px}}
.note{{font-size:11.5px;color:#6d7a86;line-height:1.55;margin-top:16px;
  border-left:2px solid rgba(255,255,255,.12);padding-left:11px}}
.empty{{color:#8b97a4;font-size:13px;line-height:1.6}}

.pane{{max-width:1080px;margin:0 auto;padding:26px 28px 60px}}
.pane h2{{font-size:22px;font-weight:600;margin:0 0 4px;letter-spacing:-.015em}}
.pane .lede{{color:#8b97a4;font-size:13.5px;max-width:70ch;margin:0 0 22px}}
.card{{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.09);
  border-radius:11px;padding:18px 20px;margin-bottom:14px}}
table.gt{{border-collapse:collapse;width:100%;font-size:12.5px}}
table.gt th,table.gt td{{text-align:left;padding:7px 9px;
  border-bottom:1px solid rgba(255,255,255,.07)}}
table.gt th{{color:#6d7a86;font-weight:600;font-size:11px;text-transform:uppercase;
  letter-spacing:.05em}}
table.gt td.n{{text-align:right;font-family:ui-monospace,monospace}}
.big{{font-size:34px;font-weight:600;letter-spacing:-.02em}}
.time-bar{{position:absolute;left:0;right:0;bottom:0;z-index:13;display:flex;
  align-items:center;gap:14px;padding:11px 20px;
  background:linear-gradient(0deg,rgba(6,10,15,.97),rgba(6,10,15,.72));
  border-top:1px solid rgba(255,255,255,.10);backdrop-filter:blur(8px)}}
.tl-btn{{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);
  border-radius:8px;color:#e8edf2;width:34px;height:30px;cursor:pointer;font-size:12px}}
.tl-btn:hover{{background:rgba(255,255,255,.12)}}
.tl-wide{{width:auto;padding:0 12px;font-size:12px}}
.tl-year{{font-family:ui-monospace,monospace;font-size:15px;letter-spacing:.04em;
  min-width:96px;color:var(--gt-hit)}}
.tl-track{{flex:1;display:flex;align-items:center}}
.tl-track input{{width:100%;accent-color:var(--gt-hit);cursor:pointer}}
.tl-count{{font-size:12px;color:#8b97a4;min-width:200px;text-align:right}}
.sr-only{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}}
.legend{{position:absolute;left:18px;bottom:74px;z-index:11;
  background:rgba(9,13,18,.94);border:1px solid rgba(255,255,255,.10);border-radius:9px;
  padding:10px 13px;font-size:11.5px;color:#8b97a4;backdrop-filter:blur(8px)}}
.legend b{{display:block;color:#e8edf2;font-size:10.5px;text-transform:uppercase;
  letter-spacing:.06em;margin-bottom:6px}}
.key{{display:flex;align-items:center;gap:7px;margin-top:4px}}
.sw{{width:10px;height:10px;border-radius:50%;display:inline-block}}
.maplibregl-popup-content{{background:#0b1017;color:#e8edf2;
  border:1px solid rgba(255,255,255,.12);border-radius:8px;font-size:13px}}
.maplibregl-ctrl-group{{background:rgba(9,13,18,.94)!important;
  border:1px solid rgba(255,255,255,.10)!important}}
.maplibregl-ctrl-group button{{filter:invert(.88)}}
</style></head>
<body data-route="observe">
<div class="app-shell">

  <header class="app-header">
    <div class="brand-block">
      <p class="brand-wordmark">GROUND TRUTH</p>
      <p class="brand-sub">Canada's public record, read</p>
    </div>
    <nav class="primary-nav icon-nav" aria-label="Views">{_nav()}</nav>
    <div class="header-stats">
      <div class="hstat"><b>{s['located']}</b><span>located</span></div>
      <div class="hstat"><b>{s['read']}</b><span>read</span></div>
      <div class="hstat"><b>{s['records']}</b><span>measurements</span></div>
      <div class="hstat"><b>{s['precision']:.0%}</b><span>precision</span></div>
      <div class="hstat"><b>{s['silent_n']}</b><span>silent {s['silent_year']}</span></div>
    </div>
  </header>

  <div class="app-body">

    <section class="view is-active" data-view="observe">
      <div id="map"></div>
      <div class="legend">
        <b>Municipal sewage reports</b>
        <div class="key"><span class="sw" style="background:var(--gt-hit)"></span> read from the scans</div>
        <div class="key"><span class="sw" style="background:var(--gt-cold)"></span> located, not yet read</div>
        <div class="key" style="margin-top:6px;color:#6d7a86">dot size = surviving reports</div>
      </div>
      <section class="time-bar" id="time-bar" aria-label="Timeline">
        <button id="tl-play" class="tl-btn" aria-label="Play">&#9654;</button>
        <strong id="tl-year" class="tl-year">ALL YEARS</strong>
        <label class="tl-track">
          <span class="sr-only">Year</span>
          <input id="tl-range" type="range" min="0" max="0" step="1" value="0">
        </label>
        <span id="tl-count" class="tl-count"></span>
        <button id="tl-all" class="tl-btn tl-wide">All</button>
      </section>
      <aside class="dock" id="dock">
        <button class="dock-close" id="dock-close" aria-label="Close">&times;</button>
        <div id="dock-body"></div>
      </aside>
    </section>

    <section class="view" data-view="record">
      <div class="pane" id="record-pane">
        <h2>The record</h2>
        <p class="lede">Every place that has been read out of the scans. Each number links
        back to the page it came from.</p>
        <div id="record-list"></div>
      </div>
    </section>

    <section class="view" data-view="silence">
      <div class="pane" id="silence-pane">
        <h2>What stopped being measured</h2>
        <p class="lede">A whole series vanishing at once usually means the scanning stopped,
        not the reporting. So it is checked against the rest of the collection before it is
        called a finding.</p>
        <div id="silence-body"></div>
      </div>
    </section>

    <section class="view" data-view="ask">
      <div class="pane">
        <h2>Ask Honu</h2>
        <p class="lede">Honu answers only from the extracted record. It cannot answer from
        memory, every number it reports carries the page it was read from, and it will not
        state that somewhere went quiet without the control that separates real silence from
        the scanning having stopped.</p>
        <div class="card">
          <div style="display:flex;gap:9px">
            <input id="ask-input" placeholder="What did Owen Sound discharge?"
              style="flex:1;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.14);
              border-radius:8px;color:#e8edf2;padding:10px 12px;font:inherit;font-size:14px">
            <button id="ask-go" style="background:var(--gt-hit);border:0;border-radius:8px;
              color:#04080d;font-weight:600;padding:10px 18px;cursor:pointer;font:inherit">Ask</button>
          </div>
          <div id="ask-hint" style="margin-top:9px;font-size:11.5px;color:#6d7a86">
            Runs a local model. First answer takes a minute or two.
          </div>
        </div>
        <div id="ask-out"></div>
      </div>
    </section>

    <section class="view" data-view="rivers">
      <div class="pane">
        <h2>Whose effluent was in your water</h2>
        <p class="lede">Treatment plants tied to the nearest river gauge, then ordered by
        catchment area — which necessarily grows downstream, so the towns sort themselves without
        any flow routing. Read each list top to bottom the way the water runs.</p>
        <div id="rivers-body"></div>
      </div>
    </section>

    <section class="view" data-view="verify">
      <div class="pane">
        <h2>How accurate is this?</h2>
        <p class="lede">Measured against ground truth a human read off the same scans by hand.
        Published including the failures — an archive misread at scale is worse than one never
        read, because the errors look like findings.</p>
        <div id="verify-body"></div>
      </div>
    </section>

    <section class="view" data-view="decisions">
      <div class="pane">
        <h2>Who decided, and who voted against</h2>
        <p class="lede">Minutes, agendas, hansard and commission hearings are 13,604 items —
        13.1% of this collection — and they were the material most damaged by a routing bug
        that discarded narrow columns. They are also the cheapest thing here to read: "It was
        moved by X and seconded by Y that Z. CARRIED." is a form that has barely changed in a
        century, so a pattern finds it. No model, no GPU, and a person can check it.</p>
        <p class="lede" style="opacity:.72">The control is the clerk's own tally. That "-16."
        at the end of a roll was written by someone in the room; if the names don't add up to
        it, the roll was misread and it says so rather than publishing a division quietly
        missing two people.</p>
        <div style="display:flex;gap:8px;margin:0 0 12px">
          <input id="dec-id" placeholder="archive.org identifier" value="32022213341486"
            style="flex:1;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.14);
                   border-radius:8px;padding:8px 11px;color:inherit;font:inherit">
          <button id="dec-go" style="background:var(--gt-hit);border:0;border-radius:8px;
            padding:8px 15px;font:inherit;cursor:pointer">Read</button>
        </div>
        <div id="decisions-body"></div>
      </div>
    </section>

    <section class="view" data-view="disputed">
      <div class="pane">
        <h2>Where the readings disagree</h2>
        <p class="lede">Every reading here cites a page and quotes a sentence, and the archive
        checks both. When two readings survive that check and still disagree, nobody decides
        between them — they are shown side by side with a picture of the paper each one came
        from. You settle it in about two seconds. That is what lets this run with no moderator.</p>
        <p class="lede" style="opacity:.72">Flagging one tells us people think it is wrong. It
        does not change the record: an objection with no evidence cannot outrank a sentence on a
        page, because then somebody would have to judge the objection. To change what is shown,
        bring a page and a sentence.</p>
        <details style="margin:0 0 14px">
          <summary style="cursor:pointer;font-size:12px;color:var(--gt-hit)">Add a reading
            yourself</summary>
          <div class="card" style="margin-top:10px">
            <p class="lede" style="margin:0 0 10px">Cite a page and quote a sentence from it.
            Nobody reviews this — the archive is asked whether that sentence is on that page
            and whether your number is in the sentence. If it is, your reading is in the record
            on exactly the same footing as everything the machine read. If it isn't, nothing is
            deleted and nobody has rejected you; the page did.</p>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
              <input id="sb-id" placeholder="archive.org identifier">
              <input id="sb-page" placeholder="page number" inputmode="numeric">
              <input id="sb-param" placeholder="what was measured, e.g. BOD">
              <input id="sb-value" placeholder="the number">
              <input id="sb-unit" placeholder="unit, e.g. mg/L">
              <input id="sb-place" placeholder="place">
              <input id="sb-facility" placeholder="which plant / hospital / board (optional)">
              <input id="sb-period" placeholder="year">
            </div>
            <textarea id="sb-quote" rows="2" placeholder="the exact sentence, copied from the page"
              style="width:100%;margin-top:8px"></textarea>
            <button id="sb-go" style="margin-top:8px;background:var(--gt-hit);border:0;
              border-radius:8px;padding:8px 15px;font:inherit;cursor:pointer">Offer it</button>
            <div id="sb-out" class="lede" style="margin-top:9px"></div>
          </div>
        </details>
        <div id="disputed-body"></div>
      </div>
    </section>

  </div>
</div>

<script src="https://unpkg.com/maplibre-gl@{MAPLIBRE_VERSION}/dist/maplibre-gl.js"></script>
<script>
const PRECISION = "{s['precision']:.0%}";

/* ---- view switching ------------------------------------------------ */
const views = [...document.querySelectorAll(".view")];
const loaded = {{}};
document.querySelectorAll(".nav-button").forEach(btn => btn.onclick = () => {{
  document.querySelectorAll(".nav-button").forEach(b => b.classList.remove("is-active"));
  btn.classList.add("is-active");
  const key = btn.dataset.view;
  views.forEach(v => v.classList.toggle("is-active", v.dataset.view === key));
  document.body.dataset.route = key;
  if (!loaded[key] && LOADERS[key]) {{ loaded[key] = true; LOADERS[key](); }}
  if (key === "observe" && window._map) setTimeout(() => window._map.resize(), 60);
}});

/* ---- shared ---------------------------------------------------------- */
function spark(points){{
  if(!points || points.length < 2) return "";
  const W=350,H=42,P=4;
  const xs=points.map(p=>p[0]), ys=points.map(p=>p[1]);
  const x0=Math.min(...xs), x1=Math.max(...xs);
  let y0=Math.min(...ys), y1=Math.max(...ys);
  if(y1===y0){{y0-=1;y1+=1;}}
  const px=x=>P+(x-x0)/((x1-x0)||1)*(W-2*P);
  const py=y=>P+(1-(y-y0)/(y1-y0))*(H-2*P);
  const d=points.map((p,i)=>(i?"L":"M")+px(p[0]).toFixed(1)+","+py(p[1]).toFixed(1)).join(" ");
  const dots=points.map(p=>`<circle cx="${{px(p[0]).toFixed(1)}}" cy="${{py(p[1]).toFixed(1)}}" r="2.4" fill="#f0a24a"/>`).join("");
  return `<svg class="spark" viewBox="0 0 ${{W}} ${{H}}"><path d="${{d}}" fill="none" stroke="#f0a24a" stroke-width="1.4" opacity=".85"/>${{dots}}</svg>`;
}}

function seriesHtml(d){{
  let h = "";
  (d.series||[]).forEach(s => {{
    h += `<div class="sec"><h3>${{s.label}}${{s.unit?" · "+s.unit:""}}</h3>` + spark(s.points);
    s.rows.forEach(x => {{
      const cite = x.identifier && x.page
        ? ` <button type="button" class="paper-btn" data-id="${{x.identifier}}"
             data-page="${{x.page}}" data-quote="${{encodeURIComponent(x.quote||"")}}"
             title="show the sentence on the scan">show the paper</button>` : "";
      h += `<div class="row"><span class="y">${{x.period||""}}</span>`
         + `<span>${{x.parameter}}</span><span class="v">${{x.value}} ${{x.unit||""}}</span>`
         + `<span class="src">“${{x.read_from}}” <a href="${{x.page_url}}" target="_blank" rel="noopener">scan ↗</a>${{cite}}`
         + `<span class="paper"></span></span></div>`;
    }});
    h += `</div>`;
  }});
  return h;
}}

/* Show the sentence, on the paper, next to the number.
   Provenance that nobody looks at is most of the way to no provenance, and
   "open a 300-page scan and find the line" is why nobody looks. A crop is a
   URL -- archive.org serves it -- so this costs nothing to offer. */
document.addEventListener("click", async ev => {{
  const b = ev.target.closest(".paper-btn");
  if (!b) return;
  const holder = b.parentElement.querySelector(".paper");
  if (holder.dataset.open === "1") {{
    holder.innerHTML = ""; holder.dataset.open = "0";
    b.textContent = "show the paper"; return;
  }}
  b.textContent = "finding it…";
  const d = await (await fetch("/api/citation?identifier=" + encodeURIComponent(b.dataset.id)
      + "&page=" + b.dataset.page + "&quote=" + b.dataset.quote)).json();
  if (d.error) {{ b.textContent = "not retrievable"; return; }}
  holder.dataset.open = "1";
  b.textContent = "hide";
  holder.innerHTML =
    `<a href="${{d.page_url}}" target="_blank" rel="noopener" style="display:block;margin-top:7px">
       <img src="${{d.crop_url}}" alt="the sentence this number was read from" loading="lazy"
            style="max-width:100%;border-radius:6px;background:#f6f1e4"></a>`
    + (d.exact ? "" : `<div style="font-size:10px;opacity:.6;margin-top:3px">${{d.note}}</div>`);
}});

/* ---- observe --------------------------------------------------------- */
const dock = document.getElementById("dock");
const dockBody = document.getElementById("dock-body");
document.getElementById("dock-close").onclick = () => dock.classList.remove("open");

async function openTown(p){{
  dock.classList.add("open");
  dockBody.innerHTML = `<h2>${{p.place}}</h2><div class="meta">loading…</div>`;
  const d = await (await fetch("/api/town?place=" + encodeURIComponent(p.place)
                   + "&raw=" + encodeURIComponent(p.raw||""))).json();
  let h = `<h2>${{p.place}}</h2><div class="meta">${{p.years}} surviving reports · ${{p.first}}–${{p.last}}`
        + (p.silent_since ? ` · <span style="color:var(--gt-hit)">silent since ${{p.silent_since}}</span>` : "")
        + (d.facility ? ` · ${{d.facility}}` : "") + `</div>`;
  if(!d.found){{
    h += `<div class="empty">Nobody has read this one yet.<br><br>
      ${{p.years}} scanned reports are waiting. If you read them, they are in the
      library for everyone from then on &mdash; roughly an hour on this machine.</div>
      <button id="read-now" style="margin-top:14px;background:var(--gt-hit);border:0;
        border-radius:8px;color:#04080d;font-weight:600;padding:10px 16px;cursor:pointer;
        font:inherit;width:100%">Read ${{p.place}} now</button>
      <div id="read-log" style="margin-top:10px;font-size:12px;color:#8b97a4"></div>`;
  }} else {{
    h += seriesHtml(d);
    h += `<div class="note">${{d.n_measurements}} measurements from ${{d.sources.length}} documents.
      Every value was read from a scanned page by a language model and links back to it.
      Measured precision against hand-checked ground truth is ${{PRECISION}}.
      Nothing here should be believed without checking it.</div>`;
  }}
  dockBody.innerHTML = h;

  const btn = document.getElementById("read-now");
  if(btn) btn.onclick = async () => {{
    btn.disabled = true; btn.textContent = "reading…";
    const log = document.getElementById("read-log");
    log.textContent = "Working through the scans. This takes about an hour and the "
                    + "tab can be closed — it runs on this machine, not a server.";
    try {{
      const r = await (await fetch("/api/read?place=" + encodeURIComponent(p.place))).json();
      log.innerHTML = r.message
        + (r.contributed ? "<br><br>Verified and added to the library." : "");
      btn.textContent = "done";
    }} catch(e) {{
      log.textContent = "Reading failed: " + e;
      btn.disabled = false; btn.textContent = "Try again";
    }}
  }};
}}

const map = new maplibregl.Map({{
  container:"map", center:[-81.2,44.3], zoom:5.4,
  attributionControl:{{compact:true}},
  style:{{ version:8,
    sources:{{
      sat:{{type:"raster",tiles:["{SAT_TILES}"],tileSize:256,maxzoom:19,
            attribution:"Imagery &copy; Esri, Maxar, Earthstar Geographics"}},
      dem:{{type:"raster-dem",tiles:["{DEM_TILES}"],encoding:"terrarium",tileSize:256,maxzoom:15,
            attribution:"Elevation &copy; Mapzen / AWS Terrain Tiles"}}
    }},
    layers:[
      {{id:"bg",type:"background",paint:{{"background-color":"#04080d"}}}},
      {{id:"sat",type:"raster",source:"sat"}},
      {{id:"hill",type:"hillshade",source:"dem",
        paint:{{"hillshade-exaggeration":0.4,"hillshade-shadow-color":"#0a1622"}}}}
    ]}}
}});
window._map = map;
map.addControl(new maplibregl.NavigationControl({{visualizePitch:true,showCompass:true}}),"top-left");
if(typeof maplibregl.GlobeControl==="function") map.addControl(new maplibregl.GlobeControl(),"top-left");
map.addControl(new maplibregl.ScaleControl({{maxWidth:110,unit:"metric"}}),"bottom-right");

map.on("load", async () => {{
  const geo = await (await fetch("/api/places.geojson")).json();
  map.addSource("towns",{{type:"geojson",data:geo}});
  map.addLayer({{id:"halo",type:"circle",source:"towns",
    filter:["==",["get","extracted"],true],
    paint:{{"circle-radius":["+",["*",["get","years"],0.8],9],
           "circle-color":"#f0a24a","circle-opacity":0.16}}}});
  map.addLayer({{id:"dots",type:"circle",source:"towns",
    paint:{{"circle-radius":["+",["*",["get","years"],0.55],3.5],
           "circle-color":["case",["==",["get","extracted"],true],"#f0a24a","#5b7285"],
           "circle-opacity":["case",["==",["get","extracted"],true],0.95,0.6],
           "circle-stroke-width":1.2,"circle-stroke-color":"#04080d"}}}});
  map.on("click","dots", e => e.features[0] && openTown(e.features[0].properties));
  map.on("mouseenter","dots",()=>map.getCanvas().style.cursor="pointer");
  map.on("mouseleave","dots",()=>map.getCanvas().style.cursor="");
  const b=new maplibregl.LngLatBounds();
  geo.features.forEach(f=>b.extend(f.geometry.coordinates));
  map.fitBounds(b,{{padding:{{top:60,bottom:120,left:60,right:450}},duration:0}});

  /* Timeline. A town is drawn only in the years it actually filed a report, so
     scrubbing shows coverage blooming and then dying -- which is the point of
     this archive as much as the measurements are. */
  const years = [...new Set(geo.features.flatMap(f => f.properties.reported || []))]
                  .sort((a,b) => a-b);
  const range = document.getElementById("tl-range");
  const label = document.getElementById("tl-year");
  const count = document.getElementById("tl-count");
  const playBtn = document.getElementById("tl-play");
  const allBtn = document.getElementById("tl-all");
  range.max = Math.max(0, years.length - 1);
  range.value = range.max;
  let timer = null, showAll = true;

  function paint(){{
    if(showAll){{
      map.setFilter("dots", null);
      map.setFilter("halo", ["==",["get","extracted"],true]);
      label.textContent = "ALL YEARS";
      count.textContent = geo.features.length + " municipalities \\u00b7 "
                        + years[0] + "\\u2013" + years[years.length-1];
      return;
    }}
    const y = years[+range.value];
    // MapLibre cannot test membership of an array property, so the reporting
    // state is precomputed per feature and read back as a plain flag.
    geo.features.forEach(f => {{
      f.properties._on = (f.properties.reported || []).indexOf(y) >= 0;
    }});
    map.getSource("towns").setData(geo);
    map.setFilter("dots", ["==",["get","_on"],true]);
    map.setFilter("halo", ["all",["==",["get","_on"],true],
                                 ["==",["get","extracted"],true]]);
    const n = geo.features.filter(f => f.properties._on).length;
    label.textContent = y;
    count.textContent = n
      ? n + " municipalities reporting"
      : "nothing reported \\u2014 the record is silent";
  }}

  function stop(){{ if(timer){{ clearInterval(timer); timer = null; playBtn.innerHTML = "&#9654;"; }} }}

  range.addEventListener("input", () => {{ showAll = false; paint(); }});
  allBtn.onclick = () => {{ showAll = true; stop(); paint(); }};
  playBtn.onclick = () => {{
    if(timer) return stop();
    showAll = false;
    playBtn.innerHTML = "&#9632;";
    timer = setInterval(() => {{
      range.value = (+range.value >= years.length - 1) ? 0 : +range.value + 1;
      paint();
    }}, 750);
  }};

  paint();
}});

/* ---- the other three views ------------------------------------------- */
const LOADERS = {{
  record: async () => {{
    const el = document.getElementById("record-list");
    const geo = await (await fetch("/api/places.geojson")).json();
    const read = geo.features.filter(f=>f.properties.extracted);
    let h = "";
    for (const f of read) {{
      const p = f.properties;
      const d = await (await fetch("/api/town?place="+encodeURIComponent(p.place)
                       +"&raw="+encodeURIComponent(p.raw||""))).json();
      h += `<div class="card"><h2 style="font-size:18px">${{p.place}}</h2>`
         + `<p class="lede" style="margin-bottom:10px">${{p.years}} reports · ${{p.first}}–${{p.last}}`
         + (d.facility?` · ${{d.facility}}`:"") + `</p>` + seriesHtml(d) + `</div>`;
    }}
    el.innerHTML = h || `<div class="card empty">Nothing read yet.</div>`;
  }},

  silence: async () => {{
    const d = await (await fetch("/api/quiet")).json();
    const el = document.getElementById("silence-body");
    if(!d.available){{ el.innerHTML = `<div class="card empty">${{d.message}}</div>`; return; }}
    const st = d.largest_simultaneous_stop || {{}};
    let h = `<div class="card"><div class="big">${{st.municipalities}} of ${{d.n_municipalities}}</div>`
          + `<p class="lede" style="margin:4px 0 0">municipalities stop filing reports in
             <strong style="color:var(--gt-hit)">${{st.year}}</strong>.</p></div>`;
    h += `<div class="card"><h3 style="margin:0 0 8px;font-size:11px;color:#6d7a86;
          text-transform:uppercase;letter-spacing:.06em">Did the collection itself stop?</h3>
          <table class="gt"><tr><th>series</th><th class="n">before</th><th class="n">after</th><th></th></tr>`;
    (d.control||[]).forEach(c => {{
      const grew = c.from_cliff_onward > c.before*0.5;
      h += `<tr><td>${{c.series}}</td><td class="n">${{c.before.toLocaleString()}}</td>`
         + `<td class="n">${{c.from_cliff_onward.toLocaleString()}}</td>`
         + `<td style="color:${{grew?"#36e0c8":"#f0a24a"}}">${{grew?"keeps going":"also stops"}}</td></tr>`;
    }});
    h += `</table><p class="lede" style="margin:12px 0 0">${{d.control_verdict === "real"
        ? "The archive kept growing while this one series died. <strong>The silence is real.</strong>"
        : "The whole collection thins at once — probably a digitisation boundary."}}</p></div>`;
    h += `<div class="card note" style="border:0;padding-left:11px">${{d.caveat}}</div>`;
    el.innerHTML = h;
  }},

  ask: () => {{
    const input = document.getElementById("ask-input");
    const go = document.getElementById("ask-go");
    const out = document.getElementById("ask-out");
    const run = async () => {{
      const question = input.value.trim();
      if(!question) return;
      go.disabled = true; go.textContent = "thinking…";
      out.innerHTML = `<div class="card empty">Reading the record…</div>` + out.innerHTML;
      try {{
        const d = await (await fetch("/api/ask?q=" + encodeURIComponent(question))).json();
        let h = `<div class="card"><p class="lede" style="color:#e8edf2;margin:0 0 10px">`
              + `<strong style="color:var(--gt-hit)">Q</strong> ${{question}}</p>`;
        if(d.error){{
          h += `<p class="empty">No answer: ${{d.error}}<br><br>Honu needs a local model
                running (<code>ollama serve</code>), or an ANTHROPIC_API_KEY.</p>`;
        }} else {{
          h += `<p style="margin:0;white-space:pre-wrap">${{d.reply}}</p>`;
          if(d.tools && d.tools.length){{
            h += `<p style="margin:12px 0 0;font-size:11.5px;color:#6d7a86">`
               + `Answered using: ${{d.tools.map(t=>"<code>"+t.tool+"</code>").join(", ")}}`
               + ` — no part of this came from the model's own knowledge.</p>`;
          }}
        }}
        out.innerHTML = h + "</div>" + out.innerHTML.replace(
          `<div class="card empty">Reading the record…</div>`, "");
      }} catch(e) {{
        out.innerHTML = `<div class="card empty">Request failed: ${{e}}</div>`
          + out.innerHTML.replace(`<div class="card empty">Reading the record…</div>`,"");
      }}
      go.disabled = false; go.textContent = "Ask";
    }};
    go.onclick = run;
    input.addEventListener("keydown", e => {{ if(e.key === "Enter") run(); }});
  }},

  rivers: async () => {{
    const el = document.getElementById("rivers-body");
    el.innerHTML = `<div class="card empty">Fetching river gauges…</div>`;
    const d = await (await fetch("/api/watershed")).json();
    if(d.error){{ el.innerHTML = `<div class="card empty">${{d.error}}</div>`; return; }}
    let h = "";
    d.rivers.forEach(r => {{
      const towns = [];
      r.links.forEach(l => {{
        if(!towns.find(t=>t.name===l.upstream)) towns.push({{name:l.upstream, area:l.up_area}});
        if(!towns.find(t=>t.name===l.downstream)) towns.push({{name:l.downstream, area:l.down_area}});
      }});
      towns.sort((a,b)=>a.area-b.area);
      const max = towns[towns.length-1].area || 1;
      h += `<div class="card"><h3 style="margin:0 0 12px;font-size:14px;font-weight:600;
            text-transform:capitalize">${{r.river}}</h3>`;
      towns.forEach((t,i) => {{
        const w = 14 + 86*(t.area/max);
        h += `<div style="margin-bottom:3px">
                <div style="height:8px;border-radius:2px;background:var(--gt-hit);opacity:.42;
                     width:${{w.toFixed(0)}}%"></div>
                <div style="font-size:14px;margin-top:2px">${{t.name}}</div>
                <div style="font-size:11px;color:#6d7a86;font-family:ui-monospace,monospace">
                     ${{Math.round(t.area).toLocaleString()}} km² catchment</div></div>`;
        if(i < towns.length-1) h += `<div style="color:#6d7a86;margin:1px 0 5px">↓</div>`;
      }});
      h += `</div>`;
    }});
    if(d.warnings && d.warnings.length){{
      h += `<div class="card"><h3 style="margin:0 0 8px;font-size:11px;color:#6d7a86;
            text-transform:uppercase;letter-spacing:.06em">What the method refused to link</h3>`;
      d.warnings.forEach(w => h += `<p class="lede" style="margin:0 0 6px;color:#f0a24a">${{w}}</p>`);
      h += `<p class="lede" style="margin:8px 0 0">Shown because a page that displays only its
            successes teaches nobody where it fails.</p></div>`;
    }}
    h += `<div class="card note" style="border:0;padding-left:11px">${{d.caveat||""}}</div>`;
    el.innerHTML = h;
  }},

  verify: async () => {{
    const d = await (await fetch("/api/accuracy")).json();
    const el = document.getElementById("verify-body");
    const t = d.totals || {{}};
    let h = `<div class="card"><table class="gt">
      <tr><th>measure</th><th class="n">value</th><th>what it means</th></tr>
      <tr><td>precision</td><td class="n">${{(t.precision*100||0).toFixed(1)}}%</td><td>of what it extracted, how much was right</td></tr>
      <tr><td>recall</td><td class="n">${{(t.recall*100||0).toFixed(1)}}%</td><td>of what a human found, how much it found</td></tr>
      <tr><td>kind accuracy</td><td class="n">${{(t.kind_accuracy*100||0).toFixed(1)}}%</td><td>measurement vs design spec vs regulatory limit</td></tr>
      <tr><td>stream accuracy</td><td class="n">${{(t.stream_accuracy*100||0).toFixed(1)}}%</td><td>influent vs effluent — getting this backwards turns a working plant into a polluting one</td></tr>
      </table></div>`;
    h += `<div class="card"><h3 style="margin:0 0 6px;font-size:11px;color:#6d7a86;
          text-transform:uppercase;letter-spacing:.06em">The first number was wrong, and it was the ruler</h3>
      <p class="lede" style="margin:0">The first scored run reported 49% precision. Auditing the
      records it called wrong showed nearly all of them were right — the scorer could not convert
      "3.0 million gallons" to "3000000 gallons", and the hand-written ground truth was incomplete.
      Fixing the measurement, with no change at all to the extractor, moved precision from 49.1%
      to ${{(t.precision*100||0).toFixed(1)}}%. Publishing the first figure would have narrowed
      the project for no reason.</p></div>`;
    el.innerHTML = h;
  }},

  decisions: async () => {{
    const el = document.getElementById("decisions-body");
    const run = async () => {{
      const id = document.getElementById("dec-id").value.trim();
      if (!id) return;
      el.innerHTML = `<div class="card note" style="border:0">Reading every page of
        ${{id}} for motions and recorded votes…</div>`;
      const d = await (await fetch("/api/decisions?identifier=" + encodeURIComponent(id))).json();
      if (d.error) {{ el.innerHTML = `<div class="card note" style="border:0">${{d.error}}</div>`; return; }}

      const o = d.outcomes || {{}};
      let h = `<div class="card"><table class="gt">
        <tr><th>found</th><th class="n">n</th></tr>
        <tr><td>motions and recorded divisions</td><td class="n">${{d.motions||0}}</td></tr>
        <tr><td>people named</td><td class="n">${{d.people||0}}</td></tr>
        <tr><td>recorded votes</td><td class="n">${{d.recorded_votes||0}}</td></tr>
        <tr><td>rolls that do not match the clerk's tally</td><td class="n">${{d.rolls_that_do_not_reconcile||0}}</td></tr>
        </table>
        <p class="lede" style="margin:8px 0 0">${{
          Object.entries(o).map(([k,v]) => `${{v}} ${{k}}`).join(" · ")}}</p></div>`;

      if ((d.divided||[]).length) {{
        h += `<div class="card"><h3 style="margin:0 0 8px;font-size:11px;color:#6d7a86;
              text-transform:uppercase;letter-spacing:.06em">Where they disagreed</h3>`;
        d.divided.forEach(x => {{
          h += `<div style="margin:0 0 10px;padding-left:11px;border-left:2px solid rgba(255,255,255,.14)">
            <div style="font-size:12px">${{(x.text||"").replace(/</g,"&lt;")}}</div>
            <div class="lede" style="margin:3px 0 0;font-size:11px">
              ${{x.outcome}} · against: ${{(x.against||[]).join(", ") || "—"}}
              ${{x.page_url ? ` · <a href="${{x.page_url}}" target="_blank" rel="noopener">the page</a>` : ""}}
            </div></div>`;
        }});
        h += `</div>`;
      }}

      if ((d.most_active||[]).length) {{
        h += `<div class="card"><h3 style="margin:0 0 6px;font-size:11px;color:#6d7a86;
              text-transform:uppercase;letter-spacing:.06em">Who was in the room</h3>
              <table class="gt"><tr><th>person</th><th>role</th><th class="n">moved</th>
              <th class="n">seconded</th><th class="n">yea</th><th class="n">nay</th></tr>`;
        d.most_active.forEach(p => {{
          const v = p.votes || {{}};
          h += `<tr><td>${{p.name}}</td><td>${{(p.roles||[])[0]||""}}</td>
                <td class="n">${{p.moved||0}}</td><td class="n">${{p.seconded||0}}</td>
                <td class="n">${{v.yea||0}}</td><td class="n">${{v.nay||0}}</td></tr>`;
        }});
        h += `</table></div>`;
      }}

      if ((d.dissenters||[]).length) {{
        h += `<div class="card"><h3 style="margin:0 0 6px;font-size:11px;color:#6d7a86;
              text-transform:uppercase;letter-spacing:.06em">Dissent</h3>
              <p class="lede" style="margin:0 0 6px">Most recorded votes are unanimous, so a
              nay is the rarest and most informative thing in the record.</p>`;
        d.dissenters.forEach(x => {{
          h += `<div style="font-size:12px">${{x.person}} — ${{x.nays}} against, ${{x.yeas}} for</div>`;
        }});
        h += `</div>`;
      }}

      (d.not_measured||[]).forEach(n => {{
        h += `<div class="card note" style="border:0;padding-left:11px">${{n}}</div>`;
      }});
      el.innerHTML = h;
    }};
    document.getElementById("dec-go").onclick = run;
    run();
  }},

  disputed: async () => {{
    const el = document.getElementById("disputed-body");

    document.getElementById("sb-go").onclick = async () => {{
      const v = id => document.getElementById(id).value.trim();
      const out = document.getElementById("sb-out");
      if (!v("sb-id") || !v("sb-page") || !v("sb-quote")) {{
        out.textContent = "An identifier, a page and a sentence are the whole requirement.";
        return;
      }}
      out.textContent = "Asking the page…";
      const qs = new URLSearchParams({{
        identifier: v("sb-id"), page: v("sb-page"), parameter: v("sb-param"),
        value: v("sb-value"), unit: v("sb-unit"), place: v("sb-place"),
        facility: v("sb-facility"), period: v("sb-period"), quote: v("sb-quote"),
      }});
      const d = await (await fetch("/api/submit?" + qs)).json();
      out.innerHTML = (d.accepted
          ? `<strong style="color:#36e0c8">In the record.</strong> `
          : `<strong style="color:#f0a24a">Not in the record.</strong> `)
        + d.what_happens_now;
      if (d.accepted) LOADERS.disputed();
    }};
    el.innerHTML = `<div class="card note" style="border:0">Checking every claim against the
      scans it cites…</div>`;
    const d = await (await fetch("/api/ledger")).json();

    let h = `<div class="card"><table class="gt">
      <tr><th>state</th><th class="n">measurements</th><th>what it means</th></tr>
      <tr><td>settled</td><td class="n">${{d.settled||0}}</td><td>one reading, and the page backs it</td></tr>
      <tr><td>contested</td><td class="n">${{d.contested||0}}</td><td>two readings, both backed by the page — shown, not chosen between</td></tr>
      <tr><td>unsupported</td><td class="n">${{d.unsupported||0}}</td><td>nothing surviving cites a sentence that is really there</td></tr>
      <tr><td>flags raised</td><td class="n">${{d.flags||0}}</td><td>counted, shown, and inert by design</td></tr>
      </table></div>`;

    (d.contested_detail || []).forEach(slot => {{
      const parts = slot.slot.split("|");
      const title = parts.filter(Boolean).join(" · ") || "(unnamed)";
      h += `<div class="card"><h3 style="margin:0 0 4px;font-size:12px">${{title}}</h3>`;
      h += `<p class="lede" style="margin:0 0 10px">${{
        slot.same_sentence
          ? "One sentence, read two ways. The document itself is ambiguous here."
          : "Two different sentences are being cited. They may not be about the same thing."
      }}${{slot.n_flags ? ` · ${{slot.n_flags}} reader flag(s)` : ""}}</p>`;
      h += `<div style="display:flex;gap:14px;flex-wrap:wrap">`;
      (slot.readings || []).forEach(r => {{
        h += `<div style="flex:1 1 280px;min-width:260px;border:1px solid rgba(255,255,255,.09);
              border-radius:10px;padding:10px">
          <div style="font-size:20px;font-weight:600">${{r.value}} <span
              style="font-size:12px;opacity:.6">${{r.unit||""}}</span></div>
          <div style="font-size:11px;opacity:.6;margin:2px 0 8px">${{r.contributor||"extraction"}}</div>`;
        if (r.crop_url) {{
          h += `<a href="${{r.page_url}}" target="_blank" rel="noopener">
                <img src="${{r.crop_url}}" alt="the sentence this number was read from"
                     loading="lazy" style="width:100%;border-radius:6px;background:#f6f1e4"></a>`;
        }}
        h += `<div class="lede" style="margin:8px 0 0;font-size:11px">“${{
              (r.quote||"").replace(/</g,"&lt;")}}”</div>
          <button type="button" data-claim="${{r.claim_id}}" class="flag-btn"
            style="margin-top:8px;background:transparent;border:1px solid rgba(255,255,255,.16);
                   color:inherit;border-radius:7px;padding:4px 9px;font:inherit;font-size:11px;
                   cursor:pointer">Looks wrong</button>
        </div>`;
      }});
      h += `</div></div>`;
    }});

    if (!(d.contested_detail || []).length) {{
      h += `<div class="card note" style="border:0">Nothing is contested yet. That is not the
            same as everything being right — it means no two readings of the same measurement
            have both survived the check.</div>`;
    }}

    (d.not_measured || []).forEach(n => {{
      h += `<div class="card note" style="border:0;padding-left:11px">${{n}}</div>`;
    }});
    el.innerHTML = h;

    el.querySelectorAll(".flag-btn").forEach(b => b.onclick = async () => {{
      const reason = prompt("What looks wrong about it?") || "";
      await fetch("/api/flag?claim=" + encodeURIComponent(b.dataset.claim)
                  + "&reason=" + encodeURIComponent(reason));
      b.textContent = "Flagged — the record is unchanged";
      b.disabled = true;
      b.style.opacity = ".6";
    }});
  }}
}};
</script></body></html>"""
