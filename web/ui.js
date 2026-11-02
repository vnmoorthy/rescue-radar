// Shared UI helpers: escaping, formatting, label chips, toasts, tooltips, count-up numbers.

export const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// Tweets arrive with HTML entities (&amp;) still encoded; decode the common ones, then escape for display.
const ENT = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'", '&#039;': "'", '&nbsp;': ' ' };
export const txt = s => esc(String(s ?? '').replace(/&(?:amp|lt|gt|quot|#0?39|nbsp);/g, m => ENT[m]));

// ---- label registry (filled from /api/meta) ----
export const LABELS = new Map();
export const CRITICAL = new Set(['requests_or_urgent_needs', 'injured_or_dead_people', 'missing_or_found_people']);
export function setLabels(list) {
  LABELS.clear();
  if (Array.isArray(list) && list.length) {
    CRITICAL.clear();
    for (const l of list) {
      LABELS.set(l.id, l);
      if (l.critical) CRITICAL.add(l.id);
    }
  }
}
export const labelName = id => (LABELS.get(id) && LABELS.get(id).name) || (id ? id.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase()) : 'n/a');
export const isCritical = id => CRITICAL.has(id);
const SHORT = {
  requests_or_urgent_needs: 'Urgent request', injured_or_dead_people: 'Injured / dead', missing_or_found_people: 'Missing / found',
  displaced_people_and_evacuations: 'Displaced / evac', infrastructure_and_utility_damage: 'Infrastructure',
  caution_and_advice: 'Caution / advice', rescue_volunteering_or_donation_effort: 'Volunteer / donate',
  sympathy_and_support: 'Sympathy', other_relevant_information: 'Other info', not_humanitarian: 'Not humanitarian',
};
export const shortName = id => SHORT[id] || labelName(id);

export function chip(id, { full = false, title = null } = {}) {
  if (!id) return '<span class="chip chip--none">pending</span>';
  const crit = isCritical(id);
  const def = (LABELS.get(id) && LABELS.get(id).definition) || '';
  return `<span class="chip${crit ? ' chip--crit' : ''}" data-cat="${esc(id)}" title="${esc(title || `${labelName(id)}${def ? ': ' + def : ''}`)}">${esc(full ? labelName(id) : shortName(id))}</span>`;
}

// ---- formatting ----
const nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
export const fmtInt = n => (n == null || !isFinite(n) ? 'n/a' : nf0.format(Math.round(n)));
export const fmtPct = (x, d = 1) => (x == null || !isFinite(x) ? 'n/a' : `${(x * 100).toFixed(d)}%`);
export const fmtNum = (x, d = 3) => (x == null || !isFinite(x) ? 'n/a' : Number(x).toFixed(d));
export function fmtUsd(x, { small = false } = {}) {
  if (x == null || !isFinite(x)) return 'n/a';
  if (x === 0) return '$0';
  if (small || Math.abs(x) < 0.01) {
    if (Math.abs(x) < 0.0001) return `$${x.toExponential(1)}`;
    return `$${x.toFixed(Math.abs(x) < 0.001 ? 5 : 4)}`;
  }
  if (Math.abs(x) < 100) return `$${x.toFixed(2)}`;
  return `$${nf0.format(Math.round(x))}`;
}
export const fmtMs = ms => (ms == null || !isFinite(ms) ? 'n/a' : ms >= 10000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);
export function fmtDur(ms) {
  if (ms == null || !isFinite(ms)) return 'n/a';
  const s = Math.max(0, Math.round(ms / 1000));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${String(m).padStart(2, '0')}m`;
  if (m) return `${m}m ${String(s % 60).padStart(2, '0')}s`;
  return `${s}s`;
}
const dtf = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', hour12: false });
const tf = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'UTC', hour12: false });
const df = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' });
export const fmtDateTime = ts => (ts ? `${dtf.format(new Date(ts)).replace(',', '')} UTC` : 'n/a');
export const fmtTime = ts => (ts ? tf.format(new Date(ts)) : '');
export const fmtDay = ts => (ts ? df.format(new Date(ts)) : '');

// ---- toasts ----
export function toast(msg, kind = 'info', { timeout = 4200 } = {}) {
  const host = document.getElementById('toasts');
  if (!host) return;
  const el = document.createElement('div');
  el.className = `toast toast--${kind}`;
  el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  el.innerHTML = `<div>${esc(msg)}</div><button type="button" aria-label="Dismiss notification">×</button>`;
  const close = () => { el.classList.add('toast--out'); setTimeout(() => el.remove(), 220); };
  el.querySelector('button').addEventListener('click', close);
  host.appendChild(el);
  while (host.children.length > 4) host.firstElementChild.remove();
  if (timeout) setTimeout(close, kind === 'error' ? timeout * 2 : timeout);
}
export function errMessage(e) {
  if (!e) return 'Unknown error';
  if (e.status === 503) return `Model unavailable (503): ${e.detail || e.message}`;
  if (e.status) return `Error ${e.status}: ${e.detail || e.message}`;
  return e.message || String(e);
}

// ---- tooltip (delegated: any element with data-tip) ----
export function initTooltips() {
  const tip = document.getElementById('tooltip');
  if (!tip) return;
  let cur = null;
  const place = ev => {
    const pad = 14;
    let x = ev.clientX + pad, y = ev.clientY + pad;
    const r = tip.getBoundingClientRect();
    if (x + r.width > window.innerWidth - 8) x = ev.clientX - r.width - pad;
    if (y + r.height > window.innerHeight - 8) y = ev.clientY - r.height - pad;
    tip.style.left = `${Math.max(8, x)}px`;
    tip.style.top = `${Math.max(8, y)}px`;
  };
  document.addEventListener('mouseover', ev => {
    const t = ev.target.closest && ev.target.closest('[data-tip]');
    if (t === cur) return;
    cur = t;
    if (!t) { tip.hidden = true; return; }
    tip.innerHTML = t.getAttribute('data-tip');
    tip.hidden = false;
    place(ev);
  });
  document.addEventListener('mousemove', ev => { if (cur) place(ev); });
  document.addEventListener('scroll', () => { tip.hidden = true; cur = null; }, true);
}

// Run fn on the next animation frame, or after 120 ms if the browser is not painting (hidden window).
export function nextFrame(fn) {
  let done = false;
  const run = t => { if (done) return; done = true; fn(t ?? performance.now()); };
  requestAnimationFrame(run);
  setTimeout(run, 120);
}

// ---- count-up numbers: time-based tween toward the latest target ----
const tweens = new Map();
let tweenQueued = false;
const TWEEN_MS = 450;
export function countTo(el, target, format = fmtInt) {
  if (!el) return;
  if (target == null || !isFinite(target)) { tweens.delete(el); el.textContent = format(null); el._v = null; return; }
  if (reducedMotion() || el._v == null) { el._v = target; el.textContent = format(target); tweens.delete(el); return; }
  if (el._v === target) return;
  const t = tweens.get(el);
  if (t && t.target === target) return;
  tweens.set(el, { from: el._v, target, format, t0: performance.now() });
  queueTweens();
}
function queueTweens() {
  if (tweenQueued) return;
  tweenQueued = true;
  nextFrame(stepTweens);
}
function stepTweens() {
  tweenQueued = false;
  const now = performance.now();
  for (const [el, t] of tweens) {
    const k = Math.min(1, (now - t.t0) / TWEEN_MS);
    const e = 1 - Math.pow(1 - k, 3);
    const v = k >= 1 ? t.target : t.from + (t.target - t.from) * e;
    el._v = v;
    el.textContent = t.format(v);
    if (k >= 1) tweens.delete(el);
  }
  if (tweens.size) queueTweens();
}

export function downloadText(filename, text, type = 'text/csv') {
  const blob = new Blob([text], { type });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}
export function csvCell(v) {
  const s = v == null ? '' : String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
export function hashId(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0).toString(36);
}
export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
