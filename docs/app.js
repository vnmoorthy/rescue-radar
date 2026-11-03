// Rescue Radar dispatch console: bootstrap, routing, theme, health, shortcuts.
import { connect, SERVER_CMD, CAN_GO_LIVE, probeLive } from './api.js';
import { setLabels, toast, errMessage, initTooltips, esc } from './ui.js';
import { QueueStore } from './queue.js';
import { createReplay } from './views/replay.js';
import { createTriage } from './views/triage.js';
import { createH2H } from './views/h2h.js';
import { createBench } from './views/bench.js';
import { createHow } from './views/how.js';
import { createLive } from './views/live.js?v=sunrise-7'; // versioned with index.html: Pages caches modules for 10 min

const VIEWS = ['replay', 'triage', 'h2h', 'bench', 'how', 'live'];
const FACTORIES = { replay: createReplay, triage: createTriage, h2h: createH2H, bench: createBench, how: createHow, live: createLive };
const root = document.documentElement;
const getTheme = () => (root.dataset.theme === 'light' ? 'light' : 'dark');

// Theme (guide/THEME.md): the inline head script picked it before first paint; this keeps the toggle in sync,
// persists explicit choices and tells charts and the map to repaint via a 'rr:themechange' event on window.
function syncToggle(t) {
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  btn.setAttribute('aria-pressed', String(t === 'dark'));
  btn.title = t === 'dark' ? 'Switch to light theme (T)' : 'Switch to dark theme (T)';
}
function setTheme(t, persist = true) {
  const changed = getTheme() !== t || root.dataset.theme !== t;
  root.dataset.theme = t;
  if (persist) { root.dataset.themeSrc = 'saved'; try { localStorage.setItem('rr-theme', t); } catch { /* ignore */ } }
  syncToggle(t);
  if (changed) window.dispatchEvent(new CustomEvent('rr:themechange', { detail: { theme: t } }));
}
const toggleTheme = () => setTheme(getTheme() === 'dark' ? 'light' : 'dark');
// No saved choice and no ?theme=: keep following the OS while the page is open.
try {
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', e => {
    if (root.dataset.themeSrc === 'os') setTheme(e.matches ? 'light' : 'dark', false);
  });
} catch { /* old browsers */ }

function paintHealth(h, mode) {
  const host = document.getElementById('health');
  if (mode === 'static') {
    host.innerHTML = `<span class="pill pill--static" title="Recorded predictions only. Live model calls need: ${esc(SERVER_CMD)}"><i class="dot"></i>Static demo<span class="lbl-long">&nbsp;· recorded data</span></span>`;
    return;
  }
  if (!h) {
    host.innerHTML = '<span class="pill pill--bad" title="The backend did not answer /api/health"><i class="dot"></i>Server unreachable</span>';
    return;
  }
  const m = h.model || {}, f = h.frontier || {};
  const pill = (ok, label, title) => `<span class="pill ${ok ? 'pill--ok' : 'pill--bad'}" title="${esc(title)}"><i class="dot"></i>${label}<span class="lbl-long">&nbsp;${ok ? 'ready' : 'offline'}</span></span>`;
  host.innerHTML = pill(!!m.ready, 'Model', `${m.name || 'Rescue Radar'}: ${m.ready ? 'ready' : 'not ready'}`)
    + pill(!!f.ready, 'Frontier', `${f.name || 'Claude Opus 5.5'}: ${f.ready ? 'ready' : 'not ready'}`);
}

