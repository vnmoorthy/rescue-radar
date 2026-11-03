// Live City: poll a real city's public-safety open-data feeds and show events as they happen.
// San Francisco for now: DataSF publishes dispatched 911 calls (CAD) with CORS enabled, so this view
// works in the static GitHub Pages demo with no backend and no API key. These are structured dispatch
// records already triaged by human call-takers — the live situational layer next to Rescue Radar's
// social-post queue; classifying live *social* posts needs server-side ingestion (see How it works).
import { esc, txt, fmtInt, toast, errMessage, reducedMotion } from '../ui.js';

// Same keyless basemap as the replay view (CARTO's free tiles now demand a key; see views/replay.js).
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas';
const BASEMAP = {
  dark: [`${ESRI}/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`, `${ESRI}/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`],
  light: [`${ESRI}/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`, `${ESRI}/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`],
  opts: { maxNativeZoom: 16, maxZoom: 18 },
  attr: 'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, HERE, Garmin, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, and the GIS user community',
};

// DataSF timestamps are naive local San Francisco time. Interpret them in America/Los_Angeles
// (two-pass offset lookup so DST transitions land on the right side).
const PT = 'America/Los_Angeles';
const ptFmt = new Intl.DateTimeFormat('en-US', {
  timeZone: PT, year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
});
function ptParts(ms) {
  const p = {};
  for (const { type, value } of ptFmt.formatToParts(ms)) p[type] = value;
  return Date.UTC(+p.year, +p.month - 1, +p.day, p.hour === '24' ? 0 : +p.hour, +p.minute, +p.second);
}
function fromPT(iso) {
  if (!iso) return null;
  const t = Date.parse(`${iso}Z`);
  if (!isFinite(t)) return null;
  let ms = t - (ptParts(t) - t);
  ms = t - (ptParts(ms) - ms);
  return ms;
}
function ptNowISO(backMs = 0) {
  // Naive PT timestamp string for SoQL $where clauses.
  const ms = ptParts(Date.now() - backMs);
  return new Date(ms).toISOString().slice(0, 19);
}
function ago(ms) {
  if (ms == null) return 'n/a';
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 90) return `${Math.round(s)} s ago`;
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 129600) return `${(s / 3600).toFixed(1)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}
const tfPT = new Intl.DateTimeFormat(undefined, { timeZone: PT, hour: '2-digit', minute: '2-digit' });
const dfPT = new Intl.DateTimeFormat(undefined, { timeZone: PT, month: 'short', day: 'numeric' });

// ---------- feed adapters: each returns normalized events ----------
// { id, kind, ts (ms), type, priority ('crit'|'med'|'low'), agency, place, neighborhood, lat, lng,
//   active, onscene, sensitive, raw }
const soql = (base, params) => `${base}?${Object.entries(params).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&')}`;

async function fetchJSON(url) {
  const r = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!r.ok) throw new Error(`HTTP ${r.status} from ${new URL(url).host}`);
  return r.json();
}

async function sfPolice(windowMs) {
  // Law Enforcement Dispatched Calls for Service: Real-Time (refreshed every ~10 min).
  // https://data.sf.gov/d/gnap-fj3t
  const rows = await fetchJSON(soql('https://data.sf.gov/resource/gnap-fj3t.json', {
    $where: `received_datetime > '${ptNowISO(windowMs)}'`,
    $order: 'received_datetime DESC',
    $limit: '1500',
  }));
  const seen = new Set();
  const out = [];
  for (const r of rows) {
    const id = r.cad_number || r.id;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const pr = r.priority_final || r.priority_original || '';
    const pt = r.intersection_point && r.intersection_point.coordinates;
    out.push({
      id: `pd-${id}`, kind: 'police', ts: fromPT(r.received_datetime),
      type: r.call_type_final_desc || r.call_type_original_desc || 'Unknown call',
      priority: pr === 'A' ? 'crit' : pr === 'B' ? 'med' : 'low', priRaw: pr,
      agency: r.agency || 'Police',
      place: r.intersection_name || null, neighborhood: r.analysis_neighborhood || null,
      lat: pt ? pt[1] : null, lng: pt ? pt[0] : null,
      active: !r.close_datetime, onscene: !!r.onscene_datetime,
      sensitive: r.sensitive_call === true,
      asOf: fromPT(r.data_as_of),
    });
  }
  return out;
}

