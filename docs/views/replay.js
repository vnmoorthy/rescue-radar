// Live Replay: stream an unseen 2019 disaster through the console in timestamp order.
import {
  esc, chip, fmtInt, fmtPct, fmtUsd, fmtDur, fmtDateTime, fmtTime, fmtDay, labelName, isCritical,
  countTo, toast, errMessage, reducedMotion, hashId, nextFrame, txt,
} from '../ui.js';

const BASE = 60;            // 1x = one event-minute per wall-second
const GAP_CAP = 180000;     // quiet gaps longer than 3 event-minutes are compressed to 3 minutes
const SPEEDS = [1, 10, 50, 100, 'max'];
const MAX_PER_FRAME = 12;
const FEED_CAP = 160;
// Basemap. CARTO's free raster basemaps now answer every request with an "API KEY REQUIRED" tile, so the
// default is Esri's keyless Canvas (dark/light gray) with its label overlay. ?basemap=carto restores CARTO
// (for a network or key setup where it works).
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas';
const BASEMAPS = {
  esri: {
    dark: [`${ESRI}/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`, `${ESRI}/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`],
    light: [`${ESRI}/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`, `${ESRI}/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`],
    opts: { maxNativeZoom: 16, maxZoom: 18 },
    attr: 'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, HERE, Garmin, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, and the GIS user community',
  },
  carto: {
    dark: ['https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', 'https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png'],
    light: ['https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', 'https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png'],
    opts: { subdomains: 'abcd', maxZoom: 19 },
    attr: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
  },
};
const BASEMAP = BASEMAPS[new URLSearchParams(location.search).get('basemap')] || BASEMAPS.esri;
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
};