async function main() {
  window.__rrBooted = true;
  const bootFail = document.getElementById('boot-fail'); if (bootFail) bootFail.remove();
  initTooltips();
  syncToggle(getTheme());
  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
  const help = document.getElementById('help');
  const openHelp = () => { help.hidden = false; help.querySelector('[data-close]').focus(); };
  const closeHelp = () => { if (!help.hidden) { help.hidden = true; document.getElementById('help-btn').focus(); } };
  document.getElementById('help-btn').addEventListener('click', openHelp);
  help.addEventListener('click', e => { if (e.target === help || e.target.closest('[data-close]')) closeHelp(); });
  help.addEventListener('keydown', e => {
    if (e.key !== 'Tab') return;
    const f = Array.from(help.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')).filter(n => !n.disabled);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && (document.activeElement === first || !help.contains(document.activeElement))) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && (document.activeElement === last || !help.contains(document.activeElement))) { e.preventDefault(); first.focus(); }
  });

  let conn;
  try {
    conn = await connect();
  } catch (e) {
    document.getElementById('view-replay').innerHTML = `<div class="err-note" style="margin:16px"><b>Could not start the console.</b>
      Neither the API (/api/health) nor the recorded data (./data/meta.json) could be loaded: ${esc(errMessage(e))}.
      Run <span class="mono">${esc(SERVER_CMD)}</span> from the repo root, or regenerate fixtures with
      <span class="mono">.venv/bin/python scripts/make_dev_fixtures.py</span>.</div>`;
    paintHealth(null, 'live');
    document.getElementById('model-badge').textContent = 'no model';
    return;
  }
  const { api, health, meta } = conn;
  setLabels(meta.labels);
  paintHealth(health, api.mode);
  // The badge leads with the step and whether these exact weights were scored, so a narrow badge never hides them.
  const paintBadge = h => {
    const badge = document.getElementById('model-badge');
    const m = { ...(meta.model || {}), ...((h && h.model) || {}) };
    const name = m.name || 'Rescue Radar';
    const step = m.step != null ? m.step : ((/\(step (\d+)\)/.exec(name) || [])[1] ?? null);
    const short = name.replace(/\s*\((?:main run, )?step \d+\)\s*$/, '');
    const live = api.mode === 'live';
    const scored = m.scored === true || !live;
    const tag = !live ? 'recorded' : scored ? 'scored' : 'training checkpoint, not scored';
    badge.innerHTML = `<b>${live ? 'LIVE' : 'REC'}</b>&nbsp;${step != null ? `<span class="mb-step">step ${esc(step)}</span> · ` : ''}`
      + `<span class="${scored ? '' : 'mb-warn'}">${esc(tag)}</span> · ${esc(short)}`;
    badge.title = `${live ? 'Live' : 'Recorded'} model: ${name}${m.kind ? ` (${m.kind})` : ''}. `
      + (!live ? 'The static demo shows the predictions the benchmark scored.'
        : scored ? `These are exactly the weights the benchmark scored${m.system ? ` as ${m.system}` : ''}.`
          : 'This checkpoint has not been scored on the held-out disasters; its numbers are not in the Benchmark.');
  };
  paintBadge(health);

  let results = null;
  const replayCache = new Map();
  const ctx = {
    api, meta, health,
    queue: new QueueStore(api),
    theme: getTheme,
    onTheme: fn => window.addEventListener('rr:themechange', e => { try { fn(e.detail.theme); } catch (err) { console.error(err); } }),
    results: null,
    resultsNow: () => results,
    setResults: r => { results = r; ctx.results = Promise.resolve(r); },
    getReplay: id => {
      if (!replayCache.has(id)) replayCache.set(id, api.replay(id).catch(e => { replayCache.delete(id); throw e; }));
      return replayCache.get(id);
    },
  };
  ctx.results = api.results().then(r => (results = r)).catch(e => (results = { status: 'error', detail: errMessage(e) }));

  const views = {};
  let current = null;
  const viewFor = name => {
    if (!views[name]) {
      const el = document.getElementById(`view-${name}`);
      try { views[name] = FACTORIES[name](el, ctx); } catch (e) {
        console.error(e);
        el.innerHTML = `<div class="err-note"><b>This view failed to load.</b> ${esc(e.message)}</div>`;
        views[name] = { activate() {}, deactivate() {} };
      }
    }
    return views[name];
  };
  function show(name, { focus = false } = {}) {
    if (!VIEWS.includes(name)) name = 'replay';
    if (current === name) return;
    if (current && views[current]) views[current].deactivate();
    current = name;
    for (const v of VIEWS) document.getElementById(`view-${v}`).hidden = v !== name;
    document.querySelectorAll('.rail__btn').forEach(b => {
      if (b.dataset.view === name) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    if (location.hash.slice(1) !== name) history.replaceState(null, '', `#${name}`);
    viewFor(name).activate();
    if (focus) document.getElementById('main').focus({ preventScroll: true });
  }
  document.querySelectorAll('.rail__btn').forEach(b => b.addEventListener('click', () => show(b.dataset.view)));
  window.addEventListener('hashchange', () => show(location.hash.slice(1)));
  viewFor('replay');
  show(location.hash.slice(1) || 'replay');

  const typing = t => t && t.closest && t.closest('input:not([type="checkbox"]):not([type="range"]), textarea, select, [contenteditable="true"]');
  const onControl = t => t && t.closest && t.closest('button, a[href], input, [role="button"], summary, [tabindex]:not(#main)');
  document.addEventListener('keydown', e => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'Escape') { closeHelp(); return; }
    if (typing(e.target)) return;
    if (e.key === '?' || (e.key === '/' && e.shiftKey)) { e.preventDefault(); if (help.hidden) openHelp(); else closeHelp(); return; }
    if (!help.hidden) return;
    if (/^[1-6]$/.test(e.key)) { e.preventDefault(); show(VIEWS[Number(e.key) - 1]); return; }
    if (e.key === ' ' || e.code === 'Space') {
      if (current !== 'replay' || onControl(e.target)) return;
      e.preventDefault();
      viewFor('replay').togglePlay();
      return;
    }
    const k = e.key.toLowerCase();
    if (k === 't') toggleTheme();
    else if (k === 'r' && current === 'replay') viewFor('replay').reset();
    else if (k === 'g' && current === 'replay') viewFor('replay').toggleGT();
  });
  document.addEventListener('keyup', e => { if ((e.key === ' ' || e.code === 'Space') && current === 'replay' && !typing(e.target) && !onControl(e.target)) e.preventDefault(); });

  if (api.mode === 'live') {
    let lastOk = true;
    setInterval(async () => {
      try {
        const h = await api.health();
        paintHealth(h, 'live');
        paintBadge(h);
        if (h && h.frontier && h.frontier.name) { meta.frontier = { ...(meta.frontier || {}), name: h.frontier.name }; document.dispatchEvent(new CustomEvent('rr:health', { detail: h })); }
        if (!lastOk) toast('Server connection restored', 'ok');
        lastOk = true;
      } catch (e) {
        paintHealth(null, 'live');
        if (lastOk) toast(`Lost connection to the server: ${errMessage(e)}`, 'error');
        lastOk = false;
      }
    }, 20000);
  } else {
    toast('Static demo: recorded predictions only. Live classification needs the local server.', 'info', { timeout: 5200 });
    if (CAN_GO_LIVE) {
      // We fell back to recorded data on a host that can have the live server (e.g. reloaded while rr.server was
      // restarting). Switch back as soon as it answers instead of staying on recorded data.
      const retry = setInterval(async () => {
        try {
          if (await probeLive()) { clearInterval(retry); toast('Live server is back: reloading in live mode', 'ok'); setTimeout(() => location.reload(), 900); }
        } catch (e) { if (e && e.status === 404) clearInterval(retry); /* static host: no /api here */ }
      }, 8000);
    }
  }
  window.addEventListener('unhandledrejection', ev => { console.error(ev.reason); toast(errMessage(ev.reason), 'error'); });
}

main();