async function sfFire(windowMs) {
  // Fire Department and Emergency Medical Services Dispatched Calls for Service (refreshed daily,
  // so it trails the police feed; one row per dispatched unit — collapse to one event per call).
  // https://data.sf.gov/d/nuek-vuh3
  const rows = await fetchJSON(soql('https://data.sf.gov/resource/nuek-vuh3.json', {
    $where: `received_dttm > '${ptNowISO(windowMs)}'`,
    $order: 'received_dttm DESC',
    $limit: '1500',
  }));
  const byCall = new Map();
  for (const r of rows) {
    const id = r.call_number;
    if (!id) continue;
    const prev = byCall.get(id);
    if (prev) { prev.units += 1; continue; }
    const pr = r.final_priority || r.priority || r.original_priority || '';
    const pt = r.case_location && r.case_location.coordinates;
    byCall.set(id, {
      id: `fd-${id}`, kind: 'fire', ts: fromPT(r.received_dttm),
      type: r.call_type || 'Unknown call',
      // SFFD priorities: 3/E = emergency (lights and sirens), 2 = non-emergency.
      priority: pr === '3' || pr === 'E' ? 'crit' : 'med', priRaw: pr,
      agency: r.unit_type === 'MEDIC' || r.unit_type === 'PRIVATE' ? 'EMS' : 'Fire',
      place: r.address || null, neighborhood: r.neighborhoods_analysis_boundaries || null,
      lat: pt ? pt[1] : null, lng: pt ? pt[0] : null,
      active: !r.call_final_disposition, onscene: false, sensitive: false,
      asOf: fromPT(r.data_as_of), units: 1,
    });
  }
  return Array.from(byCall.values());
}

const CITIES = [{
  id: 'sf', name: 'San Francisco', center: [37.7749, -122.4194], zoom: 13,
  feeds: [
    { id: 'police', label: 'Police & Sheriff', fetch: sfPolice, pollMs: 120000, on: true,
      note: 'DataSF law-enforcement dispatched calls, real-time dataset (city refreshes it every ~10 min)' },
    { id: 'fire', label: 'Fire & EMS', fetch: sfFire, pollMs: 900000, on: true,
      note: 'DataSF fire/EMS dispatched calls (the city refreshes this one daily, so it trails)' },
  ],
}];
const WINDOWS = [{ h: 2, label: '2 h' }, { h: 6, label: '6 h' }, { h: 24, label: '24 h' }];

