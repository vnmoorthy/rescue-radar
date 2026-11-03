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
  // The city publishes this extract about 10 minutes after the call states in it ("delayed by an additional
  // 10 minutes"), so data_as_of overstates how long an open call has waited. The newest call_last_updated_at is
  // the moment the data actually describes.
  const touched = rows.map(r => fromPT(r.call_last_updated_at)).filter(Number.isFinite);
  const stateAt = touched.length ? Math.max(...touched) : null;
  const seen = new Set();
  const out = [];
  for (const r of rows) {
    const id = r.cad_number || r.id;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const pr = r.priority_final || r.priority_original || '';
    const pt = r.intersection_point && r.intersection_point.coordinates;
    out.push({
      id: `pd-${id}`, kind: 'police', callNo: String(id), ts: fromPT(r.received_datetime),
      type: r.call_type_final_desc || r.call_type_original_desc || 'Unknown call',
      typeOrig: r.call_type_original_desc || null,
      priority: pr === 'A' ? 'crit' : pr === 'B' ? 'med' : 'low', priRaw: pr, priOrig: r.priority_original || null,
      agency: r.agency || 'Police',
      place: r.intersection_name || null, neighborhood: r.analysis_neighborhood || null,
      district: r.police_district ? `${titleCase(r.police_district)} police district` : null,
      supervisor: supervisorDistrict(r.supervisor_district),
      lat: pt ? pt[1] : null, lng: pt ? pt[0] : null,
      active: !r.close_datetime, onscene: !!r.onscene_datetime,
      times: {
        received: fromPT(r.received_datetime), entry: fromPT(r.entry_datetime), dispatch: fromPT(r.dispatch_datetime),
        enroute: fromPT(r.enroute_datetime), onscene: fromPT(r.onscene_datetime), close: fromPT(r.close_datetime),
      },
      disposition: r.disposition || null, onview: r.onview_flag === 'Y',
      sensitive: r.sensitive_call === true,
      asOf: fromPT(r.data_as_of),
      stateAt: stateAt ?? (fromPT(r.data_as_of) == null ? null : fromPT(r.data_as_of) - 600000),
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
    let c = byCall.get(id);
    if (!c) {
      const pr = r.final_priority || r.priority || r.original_priority || '';
      const pt = r.case_location && r.case_location.coordinates;
      c = {
        id: `fd-${id}`, kind: 'fire', callNo: String(id), ts: fromPT(r.received_dttm),
        type: r.call_type || 'Unknown call', group: r.call_type_group || null,
        // SFFD priorities: 3/E = emergency (lights and sirens), 2 = non-emergency.
        priority: pr === '3' || pr === 'E' ? 'crit' : 'med', priRaw: pr, priOrig: r.original_priority || null,
        agency: 'Fire',
        place: r.address || null, neighborhood: r.neighborhoods_analysis_boundaries || null,
        district: [r.battalion ? `Battalion ${r.battalion}` : null, r.station_area ? `station ${r.station_area}` : null].filter(Boolean).join(' · ') || null,
        supervisor: supervisorDistrict(r.supervisor_district),
        zip: r.zipcode_of_incident ? String(parseInt(r.zipcode_of_incident, 10)) : null,
        lat: pt ? pt[1] : null, lng: pt ? pt[0] : null,
        active: !r.call_final_disposition, onscene: false, sensitive: false,
        times: { received: fromPT(r.received_dttm), entry: fromPT(r.entry_dttm) },
        disposition: r.call_final_disposition || null, alarms: Number(r.number_of_alarms) || null,
        unitList: [], units: 0, asOf: fromPT(r.data_as_of),
      };
      byCall.set(id, c);
    }
    // One row per dispatched unit: the call's timeline is the first unit for each step, the last one to clear.
    c.unitList.push({ id: r.unit_id || '?', type: r.unit_type || '', als: r.als_unit === true });
    c.units = c.unitList.length;
    const first = (k, v) => { const t = fromPT(v); if (t != null && (c.times[k] == null || t < c.times[k])) c.times[k] = t; };
    first('dispatch', r.dispatch_dttm); first('enroute', r.response_dttm); first('onscene', r.on_scene_dttm);
    first('transport', r.transport_dttm); first('hospital', r.hospital_dttm);
    const cleared = fromPT(r.available_dttm);
    if (cleared == null) c.uncleared = (c.uncleared || 0) + 1;
    else if (c.times.close == null || cleared > c.times.close) c.times.close = cleared;
  }
  for (const c of byCall.values()) {
    if (c.uncleared) c.times.close = null; // the daily extract can catch a call before every unit is free again
    c.onscene = c.times.onscene != null;
    const med = c.unitList.some(u => /^(MEDIC|PRIVATE|BLS|RESCUE CAPTAIN)$/.test(u.type));
    const fire = c.unitList.some(u => /^(ENGINE|TRUCK|RESCUE SQUAD|CHIEF|SUPPORT|CP|INVESTIGATION)$/.test(u.type));
    c.agency = med && fire ? 'Fire + EMS' : med ? 'EMS' : 'Fire';
  }
  return Array.from(byCall.values());
}

// Where each event comes from: the city's own published record, linked so anyone can check it.
const SOURCES = {
  police: {
    label: 'SF police 911 dispatch record', dataset: 'Law Enforcement Dispatched Calls for Service: Real-Time',
    page: 'https://data.sf.gov/Public-Safety/Law-Enforcement-Dispatched-Calls-for-Service-Real-/gnap-fj3t',
    record: n => `https://data.sf.gov/resource/gnap-fj3t.json?cad_number=${encodeURIComponent(n)}`,
  },
  fire: {
    label: 'SF fire/EMS 911 dispatch record', dataset: 'Fire Department and Emergency Medical Services Dispatched Calls for Service',
    page: 'https://data.sf.gov/Public-Safety/Fire-Department-and-Emergency-Medical-Services-Dis/nuek-vuh3',
    record: n => `https://data.sf.gov/resource/nuek-vuh3.json?call_number=${encodeURIComponent(n)}`,
  },
};
const sourceOf = e => SOURCES[e.kind === 'police' ? 'police' : 'fire'];
// SFFD dispositions as published, in plain words (the dataset's own example: "FIR: Resolved by Fire Department").
const FIRE_OUTCOME = {
  Fire: 'resolved by the fire department', 'Code 2 Transport': 'patient taken to hospital (non-emergency transport)',
  'Code 3 Transport': 'patient taken to hospital (emergency transport)', 'Medical Examiner': 'referred to the medical examiner',
  'Unable to Locate': 'unable to locate', Cancelled: 'cancelled', Other: 'other',
};
const firePri = p => (p === 'E' ? '3' : p);
const firePriChanged = e => /^[23]$/.test(firePri(e.priOrig) || '') && /^[23]$/.test(firePri(e.priRaw) || '')
  && firePri(e.priOrig) !== firePri(e.priRaw);
const safeUrl = u => (/^https?:\/\//i.test(String(u || '')) ? String(u) : null);
function extLink(href, label, cls = '', ctx = '') {
  const url = safeUrl(href);
  if (!url) return `<span${cls ? ` class="${cls}"` : ''}>${esc(label)}</span>`;
  return `<a${cls ? ` class="${cls}"` : ''} href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}`
    + `<span class="sr-only">${ctx ? ` for ${esc(ctx)}` : ''} (opens in a new tab)</span><span aria-hidden="true"> ↗</span></a>`;
}

// "GEARY ST \ JONES ST" -> "Geary St & Jones St"; "CALL BOX: CARGO WY/JENNINGS ST,SF" -> "Cargo Wy & Jennings St (call box)".
function titleCase(s) {
  return String(s).toLowerCase().replace(/\b[a-z]/g, c => c.toUpperCase())
    .replace(/\b0+(\d)/g, '$1').replace(/(\d)(St|Nd|Rd|Th)\b/g, (m, d, suf) => d + suf.toLowerCase());
}
function prettyPlace(s) {
  if (!s) return null;
  let p = String(s).trim();
  if (/^not available$/i.test(p)) return null; // the city's placeholder, not a place
  const box = /^CALL BOX:\s*/i.test(p);
  p = p.replace(/^CALL BOX:\s*/i, '').replace(/,\s*SF$/i, '');
  p = p.split(/\s*[\\/]\s*/).filter(Boolean).map(titleCase).join(' & ').replace(/\bBlock Of\b/g, 'block of')
    .replace(/\bOfarrell\b/g, 'O\'Farrell').replace(/\bOshaughnessy\b/g, 'O\'Shaughnessy');
  return box ? `${p} (call box)` : p;
}
function supervisorDistrict(v) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? `Supervisor district ${n}` : null;
}
const clockFmt = new Intl.DateTimeFormat(undefined, { timeZone: PT, hour: 'numeric', minute: '2-digit' });
const clockPT = ms => (ms == null ? 'n/a' : clockFmt.format(ms));
function span(ms) {
  if (ms == null || !isFinite(ms)) return 'n/a';
  if (ms < 60000) return '<1 min';
  if (ms < 5400000) return `${Math.round(ms / 60000)} min`;
  return `${(ms / 3600000).toFixed(1)} h`;
}

// ---------- priority score: 0-100, computed in the browser from the city's own record fields ----------
// Every call in the Priority panel is already emergency priority by the city's code (police A, fire/EMS code 3).
// The score orders them: how severe the call type is (up to 50), whether help has arrived (25 while no unit is
// on scene, 15 once one is, 0 when closed), how fresh the call is (15), and how big it got (10: units sent, or
// the priority raised during the call). Severity is a keyword match on the call-type text plus the fire
// department's own life-threat grouping: a triage aid, disclosed in the panel, not a judgment of the call.
const SEV_LIFE = /shoot|shot|stab|gun|firearm|knife|armed|weapon|\badw\b|agg assault|homicide|kidnap|hostage|barricad|rape|explosi|bomb|suicid|overdose|od arrest|cardiac|card arr|unconscious|breath|person down|drown|water rescue|structure fire|building fire|full box|collapse|entrap|extricat/i;
const SEV_HARM_KINDS = [
  [/assault|battery|fight|robbery|carjack|domestic/i, 'violence'],
  [/injur|collision|medical/i, 'injury or medical'],
  [/fire|smoke|hazmat|gas leak/i, 'fire or hazard'],
  [/rescue|missing|distress|elevator|escalator/i, 'rescue or missing person'],
];
const SEV_ROUTINE = /alarm|fireworks/i;
const SEV_PTS = { 1: 50, 2: 34, 3: 14 };
function severity(e) {
  // "MEET W/CITY EMPLOYEE" is a police role code (assisting the fire department): the original type says what happened.
  const base = /meet w\/city employee/i.test(e.type || '') && e.typeOrig ? e.typeOrig : String(e.type || '');
  const t = base.replace(/no weapon|non[- ]?injury/gi, ' ');
  const harm = SEV_HARM_KINDS.find(([re]) => re.test(t));
  let tier = SEV_ROUTINE.test(t) ? 3 : SEV_LIFE.test(t) ? 1 : harm ? 2 : 3;
  let dept = null; // the fire department's own grouping of the call type
  if (e.group === 'Potentially Life-Threatening') { tier = 1; dept = 'potentially life-threatening'; }
  else if (e.group === 'Non Life-threatening') { if (tier === 1) tier = 2; dept = 'non life-threatening'; }
  else if (e.group === 'Alarm' && tier !== 1) { tier = 3; dept = 'alarm'; }
  else if (e.group === 'Fire' && tier === 3) { tier = 2; dept = 'fire'; }
  let label = tier === 1 ? 'life threat' : tier === 2 ? `possible harm: ${harm ? harm[1] : 'injury or medical'}` : 'other emergency call';
  if (dept) label += ` (fire department group: ${dept})`;
  if (base !== e.type) label += `; judged on the original call type, ${base}`;
  return { tier, pts: SEV_PTS[tier], label };
}
function responseStatus(e) {
  const T = e.times || {};
  if (!e.active) return { key: 'closed', label: 'closed', pts: 0 };
  if (e.onscene) return { key: 'onscene', label: 'unit on scene', pts: 15 };
  if (T.enroute != null || T.dispatch != null) return { key: 'enroute', label: 'unit en route, none on scene yet', pts: 25 };
  return { key: 'pending', label: 'awaiting dispatch', pts: 25 };
}
const POLICE_RANK = { C: 1, B: 2, A: 3 };
function sizeOrEscalation(e) {
  const raised = e.kind === 'police'
    ? (POLICE_RANK[e.priRaw] || 0) > (POLICE_RANK[e.priOrig] || 9)
    : firePriChanged(e) && firePri(e.priRaw) === '3';
  if (raised) return { pts: 10, label: `priority raised from ${e.priOrig} to ${e.priRaw}` };
  const n = e.units || 0;
  if (n >= 2) return { pts: n >= 4 ? 10 : n === 3 ? 7 : 4, label: `${n} units sent` };
  return { pts: 0, label: e.kind === 'police' ? 'not available for police calls: the real-time feed has no unit counts' : 'one unit sent' };
}
function scoreOf(e, now = Date.now()) {
  const sev = severity(e);
  const st = responseStatus(e);
  const age = now - e.ts;
  const fresh = { pts: age <= 1800000 ? 15 : age <= 3600000 ? 10 : age <= 7200000 ? 6 : age <= 21600000 ? 2 : 0, label: `received ${ago(e.ts)}` };
  const size = sizeOrEscalation(e);
  const total = Math.min(100, sev.pts + st.pts + fresh.pts + size.pts);
  const band = !e.active ? 'closed' : total >= 75 ? 'crit' : total >= 55 ? 'high' : 'mod';
  return { total, band, sev, st, fresh, size };
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

const PRIO_CLOSED_MAX = 12; // closed emergencies listed under the open ones, newest first

export function createLive(root, ctx) {
  const S = {
    city: CITIES[0], windowH: 6, events: new Map(), timers: [], activeView: false,
    map: null, layer: null, renderer: null, markers: new Map(), filter: 'all',
    lastFetch: {}, feedErr: {}, firstLoad: true, social: null, socialErr: null,
    selected: null, ring: null, onArrive: null, prioSeen: new Set(), prioReady: false, prioHTML: '',
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
      <section class="panel p-prio" aria-label="Priority calls">
        <div class="panel__head"><h2 class="panel__title">Priority</h2><span class="panel__meta" id="lv-prio-meta">&nbsp;</span></div>
        <div class="feed prio-list" id="lv-prio" aria-label="Emergency-priority calls, highest priority score first. Choose one to show it on the map with its details."><div class="feed__empty"><span class="spinner"></span> Contacting the city feeds…</div></div>
        <div class="lv-prio-foot">City 911 dispatch records, emergency priority only. Score 0–100: severity 50 · no unit on scene 25 · freshness 15 · size 10. Choose a call for the map and full details.</div>
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
    prio: $('#lv-prio'), prioMeta: $('#lv-prio-meta'), mapPanel: $('.p-map'),
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
    const sc = e.priority === 'crit' ? scoreOf(e) : null;
    const where = prettyPlace(e.place);
    return `<div class="pop__head">${sc ? `<span class="tag tag--score sc--${sc.band}" title="Rescue Radar priority score, 0 to 100">score ${sc.total}</span>` : ''}<span class="tag ${e.priority === 'crit' ? 'tag--bad' : ''}">${esc(prName(e))}</span>
        <span class="tag">${esc(e.agency)}</span>${e.active ? '<span class="tag tag--warn">open</span>' : '<span class="tag tag--ok">closed</span>'}${e.onscene && e.active ? '<span class="tag tag--ok">on scene</span>' : ''}</div>
      <div class="pop__meta">${esc(when(e))}${e.neighborhood ? ` · ${esc(e.neighborhood)}` : ''}</div>
      <div class="pop__text">${txt(e.type)}${where ? ` — ${txt(where)}` : ''}${e.units > 1 ? ` · ${fmtInt(e.units)} units` : ''}</div>
      <div class="pop__src">${extLink(sourceOf(e).record(e.callNo), `Source: ${sourceOf(e).label}`, '', callName(e))}</div>`;
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
        m.on('click', () => select(e.id, { fly: false }));
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

  // ---------- selection: jump to one call on the map (Priority panel, feed card or a map dot) ----------
  function select(id, { fly = true } = {}) {
    const e = S.events.get(id);
    if (!e) return;
    S.selected = id;
    paintPriority(visible()); // the chosen call opens up with its full details
    markSelected({ scroll: true });
    const m = S.markers.get(id);
    if (!m) {
      clearRing();
      if (S.map) S.map.closePopup(); // the previous call's popup would read as this one's
      toast(e.lat == null
        ? (e.sensitive ? 'The city publishes this call without a location (sensitive call type), so it cannot be shown on the map.'
          : 'The city’s record for this call has no location, so it cannot be shown on the map.')
        : 'The map is not available (offline?), so this call cannot be shown on it.', 'info');
      return;
    }
    m.bindPopup(popupHTML(e), { maxWidth: 300 }); // fresh content: the call may have closed since the dot was drawn
    placeRing(m.getLatLng());
    if (!fly) { m.openPopup(); return; }
    revealMap();
    if (S.onArrive) S.map.off('moveend', S.onArrive);
    S.onArrive = () => { S.onArrive = null; if (S.selected === id) m.openPopup(); };
    S.map.once('moveend', S.onArrive);
    const zoom = Math.max(S.map.getZoom(), 16);
    if (reducedMotion()) S.map.setView(m.getLatLng(), zoom, { animate: false });
    else S.map.flyTo(m.getLatLng(), zoom, { duration: 0.8 });
  }
  function placeRing(latlng) {
    clearRing(); // a new marker restarts the pulse
    S.ring = window.L.marker(latlng, {
      icon: window.L.divIcon({ className: 'lv-target', html: '<span></span>', iconSize: [0, 0] }),
      interactive: false, keyboard: false,
    }).addTo(S.map);
  }
  function clearRing() { if (S.ring) { S.ring.remove(); S.ring = null; } }
  function clearSelection() { S.selected = null; clearRing(); markSelected(); }
  function markSelected({ scroll = false } = {}) {
    for (const n of root.querySelectorAll('[data-id][aria-current]')) n.removeAttribute('aria-current');
    if (!S.selected) return;
    for (const list of [el.prio, el.feed]) {
      const n = list.querySelector(`[data-id="${CSS.escape(S.selected)}"]`);
      if (!n) continue;
      n.setAttribute('aria-current', 'true');
      if (scroll) scrollWithin(list, n);
    }
  }
  function scrollWithin(list, item) {
    // Scroll only the list, never the page: a click on the map must not jump the page to a list below the fold.
    const c = list.getBoundingClientRect();
    const r = item.getBoundingClientRect();
    if (r.top < c.top + 30 || r.bottom > c.bottom) list.scrollTop += r.top - c.top - 34; // room for the sticky group label
  }
  function revealMap() {
    // When the map is mostly off screen (narrow layouts stack it above the lists), bring it back into view.
    const box = el.mapPanel.getBoundingClientRect();
    const top = document.querySelector('.topbar')?.getBoundingClientRect().bottom || 0;
    const shown = Math.min(box.bottom, window.innerHeight) - Math.max(box.top, top);
    if (shown < box.height * 0.6) el.mapPanel.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'nearest' });
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
    const body = safeUrl(it.url)
      ? `<a href="${esc(safeUrl(it.url))}" target="_blank" rel="noopener noreferrer">${txt(it.text)}</a>` : txt(it.text);
    const label = it.label
      ? `<span class="tag ${crit ? 'tag--bad' : ''}">${esc(it.label_name || it.label)}</span>`
      : '<span class="tag" title="Waiting for the model">classifying…</span>';
    const origin = it.source === 'reddit' ? `Reddit post in ${it.feed || 'a city subreddit'}` : `${it.feed || 'News'} article`;
    const src = safeUrl(it.url) ? extLink(it.url, `Source: ${origin}`, 'post__src', String(it.title || it.text || '').slice(0, 80))
      : `<span class="post__src post__src--none">Source: ${esc(origin)} (no link published)</span>`;
    return `<article class="post${crit ? ' post--crit' : ''}">
      <div class="post__bar"></div>
      <div class="post__body">
        <div class="post__top"><span title="${esc(when({ ts: it.ts }))}">${esc(ago(it.ts))}</span>
          <span class="post__place">${esc(it.feed || it.source || '')}</span>${label}</div>
        <div class="post__text">${body}</div>
        <div class="post__truth">${it.queued ? '<span class="tag tag--warn">pushed to dispatch queue</span>' : ''}${src}</div>
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
    const where = prettyPlace(e.place);
    return `<article class="post${crit ? ' post--crit' : ''}" data-id="${esc(e.id)}"${S.selected === e.id ? ' aria-current="true"' : ''}>
      <div class="post__bar"></div>
      <div class="post__body">
        <div class="post__top"><span title="${esc(when(e))}">${esc(ago(e.ts))}</span>
          ${e.neighborhood ? `<span class="post__place" title="${esc(where || e.neighborhood)}">⌖ ${esc(e.neighborhood)}</span>` : (e.sensitive ? '<span class="post__place muted" title="Sensitive call type: the city publishes it without a location">⌖ withheld</span>' : '')}
          <span class="tag ${crit ? 'tag--bad' : ''}">${esc(prName(e))}</span></div>
        <div class="post__text"><b>${txt(e.type)}</b>${where ? ` — ${txt(where)}` : ''}</div>
        <div class="post__truth"><span class="tag">${esc(e.agency)}</span>${e.units > 1 ? `<span class="tag">${fmtInt(e.units)} units</span>` : ''}${e.active ? '<span class="tag tag--warn">open</span>' : '<span class="tag tag--ok">closed</span>'}${e.onscene && e.active ? '<span class="tag tag--ok">on scene</span>' : ''}${extLink(sourceOf(e).record(e.callNo), 'source', 'post__src', callName(e))}</div>
      </div></article>`;
  }

  // ---------- Priority panel: score, location, response timeline and source on every card ----------
  const callName = e => `${e.type}, call ${e.callNo}`;
  const dataTime = (e, now) => Math.min(now, e.stateAt ?? e.asOf ?? now); // the moment the city's data describes
  function stepsLine(e, now) {
    const T = e.times || {};
    const t0 = T.received ?? e.ts;
    if (e.onview) { // an officer started it in the field: there is no dispatch to time
      return [`officer-initiated ${clockPT(t0)}`, !e.active && T.close != null ? `closed after ${span(T.close - t0)}` : null]
        .filter(Boolean).join(' · ');
    }
    const bits = [`received ${clockPT(t0)}`];
    if (T.dispatch != null) bits.push(`dispatched in ${span(T.dispatch - t0)}`);
    if (T.onscene != null) bits.push(`on scene in ${span(T.onscene - t0)}`);
    else if (e.active) bits.push(`no unit on scene ${span(dataTime(e, now) - t0)} in`);
    if (!e.active && T.close != null) bits.push(`${e.kind === 'police' ? 'closed' : 'cleared'} after ${span(T.close - t0)}`);
    return bits.join(' · ');
  }
  function ringHTML(sc) {
    return `<span class="prio__score" title="Rescue Radar priority score: ${sc.total} of 100">
      <svg viewBox="0 0 40 40" aria-hidden="true"><circle class="prio__ring-bg" cx="20" cy="20" r="17"/><circle class="prio__ring" cx="20" cy="20" r="17" pathLength="100" stroke-dasharray="${sc.total} 100"/></svg>
      <b aria-hidden="true">${sc.total}</b><small aria-hidden="true">score</small><span class="sr-only">Priority score ${sc.total} of 100.</span></span>`;
  }
  function detailsHTML(e, sc, now) {
    const T = e.times || {};
    const t0 = T.received ?? e.ts;
    const bar = (k, part, max) => `<div class="pm-bar"><span class="pm-bar__k">${k}</span>
      <span class="pm-bar__track" aria-hidden="true"><i style="width:${Math.round(part.pts / max * 100)}%"></i></span>
      <span class="pm-bar__pts num">+${part.pts}<small>/${max}</small></span><span class="pm-bar__note">${esc(part.label)}</span></div>`;
    const STEPS = e.onview
      ? [['received', 'started by an officer in the field (on-view)'], ['close', 'call closed']]
      : [['received', 'call received'], ['entry', 'entered into dispatch'], ['dispatch', 'first unit dispatched'],
        ['enroute', 'first unit en route'], ['onscene', 'first unit on scene'], ['transport', 'patient transport began'],
        ['hospital', 'arrived at hospital'], ['close', e.kind === 'police' ? 'call closed' : 'last unit cleared']];
    const steps = STEPS.filter(([k]) => T[k] != null).map(([k, label]) => `<li><span class="pm-t num">${esc(clockPT(T[k]))}</span>
      <span>${esc(label)}</span><span class="pm-d num">${k === 'received' ? '' : `+${esc(span(T[k] - t0))}`}</span></li>`).join('')
      + (e.active ? `<li class="pm-open"><span class="pm-t num">${esc(clockPT(dataTime(e, now)))}</span><span>still open in the city's latest data</span><span class="pm-d"></span></li>` : '')
      + (e.uncleared ? `<li class="pm-open"><span class="pm-t num">${esc(clockPT(e.asOf))}</span><span>${e.uncleared === 1 ? 'one unit was' : `${e.uncleared} units were`} still assigned when the city published its daily extract</span><span class="pm-d"></span></li>` : '');
    const where = prettyPlace(e.place);
    const loc = e.lat == null
      ? (e.sensitive ? 'Withheld by the city: sensitive call types are published without a location.'
        : 'Not in the city’s record: it publishes this call’s location as “Not Available”.')
      : [where, e.neighborhood, e.zip ? `ZIP ${e.zip}` : null].filter(Boolean).map(esc).join(' · ');
    const areas = [e.district, e.supervisor].filter(Boolean).map(esc).join(' · ');
    const coords = e.lat != null ? `<br><span class="num">${e.lat.toFixed(5)}, ${e.lng.toFixed(5)}</span>` : '';
    const call = (e.kind === 'police'
      ? [`CAD ${esc(e.callNo)}`, e.onview ? 'officer-initiated (on-view)' : 'reported by a 911 caller',
        e.typeOrig && e.typeOrig !== e.type ? `first reported as ${txt(e.typeOrig)}` : null,
        e.priOrig && e.priOrig !== e.priRaw ? `priority ${esc(e.priOrig)} → ${esc(e.priRaw)}` : null,
        e.disposition ? `<span title="Code as published by the city">disposition code ${esc(e.disposition)}</span>` : null]
      : [`call ${esc(e.callNo)}`, e.group ? esc(e.group.toLowerCase()) : null,
        firePriChanged(e) ? `code ${esc(firePri(e.priOrig))} → ${esc(firePri(e.priRaw))}` : null,
        e.disposition ? `<span title="City disposition: ${esc(e.disposition)}">outcome: ${esc(FIRE_OUTCOME[e.disposition] || e.disposition)}</span>` : null]).filter(Boolean).join(' · ');
    const units = (e.unitList || []).map(u => `<span title="${esc(u.type.toLowerCase())}${u.als ? ', paramedic on board (ALS)' : ''}">${esc(u.id)}${u.als ? '<sup>ALS</sup>' : ''}</span>`).join(' ');
    const src = sourceOf(e);
    return `<div class="prio__more" id="lvp-${esc(e.id)}">
      <div class="pm-sec"><div class="pm-h">Why ${sc.total}</div>${bar('Call type', sc.sev, 50)}${bar('Response', sc.st, 25)}${bar('Freshness', sc.fresh, 15)}${bar('Size', sc.size, 10)}</div>
      <div class="pm-sec"><div class="pm-h">Timeline · SF time</div><ol class="pm-steps">${steps}</ol></div>
      <dl class="pm-dl">
        <dt>Location</dt><dd>${loc}${areas ? `<br>${areas}` : ''}${coords}</dd>
        <dt>Call</dt><dd>${call}</dd>
        ${units ? `<dt>Units</dt><dd class="pm-units">${units}</dd>` : ''}
        <dt>Source</dt><dd>${esc(src.dataset)}, published by the City and County of San Francisco on DataSF${e.asOf ? ` (city update ${esc(clockPT(e.asOf))})` : ''}.<br>${extLink(src.record(e.callNo), 'Raw record for this call', '', callName(e))} · ${extLink(src.page, 'Dataset', '', src.dataset)}</dd>
      </dl>
    </div>`;
  }
  function prioHTML(e, sc, now) {
    const located = e.lat != null;
    const sel = S.selected === e.id;
    const fresh = S.prioReady && e.active && !S.prioSeen.has(e.id);
    const status = {
      closed: '<span class="tag">closed</span>', onscene: '<span class="tag tag--ok">unit on scene</span>',
      enroute: '<span class="tag tag--warn">unit en route</span>', pending: '<span class="tag tag--bad">awaiting dispatch</span>',
    }[sc.st.key];
    const where = [prettyPlace(e.place), e.neighborhood].filter(Boolean).join(' · ');
    const place = located ? `<span class="prio__pin" aria-hidden="true">⌖</span>${esc(where || 'on the map')}`
      : e.sensitive ? 'Location withheld by the city (sensitive call type)' : 'No location in the city’s record';
    const src = sourceOf(e);
    return `<article class="prio sc--${sc.band}${located ? '' : ' prio--nomap'}${fresh ? ' prio--new' : ''}" data-id="${esc(e.id)}"${sel ? ' aria-current="true"' : ''}>
      <span class="prio__bar" aria-hidden="true"></span>
      <div class="prio__col">
        <button type="button" class="prio__main" aria-expanded="${sel}"${sel ? ` aria-controls="lvp-${esc(e.id)}"` : ''} title="${sel ? 'Close this call’s details' : located ? 'Show this call on the map with its details' : 'Show this call’s details (it has no map location)'}">
          ${ringHTML(sc)}
          <span class="prio__body">
            <span class="prio__head"><span class="prio__type">${txt(e.type)}</span><span class="prio__ago" title="${esc(when(e))}">${esc(ago(e.ts))}</span></span>
            <span class="prio__place">${place}</span>
            <span class="prio__top"><span class="tag tag--bad">${esc(prName(e))}</span>${status}<span class="prio__agency">${esc(e.agency)}</span></span>
            <span class="prio__steps">${esc(stepsLine(e, now))}</span>
          </span>
          <span class="prio__go" aria-hidden="true">${locateIcon()}</span>
        </button>
        <div class="prio__src">${extLink(src.record(e.callNo), `Source: ${src.label}`, '', callName(e))}</div>
        ${sel ? detailsHTML(e, sc, now) : ''}
      </div>
    </article>`;
  }
  function paintPriority(list) {
    const now = Date.now();
    const em = list.filter(e => e.priority === 'crit').map(e => ({ e, sc: scoreOf(e, now) }));
    const open = em.filter(x => x.e.active).sort((a, b) => (b.sc.total - a.sc.total) || (b.e.ts - a.e.ts));
    const closed = em.filter(x => !x.e.active); // list is newest first already
    const shownClosed = closed.slice(0, PRIO_CLOSED_MAX);
    const picked = S.selected && !shownClosed.some(x => x.e.id === S.selected) && closed.find(x => x.e.id === S.selected);
    if (picked) shownClosed.push(picked); // a closed call chosen on the map still gets its card
    el.prioMeta.textContent = `${fmtInt(open.length)} open · ${fmtInt(em.length)} in window`;
    const row = x => prioHTML(x.e, x.sc, now);
    let html;
    if (!em.length) {
      html = `<div class="feed__empty">${Object.keys(S.feedErr).length ? 'The city feeds could not be reached.' : S.firstLoad ? '<span class="spinner"></span> Contacting the city feeds…' : 'No emergency-priority calls in the window.'}</div>`;
    } else {
      html = `<div class="prio-group"><span>Open now · by score</span><span class="num">${fmtInt(open.length)}</span></div>`
        + (open.length ? open.map(row).join('') : '<div class="prio-empty">No open emergency calls right now.</div>');
      if (shownClosed.length) {
        const newest = Math.min(closed.length, PRIO_CLOSED_MAX);
        html += `<div class="prio-group"><span>Recently closed</span><span class="num">${newest < closed.length ? `newest ${fmtInt(newest)} of ${fmtInt(closed.length)}` : fmtInt(closed.length)}${picked ? ' + the call you chose' : ''}</span></div>`
          + shownClosed.map(row).join('');
      }
    }
    if (html !== S.prioHTML) {
      const ae = document.activeElement;
      const card = el.prio.contains(ae) ? ae.closest('[data-id]') : null;
      const at = card ? Array.from(card.querySelectorAll('button, a')).indexOf(ae) : -1;
      const chosen = S.selected ? el.prio.querySelector(`[data-id="${CSS.escape(S.selected)}"]`) : null;
      const top0 = chosen ? chosen.getBoundingClientRect().top : null;
      el.prio.innerHTML = html;
      S.prioHTML = html;
      const moved = top0 != null ? el.prio.querySelector(`[data-id="${CSS.escape(S.selected)}"]`) : null;
      if (moved) el.prio.scrollTop += moved.getBoundingClientRect().top - top0; // a re-sort must not yank the card away
      if (card) {
        const again = el.prio.querySelector(`[data-id="${CSS.escape(card.dataset.id)}"]`);
        (again && (again.querySelectorAll('button, a')[at] || again.querySelector('.prio__main')))?.focus({ preventScroll: true });
      }
    }
    for (const x of open) S.prioSeen.add(x.e.id);
  }
  function paint() {
    const list = visible();
    if (S.selected && !list.some(e => e.id === S.selected)) clearSelection();
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
    const fa = document.activeElement;
    const feedCard = el.feed.contains(fa) && fa !== el.feed ? fa.closest('[data-id]') : null;
    el.feed.innerHTML = shown.length
      ? shown.map(eventHTML).join('')
      : `<div class="feed__empty">${Object.keys(S.feedErr).length ? 'The city feeds could not be reached.' : S.firstLoad ? '<span class="spinner"></span> Contacting the city feeds…' : 'No calls match this filter in the window.'}</div>`;
    el.feedMeta.textContent = shown.length < list.filter(matches).length ? `newest 200 of ${fmtInt(list.filter(matches).length)}` : `${fmtInt(shown.length)} shown`;
    if (feedCard) { // keep keyboard focus on the same source link through the repaint
      const again = el.feed.querySelector(`[data-id="${CSS.escape(feedCard.dataset.id)}"] a.post__src`);
      (again || el.feed).focus({ preventScroll: true });
    }
    paintPriority(list);

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
    S.prioReady = false; // a wider window brings older calls in: they are not new arrivals
    pollAll().then(() => { S.prioReady = true; });
    paint();
  }));
  root.querySelectorAll('[data-lvf]').forEach(b => b.addEventListener('click', () => {
    S.filter = b.dataset.lvf;
    root.querySelectorAll('[data-lvf]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    paint();
  }));
  el.refresh.addEventListener('click', () => { el.refresh.disabled = true; pollAll({ announce: true }).finally(() => { el.refresh.disabled = false; }); });
  el.feed.addEventListener('click', ev => {
    if (ev.target.closest('a')) return; // the source link opens the city record in a new tab
    const card = ev.target.closest('.post');
    if (card) select(card.dataset.id);
  });
  function collapse(id) {
    clearSelection();
    if (S.map) S.map.closePopup();
    paintPriority(visible());
    // an older closed call chosen on the map leaves the list when it closes: land on the first card instead
    (el.prio.querySelector(`[data-id="${CSS.escape(id)}"] .prio__main`) || el.prio.querySelector('.prio__main'))?.focus({ preventScroll: true });
  }
  el.prio.addEventListener('click', ev => {
    if (ev.target.closest('a')) return;
    const b = ev.target.closest('.prio__main');
    if (!b) return;
    const id = b.closest('[data-id]').dataset.id;
    if (S.selected === id) collapse(id); else select(id);
  });
  el.prio.addEventListener('keydown', ev => {
    // Arrow keys walk the list, Enter or Space (native button) opens or closes a call, Escape closes it.
    if (ev.key === 'Escape' && S.selected) { collapse(S.selected); return; }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(ev.key)) return;
    const items = Array.from(el.prio.querySelectorAll('.prio__main'));
    if (!items.length) return;
    ev.preventDefault();
    const i = items.indexOf(document.activeElement.closest('.prio')?.querySelector('.prio__main'));
    const next = ev.key === 'Home' ? 0 : ev.key === 'End' ? items.length - 1
      : Math.max(0, Math.min(items.length - 1, i + (ev.key === 'ArrowDown' ? 1 : -1)));
    items[next].focus();
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
      // Calls already in the feed on first load are not "new": only later arrivals flash in the Priority panel.
      if (stale) pollAll().then(() => { S.prioReady = true; });
      else S.prioReady = true;
      pollSocial();
      startTimers();
    },
    deactivate() { S.activeView = false; stopTimers(); },
  };
}

function locateIcon() {
  return '<svg viewBox="0 0 24 24" aria-hidden="true" width="15" height="15" style="fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round"><circle cx="12" cy="12" r="6.5"/><circle cx="12" cy="12" r="2"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3"/></svg>';
}
function refreshIcon() {
  return '<svg viewBox="0 0 24 24" aria-hidden="true" width="16" height="16" style="fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round"><path d="M20 12a8 8 0 1 1-2.3-5.6M20 3v4h-4"/></svg>';
}
