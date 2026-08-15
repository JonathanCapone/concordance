"""The map portal, forked from the OMEGA-wave portal.

What comes across: the app shell -- header, icon nav rail, panel dock -- its
553 KB of chrome CSS, and the MapLibre setup with keyless Esri imagery and AWS
terrarium terrain.

What does not: OMEGA's `portal.js`. It is 2.3 MB bound to endpoints for mesh
routing, firmware builds, acoustic messaging and storm tracking, none of which
exist here. Forking it wholesale would produce a menu full of controls wired to
nothing, which is worse than a smaller portal that works.

So the chrome is OMEGA's and the views are this project's:

    Observe     where the extracted records are
    Record      one place, read out of the scans -- every number keeps its page
                link and can show a crop when the image service permits
    Silence     where title-derived series have no later indexed entry
    Rivers      who was downstream of whom, and what the method refused to link
    Verify      how accurate the reading is, against hand-checked ground truth
    Decisions   who moved what, who seconded, and how each person voted
    Disputed    claims two readings disagree about, shown with source links and
                available crops, because nobody here adjudicates
    Ask Jay    the agent, over the whole toolset

This is the SERVING layer, and the one place allowed outside dependencies. The
core stays dependency-free: nobody should need a mapping library installed to
check whether 104 mg/L is what the page says.
"""

from __future__ import annotations

MAPLIBRE_VERSION = "5.24.0"
SAT_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
DEM_TILES = "https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png"

