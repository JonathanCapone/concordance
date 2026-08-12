"""The map portal, forked from the OMEGA-wave portal.

What comes across: the app shell -- header, icon nav rail, panel dock -- its
553 KB of chrome CSS, and the MapLibre setup with keyless Esri imagery and AWS
terrarium terrain.

What does not: OMEGA's `portal.js`. It is 2.3 MB bound to endpoints for mesh
routing, firmware builds, acoustic messaging and storm tracking, none of which
exist here. Forking it wholesale would produce a menu full of controls wired to
nothing, which is worse than a smaller portal that works.

So the chrome is OMEGA's and the four views are this project's:

    Observe   where the measurements are
    Record    one place, read out of the scans
    Silence   what stopped being measured, and when
    Verify    how accurate the reading is, against hand-checked ground truth

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
    ("verify", "Verify", "M5 12.6 9.8 17.4 19 6.6"),
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
.legend{{position:absolute;left:18px;bottom:20px;z-index:11;
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

    <section class="view" data-view="verify">
      <div class="pane">
        <h2>How accurate is this?</h2>
        <p class="lede">Measured against ground truth a human read off the same scans by hand.
        Published including the failures — an archive misread at scale is worse than one never
        read, because the errors look like findings.</p>
        <div id="verify-body"></div>
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
      h += `<div class="row"><span class="y">${{x.period||""}}</span>`
         + `<span>${{x.parameter}}</span><span class="v">${{x.value}} ${{x.unit||""}}</span>`
         + `<span class="src">“${{x.read_from}}” <a href="${{x.page_url}}" target="_blank" rel="noopener">scan ↗</a></span></div>`;
    }});
    h += `</div>`;
  }});
  return h;
}}

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
    h += `<div class="empty">Located, but not read yet. Reading one town is about an hour
      of local inference; ${{p.years}} scanned reports are waiting here.</div>`;
  }} else {{
    h += seriesHtml(d);
    h += `<div class="note">${{d.n_measurements}} measurements from ${{d.sources.length}} documents.
      Every value was read from a scanned page by a language model and links back to it.
      Measured precision against hand-checked ground truth is ${{PRECISION}}.
      Nothing here should be believed without checking it.</div>`;
  }}
  dockBody.innerHTML = h;
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
  map.fitBounds(b,{{padding:{{top:60,bottom:60,left:60,right:450}},duration:0}});
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
  }}
}};
</script></body></html>"""