export function createReplay(root, ctx) {
  const { api, meta, queue } = ctx;
  const events = meta.events || [];
  const S = {
    eventId: null, event: null, posts: [], v: [], vTotal: 0, idx: 0, vclock: 0,
    playing: false, raf: 0, last: 0, speed: 1, gt: false, source: 'ours', loading: false,
    feedPosts: [], buffered: 0, hover: false, results: null, map: null, tiles: null, layer: null, renderer: null,
    markers: new Map(), placeCount: new Map(), st: null, lastScrubPaint: 0,
  };
  const savedSpeed = store.get('rr-speed', '1');
  S.speed = savedSpeed === 'max' ? 'max' : (SPEEDS.includes(Number(savedSpeed)) ? Number(savedSpeed) : 1);

  root.innerHTML = `
  <div class="replay">
    <div class="panel transport">
      <div class="events" role="group" aria-label="Disaster to replay">
        ${events.map(e => `<button type="button" class="event-btn" data-event="${esc(e.id)}" aria-pressed="false">
          <span class="event-btn__name">${esc(e.name)}</span>
          <span class="event-btn__meta">${esc(e.country || '')} · ${fmtInt(e.n_posts)} posts</span></button>`).join('')}
      </div>
      <div class="transport__sep" aria-hidden="true"></div>
      <div class="transport__group">
        <button type="button" class="btn btn--primary btn--play" id="rp-play" aria-label="Play replay (Space)">${playIcon()}<span>Play</span></button>
        <button type="button" class="btn" id="rp-reset" aria-label="Reset replay (R)">${resetIcon()}<span>Reset</span></button>
      </div>
      <div class="seg" role="group" aria-label="Replay speed">
        ${SPEEDS.map(s => `<button type="button" data-speed="${s}" aria-pressed="false" title="${s === 'max' ? 'As fast as the browser can render' : s === 1 ? '1x = one event-minute per second, quiet gaps compressed' : `${s}x real-time-compressed`}">${s === 'max' ? 'Max' : `${s}x`}</button>`).join('')}
      </div>
      <div class="scrub">
        <div class="scrub__row"><span class="scrub__clock" id="rp-clock">Select a disaster</span><span id="rp-progress">0 / 0</span></div>
        <input type="range" id="rp-scrub" min="0" max="1000" value="0" step="1" aria-label="Replay position">
      </div>
      <label class="switch" title="Reveal human labels and mark model mistakes (G)"><input type="checkbox" id="rp-gt"><span class="switch__track"></span>Show ground truth</label>
    </div>
    <div id="rp-banner"></div>
    <div class="kpis" id="rp-kpis">
      <div class="kpi"><div class="kpi__label">Posts screened</div><div class="kpi__value" id="k-n">0</div><div class="kpi__sub" id="k-n-sub">&nbsp;</div></div>
      <div class="kpi kpi--crit"><div class="kpi__label">Rescue-critical flagged</div><div class="kpi__value" id="k-flag">0</div><div class="kpi__sub" id="k-flag-sub">&nbsp;</div></div>
      <div class="kpi"><div class="kpi__label">Time to first flag</div><div class="kpi__value" id="k-first">n/a</div><div class="kpi__sub" id="k-first-sub">event clock, from first post</div></div>
      <div class="kpi"><div class="kpi__label">Accuracy so far</div><div id="k-acc"></div></div>
      <div class="kpi"><div class="kpi__label">Critical recall so far</div><div id="k-rec"></div></div>
      <div class="kpi"><div class="kpi__label">Cost so far</div><div id="k-cost"></div></div>
    </div>
    <div class="replay-grid">
      <section class="panel p-map" aria-label="Map">
        <div class="panel__head"><h2 class="panel__title">Map</h2><span class="panel__meta" id="map-meta">0 placed</span></div>
        <div class="map-wrap"><div id="map"></div>
          <div class="map-legend" aria-hidden="true"><span><i class="lg-crit"></i>Rescue-critical</span><span><i class="lg-other"></i>Other posts</span><span id="lg-miss" hidden><i class="lg-miss"></i>Model mistake</span></div>
        </div>
      </section>
      <section class="panel p-feed" aria-label="Incoming posts">
        <div class="panel__head"><h2 class="panel__title">Incoming feed</h2><span class="panel__meta"><span id="feed-state">auto-scroll</span></span></div>
        <div class="feed" id="feed" tabindex="0" aria-label="Incoming posts, newest first"><div class="feed__empty">Press <kbd>Space</kbd> or Play to start the replay.</div></div>
      </section>
      <section class="panel p-queue" aria-label="Priority queue">
        <div class="panel__head"><h2 class="panel__title">Priority queue</h2><span class="panel__meta"><span class="count-badge count-badge--crit" id="q-open">0 open</span></span></div>
        <div class="queue-filters" role="group" aria-label="Filter queue">
          ${[['active', 'Active'], ['open', 'Open'], ['dispatched', 'Dispatched'], ['resolved', 'Resolved'], ['dismissed', 'Dismissed'], ['all', 'All']]
            .map(([k, l]) => `<button type="button" class="qf" data-filter="${k}" aria-pressed="${k === 'active'}">${l} <span data-count="${k}">0</span></button>`).join('')}
        </div>
        <div class="queue-list" id="qlist" aria-live="off"></div>
        <div class="queue-foot">
          <button type="button" class="btn btn--sm" id="q-csv">${dlIcon()}Export CSV</button>
          <button type="button" class="btn btn--sm btn--danger" id="q-clear">Clear</button>
          <span class="muted" id="q-mode"></span>
        </div>
      </section>
    </div>
  </div>`;

  const $ = s => root.querySelector(s);
  const el = {
    play: $('#rp-play'), reset: $('#rp-reset'), clock: $('#rp-clock'), progress: $('#rp-progress'), scrub: $('#rp-scrub'),
    gt: $('#rp-gt'), banner: $('#rp-banner'), feed: $('#feed'), feedState: $('#feed-state'), qlist: $('#qlist'),
    qopen: $('#q-open'), mapMeta: $('#map-meta'), kN: $('#k-n'), kNSub: $('#k-n-sub'), kFlag: $('#k-flag'),
    kFlagSub: $('#k-flag-sub'), kFirst: $('#k-first'), kFirstSub: $('#k-first-sub'), kAcc: $('#k-acc'), kRec: $('#k-rec'),
    kCost: $('#k-cost'), qmode: $('#q-mode'), lgMiss: $('#lg-miss'),
  };
  el.qmode.textContent = api.mode === 'live' ? 'saved on server' : 'saved in this browser';

  // ---------- KPI scaffolding ----------
  const vsHTML = (id) => `
    <div class="vs">
      <span class="vs__name">Rescue Radar</span><span class="vs__bar"><i id="${id}-ob"></i></span><span class="vs__val" id="${id}-o">n/a</span>
      <span class="vs__name">Opus 5.5</span><span class="vs__bar vs__bar--frontier"><i id="${id}-fb"></i></span><span class="vs__val" id="${id}-f">n/a</span>
    </div><div class="kpi__sub" id="${id}-sub"></div>`;
  el.kAcc.innerHTML = vsHTML('ka');
  el.kRec.innerHTML = vsHTML('kr');
  el.kCost.innerHTML = vsHTML('kc');

  // ---------- results (for cost per post) ----------
  Promise.resolve(ctx.results).then(r => { S.results = r && r.systems ? r : null; paintKpis(); }).catch(() => {});
  function costInfo() {
    const r = S.results;
    if (!r) return { ours: null, oursTag: null, front: null, frontTag: null };
    const hl = r.headline || {};
    const ours = r.systems[hl.ours || 'rescue_radar'];
    const fr = r.systems[hl.frontier || 'opus_few'];
    const tagOf = s => (!s || s.cost_per_1m_usd == null ? null
      : (s.cost_measured === true || /^measured/i.test(s.cost_note || '')) ? 'measured' : 'estimated');
    return { ours: ours && ours.cost_per_1m_usd != null ? ours.cost_per_1m_usd / 1e6 : null, oursTag: tagOf(ours), oursNote: ours && ours.cost_note,
      front: fr && fr.cost_per_1m_usd != null ? fr.cost_per_1m_usd / 1e6 : null, frontTag: tagOf(fr), frontNote: fr && fr.cost_note };
  }

  // ---------- map ----------
  function initMap() {
    if (S.map || !window.L) {
      if (!window.L && !root.querySelector('.map-fallback')) {
        root.querySelector('.map-wrap').insertAdjacentHTML('beforeend', '<div class="map-fallback">Map library unavailable (offline?). The feed, queue and KPIs keep working.</div>');
      }
      return;
    }
    const L = window.L;
    S.renderer = L.canvas({ padding: 0.4 });
    S.map = L.map('map', { zoomControl: true, attributionControl: true, worldCopyJump: true, preferCanvas: true, renderer: S.renderer });
    const [base, labels] = BASEMAP[ctx.theme()];
    S.tiles = L.tileLayer(base, { attribution: BASEMAP.attr, ...BASEMAP.opts }).addTo(S.map);
    const lp = S.map.createPane('rr-labels');
    lp.style.zIndex = 350;
    lp.style.pointerEvents = 'none';
    S.labels = L.tileLayer(labels, { ...BASEMAP.opts, pane: 'rr-labels', opacity: 0.85 }).addTo(S.map);
    S.layer = L.layerGroup().addTo(S.map);
    S.map.setView([20, 0], 2);
    ctx.onTheme(t => { if (S.tiles) { S.tiles.setUrl(BASEMAP[t][0]); S.labels.setUrl(BASEMAP[t][1]); } repaintMarkers(); });
  }
  function markerStyle(p) {
    const src = labelOf(p);
    const crit = !!(src && src.critical);
    const mistake = S.gt && src && src.label !== p.truth;
    const css = getComputedStyle(document.documentElement);
    const color = crit ? css.getPropertyValue('--cat-req').trim() : css.getPropertyValue('--cat-dis').trim();
    const missColor = css.getPropertyValue('--warn').trim();
    return {
      radius: crit ? 6.5 : 4, color: mistake ? missColor : color, weight: mistake ? 2 : (crit ? 1.5 : 1),
      dashArray: mistake ? '3 3' : null, fillColor: color, fillOpacity: crit ? 0.85 : 0.38, opacity: crit || mistake ? 1 : 0.6,
    };
  }
  function jitter(p) {
    const key = p.place.name;
    const n = (S.placeCount.get(key) || 0) + 1;
    S.placeCount.set(key, n);
    const h = parseInt(hashId(p.id), 36);
    const ang = (h % 360) * Math.PI / 180;
    const rad = Math.min(0.5, 0.025 + 0.018 * Math.sqrt(n));
    return [p.place.lat + Math.sin(ang) * rad * 0.8, p.place.lng + Math.cos(ang) * rad];
  }
  function addMarker(p, pulse) {
    if (!S.map || !p.place || p.place.lat == null) return;
    const L = window.L;
    const m = L.circleMarker(jitter(p), { ...markerStyle(p), renderer: S.renderer });
    m.on('click', () => m.bindPopup(popupHTML(p), { maxWidth: 300 }).openPopup());
    m.addTo(S.layer);
    S.markers.set(p.id, m);
    if (pulse && !reducedMotion()) {
      const pm = L.marker(m.getLatLng(), { icon: L.divIcon({ className: 'pulse-icon', html: '<span></span>', iconSize: [0, 0] }), interactive: false, keyboard: false }).addTo(S.map);
      setTimeout(() => pm.remove(), 3300);
    }
    if (labelOf(p) && labelOf(p).critical) m.bringToFront();
  }
  function repaintMarkers() {
    if (!S.map) return;
    const byId = new Map(S.posts.slice(0, S.idx).map(p => [p.id, p]));
    for (const [id, m] of S.markers) { const p = byId.get(id); if (p) m.setStyle(markerStyle(p)); }
  }
  function popupHTML(p) {
    const src = labelOf(p);
    return `<div class="pop__head">${chip(src && src.label, { full: true })}${src && src.critical ? '<span class="crit-flag">rescue-critical</span>' : ''}</div>
      <div class="pop__meta">${esc(fmtDateTime(p.ts))}${p.place ? ` · ${esc(p.place.name)}` : ''}</div>
      <div class="pop__text">${txt(p.text)}</div>
      ${S.gt ? `<div class="post__truth" style="margin-top:8px">Human label ${chip(p.truth)} ${src ? (src.label === p.truth ? '<span class="tag tag--ok">correct</span>' : '<span class="tag tag--bad">model wrong</span>') : ''}</div>` : ''}`;
  }

  // ---------- labels ----------
  function labelOf(p) { return S.source === 'frontier' ? p.frontier : p.ours; }
  const sourceName = () => (S.source === 'frontier' ? 'Claude Opus 5.5' : 'Rescue Radar');

  // ---------- feed ----------
  function postHTML(p, isNew) {
    const src = labelOf(p);
    const crit = !!(src && src.critical);
    let truth = '';
    if (S.gt) {
      const wrong = src && src.label !== p.truth;
      const miss = p.truth_critical && !(src && src.critical);
      const fa = crit && !p.truth_critical;
      truth = `<div class="post__truth">Human ${chip(p.truth)}
        ${src ? (wrong ? '<span class="tag tag--bad">wrong</span>' : '<span class="tag tag--ok">correct</span>') : '<span class="tag">unscored</span>'}
        ${miss && src ? '<span class="tag tag--bad">missed rescue</span>' : ''}${fa ? '<span class="tag tag--warn">false alarm</span>' : ''}</div>`;
    }
    const wrongCls = S.gt && src && src.label !== p.truth ? ' post--wrong' : '';
    return `<article class="post${crit ? ' post--crit' : ''}${isNew ? ' post--new' : ''}${wrongCls}" data-cat="${esc(src ? src.label : '')}" data-id="${esc(p.id)}">
      <div class="post__bar"></div>
      <div class="post__body">
        <div class="post__top"><span>${esc(fmtDay(p.ts))} ${esc(fmtTime(p.ts))}</span>${p.place ? `<span class="post__place" title="${esc(p.place.name)}">⌖ ${esc(p.place.name)}</span>` : ''}${chip(src && src.label)}</div>
        <div class="post__text">${txt(p.text)}</div>${truth}
      </div></article>`;
  }
  function feedAdd(batch, animate) {
    for (const p of batch) S.feedPosts.push(p);
    if (S.feedPosts.length > FEED_CAP) S.feedPosts.splice(0, S.feedPosts.length - FEED_CAP);
    if (S.hover || el.feed.scrollTop > 40) {
      S.buffered += batch.length;
      showNewPill();
      return;
    }
    renderFeedAppend(batch.slice(-40), animate);
  }
  function renderFeedAppend(batch, animate) {
    const empty = el.feed.querySelector('.feed__empty');
    if (empty) empty.remove();
    const html = batch.slice().reverse().map(p => postHTML(p, animate)).join('');
    const pill = el.feed.querySelector('.feed__new');
    if (pill) pill.insertAdjacentHTML('afterend', html); else el.feed.insertAdjacentHTML('afterbegin', html);
    const posts = el.feed.querySelectorAll('.post');
    for (let i = posts.length - 1; i >= FEED_CAP; i--) posts[i].remove();
  }
  function renderFeedFull() {
    S.buffered = 0;
    if (!S.feedPosts.length) {
      el.feed.innerHTML = `<div class="feed__empty">${S.loading ? '<span class="spinner"></span> Loading replay…' : 'Press <kbd>Space</kbd> or Play to start the replay.'}</div>`;
      return;
    }
    el.feed.innerHTML = S.feedPosts.slice().reverse().map(p => postHTML(p, false)).join('');
  }
  function showNewPill() {
    let pill = el.feed.querySelector('.feed__new');
    if (!pill) {
      el.feed.insertAdjacentHTML('afterbegin', '<button type="button" class="feed__new"></button>');
      pill = el.feed.querySelector('.feed__new');
      pill.addEventListener('click', flushFeed);
    }
    pill.textContent = `${fmtInt(S.buffered)} new post${S.buffered === 1 ? '' : 's'} · paused while you read`;
    el.feedState.textContent = 'paused (hover)';
  }
  function flushFeed() {
    if (!S.buffered) return;
    renderFeedFull();
    el.feed.scrollTop = 0;
    el.feedState.textContent = 'auto-scroll';
  }
  el.feed.addEventListener('mouseenter', () => { S.hover = true; el.feedState.textContent = 'paused (hover)'; });
  el.feed.addEventListener('mouseleave', () => { S.hover = false; if (el.feed.scrollTop <= 40) { flushFeed(); el.feedState.textContent = 'auto-scroll'; } });
  el.feed.addEventListener('scroll', () => { if (!S.hover && el.feed.scrollTop <= 40 && S.buffered) flushFeed(); }, { passive: true });

  // ---------- stats ----------
  function resetStats() {
    S.st = { n: 0, flagged: 0, first: null, truthCrit: 0, placed: 0,
      o: { n: 0, correct: 0, critN: 0, critTP: 0 }, f: { n: 0, correct: 0, critN: 0, critTP: 0, cost: 0, costN: 0 } };
  }
  function account(p) {
    const st = S.st;
    st.n++;
    if (p.place) st.placed++;
    if (p.truth_critical) st.truthCrit++;
    const src = labelOf(p);
    if (src && src.critical) { st.flagged++; if (!st.first) st.first = { ts: p.ts, n: st.n }; }
    for (const [k, r] of [['o', p.ours], ['f', p.frontier]]) {
      if (!r) continue;
      const s = st[k];
      s.n++;
      if (r.label === p.truth) s.correct++;
      if (p.truth_critical) { s.critN++; if (r.critical) s.critTP++; }
      if (k === 'f' && r.cost_usd != null) { s.cost += r.cost_usd; s.costN++; }
    }
  }
  function setVs(id, o, f, fmt, max, sub) {
    const oe = root.querySelector(`#${id}-o`), fe = root.querySelector(`#${id}-f`);
    countTo(oe, o, fmt);
    countTo(fe, f, fmt);
    root.querySelector(`#${id}-ob`).style.width = o == null ? '0%' : `${Math.min(100, (o / (max || 1)) * 100)}%`;
    root.querySelector(`#${id}-fb`).style.width = f == null ? '0%' : `${Math.min(100, (f / (max || 1)) * 100)}%`;
    const s = root.querySelector(`#${id}-sub`);
    if (s && sub !== undefined && s.innerHTML !== sub) s.innerHTML = sub;
  }
  function paintKpis() {
    const st = S.st;
    if (!st) return;
    countTo(el.kN, st.n);
    el.kNSub.textContent = S.posts.length ? `of ${fmtInt(S.posts.length)} in ${S.event ? S.event.name : 'event'}` : '';
    countTo(el.kFlag, st.flagged);
    el.kFlagSub.textContent = `by ${sourceName()}${S.gt ? ` · ${fmtInt(st.truthCrit)} truly critical` : ''}`;
    if (st.first && S.posts.length) {
      el.kFirst.textContent = fmtDur(st.first.ts - S.posts[0].ts);
      el.kFirstSub.textContent = `event clock · post #${fmtInt(st.first.n)} · ${fmtTime(st.first.ts)} UTC`;
    } else {
      el.kFirst.textContent = st.n ? 'none yet' : 'n/a';
      el.kFirstSub.textContent = 'event clock, from first post';
    }
    const o = st.o, f = st.f;
    const pct = x => fmtPct(x, 1);
    setVs('ka', o.n ? o.correct / o.n : null, f.n ? f.correct / f.n : null, pct, 1,
      `vs human labels · n=${fmtInt(o.n)}${o.n !== f.n ? ` / ${fmtInt(f.n)}` : ''}${!o.n && st.n ? ' · ours pending' : ''}`);
    setVs('kr', o.critN ? o.critTP / o.critN : null, f.critN ? f.critTP / f.critN : null, pct, 1,
      `${fmtInt(st.truthCrit)} truly critical posts so far`);
    const ci = costInfo();
    const oursCost = ci.ours != null ? st.n * ci.ours : null;
    const frCost = f.costN ? f.cost : (ci.front != null ? st.n * ci.front : null);
    const frTag = f.costN ? 'measured' : ci.frontTag;
    const tag = t => (t ? `<span class="tag tag--${t}">${t}</span>` : '');
    setVs('kc', oursCost, frCost, x => fmtUsd(x, { small: true }), Math.max(oursCost || 0, frCost || 0),
      `<span title="${esc(ci.oursNote || 'Rescue Radar serving cost per post from results/metrics.json')}">ours ${ci.ours == null ? 'n/a' : tag(ci.oursTag)}</span> · <span title="${esc(f.costN ? 'Sum of per-post cost from recorded API token counts x list price' : (ci.frontNote || ''))}">Opus ${frCost == null ? 'n/a' : tag(frTag)}</span>`);
    el.mapMeta.textContent = `${fmtInt(st.placed)} placed`;
  }

  // ---------- clock / transport ----------
  function paintClock(force) {
    const n = S.posts.length;
    if (!n) { el.clock.textContent = S.loading ? 'Loading…' : 'Select a disaster'; el.progress.textContent = '0 / 0'; return; }
    let ts = S.posts[0].ts;
    if (S.idx > 0) {
      const i = S.idx - 1;
      ts = S.posts[i].ts + Math.max(0, S.vclock - S.v[i]);
      if (S.idx < n) ts = Math.min(ts, S.posts[S.idx].ts);
    }
    el.clock.innerHTML = `${esc(fmtDateTime(ts))}<em>T+${esc(fmtDur(ts - S.posts[0].ts))}</em>`;
    el.progress.textContent = `${fmtInt(S.idx)} / ${fmtInt(n)}`;
    const now = performance.now();
    if (force || now - S.lastScrubPaint > 120) {
      S.lastScrubPaint = now;
      const frac = S.vTotal ? Math.min(1, S.vclock / S.vTotal) : 0;
      if (document.activeElement !== el.scrub) el.scrub.value = String(Math.round(frac * 1000));
      el.scrub.style.setProperty('--p', `${(frac * 100).toFixed(2)}%`);
    }
  }
  function paintTransport() {
    const done = S.posts.length && S.idx >= S.posts.length;
    el.play.innerHTML = S.playing ? `${pauseIcon()}<span>Pause</span>` : `${playIcon()}<span>${done ? 'Replay' : S.idx ? 'Resume' : 'Play'}</span>`;
    el.play.setAttribute('aria-label', S.playing ? 'Pause replay (Space)' : 'Play replay (Space)');
    el.play.disabled = !S.posts.length;
    root.querySelectorAll('[data-speed]').forEach(b => b.setAttribute('aria-pressed', String(String(S.speed) === b.dataset.speed)));
    root.querySelectorAll('[data-event]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.event === S.eventId)));
  }

  function ingest(batch, { animate = true, silent = false } = {}) {
    if (!batch.length) return;
    for (const p of batch) account(p);
    const pulseFrom = batch.length - 3;
    batch.forEach((p, i) => addMarker(p, animate && i >= pulseFrom && labelOf(p) && labelOf(p).critical));
    feedAdd(batch, animate && batch.length <= 6 && !reducedMotion());
    for (const p of batch) {
      const src = labelOf(p);
      if (src && src.critical && !queue.has(p.id)) {
        queue.add({ post_id: p.id, text: p.text, label: src.label, event: S.eventId, place: p.place || null }, { silent: true }).catch(() => {});
      }
    }
    if (!silent) paintKpis();
  }

  // step() advances the replay clock; frame() drives it from requestAnimationFrame. A slow interval keeps the
  // replay moving when the browser stops painting (hidden window, screen-share switch), at a coarser cadence.
  function step(now) {
    const dt = Math.min(1000, now - (S.last || now));
    S.last = now;
    const n = S.posts.length;
    const batch = [];
    if (S.speed === 'max') {
      const k = dt > 100 ? MAX_PER_FRAME * 6 : MAX_PER_FRAME;
      while (S.idx < n && batch.length < k) batch.push(S.posts[S.idx++]);
      S.vclock = S.idx ? S.v[S.idx - 1] : 0;
    } else {
      S.vclock += dt * BASE * S.speed;
      while (S.idx < n && S.v[S.idx] <= S.vclock) batch.push(S.posts[S.idx++]);
    }
    ingest(batch, { animate: S.speed !== 'max' && dt < 100 });
    paintClock();
    if (S.idx >= n) {
      S.vclock = S.vTotal;
      paintClock(true);
      pause();
      toast(`Replay complete: ${fmtInt(S.st.n)} posts screened, ${fmtInt(S.st.flagged)} flagged rescue-critical`, 'ok');
    }
  }
  function frame(now) {
    S.raf = 0;
    if (!S.playing) return;
    step(now);
    if (S.playing) S.raf = requestAnimationFrame(frame);
  }
  setInterval(() => {
    if (S.playing && performance.now() - S.last > 300) step(performance.now());
  }, 250);
  function play() {
    if (!S.posts.length || S.loading) return;
    if (S.idx >= S.posts.length) reset();
    S.playing = true;
    S.last = performance.now();
    paintTransport();
    if (!S.raf) S.raf = requestAnimationFrame(frame);
  }
  function pause() {
    S.playing = false;
    if (S.raf) cancelAnimationFrame(S.raf);
    S.raf = 0;
    paintTransport();
  }
  function togglePlay() { if (S.playing) pause(); else play(); }
  function clearScene() {
    S.idx = 0; S.vclock = 0; S.feedPosts = []; S.buffered = 0; S.placeCount.clear();
    if (S.layer) S.layer.clearLayers();
    S.markers.clear();
    resetStats();
  }
  function reset() {
    const was = S.playing;
    pause();
    clearScene();
    renderFeedFull();
    paintKpis();
    paintClock(true);
    paintTransport();
    if (S.map && S.event && S.event.center) S.map.setView(S.event.center, S.event.zoom || 5, { animate: false });
    if (was) play();
  }
  function seekFrac(frac) {
    if (!S.posts.length) return;
    const target = frac * S.vTotal;
    let lo = 0, hi = S.posts.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (S.v[mid] <= target) lo = mid + 1; else hi = mid; }
    const newIdx = lo;
    if (newIdx < S.idx) {
      clearScene();
      ingest(S.posts.slice(0, newIdx), { animate: false, silent: true });
    } else if (newIdx > S.idx) {
      ingest(S.posts.slice(S.idx, newIdx), { animate: false, silent: true });
    }
    S.idx = newIdx;
    S.vclock = target;
    renderFeedFull();
    paintKpis();
    paintClock(true);
    paintTransport();
  }

  async function selectEvent(id) {
    if (id === S.eventId && S.posts.length) return;
    pause();
    S.eventId = id;
    S.event = events.find(e => e.id === id) || null;
    store.set('rr-event', id);
    S.posts = []; S.v = []; S.vTotal = 0; S.loading = true;
    clearScene();
    renderFeedFull();
    paintTransport();
    paintClock(true);
    paintKpis();
    try {
      const data = await getReplay(id);
      if (S.eventId !== id) return;
      S.event = data.event || S.event;
      S.posts = (data.posts || []).slice().sort((a, b) => a.ts - b.ts);
      S.v = new Array(S.posts.length);
      let acc = 0;
      for (let i = 0; i < S.posts.length; i++) {
        if (i) acc += Math.min(GAP_CAP, Math.max(0, S.posts[i].ts - S.posts[i - 1].ts));
        S.v[i] = acc;
      }
      S.vTotal = acc || 1;
      const anyOurs = S.posts.some(p => p.ours);
      const anyFront = S.posts.some(p => p.frontier);
      S.source = anyOurs || !anyFront ? 'ours' : 'frontier';
      paintBanner(anyOurs, anyFront);
    } catch (e) {
      toast(`Could not load replay for ${S.event ? S.event.name : id}: ${errMessage(e)}`, 'error');
      el.banner.innerHTML = `<div class="err-note"><b>Replay unavailable.</b> ${esc(errMessage(e))}</div>`;
    } finally {
      S.loading = false;
    }
    if (S.map && S.event && S.event.center) S.map.setView(S.event.center, S.event.zoom || 5, { animate: false });
    renderFeedFull();
    paintKpis();
    paintClock(true);
    paintTransport();
  }
  function paintBanner(anyOurs, anyFront) {
    if (!anyOurs && anyFront) {
      el.banner.innerHTML = `<div class="banner"><b>Rescue Radar predictions pending.</b><span>No recorded Rescue Radar labels for this event yet (data/preds/rescue_radar.jsonl or rescue_radar_quick.jsonl). The feed, map and queue show Claude Opus 5.5's recorded labels until they land; Rescue Radar KPIs read n/a.</span></div>`;
    } else if (!anyOurs && !anyFront) {
      el.banner.innerHTML = `<div class="banner"><b>No recorded predictions.</b><span>Neither system has recorded labels for this event yet, so posts show as pending. Ground truth still works.</span></div>`;
    } else {
      el.banner.innerHTML = '';
    }
  }
  const cache = new Map();
  function getReplay(id) {
    if (ctx.getReplay) return ctx.getReplay(id);
    if (!cache.has(id)) cache.set(id, api.replay(id).catch(e => { cache.delete(id); throw e; }));
    return cache.get(id);
  }

  // ---------- queue panel ----------
  let qfilter = 'active';
  const qEls = new Map();
  let qPaintQueued = false;
  function qMatches(i) {
    if (qfilter === 'all') return true;
    if (qfilter === 'active') return i.status === 'open' || i.status === 'dispatched';
    return i.status === qfilter;
  }
  function qItemHTML(i) {
    const place = i.place && typeof i.place === 'object' ? i.place.name : (i.place || '');
    const t = i.created_at ? new Date(i.created_at) : null;
    return `<div class="qitem__bar"></div><div class="qitem__body">
      <div class="qitem__top">${chip(i.label)}<span>${t ? esc(t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })) : ''}</span>${place ? `<span class="post__place" title="${esc(place)}">⌖ ${esc(place)}</span>` : ''}<span class="status status--${esc(i.status)}">${esc(i.status)}${i._pending ? '…' : ''}</span></div>
      <div class="qitem__text" role="button" tabindex="0" title="${place ? 'Show on map' : 'Post text'}">${txt(i.text)}</div>
      <div class="qitem__actions">
        <button type="button" class="btn btn--sm" data-act="dispatched" aria-pressed="${i.status === 'dispatched'}">Dispatch</button>
        <button type="button" class="btn btn--sm" data-act="resolved" aria-pressed="${i.status === 'resolved'}">Resolve</button>
        <button type="button" class="btn btn--sm" data-act="dismissed" aria-pressed="${i.status === 'dismissed'}">Dismiss</button>
        <input type="text" class="qitem__note field" placeholder="Add note, Enter to save" aria-label="Dispatcher note" value="${esc(i.note || '')}" maxlength="500">
      </div></div>`;
  }
  function qKey(i) { return i.post_id; }
  function paintQueue() {
    qPaintQueued = false;
    const counts = queue.counts();
    counts.active = (counts.open || 0) + (counts.dispatched || 0);
    root.querySelectorAll('[data-count]').forEach(s => { s.textContent = fmtInt(counts[s.dataset.count] || 0); });
    el.qopen.textContent = `${fmtInt(counts.open || 0)} open`;
    const list = queue.items.filter(qMatches).slice(0, 250);
    const focused = el.qlist.contains(document.activeElement) && document.activeElement.classList.contains('qitem__note');
    const want = new Set(list.map(qKey));
    for (const [k, node] of qEls) if (!want.has(k) || !node.isConnected) { if (!(focused && node.contains(document.activeElement))) { node.remove(); qEls.delete(k); } }
    let prev = null;
    for (const i of list) {
      const k = qKey(i);
      let node = qEls.get(k);
      const sig = `${i.status}|${i.note}|${i._pending ? 1 : 0}|${i.label}|${i.qid}`;
      if (!node) {
        node = document.createElement('article');
        node.className = `qitem qitem--${i.status}${S.playing && !reducedMotion() ? ' qitem--new' : ''}`;
        node.dataset.post = k;
        node.dataset.cat = i.label || '';
        node.innerHTML = qItemHTML(i);
        node._sig = sig;
        qEls.set(k, node);
      } else if (node._sig !== sig && !node.contains(document.activeElement)) {
        node.className = `qitem qitem--${i.status}`;
        node.innerHTML = qItemHTML(i);
        node._sig = sig;
      } else if (node._sig !== sig) {
        node.className = `qitem qitem--${i.status}`;
        const s = node.querySelector('.status');
        if (s) { s.className = `status status--${i.status}`; s.textContent = i.status; }
        node.querySelectorAll('[data-act]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.act === i.status)));
        node._sig = sig;
      }
      const expectedPrev = prev ? prev.nextSibling : el.qlist.firstChild;
      if (expectedPrev !== node && !(focused && node.contains(document.activeElement))) {
        if (prev) prev.after(node); else el.qlist.prepend(node);
      }
      prev = node;
    }
    const empty = el.qlist.querySelector('.queue__empty');
    if (!list.length && !empty) el.qlist.insertAdjacentHTML('beforeend', `<div class="queue__empty">${queue.items.length ? 'Nothing in this filter.' : 'Rescue-critical posts flagged by the model land here.'}</div>`);
    if (list.length && empty) empty.remove();
  }
  function schedQueuePaint() { if (!qPaintQueued) { qPaintQueued = true; nextFrame(paintQueue); } }
  queue.on(schedQueuePaint);

  const itemFor = node => queue.byPost.get(node.closest('.qitem').dataset.post);
  el.qlist.addEventListener('click', async ev => {
    const b = ev.target.closest('[data-act]');
    if (b) {
      const item = itemFor(b);
      if (!item) return;
      const next = item.status === b.dataset.act ? 'open' : b.dataset.act;
      const note = (b.closest('.qitem').querySelector('.qitem__note') || {}).value;
      try {
        await queue.patch(item, { status: next, note: note ?? item.note ?? '' });
        toast(next === 'open' ? 'Reopened' : `${next[0].toUpperCase()}${next.slice(1)}: ${labelName(item.label)}`, 'ok', { timeout: 2000 });
      } catch { /* toast already shown */ }
      return;
    }
    const t = ev.target.closest('.qitem__text');
    if (t) focusOnMap(itemFor(t));
  });
  el.qlist.addEventListener('keydown', ev => {
    if (ev.key === 'Enter' && ev.target.classList.contains('qitem__note')) { ev.preventDefault(); ev.target.blur(); }
    if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.classList.contains('qitem__text')) { ev.preventDefault(); focusOnMap(itemFor(ev.target)); }
  });
  el.qlist.addEventListener('change', async ev => {
    if (!ev.target.classList.contains('qitem__note')) return;
    const item = itemFor(ev.target);
    if (!item || ev.target.value === (item.note || '')) return;
    try { await queue.patch(item, { status: item.status, note: ev.target.value }); toast('Note saved', 'ok', { timeout: 1600 }); } catch { /* shown */ }
  });
  function focusOnMap(item) {
    if (!item) return;
    const m = S.markers.get(item.post_id);
    if (m && S.map) {
      S.map.flyTo(m.getLatLng(), Math.max(S.map.getZoom(), 8), { duration: reducedMotion() ? 0 : 0.8 });
      const p = S.posts.find(x => x.id === item.post_id);
      if (p) m.bindPopup(popupHTML(p), { maxWidth: 300 }).openPopup();
    } else if (item.place && item.place.lat != null && S.map) {
      S.map.flyTo([item.place.lat, item.place.lng], 8, { duration: reducedMotion() ? 0 : 0.8 });
    } else {
      toast('This post has no known place to show on the map', 'info', { timeout: 2000 });
    }
  }
  root.querySelectorAll('[data-filter]').forEach(b => b.addEventListener('click', () => {
    qfilter = b.dataset.filter;
    root.querySelectorAll('[data-filter]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    el.qlist.innerHTML = '';
    qEls.clear();
    paintQueue();
  }));
  root.querySelector('#q-csv').addEventListener('click', () => queue.exportCsv());
  const clearBtn = root.querySelector('#q-clear');
  let clearArm = 0;
  clearBtn.addEventListener('click', () => {
    if (!queue.items.length) { toast('The queue is already empty', 'info', { timeout: 1800 }); return; }
    if (!clearArm) {
      clearBtn.textContent = 'Click again to clear';
      clearBtn.classList.add('btn--confirm');
      clearArm = setTimeout(() => { clearArm = 0; clearBtn.textContent = 'Clear'; clearBtn.classList.remove('btn--confirm'); }, 3000);
      return;
    }
    clearTimeout(clearArm); clearArm = 0;
    clearBtn.textContent = 'Clear';
    clearBtn.classList.remove('btn--confirm');
    el.qlist.innerHTML = '';
    qEls.clear();
    queue.clear();
  });

  // ---------- wiring ----------
  el.play.addEventListener('click', togglePlay);
  el.reset.addEventListener('click', () => { reset(); toast('Replay reset', 'info', { timeout: 1500 }); });
  root.querySelectorAll('[data-speed]').forEach(b => b.addEventListener('click', () => {
    S.speed = b.dataset.speed === 'max' ? 'max' : Number(b.dataset.speed);
    store.set('rr-speed', String(S.speed));
    paintTransport();
  }));
  root.querySelectorAll('[data-event]').forEach(b => b.addEventListener('click', () => selectEvent(b.dataset.event)));
  el.scrub.addEventListener('input', () => {
    const was = S.playing;
    if (was) pause();
    seekFrac(Number(el.scrub.value) / 1000);
    S.resumeAfterScrub = S.resumeAfterScrub || was;
  });
  el.scrub.addEventListener('change', () => { if (S.resumeAfterScrub) { S.resumeAfterScrub = false; play(); } });
  el.gt.addEventListener('change', () => setGT(el.gt.checked));
  function setGT(on) {
    S.gt = on;
    el.gt.checked = on;
    el.lgMiss.hidden = !on;
    renderFeedFull();
    repaintMarkers();
    paintKpis();
    toast(on ? 'Ground truth on: human labels shown, model mistakes marked' : 'Ground truth hidden', 'info', { timeout: 1800 });
  }

  resetStats();
  paintKpis();
  paintTransport();
  queue.load();

  let started = false;
  return {
    activate() {
      if (!started) {
        started = true;
        initMap();
        const saved = store.get('rr-event', null);
        const first = events.find(e => e.id === saved) || events[0];
        if (first) selectEvent(first.id);
      } else if (S.map) {
        setTimeout(() => S.map.invalidateSize(), 0);
      }
    },
    deactivate() {},
    togglePlay,
    reset: () => reset(),
    toggleGT: () => setGT(!S.gt),
    refreshQueue: () => queue.load(),
  };
}

function playIcon() { return '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2.5v11l9-5.5z"/></svg>'; }
function pauseIcon() { return '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z"/></svg>'; }
function resetIcon() { return '<svg viewBox="0 0 16 16" aria-hidden="true" style="fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round"><path d="M3 8a5 5 0 1 0 1.6-3.7"/><path d="M3 2.5v3h3"/></svg>'; }
function dlIcon() { return '<svg viewBox="0 0 16 16" aria-hidden="true" style="fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round"><path d="M8 2v8M4.5 6.8 8 10.3l3.5-3.5M3 13.5h10"/></svg>'; }