#: The nav, in a visitor's words rather than mine.
#:
#: These used to be nine module names in the order the modules were built --
#: Observe, Record, Silence, Rivers, Verify, Frontier, Decisions, Disputed --
#: which is a map of my work and not of anything a person arrives wanting. The
#: complaint that started this was exact: "I didn't really understand what the
#: tabs were for or how I would actually use any of the information."
#:
#: Rivers is gone: "whose sewage was in my water" is a question about YOUR
#: town, so it lives on the town's page, with a link out to the whole river.
#: Record and Frontier are gone too -- one was the place panel, which opens
#: from the map, and the other was a to-read list that belongs beside the map
#: it ranks.
NAV = [
    ("observe", "Find a place", "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17Zm0 4.6a3.9 3.9 0 1 1 0 7.8 3.9 3.9 0 0 1 0-7.8Z"),
    ("silence", "What stopped", "M4 12h4l3.2-5.4v10.8L8 12H4Zm12.4-3.4a6 6 0 0 1 0 6.8M19 6a9.4 9.4 0 0 1 0 12"),
    ("disputed", "Disagreements", "M12 4.5 3.5 19.5h17L12 4.5Zm0 5.4v4.4m0 2.6v.1"),
    ("decisions", "Who decided", "M7 4.5h10v15H7Zm2.6 4h4.8m-4.8 3.6h4.8m-4.8 3.6h3"),
    ("verify", "Can I trust it", "M5 12.6 9.8 17.4 19 6.6"),
    ("frontier", "What to read next", "M12 4.5v15M4.5 12h15M7.5 7.5l9 9M16.5 7.5l-9 9"),
    ("record", "One town, in full", "M4 19.2V4.8h9.6l6.4 6.4v8H4Zm9.2-13.4v5.4h5.4"),
    ("ask", "Ask Jay", "M4.5 6.5h15v9h-8.4L6.6 19v-3.5H4.5Z"),
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
<title>Concordance — Canada's public record, read</title>
<link rel="stylesheet" href="/static/omega-portal.css">
<style>
/* Concordance overrides on top of the inherited OMEGA chrome. */
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
.chart{{width:100%;height:auto;display:block;margin:2px 0 10px;color:var(--ink,#cfd8e0)}}
.inv{{display:flex;flex-wrap:wrap;gap:5px;margin:2px 0 4px}}
.chip{{font-size:11px;padding:3px 7px;border-radius:11px;background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.09);white-space:nowrap}}
.chip b{{opacity:.55;font-weight:600;margin-left:3px}}
.chip.more{{opacity:.6}}
.scope{{font-size:11px;opacity:.5;font-weight:400;margin-left:8px}}
.warn{{font-size:11px;margin-left:8px;color:#f0a24a;opacity:.85}}
.grp{{margin:0 0 12px}}
.grp h4{{margin:8px 0 3px;font-size:12px;font-weight:600;opacity:.85}}
.row.charted .y{{font-weight:700}}
.row .q{{font-size:11px;opacity:.55}}
.row .pg{{font-size:10px;opacity:.45;margin-left:5px}}
.legend{{display:flex;flex-wrap:wrap;gap:10px;font-size:11px;opacity:.75;margin:0 0 2px}}
.legend i{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px}}
.findbar{{display:flex;align-items:center;gap:10px;margin:2px 0 10px;position:sticky;top:0;
  background:var(--dock-bg,rgba(9,13,18,.97));padding:6px 0;z-index:2}}
.findbar input{{flex:1;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);
  border-radius:6px;color:inherit;padding:6px 9px;font:inherit;font-size:12px}}
.findbar .count{{font-size:11px;opacity:.55;white-space:nowrap}}
.panel{{border-top:1px solid rgba(255,255,255,.08);padding:0}}
.panel>summary,.sub>summary{{display:flex;align-items:baseline;gap:10px;cursor:pointer;
  padding:7px 2px;list-style:none;font-size:13px}}
.panel>summary::-webkit-details-marker,.sub>summary::-webkit-details-marker{{display:none}}
.panel>summary::before,.sub>summary::before{{content:"▸";opacity:.4;font-size:10px;width:9px}}
.panel[open]>summary::before,.sub[open]>summary::before{{content:"▾"}}
.panel>summary:hover,.sub>summary:hover{{background:rgba(255,255,255,.03)}}
.panel .nm,.sub .nm{{flex:1;font-weight:600}}
.panel .sm,.sub .sm{{font-size:11px;opacity:.55;white-space:nowrap}}
.panel .sm.n{{opacity:.4}}
.panel>.body,.sub>.body{{padding:2px 0 12px 9px}}
.sub{{border-top:1px solid rgba(255,255,255,.05)}}
.sub>summary{{font-size:12px;padding:5px 2px}}
.river{{font-size:12px;padding:7px 9px;margin:2px 0 8px;border-radius:7px;background:rgba(125,211,252,.07);border:1px solid rgba(125,211,252,.16)}}
.river .more{{display:inline-block;margin-left:6px;font-size:11px;opacity:.7}}
.river .nm{{display:block;font-size:10px;letter-spacing:.08em;text-transform:uppercase;opacity:.5;margin-bottom:2px}}
.system{{display:flex;align-items:baseline;gap:9px;margin:14px 0 3px;padding-bottom:4px;border-bottom:1px solid rgba(255,255,255,.14)}}
.system .t{{font-size:12px;font-weight:700;letter-spacing:.03em}}
.shelf{{font-size:10px;letter-spacing:.09em;text-transform:uppercase;opacity:.4;margin:11px 0 1px;padding-top:5px;border-top:1px solid rgba(255,255,255,.06)}}
.chart.one{{display:flex;align-items:baseline;gap:7px;margin:2px 0 10px}}
.chart.one .big{{font-size:26px;font-weight:600}}
.chart.one .u{{font-size:12px;opacity:.6}}
.chart.one .note{{font-size:11px;opacity:.55;margin-left:4px}}
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
      <p class="brand-wordmark">CONCORDANCE</p>
      <p class="brand-sub">Canada's public record, read</p>
    </div>
    <nav class="primary-nav icon-nav" aria-label="Views">{_nav()}</nav>
    <div class="header-stats">
      <div class="hstat"><b>{s['located']}</b><span>located</span></div>
      <div class="hstat"><b>{s['read']}</b><span>read</span></div>
      <div class="hstat"><b>{s['records']}</b><span>source-linked records</span></div>
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
        <h2>Where the indexed record goes quiet</h2>
        <p class="lede">A missing catalogue entry does not establish that reporting stopped.
        These title-derived gaps are checked against broader collection activity to test for a
        collection-wide scanning cutoff; each individual cause remains unknown.</p>
        <div id="silence-body"></div>
      </div>
    </section>

    <section class="view" data-view="ask">
      <div class="pane">
        <h2>Ask Jay</h2>
        <p class="lede">Jay answers only from the extracted record. It cannot answer from
        memory, every number it reports carries the page it was read from, and it will not
        describe a title-series gap without the collection-wide control and its limits.</p>
        <div class="card">
          <div style="display:flex;gap:9px">
            <input id="ask-input" maxlength="1000" placeholder="What did Owen Sound discharge?"
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

    <section class="view" data-view="frontier">
      <div class="pane">
        <h2>What one more document would answer</h2>
        <p class="lede">Eleven million pages cannot be read alphabetically, and reading by
        subject only serves whoever picked the subject. This orders them by <strong>what
        reading them would unlock</strong> — because a question one document away is a
        question somebody already wanted.</p>
        <p class="lede" style="opacity:.72">It is also the honest replacement for a progress
        bar. "You processed 40 documents" is a fact about you. "You made the Grand River
        answerable, and it had been waiting on one town since 1961" is a fact about the world.</p>
        <div id="frontier-body"></div>
      </div>
    </section>

    <section class="view" data-view="decisions">
      <div class="pane">
        <h2>Who decided, and who voted against</h2>
        <p class="lede">A title-keyword census found roughly 13,600 minutes, agendas, hansard
        and commission-hearing items. The civic parser is promising, but it does not yet have
        the measurement path's hand-read benchmark. Such records can still be cheap to read: "It was
        moved by X and seconded by Y that Z. CARRIED." is a form that has barely changed in a
        century, so a pattern finds it. No model, no GPU, and a person can check it.</p>
        <p class="lede" style="opacity:.72">The control is the clerk's own tally. That "-16."
        at the end of a roll was written by someone in the room; if the names don't add up to
        it, the roll was misread and it says so rather than publishing a division quietly
        missing two people.</p>
        <div style="display:flex;gap:8px;margin:0 0 12px">
          <input id="dec-id" maxlength="256" placeholder="archive.org identifier" value="32022213341486"
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
        <p class="lede">Every claim here keeps its cited archive page. Prose uses sentence
        evidence; experimental table records retain cell locators but abstain without localized
        cell proof. When two source-backed readings still disagree, nobody decides between them
        — both remain visible with page links and crops when available. The evidence check
        establishes what the cited page says, not which interpretation is correct.</p>
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
              <input id="sb-id" maxlength="256" placeholder="archive.org identifier">
              <input id="sb-page" maxlength="7" placeholder="page number" inputmode="numeric">
              <input id="sb-param" maxlength="400" placeholder="what was measured, e.g. BOD">
              <input id="sb-value" maxlength="100" placeholder="the number">
              <input id="sb-unit" maxlength="400" placeholder="unit, e.g. mg/L">
              <input id="sb-place" maxlength="400" placeholder="place">
              <input id="sb-facility" maxlength="400" placeholder="which plant / hospital / board (optional)">
              <input id="sb-period" maxlength="400" placeholder="year">
            </div>
            <textarea id="sb-quote" rows="2" maxlength="4000" placeholder="the exact sentence, copied from the page"
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

<script>
const PRECISION = "{s['precision']:.0%}";

/* Everything drawn into innerHTML that came from a RECORD goes through this.
   Records are not ours: /api/bundle and /api/submit take readings from anyone,
   by design, because the archive decides and asking who is speaking would
   contradict the whole claim. But "we do not check the sender" has to mean we
   do not check their IDENTITY -- it cannot mean we paste their strings into the
   page as markup.

   A submitted reading whose place is `<img src=x onerror=...>` ran on the
   Disputed view, which is exactly the page a reader visits to adjudicate a
   contested number. The fields are all short labels -- place, facility,
   parameter, unit, period, contributor, and the quoted sentence itself -- so
   there is never a reason for any of them to carry markup. */
const esc = v => String(v === null || v === undefined ? "" : v)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

/* Attribute escaping does not make a URL safe: javascript:alert(1) contains
   no markup to escape. Links and images built from records/API responses are
   restricted to HTTP(S), then escaped for the quoted attribute. Relative
   paths resolve against this instance and are therefore allowed too. */
const safeHttpUrl = value => {{
  try {{
    const raw = String(value || "").trim();
    if (!raw) return "";
    const url = new URL(raw, window.location.origin);
    return (url.protocol === "http:" || url.protocol === "https:") ? esc(url.href) : "";
  }} catch (_) {{
    return "";
  }}
}};

/* Work that invokes a model/archive or changes process state is deliberately
   JSON POST. Besides making browser prefetch and crawlers harmless, this is a
   non-simple request cross-origin, and the server independently checks any
   Origin it receives against its actual Host. */
const postJson = async (path, payload) => {{
  const response = await fetch(path, {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify(payload),
  }});
  return response.json();
}};

/* ---- view switching ------------------------------------------------ */
const views = [...document.querySelectorAll(".view")];
const loaded = {{}};

/* Switching by name, so a link inside a place page can reach a view that has
   no button of its own. The whole-river index is one of those: it is real
   content and it is not a question anybody arrives with, so it is reached
   from the town whose river it is. */
function showView(key){{
  document.querySelectorAll(".nav-button").forEach(b =>
    b.classList.toggle("is-active", b.dataset.view === key));
  views.forEach(v => v.classList.toggle("is-active", v.dataset.view === key));
  document.body.dataset.route = key;
  if (!loaded[key] && LOADERS[key]) {{ loaded[key] = true; LOADERS[key](); }}
  if (key === "observe" && window._map) setTimeout(() => window._map.resize(), 60);
}}
document.querySelectorAll(".nav-button").forEach(btn =>
  btn.onclick = () => showView(btn.dataset.view));
document.addEventListener("click", ev => {{
  const link = ev.target.closest("[data-goto]");
  if (link) {{ ev.preventDefault(); showView(link.dataset.goto); }}
}});

/* ---- shared ---------------------------------------------------------- */

/* A reading chart, adapted from OMEGA's drawLineChart.

   Two things are deliberately NOT copied from the original.

   OMEGA plots by array index, because a sensor reports on a regular cadence.
   This archive does not: Brantford has 1961, 1962, then 1966. Plotting by index
   would space those evenly and quietly erase a four-year gap, in a project
   whose whole argument is that silence is a finding. The x axis here is the
   real year.

   And the line is DASHED across any gap noticeably longer than this series'
   usual interval. A solid line between 1962 and 1966 asserts a shape nobody
   measured. The dash says: two readings, and we do not know what happened
   between them.

   Series here run to two, three, five points. A chart of two points is not a
   trend and is not drawn as one -- it gets its dots, its labels and its years,
   and the table underneath carries the sentence each number was read from,
   which is the part that actually answers a question. */
/* Line colours. Influent against effluent on one axis IS the question this
   archive answers -- how much did the plant take out -- so the streams share a
   panel and are told apart by colour and a legend, after OMEGA's
   drawMultiSeriesChart. */
const LINE_INK = ["#f0a24a", "#7dd3fc", "#9ae6a4", "#f0806e", "#c4a5f0", "#e6d27a"];

function chart(s){{
  /* One panel may hold several lines (influent, effluent, raw). A single
     series still arrives as s.points, so both shapes are accepted. */
  const lines = (s.lines && s.lines.length)
    ? s.lines.map(l => ({{name: l.name || "reported",
        pts: (l.points||[]).filter(p=>Number.isFinite(+p[1])).sort((a,b)=>a[0]-b[0])}}))
        .filter(l => l.pts.length)
    : [{{name:"", pts:(s.points||[]).filter(p=>Number.isFinite(+p[1])).sort((a,b)=>a[0]-b[0])}}]
        .filter(l => l.pts.length);
  if(!lines.length) return "";
  const pts = lines.flatMap(l => l.pts);
  const unit=s.unit?String(s.unit):"";
  const fmt=v=>(Math.abs(v)>=1e6?(v/1e6).toFixed(2)+"M":Math.abs(v)>=1000?v.toLocaleString():String(+(+v).toFixed(2)));

  if(pts.length===1 && lines.length===1){{
    return `<div class="chart one"><span class="big">${{esc(fmt(pts[0][1]))}}</span>
      <span class="u">${{esc(unit)}}</span>
      <span class="note">one reading, ${{esc(String(pts[0][0]))}} — not a trend</span></div>`;
  }}

  const W=640,H=190,L=48,R=16,T=18,B=28;
  const xs=pts.map(p=>+p[0]), ys=pts.map(p=>+p[1]);
  const x0=Math.min(...xs), x1=Math.max(...xs);
  let y0=Math.min(...ys), y1=Math.max(...ys);
  if(y1===y0){{y0-=Math.abs(y0)*0.1||1; y1+=Math.abs(y1)*0.1||1;}}
  const px=x=>L+((x-x0)/((x1-x0)||1))*(W-L-R);
  const py=y=>T+(1-(y-y0)/((y1-y0)||1))*(H-T-B);

  /* These are ANNUAL reports, so a gap of more than one year is a year nobody
     read -- and that is exactly what the legend claims the dash means.

     The first version of this compared each gap against the series' own median
     interval, which sounds more sophisticated and is wrong: a series that is
     irregular throughout has no unusual gap, so Brantford's BOD discharged
     (1961, 1962, 1966, 1970, 1972) drew as a confident solid line straight
     across nine missing years. A rule that hides gaps in the gappiest series is
     the opposite of the one this project wants. */
  let segs="", dots="", broken=false;
  lines.forEach((line, li) => {{
    const ink = LINE_INK[li % LINE_INK.length];
    const lx = line.pts.map(p=>+p[0]), ly = line.pts.map(p=>+p[1]);
    for(let i=1;i<line.pts.length;i++){{
      const wide=(lx[i]-lx[i-1])>1;
      if(wide) broken=true;
      segs+=`<path d="M${{px(lx[i-1]).toFixed(1)}},${{py(ly[i-1]).toFixed(1)}} L${{px(lx[i]).toFixed(1)}},${{py(ly[i]).toFixed(1)}}"
        fill="none" stroke="${{ink}}" stroke-width="2.2" stroke-linecap="round"
        ${{wide?'stroke-dasharray="5 5" opacity=".45"':'opacity=".9"'}}/>`;
    }}
    dots+=line.pts.map(p=>`<circle cx="${{px(+p[0]).toFixed(1)}}" cy="${{py(+p[1]).toFixed(1)}}" r="3.6"
      fill="${{ink}}"><title>${{esc(line.name||"")}}${{line.name?": ":""}}${{esc(String(p[0]))}}: ${{esc(fmt(p[1]))}} ${{esc(unit)}}</title></circle>`).join("");
  }});
  const legend = lines.length>1
    ? `<div class="legend">` + lines.map((l,i)=>
        `<span><i style="background:${{LINE_INK[i%LINE_INK.length]}}"></i>${{esc(l.name)}}</span>`).join("") + `</div>`
    : "";

  const gridY=[y1,(y0+y1)/2,y0].map(v=>
    `<line x1="${{L}}" y1="${{py(v).toFixed(1)}}" x2="${{W-R}}" y2="${{py(v).toFixed(1)}}"
       stroke="currentColor" stroke-width=".5" opacity=".14"/>
     <text x="${{L-6}}" y="${{(py(v)+3.5).toFixed(1)}}" text-anchor="end"
       font-size="10" fill="currentColor" opacity=".55">${{esc(fmt(v))}}</text>`).join("");

  return legend + `<svg class="chart" viewBox="0 0 ${{W}} ${{H}}" role="img"
      aria-label="${{esc(s.label||"readings")}}${{unit?" in "+esc(unit):""}}, ${{pts.length}} readings from ${{x0}} to ${{x1}}">
    ${{gridY}}
    <text x="${{L}}" y="${{H-8}}" font-size="10" fill="currentColor" opacity=".55">${{x0}}</text>
    <text x="${{W-R}}" y="${{H-8}}" text-anchor="end" font-size="10" fill="currentColor" opacity=".55">${{x1}}</text>
    ${{segs}}${{dots}}
    ${{broken?`<text x="${{(L+W-R)/2}}" y="${{H-8}}" text-anchor="middle" font-size="10"
       fill="currentColor" opacity=".5">dashed = years with no reading</text>`:""}}
  </svg>`;
}}

function rowsHtml(rows){{
  let h = "";
  (rows||[]).forEach(x => {{
      const cite = x.identifier && x.page
        ? ` <button type="button" class="paper-btn" data-id="${{esc(x.identifier)}}"
             data-page="${{esc(x.page)}}" data-quote="${{esc(encodeURIComponent(x.quote||""))}}"
             title="show the sentence on the scan">show the paper</button>` : "";
      const scanUrl = safeHttpUrl(x.page_url);
      const scanLink = scanUrl
        ? ` <a href="${{scanUrl}}" target="_blank" rel="noopener">scan ↗</a>` : "";
    /* The page number, beside the period. Two readings of one parameter in one
       year -- from different pages of the same volume -- rendered as two rows
       both saying "1965" with different numbers and nothing to tell them
       apart. The page is what distinguishes them, and it is the thing this
       project wants in front of a reader anyway. */
    h += `<div class="row${{x.charted?" charted":""}}">`
       + `<span class="y">${{esc(x.period||"")}}${{x.page?`<span class="pg">p${{esc(x.page)}}</span>`:""}}</span>`
       + `<span>${{esc(x.parameter)}}${{x.qualifier?` <span class="q">${{esc(x.qualifier)}}</span>`:""}}</span>`
       + `<span class="v">${{esc(x.value)}} ${{esc(x.unit||"")}}</span>`
       + `<span class="src">“${{esc(x.read_from)}}”${{scanLink}}${{cite}}`
       + `<span class="paper"></span></span></div>`;
  }});
  return h;
}}

/* Everything this place measured -- not a list of seven parameters chosen when
   the corpus was one town's sewage reports.

   That list used to be the filter, and it reached 25.7% of observations.
   Stratford drew four charts out of sixty-six distinct measurements; Belleville,
   the largest town in the corpus, drew none at all. "I wondered how useful the
   data actually is being presented this way" was a correct bug report: three
   quarters of what had been read was never rendered.

   Series with more than one year get a chart. A parameter measured once gets
   its number. A group whose units cannot be reconciled gets its readings and a
   note saying so. Nothing is dropped, and every row carries the sentence it was
   read from. */
function seriesHtml(d){{
  const panels = d.series || [];
  const singles = d.singles || [];
  const fmtN = v => (Math.abs(v)>=1e6?(v/1e6).toFixed(2)+"M":Math.abs(v)>=1000?Math.round(v).toLocaleString():String(+(+v).toFixed(2)));

  /* Whose sewage was in your water. The question a person actually asks, on
     the page about their own town, instead of a cross-country river index. */
  let h = "";
  const riv = d.river;
  if (riv && (riv.upstream.length || riv.downstream.length)) {{
    const bits = [];
    if (riv.upstream.length)
      bits.push(`<b>${{esc(riv.upstream.join(", "))}}</b> discharged upstream of here`);
    if (riv.downstream.length)
      bits.push(`this discharged upstream of <b>${{esc(riv.downstream.join(", "))}}</b>`);
    h += `<div class="river"><span class="nm">${{esc(riv.name || "the river")}}</span>
      ${{bits.join(" · ")}}
      <a href="#" data-goto="rivers" class="more">the whole river ↗</a></div>`;
  }}

  h += `<div class="findbar">
      <input id="find" type="search" placeholder="filter — try chlorine, flow, cost"
        autocomplete="off" spellcheck="false">
      <span class="count">${{panels.length}} charted · ${{singles.length + (d.other||[]).reduce((n,g)=>n+g.rows.length,0)}} more</span></div>`;

  /* Charted measurements. The rows are folded away: a reader wants to see WHAT
     was measured and roughly when, then open the one they care about. Showing
     448 rows at once is the same failure as showing none -- it was all there
     and none of it was usable. */
  /* One section per works, because a town's sewage plant and its drinking
     water supply are different subjects and a reader needs to know which a
     number is about before it means anything. */
  (d.systems || []).forEach(sys => {{
    const sp = sys.span ? `${{sys.span[0]}}–${{sys.span[1]}}` : "";
    h += `<div class="system"><span class="t">${{esc(sys.title)}}</span>
      <span class="sm">${{esc(sp)}} · ${{sys.n}} readings</span></div>`;
    sys.panels.forEach(p => {{
      if (p.shelf) h += `<div class="shelf">${{esc(p.shelf)}}</div>`;
      h += panelHtml(p);
    }});
  }});
  if (!(d.systems || []).length) panels.forEach(p => {{ h += panelHtml(p); }});

  function panelHtml(p){{
    const span = p.span ? `${{p.span[0]}}–${{p.span[1]}}` : "";
    const rng = p.range ? `${{fmtN(p.range[0])}}–${{fmtN(p.range[1])}}` : "";
    return `<details class="panel" data-find="${{esc((p.plain||p.label)+" "+(p.unit||"")).toLowerCase()}}">
      <summary><span class="nm">${{esc(p.plain || p.label)}}</span>
        <span class="sm">${{esc(span)}}</span>
        <span class="sm">${{esc(rng)}} ${{esc(p.unit||"")}}</span>
        <span class="sm n">${{p.n}} reading${{p.n===1?"":"s"}}</span></summary>
      <div class="body">` + chart(p) + rowsHtml(p.rows) + `</div></details>`;
  }}

  /* Measured once, or not comparable. One compact line each: these are facts
     without a trend, and a section per group buried the page. */
  if (singles.length) {{
    h += `<details class="panel wide" data-find="single once">
      <summary><span class="nm">Measured once, or not comparable</span>
        <span class="sm n">${{singles.length}}</span></summary><div class="body">
      <p class="lede">A single reading is a fact, not a trend. Readings whose units
        cannot be reconciled are listed rather than charted — and rather than
        dropped, which is what used to happen.</p>`;
    singles.forEach(g => {{
      if (g.shelf) h += `<div class="shelf">${{esc(g.shelf)}}</div>`;
      const r = (g.rows||[])[0] || {{}};
      const extra = (g.rows||[]).length > 1 ? ` <span class="sm">+${{g.rows.length-1}}</span>` : "";
      h += `<details class="sub" data-find="${{esc((g.label+" "+(g.substance||"")+" "+(r.unit||"")).toLowerCase())}}">
        <summary><span class="nm">${{esc(g.label)}}</span>
          <span class="sm">${{esc(r.period||"")}}</span>
          <span class="sm">${{esc(r.value||"")}} ${{esc(r.unit||"")}}</span>${{extra}}
          ${{g.not_comparable?`<span class="warn">units not comparable</span>`:""}}</summary>
        <div class="body">` + rowsHtml(g.rows) + `</div></details>`;
    }});
    h += `</div></details>`;
  }}

  /* Design figures, regulatory limits and conclusions. Never charted -- a
     design capacity plotted as a measurement is the fictional trend this
     project exists to avoid -- but shown, because "what it was built for" and
     "what it was allowed to discharge" are exactly what a reader wants beside
     what it actually did. Orangeville has 22 records and not one observation. */
  (d.other || []).forEach(g => {{
    h += `<details class="panel wide" data-find="${{esc((g.title+" "+g.kind).toLowerCase())}}">
      <summary><span class="nm">${{esc(g.title)}}</span>
        <span class="sm">not a measurement</span>
        <span class="sm n">${{g.rows.length}}</span></summary>
      <div class="body">` + rowsHtml(g.rows) + `</div></details>`;
  }});
  return h;
}}

/* Filtering hides what does not match, and says so, rather than leaving a
   reader wondering whether they broke it. */
document.addEventListener("input", ev => {{
  if (ev.target.id !== "find") return;
  const q = ev.target.value.trim().toLowerCase();
  let shown = 0;
  document.querySelectorAll(".panel, .sub").forEach(el => {{
    const hay = el.dataset.find || "";
    const hit = !q || hay.includes(q);
    el.hidden = !hit;
    if (hit && el.classList.contains("panel")) shown++;
    if (q && hit && el.classList.contains("sub")) el.closest(".panel").hidden = false;
  }});
  const c = document.querySelector(".findbar .count");
  if (c) c.textContent = q ? `${{shown}} matching` : c.dataset.all || c.textContent;
}});


/* Only offer to read if this machine will actually do it. */
async function offerRead(){{
  const slot = document.getElementById("read-offer");
  if (!slot) return;
  let st;
  try {{ st = await postJson("/api/read/status", {{}}); }}
  catch (e) {{ st = null; }}
  if (!st || st.error) {{
    slot.innerHTML = `<span class="note">This is a shared instance, so it will
      not spend its graphics card on a visitor's request. Run the reader on your
      own machine and it takes an hour or two:</span>
      <code>python scripts/extract_place.py --place "${{esc(_openPlace ? _openPlace.place : "")}}"</code>`;
    return;
  }}
  slot.innerHTML = `<button type="button" id="read-btn" class="paper-btn">Read it now</button>`;
  if (st.reading && st.job) {{
    document.getElementById("read-btn").disabled = true;
    document.getElementById("read-note").textContent =
      " already reading " + st.job.place + "…";
  }}
}}

/* Reading a place, from the button, on this machine. */
document.addEventListener("click", async ev => {{
  const b = ev.target.closest("#read-btn");
  if (!b) return;
  const note = document.getElementById("read-note");
  const log = document.getElementById("read-log");
  const place = _openPlace ? _openPlace.place : "";
  b.disabled = true;
  note.textContent = " starting…";
  let r;
  try {{
    r = await postJson("/api/read", {{place: place, raw: _openPlace ? (_openPlace.raw||"") : ""}});
  }} catch (e) {{
    note.textContent = " could not reach the reader.";
    b.disabled = false;
    return;
  }}
  if (r && r.error) {{
    /* A public instance. Say so plainly and give the command that works. */
    note.textContent = "";
    log.hidden = false;
    log.textContent = r.error + (r.local_reader ? "\\n\\n" + r.local_reader : "");
    b.remove();
    return;
  }}
  note.textContent = r && r.busy ? " already reading " + (r.job ? r.job.place : "") : " reading…";
  log.hidden = false;
  const tick = async () => {{
    let st;
    try {{ st = await postJson("/api/read/status", {{}}); }} catch (e) {{ return; }}
    const j = st && st.job;
    if (!j) return;
    log.textContent = (j.log || []).join("\\n");
    if (j.state === "running") {{ setTimeout(tick, 4000); return; }}
    if (j.state === "done") {{
      note.textContent = ` read ${{j.records}} measurements from ${{j.documents}} documents.`;
      openTown(_openPlace);            // redraw with what was just read
    }} else if (j.state === "nothing") {{
      note.textContent = " read the documents and found no measurements in them.";
      if (j.note) log.textContent += "\\n" + j.note;
    }} else {{
      note.textContent = " the read failed.";
      log.textContent += "\\n" + (j.error || "");
    }}
  }};
  setTimeout(tick, 1500);
}});

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
  const d = await postJson("/api/citation", {{
    identifier: b.dataset.id,
    page: Number(b.dataset.page),
    quote: decodeURIComponent(b.dataset.quote || ""),
  }});
  const pageUrl = safeHttpUrl(d.page_url);
  if (d.error) {{
    holder.dataset.open = "1";
    b.textContent = "hide";
    holder.innerHTML = `<div style="font-size:11px;opacity:.72;margin-top:7px">${{
      esc(d.note || d.error)}}</div>`
      + (pageUrl ? `<a href="${{pageUrl}}" target="_blank" rel="noopener"
          style="display:inline-block;margin-top:5px">open the whole page ↗</a>` : "");
    return;
  }}
  const cropUrl = safeHttpUrl(d.crop_url);
  if (!cropUrl) {{
    holder.dataset.open = "1";
    b.textContent = "hide";
    holder.innerHTML = `<div style="font-size:11px;opacity:.72;margin-top:7px">${{
      esc(d.note || "The scan image is unavailable.")}}</div>`
      + (pageUrl ? `<a href="${{pageUrl}}" target="_blank" rel="noopener"
          style="display:inline-block;margin-top:5px">open the whole page ↗</a>` : "");
    return;
  }}
  holder.dataset.open = "1";
  b.textContent = "hide";
  holder.innerHTML =
    (pageUrl ? `<a href="${{pageUrl}}" target="_blank" rel="noopener"
        style="display:block;margin-top:7px">` : `<div style="display:block;margin-top:7px">`)
    + `<img src="${{cropUrl}}" alt="the sentence this number was read from" loading="lazy"
            style="max-width:100%;border-radius:6px;background:#f6f1e4">`
    + (pageUrl ? "</a>" : "</div>")
    + (d.exact ? "" : `<div style="font-size:10px;opacity:.6;margin-top:3px">${{esc(d.note)}}</div>`);
}});