export function createLive(root, ctx) {
  const S = {
    city: CITIES[0], windowH: 6, events: new Map(), timers: [], activeView: false,
    map: null, layer: null, renderer: null, markers: new Map(), filter: 'all',
    lastFetch: {}, feedErr: {}, firstLoad: true, social: null, socialErr: null,
  };
  const feedOn = Object.fromEntries(S.city.feeds.map(f => [f.id, f.on]));

  root.innerHTML = `
  <div class="live">
    <div class="panel transport">
      <div class="events" role="group" aria-label="City">
        ${CITIES.map(c => `<button type="button" class="event-btn" data-city="${esc(c.id)}" aria-pressed="true">
          <span class="event-btn__name">${esc(c.name)}</span>
          <span class="event-btn__meta">911 dispatch · open data</span></button>`).join('')}
        <span class="muted lv-more">more cities soon</span>
      </div>
      <div class="transport__sep" aria-hidden="true"></div>
      <div class="transport__group" role="group" aria-label="Sources">
        ${S.city.feeds.map(f => `<label class="switch" title="${esc(f.note)}"><input type="checkbox" data-feed="${esc(f.id)}" ${feedOn[f.id] ? 'checked' : ''}><span class="switch__track"></span>${esc(f.label)}</label>`).join('')}
      </div>
      <div class="seg" role="group" aria-label="Time window">
        ${WINDOWS.map(w => `<button type="button" data-window="${w.h}" aria-pressed="${w.h === S.windowH}">${w.label}</button>`).join('')}
      </div>
      <button type="button" class="btn" id="lv-refresh">${refreshIcon()}<span>Refresh</span></button>
      <span class="muted" id="lv-status">loading…</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="kpi__label">Calls in window</div><div class="kpi__value" id="lv-n">0</div><div class="kpi__sub" id="lv-n-sub">&nbsp;</div></div>
      <div class="kpi kpi--crit"><div class="kpi__label">Emergency priority</div><div class="kpi__value" id="lv-crit">0</div><div class="kpi__sub">priority A (police) · code 3 (fire/EMS)</div></div>
      <div class="kpi"><div class="kpi__label">Still open</div><div class="kpi__value" id="lv-open">0</div><div class="kpi__sub">no close time in the feed yet</div></div>
      <div class="kpi"><div class="kpi__label">Newest event</div><div class="kpi__value" id="lv-fresh">n/a</div><div class="kpi__sub" id="lv-fresh-sub">the real-time dataset itself lags ~10–45 min</div></div>
    </div>
    <div class="replay-grid">
      <section class="panel p-map" aria-label="Map">
        <div class="panel__head"><h2 class="panel__title">Map</h2><span class="panel__meta" id="lv-map-meta">0 placed</span></div>
        <div class="map-wrap"><div id="lv-map"></div>
          <div class="map-legend" aria-hidden="true"><span><i class="lg-crit"></i>Emergency priority</span><span><i class="lg-other"></i>Other calls</span></div>
        </div>
      </section>
      <section class="panel p-feed" aria-label="Live dispatch feed">
        <div class="panel__head"><h2 class="panel__title">Dispatch feed</h2><span class="panel__meta" id="lv-feed-meta">&nbsp;</span></div>
        <div class="queue-filters" role="group" aria-label="Filter feed">
          ${[['all', 'All'], ['crit', 'Emergency'], ['active', 'Open'], ['police', 'Police'], ['fire', 'Fire/EMS']]
            .map(([k, l]) => `<button type="button" class="qf" data-lvf="${k}" aria-pressed="${k === 'all'}">${l} <span data-lvc="${k}">0</span></button>`).join('')}
        </div>
        <div class="feed" id="lv-feed" tabindex="0" aria-label="Dispatched calls, newest first"><div class="feed__empty"><span class="spinner"></span> Contacting the city feeds…</div></div>
      </section>
      <section class="panel p-queue" aria-label="What is happening">
        <div class="panel__head"><h2 class="panel__title">Right now</h2><span class="panel__meta" id="lv-brk-meta">&nbsp;</span></div>
        <div class="panel__body" id="lv-breakdown"></div>
        <div class="panel__head panel__head--sub"><h2 class="panel__title">Social &amp; news</h2><span class="panel__meta" id="lv-soc-meta">&nbsp;</span></div>
        <div class="feed lv-social" id="lv-social" tabindex="0" aria-label="Live social and news items classified by Rescue Radar, newest first"></div>
        <div class="panel__body lv-note" id="lv-soc-note"></div>
      </section>
    </div>
  </div>`;

  const $ = s => root.querySelector(s);
  const el = {
    status: $('#lv-status'), n: $('#lv-n'), nSub: $('#lv-n-sub'), crit: $('#lv-crit'), open: $('#lv-open'),
    fresh: $('#lv-fresh'), freshSub: $('#lv-fresh-sub'), feed: $('#lv-feed'), feedMeta: $('#lv-feed-meta'),
    mapMeta: $('#lv-map-meta'), breakdown: $('#lv-breakdown'), brkMeta: $('#lv-brk-meta'), refresh: $('#lv-refresh'),
    social: $('#lv-social'), socMeta: $('#lv-soc-meta'), socNote: $('#lv-soc-note'),
  };

  // ---------- map ----------
  function ensureMap() {
    if (S.map || !window.L) {
      if (!window.L && !root.querySelector('.map-fallback')) {
        root.querySelector('.map-wrap').insertAdjacentHTML('beforeend', '<div class="map-fallback">Map library unavailable (offline?). The feed keeps working.</div>');
      }
      return;
    }
    const L = window.L;
    S.renderer = L.canvas({ padding: 0.4 });
    S.map = L.map('lv-map', { zoomControl: true, attributionControl: true, preferCanvas: true, renderer: S.renderer });
    const theme = ctx.theme();
    S.tiles = L.tileLayer(BASEMAP[theme][0], { attribution: BASEMAP.attr, ...BASEMAP.opts }).addTo(S.map);
    const lp = S.map.createPane('lv-labels');
    lp.style.zIndex = 450;
    lp.style.pointerEvents = 'none';
    S.labels = L.tileLayer(BASEMAP[theme][1], { ...BASEMAP.opts, pane: 'lv-labels', opacity: 0.85 }).addTo(S.map);
    S.layer = L.layerGroup().addTo(S.map);
    S.map.setView(S.city.center, S.city.zoom);
    ctx.onTheme(t => {
      if (!S.map) return;
      S.tiles.setUrl(BASEMAP[t][0]);
      S.labels.setUrl(BASEMAP[t][1]);
      repaintMarkers();
    });
  }
  function markerStyle(e) {
    const css = getComputedStyle(document.documentElement);
    const tok = n => css.getPropertyValue(n).trim();
    const crit = e.priority === 'crit';
    const color = crit ? tok('--critical') || '#ff5b3a' : e.kind === 'fire' ? tok('--warn') || '#e8a13a' : tok('--info') || '#5aa7d6';
    return {
      radius: crit ? 6.5 : 4, color, weight: crit ? 1.5 : 1,
      fillColor: color, fillOpacity: e.active ? (crit ? 0.85 : 0.45) : 0.18, opacity: e.active ? (crit ? 1 : 0.65) : 0.3,
    };
  }
  function popupHTML(e) {
    return `<div class="pop__head"><span class="tag ${e.priority === 'crit' ? 'tag--bad' : ''}">${esc(prName(e))}</span>
        <span class="tag">${esc(e.agency)}</span>${e.active ? '<span class="tag tag--warn">open</span>' : '<span class="tag tag--ok">closed</span>'}</div>
      <div class="pop__meta">${esc(when(e))}${e.neighborhood ? ` · ${esc(e.neighborhood)}` : ''}</div>
      <div class="pop__text">${txt(e.type)}${e.place ? ` — ${txt(e.place)}` : ''}${e.units > 1 ? ` · ${fmtInt(e.units)} units` : ''}</div>`;
  }
  function syncMarkers(list) {
    if (!S.map) return;
    const want = new Set();
    let placed = 0;
    for (const e of list) {
      if (e.lat == null) continue;
      want.add(e.id);
      placed += 1;
      let m = S.markers.get(e.id);
      if (!m) {
        m = window.L.circleMarker([e.lat, e.lng], { ...markerStyle(e), renderer: S.renderer });
        m.on('click', () => m.bindPopup(popupHTML(e), { maxWidth: 300 }).openPopup());
        m.addTo(S.layer);
        S.markers.set(e.id, m);
        if (e.priority === 'crit' && !S.firstLoad && !reducedMotion()) {
          const pm = window.L.marker(m.getLatLng(), { icon: window.L.divIcon({ className: 'pulse-icon', html: '<span></span>', iconSize: [0, 0] }), interactive: false, keyboard: false }).addTo(S.map);
          setTimeout(() => pm.remove(), 3300);
        }
      } else {
        m.setStyle(markerStyle(e));
      }
      if (e.priority === 'crit') m.bringToFront();
    }
    for (const [id, m] of S.markers) if (!want.has(id)) { m.remove(); S.markers.delete(id); }
    el.mapMeta.textContent = `${fmtInt(placed)} placed`;
  }
  function repaintMarkers() {
    const byId = new Map(visible().map(e => [e.id, e]));
    for (const [id, m] of S.markers) { const e = byId.get(id); if (e) m.setStyle(markerStyle(e)); }
  }

  // ---------- data ----------
  const prName = e => (e.kind === 'police'
    ? (e.priRaw ? `priority ${e.priRaw}` : 'priority n/a')
    : (e.priority === 'crit' ? 'code 3' : `priority ${e.priRaw || 'n/a'}`));
  const when = e => (e.ts == null ? 'n/a' : `${dfPT.format(e.ts)} ${tfPT.format(e.ts)} SF time · ${ago(e.ts)}`);

  function visible() {
    const cut = Date.now() - S.windowH * 3600000;
    const list = [];
    for (const e of S.events.values()) {
      if (!feedOn[e.kind === 'police' ? 'police' : 'fire']) continue;
      if (e.ts == null || e.ts < cut) continue;
      list.push(e);
    }
    list.sort((a, b) => b.ts - a.ts);
    return list;
  }
  const matches = e => S.filter === 'all' || (S.filter === 'crit' && e.priority === 'crit') || (S.filter === 'active' && e.active)
    || (S.filter === 'police' && e.kind === 'police') || (S.filter === 'fire' && e.kind === 'fire');

  async function poll(feed, { announce = false } = {}) {
    try {
      const got = await feed.fetch(S.windowH * 3600000 + 600000);
      for (const e of got) S.events.set(e.id, e);
      S.lastFetch[feed.id] = Date.now();
      delete S.feedErr[feed.id];
      if (announce) toast(`${feed.label}: ${fmtInt(got.length)} calls in the last ${S.windowH} h`, 'ok', { timeout: 2600 });
    } catch (err) {
      S.feedErr[feed.id] = errMessage(err);
      if (announce || S.firstLoad) toast(`${feed.label} feed failed: ${S.feedErr[feed.id]}`, 'error');
    }
    paint();
    S.firstLoad = false;
  }
  function pollAll(opts) { return Promise.all(S.city.feeds.filter(f => feedOn[f.id]).map(f => poll(f, opts))); }

  // ---------- social & news ingest (server-side: rr/ingest.py classifies live posts with the model) ----------
  async function pollSocial() {
    try {
      S.social = await ctx.api.liveSocial();
      S.socialErr = null;
    } catch (err) {
      S.socialErr = errMessage(err);
    }
    paintSocial();
  }
  function socialHTML(it) {
    const crit = !!it.critical;
    const body = it.url
      ? `<a href="${esc(it.url)}" target="_blank" rel="noopener noreferrer">${txt(it.text)}</a>` : txt(it.text);
    const label = it.label
      ? `<span class="tag ${crit ? 'tag--bad' : ''}">${esc(it.label_name || it.label)}</span>`
      : '<span class="tag" title="Waiting for the model">classifying…</span>';
    return `<article class="post${crit ? ' post--crit' : ''}">
      <div class="post__bar"></div>
      <div class="post__body">
        <div class="post__top"><span title="${esc(when({ ts: it.ts }))}">${esc(ago(it.ts))}</span>
          <span class="post__place">${esc(it.feed || it.source || '')}</span>${label}</div>
        <div class="post__text">${body}</div>
        ${it.queued ? '<div class="post__truth"><span class="tag tag--warn">pushed to dispatch queue</span></div>' : ''}
      </div></article>`;
  }
  function paintSocial() {
    if (ctx.api.mode !== 'live') {
      el.social.style.display = 'none';
      el.socMeta.textContent = 'needs the local server';
      el.socNote.innerHTML = 'Live Reddit posts and SF news headlines, classified by the fine-tuned model as they appear, rescue-critical ones pushed to the dispatch queue. The hosted demo cannot run that half of the pipeline: start the local server (<code>python -m rr.server</code>) to see it.';
      return;
    }
    if (S.socialErr && !S.social) {
      el.social.style.display = 'none';
      el.socMeta.textContent = 'unreachable';
      el.socNote.textContent = `Could not read /api/live/social: ${S.socialErr}`;
      return;
    }
    const d = S.social || {};
    if (!d.enabled) {
      el.social.style.display = 'none';
      el.socMeta.textContent = 'off';
      el.socNote.textContent = d.detail || 'The ingest worker is off (RR_INGEST=0).';
      return;
    }
    const items = (d.items || []).slice(0, 80);
    const crit = (d.items || []).filter(x => x.critical).length;
    el.social.style.display = '';
    el.socMeta.textContent = `${fmtInt((d.items || []).length)} items · ${fmtInt(crit)} critical`;
    el.social.innerHTML = items.length ? items.map(socialHTML).join('')
      : '<div class="feed__empty">Nothing ingested yet — the worker polls every couple of minutes.</div>';
    const bits = [];
    for (const s of d.sources || []) {
      if (s.enabled === false) bits.push(`${s.label}: ${s.detail || 'off'}`);
      else if (s.ok === false && s.detail) bits.push(`${s.label}: ${s.detail}`);
    }
    if (d.model_error) bits.push(`model: ${d.model_error} New items stay “classifying…” until it answers.`);
    else if (d.model) bits.push(`classified live by ${d.model}`);
    if (S.socialErr) bits.push(`last poll failed: ${S.socialErr}`);
    el.socNote.textContent = bits.join(' · ');
    el.socNote.style.display = bits.length ? '' : 'none';
  }

  // ---------- paint ----------
  function eventHTML(e) {
    const crit = e.priority === 'crit';
    return `<article class="post${crit ? ' post--crit' : ''}" data-id="${esc(e.id)}">
      <div class="post__bar"></div>
      <div class="post__body">
        <div class="post__top"><span title="${esc(when(e))}">${esc(ago(e.ts))}</span>
          ${e.neighborhood ? `<span class="post__place" title="${esc(e.place || e.neighborhood)}">⌖ ${esc(e.neighborhood)}</span>` : (e.sensitive ? '<span class="post__place muted" title="Sensitive call type: the city publishes it without a location">⌖ withheld</span>' : '')}
          <span class="tag ${crit ? 'tag--bad' : ''}">${esc(prName(e))}</span></div>
        <div class="post__text"><b>${txt(e.type)}</b>${e.place ? ` — ${txt(e.place)}` : ''}</div>
        <div class="post__truth"><span class="tag">${esc(e.agency)}</span>${e.units > 1 ? `<span class="tag">${fmtInt(e.units)} units</span>` : ''}${e.active ? '<span class="tag tag--warn">open</span>' : '<span class="tag tag--ok">closed</span>'}${e.onscene && e.active ? '<span class="tag tag--ok">on scene</span>' : ''}</div>
      </div></article>`;
  }
  function paint() {
    const list = visible();
    const crit = list.filter(e => e.priority === 'crit');
    const open = list.filter(e => e.active);
    el.n.textContent = fmtInt(list.length);
    el.nSub.textContent = `last ${S.windowH} h · ${esc(S.city.name)}`;
    el.crit.textContent = fmtInt(crit.length);
    el.open.textContent = fmtInt(open.length);
    el.fresh.textContent = list.length ? ago(list[0].ts) : 'n/a';

    const counts = { all: list.length, crit: crit.length, active: open.length, police: 0, fire: 0 };
    for (const e of list) counts[e.kind === 'police' ? 'police' : 'fire'] += 1;
    for (const [k, n] of Object.entries(counts)) { const s = root.querySelector(`[data-lvc="${k}"]`); if (s) s.textContent = fmtInt(n); }

    const shown = list.filter(matches).slice(0, 200);
    el.feed.innerHTML = shown.length
      ? shown.map(eventHTML).join('')
      : `<div class="feed__empty">${Object.keys(S.feedErr).length ? 'The city feeds could not be reached.' : S.firstLoad ? '<span class="spinner"></span> Contacting the city feeds…' : 'No calls match this filter in the window.'}</div>`;
    el.feedMeta.textContent = shown.length < list.filter(matches).length ? `newest 200 of ${fmtInt(list.filter(matches).length)}` : `${fmtInt(shown.length)} shown`;

    // breakdown: top call types in the window
    const types = new Map();
    for (const e of list) {
      const t = types.get(e.type) || { n: 0, crit: 0 };
      t.n += 1;
      if (e.priority === 'crit') t.crit += 1;
      types.set(e.type, t);
    }
    const top = Array.from(types.entries()).sort((a, b) => b[1].n - a[1].n).slice(0, 10);
    const max = top.length ? top[0][1].n : 1;
    el.breakdown.innerHTML = top.length ? `<div class="lv-types">${top.map(([name, t]) => `
      <div class="lv-type"><span class="lv-type__name" title="${esc(name)}">${esc(name.toLowerCase())}</span>
        <span class="lv-type__bar"><i style="width:${Math.max(3, Math.round(t.n / max * 100))}%${t.crit ? ';background:var(--critical)' : ''}"></i></span>
        <span class="lv-type__n num">${fmtInt(t.n)}</span></div>`).join('')}</div>` : '<p class="muted">No calls in the window yet.</p>';
    el.brkMeta.textContent = 'top call types in window';

    // status line
    const errs = Object.entries(S.feedErr);
    const fetched = Object.values(S.lastFetch);
    const fireLag = feedOn.fire && !S.feedErr.fire && S.lastFetch.fire && counts.fire === 0
      ? ' · no Fire/EMS rows yet: the city refreshes that dataset daily, so it trails this window' : '';
    el.status.innerHTML = errs.length
      ? `<span class="tag tag--bad">feed error</span> ${esc(errs.map(([k, v]) => `${k}: ${v}`).join(' · '))}`
      : fetched.length ? `updated ${ago(Math.max(...fetched))} · polls every 2 min${esc(fireLag)}` : 'loading…';

    syncMarkers(list);
  }

  // ---------- wiring ----------
  root.querySelectorAll('[data-feed]').forEach(cb => cb.addEventListener('change', () => {
    feedOn[cb.dataset.feed] = cb.checked;
    if (cb.checked && !S.lastFetch[cb.dataset.feed]) poll(S.city.feeds.find(f => f.id === cb.dataset.feed), { announce: true });
    else paint();
  }));
  root.querySelectorAll('[data-window]').forEach(b => b.addEventListener('click', () => {
    S.windowH = Number(b.dataset.window);
    root.querySelectorAll('[data-window]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    pollAll();
    paint();
  }));
  root.querySelectorAll('[data-lvf]').forEach(b => b.addEventListener('click', () => {
    S.filter = b.dataset.lvf;
    root.querySelectorAll('[data-lvf]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    paint();
  }));
  el.refresh.addEventListener('click', () => { el.refresh.disabled = true; pollAll({ announce: true }).finally(() => { el.refresh.disabled = false; }); });
  el.feed.addEventListener('click', ev => {
    const card = ev.target.closest('.post');
    if (!card || !S.map) return;
    const m = S.markers.get(card.dataset.id);
    if (m) { S.map.flyTo(m.getLatLng(), Math.max(S.map.getZoom(), 14), { duration: reducedMotion() ? 0 : 0.8 }); m.openPopup(); }
  });

  function startTimers() {
    stopTimers();
    for (const f of S.city.feeds) {
      S.timers.push(setInterval(() => { if (S.activeView && feedOn[f.id]) poll(f); }, f.pollMs));
    }
    S.timers.push(setInterval(() => { if (S.activeView) paint(); }, 30000)); // keep "ago" labels honest
    S.timers.push(setInterval(() => { if (S.activeView && ctx.api.mode === 'live') pollSocial(); }, 60000));
  }
  function stopTimers() { for (const t of S.timers) clearInterval(t); S.timers = []; }

  return {
    activate() {
      S.activeView = true;
      ensureMap();
      if (S.map) setTimeout(() => S.map.invalidateSize(), 60);
      const stale = !Object.keys(S.lastFetch).length || Math.max(...Object.values(S.lastFetch)) < Date.now() - 120000;
      if (stale) pollAll();
      pollSocial();
      startTimers();
    },
    deactivate() { S.activeView = false; stopTimers(); },
  };
}

function refreshIcon() {
  return '<svg viewBox="0 0 24 24" aria-hidden="true" width="16" height="16" style="fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round"><path d="M20 12a8 8 0 1 1-2.3-5.6M20 3v4h-4"/></svg>';
}
