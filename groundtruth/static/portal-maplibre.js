// portal-maplibre.js
// ────────────────────────────────────────────────────────────────────────────
// MapLibre GL JS v5 renderer (work-in-progress), behind a toggle. Self-
// contained: it reads the portal's station GeoJSON and the current Leaflet
// view from window.state and makes NO edits to the big portal.js. It is the
// home for the modern 3D map: a GPU globe projection with exaggerated terrain,
// hillshade relief, and an atmospheric sky -- the "advanced MapLibre features"
// the flat/aging globe-canvas never had.
//
// Toggle button (#map-gl-toggle) shows/hides the MapLibre map overlaying the
// Leaflet stage; #map-gl-style cycles satellite/vector basemaps; a projection
// button flips globe<->flat. Console/Honu hook: window.omegaMapLibre.
(function () {
  "use strict";

  const GL = window.maplibregl;
  const $ = (id) => document.getElementById(id);

  // Master switch for the work-in-progress GPU renderer. While true, the map
  // shows a "Work in Progress" toggle so the renderer + its 3D/globe features
  // can be previewed as they're built. Flip to false and the toggle disappears
  // entirely -- the renderer ships hidden until it's ready for operators.
  // The MapLibre globe is now the portal's 3D view, driven by the normal 2D/3D
  // view toggle (setMapView in portal.js) -- NOT a "Work in Progress" button.
  // Flip this true only to expose the standalone preview toggle again.
  const MAPLIBRE_WIP = false;
  const WIP_LABEL = "Work in Progress";

  if (!GL) {
    // Library blocked (offline / CSP). Don't leave a dead button on screen.
    const btn = $("map-gl-toggle");
    const styleBtn = $("map-gl-style");
    if (btn) btn.hidden = true;
    if (styleBtn) styleBtn.hidden = true;
    console.warn("[maplibre] maplibre-gl not available — WIP toggle hidden");
    return;
  }

  const SAT_TILES =
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
  // Free, no-API-key vector basemap (OpenFreeMap).
  const VECTOR_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";
  // Free, no-API-key terrain DEM (AWS open elevation tiles, terrarium encoding).
  const DEM_TILES =
    "https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png";
  const STATIONS_URL = "/v1/map/stations.geojson";

  // Sky/atmosphere shared by every style so the globe reads as a planet, not a
  // flat plane. Tuned for the portal's dark ocean palette.
  const SKY = {
    "sky-color": "#0a2a55",
    "sky-horizon-blend": 0.5,
    "horizon-color": "#5a8fc0",
    "horizon-fog-blend": 0.6,
    "fog-color": "#cfe3f2",
    "fog-ground-blend": 0.5,
    "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 10, 0],
  };

  // GPU-composited Esri World Imagery raster on a globe, with a terrain DEM
  // source + hillshade relief baked in. Terrain itself is engaged on load
  // (setTerrain) once the style is live.
  function satelliteStyle(globe) {
    return {
      version: 8,
      projection: { type: globe ? "globe" : "mercator" },
      sources: {
        esriSat: {
          type: "raster",
          tiles: [SAT_TILES],
          tileSize: 256,
          maxzoom: 19,
          attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics",
        },
        demTerrain: {
          type: "raster-dem",
          tiles: [DEM_TILES],
          encoding: "terrarium",
          tileSize: 256,
          maxzoom: 15,
          attribution: "Elevation &copy; Mapzen / AWS Terrain Tiles",
        },
      },
      layers: [
        { id: "bg", type: "background", paint: { "background-color": "#04080d" } },
        { id: "esriSat", type: "raster", source: "esriSat" },
        {
          id: "hillshade",
          type: "hillshade",
          source: "demTerrain",
          paint: { "hillshade-exaggeration": 0.4, "hillshade-shadow-color": "#0a1622" },
        },
      ],
      sky: SKY,
      light: { anchor: "viewport", intensity: 0.4 },
    };
  }

  // Default to a FLAT (mercator) preview so toggling the WIP renderer does not
  // surprise the operator by replacing the 2D map with a globe. Globe is opt-in
  // via the projection button (and the dedicated Cesium twin is where the real
  // 3D globe lives).
  const gl = { map: null, active: false, style: "satellite", globe: false, stations: null };

  function leafletMap() {
    return (window.state && window.state.map) || window.__omegaMap || null;
  }

  function leafletView() {
    const lm = leafletMap();
    try {
      if (lm && typeof lm.getCenter === "function") {
        const c = lm.getCenter();
        return { lng: c.lng, lat: c.lat, zoom: lm.getZoom() };
      }
    } catch (_e) {}
    // Global-neutral fallback (worldwide project; never region-scope) -- matches
    // portal.js MAP_INITIAL_CENTER [lat 20, lng -30].
    return { lng: -30, lat: 20, zoom: 2 };
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
    );
  }

  async function fetchStations() {
    try {
      const scope =
        (window.state && typeof window.state.dataScope === "string" && window.state.dataScope) || "real";
      const res = await fetch(`${STATIONS_URL}?data_scope=${encodeURIComponent(scope)}`, {
        headers: { Accept: "application/json" },
      });
      if (!res.ok) return null;
      const geo = await res.json();
      return geo && geo.type === "FeatureCollection" ? geo : null;
    } catch (_e) {
      return null;
    }
  }

  // Engage exaggerated 3D terrain + ensure the DEM source/hillshade exist on the
  // current style. Wrapped so a missing DEM tile server gracefully degrades to a
  // flat (but still globe-projected) map instead of throwing.
  function applyTerrain(map) {
    try {
      if (!map.getSource("demTerrain")) {
        map.addSource("demTerrain", {
          type: "raster-dem",
          tiles: [DEM_TILES],
          encoding: "terrarium",
          tileSize: 256,
          maxzoom: 15,
        });
      }
      map.setTerrain({ source: "demTerrain", exaggeration: 1.35 });
      try {
        map.setSky(SKY);
      } catch (_e) {}
    } catch (error) {
      console.warn("[maplibre] terrain unavailable, staying flat", error);
    }
  }

  function addStationLayer(map) {
    if (!gl.stations) return;
    const existing = map.getSource("omega-stations");
    if (existing) {
      existing.setData(gl.stations);
      return;
    }
    map.addSource("omega-stations", { type: "geojson", data: gl.stations });
    map.addLayer({
      id: "omega-stations-halo",
      type: "circle",
      source: "omega-stations",
      paint: { "circle-radius": 11, "circle-color": "#36e0c8", "circle-opacity": 0.16 },
    });
    map.addLayer({
      id: "omega-stations-dot",
      type: "circle",
      source: "omega-stations",
      paint: {
        "circle-radius": 5,
        "circle-color": "#36e0c8",
        "circle-stroke-width": 1.5,
        "circle-stroke-color": "#06121a",
      },
    });
    map.on("click", "omega-stations-dot", (event) => {
      const feature = event.features && event.features[0];
      if (!feature) return;
      const props = feature.properties || {};
      const name = props.name || props.device_id || props.node_id || "Station";
      const sub = [props.source, props.kind].filter(Boolean).join(" · ");
      new GL.Popup({ closeButton: true, maxWidth: "240px" })
        .setLngLat(event.lngLat)
        .setHTML(
          `<strong>${escapeHtml(name)}</strong>${
            sub ? `<br><span style="opacity:.7">${escapeHtml(sub)}</span>` : ""
          }`
        )
        .addTo(map);
    });
    map.on("mouseenter", "omega-stations-dot", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "omega-stations-dot", () => {
      map.getCanvas().style.cursor = "";
    });
  }

  // Re-apply everything that doesn't survive a setStyle: terrain, sky, stations.
  function decorate(map) {
    applyTerrain(map);
    addStationLayer(map);
  }

  async function ensureMap() {
    if (gl.map) return gl.map;
    const host = $("map-gl");
    if (!host) return null;
    const view = leafletView();
    const map = new GL.Map({
      container: host,
      style: satelliteStyle(gl.globe),
      center: [view.lng, view.lat],
      zoom: view.zoom,
      pitch: 0,
      attributionControl: { compact: true },
      // MapLibre is DPI-aware + GPU-rendered by default — no detectRetina hacks.
    });
    map.addControl(new GL.NavigationControl({ visualizePitch: true, showCompass: true }), "top-left");
    if (typeof GL.GlobeControl === "function") {
      map.addControl(new GL.GlobeControl(), "top-left");
    }
    map.addControl(new GL.TerrainControl({ source: "demTerrain", exaggeration: 1.35 }), "top-left");
    map.addControl(new GL.ScaleControl({ maxWidth: 120, unit: "metric" }), "bottom-left");
    gl.stations = gl.stations || (await fetchStations());
    map.on("style.load", () => decorate(map));
    map.on("load", () => decorate(map));
    gl.map = map;
    return map;
  }

  function applyStyle(which) {
    if (!gl.map) return;
    gl.style = which === "vector" ? "vector" : "satellite";
    const view = {
      center: gl.map.getCenter(),
      zoom: gl.map.getZoom(),
      bearing: gl.map.getBearing(),
      pitch: gl.map.getPitch(),
    };
    if (gl.style === "vector") {
      gl.map.setStyle(VECTOR_STYLE_URL);
      gl.map.once("styledata", () => {
        try {
          gl.map.setProjection({ type: gl.globe ? "globe" : "mercator" });
        } catch (_e) {}
        gl.map.jumpTo(view);
        decorate(gl.map);
      });
    } else {
      gl.map.setStyle(satelliteStyle(gl.globe));
      gl.map.once("styledata", () => {
        gl.map.jumpTo(view);
        decorate(gl.map);
      });
    }
    const styleBtn = $("map-gl-style");
    if (styleBtn) styleBtn.textContent = gl.style === "vector" ? "Vector" : "Satellite";
  }

  function setProjection(globe) {
    gl.globe = globe === undefined ? !gl.globe : !!globe;
    if (!gl.map) return;
    try {
      gl.map.setProjection({ type: gl.globe ? "globe" : "mercator" });
      gl.map.easeTo({ pitch: 0, duration: 600 });
    } catch (error) {
      console.warn("[maplibre] projection switch failed", error);
    }
    const projBtn = $("map-gl-projection");
    // Action label: shows what a click switches TO (flat now -> offer "Globe").
    if (projBtn) projBtn.textContent = gl.globe ? "Flat" : "Globe";
  }

  async function setActive(on) {
    const host = $("map-gl");
    const btn = $("map-gl-toggle");
    const styleBtn = $("map-gl-style");
    const projBtn = $("map-gl-projection");
    if (!host) return;
    gl.active = on === undefined ? !gl.active : !!on;
    if (gl.active) {
      host.hidden = false;
      const map = await ensureMap();
      if (!map) {
        gl.active = false;
        host.hidden = true;
        return;
      }
      const view = leafletView();
      map.jumpTo({ center: [view.lng, view.lat], zoom: view.zoom });
      // Container just became visible — size the GL canvas to it.
      requestAnimationFrame(() => map.resize());
      window.setTimeout(() => map.resize(), 250);
    } else {
      // Carry the GL view back to Leaflet so flipping renderers is seamless.
      const lm = leafletMap();
      if (gl.map && lm && typeof lm.setView === "function") {
        try {
          const c = gl.map.getCenter();
          lm.setView([c.lat, c.lng], Math.round(gl.map.getZoom()), { animate: false });
        } catch (_e) {}
      }
      host.hidden = true;
    }
    if (btn) {
      btn.textContent = gl.active ? "Leaflet map" : WIP_LABEL;
      btn.classList.toggle("is-active", gl.active);
      btn.setAttribute("aria-pressed", gl.active ? "true" : "false");
    }
    if (styleBtn) styleBtn.hidden = !gl.active;
    if (projBtn) projBtn.hidden = !gl.active;
  }

  // ── Globe view entry/exit, driven by the portal's 2D/3D toggle ──────────
  // enterGlobeView shows the GPU globe centered on `center` ({lng,lat,zoom});
  // exitGlobeView returns to the 2D Leaflet map. These are what setMapView()
  // calls so the 3D map is a first-class view, not a hidden preview.
  async function enterGlobeView(center) {
    gl.globe = true;
    await setActive(true);
    if (!gl.map) return;
    setProjection(true);
    const c = center || {};
    const lng = Number.isFinite(c.lng) ? c.lng : gl.map.getCenter().lng;
    const lat = Number.isFinite(c.lat) ? c.lat : gl.map.getCenter().lat;
    const zoom = Number.isFinite(c.zoom) ? c.zoom : 3.4;
    try {
      gl.map.flyTo({ center: [lng, lat], zoom, pitch: 0, duration: 900, essential: true });
    } catch (_e) {}
  }

  function exitGlobeView() {
    return setActive(false);
  }

  function init() {
    const btn = $("map-gl-toggle");
    const styleBtn = $("map-gl-style");
    const projBtn = $("map-gl-projection");
    // Only the standalone WIP preview button is gated by MAPLIBRE_WIP. The
    // renderer + API are always wired so the 2D/3D view toggle can drive the
    // globe.
    if (btn) {
      if (MAPLIBRE_WIP) {
        btn.hidden = false;
        btn.textContent = WIP_LABEL;
        btn.title = "Preview the work-in-progress MapLibre GL renderer";
        btn.addEventListener("click", () => {
          setActive().catch((error) => console.warn("[maplibre] toggle failed", error));
        });
      } else {
        btn.hidden = true;
      }
    }
    if (styleBtn) {
      styleBtn.addEventListener("click", () => applyStyle(gl.style === "vector" ? "satellite" : "vector"));
    }
    if (projBtn) {
      projBtn.addEventListener("click", () => setProjection());
    }
    // Console / Honu hook + the entry points setMapView() uses.
    window.omegaMapLibre = {
      toggle: setActive,
      setStyle: applyStyle,
      setProjection,
      enterGlobeView,
      exitGlobeView,
      map: () => gl.map,
      isActive: () => gl.active,
      refreshStations: async () => {
        gl.stations = await fetchStations();
        if (gl.map) addStationLayer(gl.map);
      },
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