/* ---- observe --------------------------------------------------------- */
const dock = document.getElementById("dock");
const dockBody = document.getElementById("dock-body");
document.getElementById("dock-close").onclick = () => dock.classList.remove("open");

/* The place the dock is currently showing, so the reader knows what to read
   and what to redraw when it finishes. */
let _openPlace = null;

async function openTown(p){{
  _openPlace = p;
  dock.classList.add("open");
  dockBody.innerHTML = `<h2>${{esc(p.place)}}</h2><div class="meta">loading…</div>`;
  const d = await (await fetch("/api/town?place=" + encodeURIComponent(p.place)
                   + "&raw=" + encodeURIComponent(p.raw||""))).json();
  let h = `<h2>${{esc(p.place)}}</h2><div class="meta">${{esc(p.years)}} surviving reports · ${{esc(p.first)}}–${{esc(p.last)}}`
        + (p.silent_since ? ` · <span style="color:var(--gt-hit)">silent since ${{esc(p.silent_since)}}</span>` : "")
        + (d.facility ? ` · ${{esc(d.facility)}}` : "") + `</div>`;
  if(!d.found){{
    /* The normal state, not an error. Nobody pre-processes this archive:
       somebody asks, the machine in front of them reads, and the answer is
       there for everyone afterwards. So this offers to read it. On a public
       host the server refuses and says why -- reading is hours of local model
       time and no visitor gets to spend somebody else's graphics card. */
    h += `<div class="empty" id="unread">
      <b>Nobody has read ${{esc(p.place)}} yet.</b><br><br>
      ${{esc(p.years)}} scanned reports are waiting — roughly a minute a page,
      so an hour or two on this machine. Once it is read it is read for
      everybody who asks after you.<br><br>
      <span id="read-offer"></span>
      <span id="read-note"></span>
      <pre id="read-log" hidden></pre></div>`;
    /* Ask the reader whether it exists before offering it. A public instance
       answers 501 and gets the honest explanation instead of a button that
       would fail when pressed. */
    offerRead();
  }} else {{
    h += seriesHtml(d);
    h += `<div class="note">${{esc(d.n_measurements)}} observations from ${{esc((d.sources||[]).length)}} documents.
      Every value was read from a scanned page by a language model and links back to it.
      Measured precision against hand-checked ground truth is ${{PRECISION}}.
      Nothing here should be believed without checking it.</div>`;
  }}
  dockBody.innerHTML = h;

}}

/* The map is the only part of this page that needs a CDN. It is loaded
   dynamically so a slow request cannot hold up the local script and leave all
   nine views inert. After four seconds the map says what is wrong; a late CDN
   response may still recover it without reloading the page. */
const MAP_LOAD_TIMEOUT_MS = 4000;

function showMapMessage(message, state) {{
  const el = document.getElementById("map");
  if (!el || window._map) return;
  el.dataset.mapState = state;
  el.innerHTML = `<div style="position:absolute;inset:0;display:flex;
    align-items:center;justify-content:center;text-align:center;padding:30px;
    color:#8b97a4;font-size:13px;line-height:1.6">${{message}}</div>`;
}}

let mapInitializationStarted = false;
function initializeMap() {{
  if (mapInitializationStarted || window._map) return;
  if (typeof maplibregl === "undefined") {{
    showMapMessage("The map library could not be loaded from the network.<br>"
      + "Every other view works from local data.", "unavailable");
    return;
  }}
  mapInitializationStarted = true;
  const mapElement = document.getElementById("map");
  if (mapElement) {{ mapElement.replaceChildren(); mapElement.dataset.mapState = "ready"; }}
  try {{
const map = new maplibregl.Map({{
  container:"map", center:[-96.8,58.5], zoom:2.9,
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
  /* Frame the country, not the data. Every town read so far is in southern
     Ontario, so fitting to the dots opened the map on one province and quietly
     implied that is what the archive covers. It is not: the corpus is national,
     while simple province-keyword counts are not reliable jurisdiction totals.
     The emptiness elsewhere is a finding rather than a background. Starting at Canada shows the
     gap, which is the honest first impression and also the project's argument.

     Capped at 74N: Canada reaches 83.1N at Ellesmere, and including it spends
     half the screen on ice and shrinks the populated south to nothing. The
     dots are extended in afterwards so nothing read can fall outside the view. */
  const b=new maplibregl.LngLatBounds([-141.0,41.7],[-52.6,74.0]);
  geo.features.forEach(f=>b.extend(f.geometry.coordinates));
  map.fitBounds(b,{{padding:{{top:60,bottom:120,left:60,right:450}},duration:0}});

  /* Timeline of dated catalogue-title entries. It shows the indexed collection,
     not proof that a municipality did or did not report in a given year. */
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
      count.textContent = geo.features.length + " title-derived place/site series \\u00b7 "
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
      ? n + " series with a dated title entry"
      : "no dated title entry in the loaded series";
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

  }} catch (err) {{
    /* Anything the map section throws stops at the map. */
    console.error("map unavailable:", err);
    if (window._map && typeof window._map.remove === "function") {{
      try {{ window._map.remove(); }} catch (_) {{ /* already incomplete */ }}
    }}
    window._map = null;
    showMapMessage("The map could not be started.<br>Every other view works from local data.",
      "unavailable");
  }}
}}

function loadMapLibrary() {{
  const css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = "https://unpkg.com/maplibre-gl@{MAPLIBRE_VERSION}/dist/maplibre-gl.css";
  css.dataset.maplibre = "";
  document.head.appendChild(css);

  if (typeof maplibregl !== "undefined") {{ initializeMap(); return; }}
  showMapMessage("Loading the map&hellip;", "loading");
  const script = document.createElement("script");
  script.src = "https://unpkg.com/maplibre-gl@{MAPLIBRE_VERSION}/dist/maplibre-gl.js";
  script.async = true;
  let settled = false;
  const timer = window.setTimeout(() => {{
    if (!settled) showMapMessage("The map is taking too long to load from the network.<br>"
      + "Every other view is available from local data.", "timed-out");
  }}, MAP_LOAD_TIMEOUT_MS);
  script.addEventListener("load", () => {{
    settled = true;
    window.clearTimeout(timer);
    initializeMap();
  }}, {{once:true}});
  script.addEventListener("error", () => {{
    settled = true;
    window.clearTimeout(timer);
    showMapMessage("The map library could not be loaded from the network.<br>"
      + "Every other view works from local data.", "unavailable");
  }}, {{once:true}});
  document.head.appendChild(script);
}}

/* ---- every view that is not the map ---------------------------------- */
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
      h += `<div class="card"><h2 style="font-size:18px">${{esc(p.place)}}</h2>`
         + `<p class="lede" style="margin-bottom:10px">${{esc(p.years)}} reports · ${{esc(p.first)}}–${{esc(p.last)}}`
         + (d.facility?` · ${{esc(d.facility)}}`:"") + `</p>` + seriesHtml(d) + `</div>`;
    }}
    el.innerHTML = h || `<div class="card empty">Nothing read yet.</div>`;
  }},

  silence: async () => {{
    const d = await (await fetch("/api/quiet")).json();
    const el = document.getElementById("silence-body");
    if(!d.available){{ el.innerHTML = `<div class="card empty">${{esc(d.message)}}</div>`; return; }}
    const st = d.largest_simultaneous_stop || {{}};
    let h = `<div class="card"><div class="big">${{esc(st.municipalities)}} of ${{esc(d.n_municipalities)}}</div>`
          + `<p class="lede" style="margin:4px 0 0">title-derived report series have no dated entry after
             <strong style="color:var(--gt-hit)">${{esc(Number(st.year)-1)}}</strong>.</p></div>`;
    h += `<div class="card"><h3 style="margin:0 0 8px;font-size:11px;color:#6d7a86;
          text-transform:uppercase;letter-spacing:.06em">Did the collection itself stop?</h3>
          <table class="gt"><tr><th>series</th><th class="n">before</th><th class="n">after</th><th></th></tr>`;
    (d.control||[]).forEach(c => {{
      const grew = c.from_cliff_onward > c.before*0.5;
      h += `<tr><td>${{esc(c.series)}}</td><td class="n">${{esc(c.before)}}</td>`
         + `<td class="n">${{esc(c.from_cliff_onward)}}</td>`
         + `<td style="color:${{grew?"#36e0c8":"#f0a24a"}}">${{grew?"keeps going":"also stops"}}</td></tr>`;
    }});
    h += `</table><p class="lede" style="margin:12px 0 0">${{d.control_verdict === "real"
        ? "Broader publishing continued, so this is not a collection-wide scanning cutoff. Individual causes remain unknown."
        : "The whole collection thins at once — a scanning boundary remains possible."}}</p></div>`;
    h += `<div class="card note" style="border:0;padding-left:11px">${{esc(d.caveat)}}</div>`;
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
        const d = await postJson("/api/ask", {{question}});
        let h = `<div class="card"><p class="lede" style="color:#e8edf2;margin:0 0 10px">`
              + `<strong style="color:var(--gt-hit)">Q</strong> ${{esc(question)}}</p>`;
        if(d.error){{
          h += `<p class="empty">No answer: ${{esc(d.error)}}<br><br>Jay needs its configured
                local Ollama service running (<code>ollama serve</code>).</p>`;
        }} else {{
          h += `<p style="margin:0;white-space:pre-wrap">${{esc(d.reply)}}</p>`;
          if(d.tools && d.tools.length){{
            h += `<p style="margin:12px 0 0;font-size:11.5px;color:#6d7a86">`
               + `Answered using: ${{d.tools.map(t=>"<code>"+esc(t.tool)+"</code>").join(", ")}}`
               + ` — no part of this came from the model's own knowledge.</p>`;
          }}
        }}
        out.innerHTML = h + "</div>" + out.innerHTML.replace(
          `<div class="card empty">Reading the record…</div>`, "");
      }} catch(e) {{
        out.innerHTML = `<div class="card empty">Request failed: ${{esc(e)}}</div>`
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
    const d = await postJson("/api/watershed", {{}});
    if(d.error){{ el.innerHTML = `<div class="card empty">${{esc(d.error)}}</div>`; return; }}
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
            text-transform:capitalize">${{esc(r.river)}}</h3>`;
      towns.forEach((t,i) => {{
        const w = 14 + 86*(t.area/max);
        h += `<div style="margin-bottom:3px">
                <div style="height:8px;border-radius:2px;background:var(--gt-hit);opacity:.42;
                     width:${{w.toFixed(0)}}%"></div>
                <div style="font-size:14px;margin-top:2px">${{esc(t.name)}}</div>
                <div style="font-size:11px;color:#6d7a86;font-family:ui-monospace,monospace">
                     ${{Math.round(t.area).toLocaleString()}} km² catchment</div></div>`;
        if(i < towns.length-1) h += `<div style="color:#6d7a86;margin:1px 0 5px">↓</div>`;
      }});
      h += `</div>`;
    }});
    if(d.warnings && d.warnings.length){{
      h += `<div class="card"><h3 style="margin:0 0 8px;font-size:11px;color:#6d7a86;
            text-transform:uppercase;letter-spacing:.06em">What the method refused to link</h3>`;
      d.warnings.forEach(w => h += `<p class="lede" style="margin:0 0 6px;color:#f0a24a">${{esc(w)}}</p>`);
      h += `<p class="lede" style="margin:8px 0 0">Shown because a page that displays only its
            successes teaches nobody where it fails.</p></div>`;
    }}
    h += `<div class="card note" style="border:0;padding-left:11px">${{esc(d.caveat||"")}}</div>`;
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
      <tr><td>kind accuracy</td><td class="n">${{esc((t.kind_accuracy*100||0).toFixed(1))}}%</td><td>measurement vs design spec vs regulatory limit</td></tr>
      <tr><td>stream accuracy</td><td class="n">${{esc((t.stream_accuracy*100||0).toFixed(1))}}%</td><td>influent vs effluent — getting this backwards turns a working plant into a polluting one</td></tr>
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

  frontier: async () => {{
    const el = document.getElementById("frontier-body");
    el.innerHTML = `<div class="card note" style="border:0">Working out what is one
      document away…</div>`;
    const d = await postJson("/api/frontier", {{}});
    if (d.error) {{ el.innerHTML = `<div class="card note" style="border:0">${{esc(d.error)}}</div>`; return; }}
    const c = d.counts || {{}};

    let h = `<div class="card"><table class="gt">
      <tr><th>state</th><th class="n">questions</th></tr>
      <tr><td>answerable now</td><td class="n">${{esc(c.answerable||0)}}</td></tr>
      <tr><td>waiting on a document</td><td class="n">${{esc(c.waiting||0)}}</td></tr>
      <tr><td>places read so far</td><td class="n">${{esc(c.places_read||0)}}</td></tr>
      </table>${{c.rivers_available ? "" :
        `<p class="lede" style="margin:8px 0 0">River questions need the live gauge list,
         which is unavailable — trends, silences and council decisions are unaffected.</p>`}}</div>`;

    if ((d.places||[]).length) {{
      h += `<div class="card"><h3 style="margin:0 0 6px;font-size:11px;color:#6d7a86;
            text-transform:uppercase;letter-spacing:.06em">Read this next</h3>
            <p class="lede" style="margin:0 0 10px">Ranked by what it opens, not by size or
            alphabet. A document sitting on several near-answerable questions beats one
            sitting on a single distant one.</p>`;
      d.places.forEach(p => {{
        h += `<div style="margin:0 0 10px;padding-left:11px;border-left:2px solid var(--gt-hit)">
          <div style="font-size:13px"><strong>${{esc(p.place)}}</strong>
            <span style="opacity:.6;font-size:11px">score ${{esc(p.score)}} ·
            unlocks ${{esc(p.unlocks_now)}} question${{p.unlocks_now===1?"":"s"}} immediately</span></div>`;
        (p.questions||[]).forEach(q => {{
          h += `<div class="lede" style="margin:2px 0 0;font-size:11.5px">${{esc(q)}}</div>`;
        }});
        h += `</div>`;
      }});
      h += `</div>`;
    }}

    if ((d.answerable||[]).length) {{
      h += `<div class="card"><h3 style="margin:0 0 6px;font-size:11px;color:#6d7a86;
            text-transform:uppercase;letter-spacing:.06em">Already answerable</h3>`;
      d.answerable.forEach(q => {{
        h += `<div style="font-size:12px;margin:0 0 4px">${{esc(q.question)}}
              <span style="opacity:.55;font-size:11px">— ${{esc(q.detail)}}</span></div>`;
      }});
      h += `</div>`;
    }}

    h += `<div class="card"><h3 style="margin:0 0 6px;font-size:11px;color:#6d7a86;
          text-transform:uppercase;letter-spacing:.06em">Waiting</h3>`;
    (d.waiting||[]).slice(0,25).forEach(q => {{
      h += `<div style="font-size:12px;margin:0 0 4px">${{esc(q.question)}}
            <span style="opacity:.55;font-size:11px">— ${{esc(q.distance)}} document${{
              q.distance===1?"":"s"}} away</span></div>`;
    }});
    h += `</div>`;
    el.innerHTML = h;
  }},

  decisions: async () => {{
    const el = document.getElementById("decisions-body");
    const run = async () => {{
      const id = document.getElementById("dec-id").value.trim();
      if (!id) return;
      el.innerHTML = `<div class="card note" style="border:0">Reading every page of
        ${{esc(id)}} for motions and recorded votes…</div>`;
      const d = await postJson("/api/decisions", {{identifier: id}});
      if (d.error) {{ el.innerHTML = `<div class="card note" style="border:0">${{esc(d.error)}}</div>`; return; }}

      const o = d.outcomes || {{}};
      let h = `<div class="card"><table class="gt">
        <tr><th>found</th><th class="n">n</th></tr>
        <tr><td>motions and recorded divisions</td><td class="n">${{esc(d.motions||0)}}</td></tr>
        <tr><td>people named</td><td class="n">${{esc(d.people||0)}}</td></tr>
        <tr><td>recorded votes</td><td class="n">${{esc(d.recorded_votes||0)}}</td></tr>
        <tr><td>rolls that do not match the clerk's tally</td><td class="n">${{esc(d.rolls_that_do_not_reconcile||0)}}</td></tr>
        </table>
        <p class="lede" style="margin:8px 0 0">${{
          Object.entries(o).map(([k,v]) => `${{esc(v)}} ${{esc(k)}}`).join(" · ")}}</p></div>`;

      if ((d.divided||[]).length) {{
        h += `<div class="card"><h3 style="margin:0 0 8px;font-size:11px;color:#6d7a86;
              text-transform:uppercase;letter-spacing:.06em">Where they disagreed</h3>`;
        d.divided.forEach(x => {{
          const decisionPage = safeHttpUrl(x.page_url);
          h += `<div style="margin:0 0 10px;padding-left:11px;border-left:2px solid rgba(255,255,255,.14)">
            <div style="font-size:12px">${{esc(x.text||"")}}</div>
            <div class="lede" style="margin:3px 0 0;font-size:11px">
              ${{esc(x.outcome)}} · against: ${{esc((x.against||[]).join(", ") || "—")}}
              ${{decisionPage ? ` · <a href="${{decisionPage}}" target="_blank" rel="noopener">the page</a>` : ""}}
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
          h += `<tr><td>${{esc(p.name)}}</td><td>${{esc((p.roles||[])[0]||"")}}</td>
                <td class="n">${{esc(p.moved||0)}}</td><td class="n">${{esc(p.seconded||0)}}</td>
                <td class="n">${{esc(v.yea||0)}}</td><td class="n">${{esc(v.nay||0)}}</td></tr>`;
        }});
        h += `</table></div>`;
      }}

      if ((d.dissenters||[]).length) {{
        h += `<div class="card"><h3 style="margin:0 0 6px;font-size:11px;color:#6d7a86;
              text-transform:uppercase;letter-spacing:.06em">Dissent</h3>
              <p class="lede" style="margin:0 0 6px">Most recorded votes are unanimous, so a
              nay is the rarest and most informative thing in the record.</p>`;
        d.dissenters.forEach(x => {{
          h += `<div style="font-size:12px">${{esc(x.person)}} — ${{esc(x.nays)}} against, ${{esc(x.yeas)}} for</div>`;
        }});
        h += `</div>`;
      }}

      (d.not_measured||[]).forEach(n => {{
        h += `<div class="card note" style="border:0;padding-left:11px">${{esc(n)}}</div>`;
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
      const submission = {{
        identifier: v("sb-id"), page: v("sb-page"), parameter: v("sb-param"),
        value: v("sb-value"), unit: v("sb-unit"), place: v("sb-place"),
        facility: v("sb-facility"), period: v("sb-period"), quote: v("sb-quote"),
      }};
      const d = await postJson("/api/submit", submission);
      out.innerHTML = (d.accepted
          ? `<strong style="color:#36e0c8">In the record.</strong> `
          : `<strong style="color:#f0a24a">Not in the record.</strong> `)
        + esc(d.what_happens_now);
      if (d.accepted) LOADERS.disputed();
    }};
    el.innerHTML = `<div class="card note" style="border:0">Checking every claim against the
      scans it cites…</div>`;
    const d = await postJson("/api/ledger", {{}});
    if (d.error) {{ el.innerHTML = `<div class="card note" style="border:0">${{
      esc(d.error)}}</div>`; return; }}

    let h = `<div class="card"><table class="gt">
      <tr><th>state</th><th class="n">claims</th><th>what it means</th></tr>
      <tr><td>settled</td><td class="n">${{esc(d.settled||0)}}</td><td>one claim survives its cited-page evidence check</td></tr>
      <tr><td>contested</td><td class="n">${{esc(d.contested||0)}}</td><td>two source-backed readings disagree — shown, not chosen between</td></tr>
      <tr><td>unsupported</td><td class="n">${{esc(d.unsupported||0)}}</td><td>no claim survives the available cited-page evidence check</td></tr>
      <tr><td>flags raised</td><td class="n">${{esc(d.flags||0)}}</td><td>counted, shown, and inert by design</td></tr>
      </table></div>`;

    (d.contested_detail || []).forEach(slot => {{
      const parts = String(slot.slot || "").split("|");
      const title = parts.filter(Boolean).join(" · ") || "(unnamed)";
      h += `<div class="card"><h3 style="margin:0 0 4px;font-size:12px">${{esc(title)}}</h3>`;
      h += `<p class="lede" style="margin:0 0 10px">${{esc(
        slot.same_sentence
          ? "One sentence, read two ways. The document itself is ambiguous here."
          : "Two different sentences are being cited. They may not be about the same thing."
      )}}${{slot.n_flags ? ` · ${{esc(slot.n_flags)}} reader flag(s)` : ""}}</p>`;
      h += `<div style="display:flex;gap:14px;flex-wrap:wrap">`;
      (slot.readings || []).forEach(r => {{
        const pageUrl = safeHttpUrl(r.page_url);
        const cropUrl = safeHttpUrl(r.crop_url);
        h += `<div style="flex:1 1 280px;min-width:260px;border:1px solid rgba(255,255,255,.09);
              border-radius:10px;padding:10px">
          <div style="font-size:20px;font-weight:600">${{esc(r.value)}} <span
              style="font-size:12px;opacity:.6">${{esc(r.unit||"")}}</span></div>
          <div style="font-size:11px;opacity:.6;margin:2px 0 8px">${{esc(r.contributor||"extraction")}}</div>`;
        if (cropUrl) {{
          h += (pageUrl ? `<a href="${{pageUrl}}" target="_blank" rel="noopener">` : `<div>`)
            + `<img src="${{cropUrl}}" alt="the sentence this number was read from"
                     loading="lazy" style="width:100%;border-radius:6px;background:#f6f1e4">`
            + (pageUrl ? `</a>` : `</div>`);
        }}
        h += `<div class="lede" style="margin:8px 0 0;font-size:11px">“${{esc(
              r.quote||"")}}”</div>
          <button type="button" data-claim="${{esc(r.claim_id)}}" class="flag-btn"
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
      h += `<div class="card note" style="border:0;padding-left:11px">${{esc(n)}}</div>`;
    }});
    el.innerHTML = h;

    el.querySelectorAll(".flag-btn").forEach(b => b.onclick = async () => {{
      const reason = prompt("What looks wrong about it?") || "";
      if (reason.length > 400) {{
        alert("Please keep the reason to 400 characters or fewer.");
        return;
      }}
      const d = await postJson("/api/flag", {{claim: b.dataset.claim, reason}});
      if (d.error) {{
        b.textContent = "Could not flag: " + d.error;
        return;
      }}
      b.textContent = "Flagged — the record is unchanged";
      b.disabled = true;
      b.style.opacity = ".6";
    }});
  }}
}};

/* LOADERS is deliberately complete before optional map startup. Even a
   synchronous DOM/CSP failure in the map loader therefore cannot strand the
   locally backed views. */
try {{
  loadMapLibrary();
}} catch (err) {{
  console.error("map library load unavailable:", err);
  showMapMessage("The map library could not be loaded from the network.<br>"
    + "Every other view works from local data.", "unavailable");
}}
</script></body></html>"""
