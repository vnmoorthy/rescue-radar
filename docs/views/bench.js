// Benchmark: results/metrics.json and training logs, drawn with hand-rolled SVG.
import { esc, fmtPct, fmtUsd, fmtMs, fmtInt, fmtNum, labelName, shortName, isCritical, LABELS, errMessage } from '../ui.js';

const EVENT_NAMES = new Map();
export function createBench(root, ctx) {
  for (const e of (ctx.meta && ctx.meta.events) || []) EVENT_NAMES.set(e.id, e.name);
  let loaded = false;
  root.innerHTML = `<div class="view-head"><div><div class="eyebrow">View 4 · held-out evaluation</div><h1>Benchmark</h1>
    <p>Every system gets the same instructions (frontier models also get 20 examples) on 4 disasters our fine-tune never saw. Numbers below are read from <span class="mono">results/metrics.json</span> and the training logs.</p></div>
    <button type="button" class="btn btn--sm" id="bench-reload">Reload results</button></div>
    <div class="bench" id="bench-body"><div class="feed__empty"><span class="spinner"></span> Loading results…</div></div>`;
  const body = root.querySelector('#bench-body');
  root.querySelector('#bench-reload').addEventListener('click', () => load(true));

  async function load(force) {
    if (loaded && !force) return;
    loaded = true;
    body.innerHTML = '<div class="feed__empty"><span class="spinner"></span> Loading results…</div>';
    const [res, log] = await Promise.all([
      (force ? ctx.api.results() : Promise.resolve(ctx.results)).then(r => { if (force) ctx.setResults(r); return r; }).catch(e => ({ status: 'error', detail: errMessage(e) })),
      ctx.api.trainLog().catch(() => ({ runs: {} })),
    ]);
    render(res, log);
  }

  let last = null;
  // Charts use theme tokens (var(--...)); re-render on a theme switch anyway so anything computed follows it.
  window.addEventListener('rr:themechange', () => {
    if (!last) return;
    const open = Array.from(body.querySelectorAll('details')).map(d => d.open);
    render(...last);
    body.querySelectorAll('details').forEach((d, i) => { if (open[i]) d.open = true; });
  });
  function render(res, log) {
    last = [res, log];
    const systems = displaySystems(res, ctx.meta);
    const keys = orderSystems(res);
    let html = '';
    if (!res || res.status === 'pending' || !keys.length) {
      html += `<div class="panel pending-card"><div class="h-display">Benchmark pending</div>
        <p class="prose">${res && res.status === 'error' ? `Could not load results: ${esc(res.detail || '')}` : 'The evaluation has not written <span class="mono">results/metrics.json</span> yet. Training curves below update as steps land.'}</p></div>`;
    } else {
      const ev = res.eval || {};
      if (res.dev_preview) html += `<div class="banner"><b>Dev preview.</b><span>${esc(res.generated_by || 'Computed from recorded predictions, not the official evaluation.')}</span></div>`;
      html += `<div class="eyebrow">${ev.n ? `${fmtInt(ev.n)} held-out posts` : ''}${ev.test_events ? ` · ${ev.test_events} unseen disasters` : ''}${ev.split ? ` · ${esc(ev.split)}` : ''}${res.generated_at ? ` · generated ${esc(String(res.generated_at).replace('T', ' '))}` : ''}</div>`;
      const hl = res.headline || {};
      if (hl.ours && hl.ours !== 'rescue_radar' && !systems.rescue_radar) {
        html += `<div class="banner"><b>Headline is the small-data run.</b><span>Rescue Radar here is ${esc(systems[hl.ours] && systems[hl.ours].run_label || hl.ours)}, which the pre-registration (guide/PREREGISTRATION.md) lists as a data-size ablation. The pre-registered main system, the larger run's checkpoint frozen at 14:55, is not scored yet.</span></div>`;
      }
      html += `<div class="sys-cards">${keys.map((k, i) => sysCard(k, systems[k], roleOf(res, k), i)).join('')}</div>`;
      html += `<div class="bench-grid">
        <section class="panel"><div class="panel__head"><h2 class="panel__title">95% confidence intervals</h2><span class="panel__meta">bootstrap, dot = point estimate</span></div>
          <div class="panel__body">${forest(keys, systems)}</div></section>
        <section class="panel"><div class="panel__head"><h2 class="panel__title">Is the difference real?</h2></div>
          <div class="panel__body prose">${comparisons(res, systems)}</div></section>
      </div>`;
      html += `<div class="bench-grid">
        <section class="panel"><div class="panel__head"><h2 class="panel__title">F1 per category</h2><span class="panel__meta legend">${keys.slice(0, 3).map((k, i) => `<span class="s${i}"><i></i>${esc(shortSys(systems[k], k))}</span>`).join('')}</span></div>
          <div class="panel__body">${perClass(keys.slice(0, 3), systems)}</div></section>
        <section class="panel"><div class="panel__head"><h2 class="panel__title">Confusion matrix</h2><span class="panel__meta">${esc(shortSys(systems[keys[0]], keys[0]))} · rows = human label</span></div>
          <div class="panel__body">${confusion(systems[keys[0]])}</div></section>
      </div>`;
      html += `<section class="panel"><div class="panel__head"><h2 class="panel__title">Per disaster</h2><span class="panel__meta">accuracy · macro-F1 · critical recall</span></div>
        <div class="table-wrap">${perEvent(keys, systems)}</div></section>`;
    }
    html += `<section class="panel"><div class="panel__head"><h2 class="panel__title">Training loss</h2><span class="panel__meta">LoRA SFT on Fireworks serverless training</span></div>
      <div class="panel__body">${lossChart(log && log.runs)}</div></section>`;
    body.innerHTML = html;
  }

  return { activate() { load(false); }, deactivate() {} };
}

// The headline system is "Rescue Radar" everywhere in the console; which run it is goes in the card's subtitle.
// Training-set size comes from the training log header (rr.server meta.training) when available.
function displaySystems(res, meta) {
  const src = (res && res.systems) || {};
  const ours = res && res.headline && res.headline.ours;
  if (!ours || !src[ours]) return src;
  const s = src[ours];
  const tr = meta && meta.training && meta.training.system === ours ? meta.training : null;
  const run = ours === 'rescue_radar_quick' ? 'small-data run' : ours === 'rescue_radar' ? 'main run' : ours;
  const run_label = [run, tr ? `${fmtInt(tr.examples)} examples` : null, s.checkpoint_step != null ? `step ${s.checkpoint_step}` : null]
    .filter(Boolean).join(', ');
  return { ...src, [ours]: { ...s, name: 'Rescue Radar', run_label, recorded_name: s.name } };
}

function orderSystems(res) {
  if (!res || !res.systems) return [];
  const hl = res.headline || {};
  const keys = Object.keys(res.systems);
  const pri = [hl.ours, 'rescue_radar', hl.frontier, 'opus_few', hl.base, 'base_zero', 'opus_zero', 'rescue_radar_quick'];
  const out = [];
  for (const k of pri) if (k && keys.includes(k) && !out.includes(k)) out.push(k);
  for (const k of keys) if (!out.includes(k)) out.push(k);
  return out;
}
function roleOf(res, k) {
  const hl = (res && res.headline) || {};
  if (k === hl.ours || k === 'rescue_radar') return 'ours';
  if (k === hl.frontier || k === 'opus_few') return 'frontier';
  return 'other';
}
const shortSys = (s, k) => {
  const n = (s && s.name) || k;
  return n.replace(/\s*\(.*?\)\s*/g, ' ').replace(/Nemotron 3\.5 Super,? no fine-tuning/i, 'Nemotron base').trim() || k;
};
const g = (o, path) => path.split('.').reduce((a, k) => (a == null ? a : a[k]), o);

function whisker(v, ci) {
  if (v == null) return '';
  const x = t => 2 + Math.max(0, Math.min(1, t)) * 96;
  return `<svg class="whisker" viewBox="0 0 100 12" preserveAspectRatio="none" aria-hidden="true">
    <line class="track" x1="2" x2="98" y1="6" y2="6" vector-effect="non-scaling-stroke"/>
    ${ci ? `<line class="ci" x1="${x(ci[0])}" x2="${x(ci[1])}" y1="6" y2="6" vector-effect="non-scaling-stroke"/>` : ''}
    <line class="pt" x1="${x(v)}" x2="${x(v)}" y1="0.5" y2="11.5" vector-effect="non-scaling-stroke"/></svg>`;
}
function sysCard(k, s, role, i) {
  const ci = s.ci95 || {};
  const metric = (label, v, c, tip) => `<div class="metric" data-tip="${esc(tip)}">
    <div class="metric__k">${label}</div><div class="metric__v num">${v == null ? 'n/a' : (v * 100).toFixed(1)}<small>${v == null ? '' : '%'}</small></div>
    ${whisker(v, c)}<div class="metric__ci">${c ? `95% CI ${(c[0] * 100).toFixed(1)}–${(c[1] * 100).toFixed(1)}` : 'CI n/a'}</div></div>`;
  const cost = s.cost_per_1m_usd;
  const costTag = cost == null ? '' : (s.cost_measured === true || /^measured/i.test(s.cost_note || '')) ? 'measured' : 'estimated';
  const p50 = g(s, 'latency_ms.p50');
  return `<article class="panel sys-card sys-card--${role}">
    <div class="sys-card__name">${esc(s.name || k)}</div>
    <div class="sys-card__kind">${esc([s.run_label, s.kind, s.model, !s.run_label && s.checkpoint_step ? `step ${s.checkpoint_step}` : null].filter(Boolean).join(' · ') || k)}</div>
    ${s.coverage != null && s.coverage < 1 ? `<div class="sys-card__cov" title="${esc(s.coverage_note || '')}">scored on ${fmtInt(s.n)} posts (${fmtPct(s.coverage, 0)} of the eval set)</div>` : ''}
    <div class="metric-grid">
      ${metric('Macro-F1', s.macro_f1, ci.macro_f1, 'Mean F1 over the 10 categories, each category weighted equally')}
      ${metric('Accuracy', s.accuracy, ci.accuracy, 'Share of posts given the human label')}
      ${metric('Critical recall', g(s, 'critical.recall'), ci.critical_recall, 'Of posts humans marked rescue-critical, the share this system flagged as critical')}
      <div class="metric" data-tip="${esc(s.cost_note || 'Serving cost per 1M posts')}"><div class="metric__k">Cost / 1M posts</div><div class="metric__v num">${esc(fmtUsd(cost))}</div>
        <div class="metric__ci">${costTag ? `<span class="tag tag--${costTag}">${costTag}</span>` : 'n/a'}</div></div>
      <div class="metric" data-tip="Median end-to-end latency per post${g(s, 'latency_ms.p95') != null ? `; p95 ${esc(fmtMs(g(s, 'latency_ms.p95')))}` : ''}"><div class="metric__k">p50 latency</div><div class="metric__v num">${esc(fmtMs(p50))}</div>
        <div class="metric__ci">${g(s, 'latency_ms.p95') != null ? `p95 ${esc(fmtMs(g(s, 'latency_ms.p95')))}` : 'p95 n/a'}</div></div>
    </div></article>`;
}

function forest(keys, systems) {
  const metrics = [['Macro-F1', 'macro_f1', 'macro_f1'], ['Accuracy', 'accuracy', 'accuracy'], ['Critical recall', 'critical.recall', 'critical_recall']];
  const rows = [];
  for (const [label, path, ciKey] of metrics) {
    rows.push({ head: label });
    keys.forEach((k, i) => rows.push({ k, i, v: g(systems[k], path), ci: g(systems[k], `ci95.${ciKey}`), label }));
  }
  const vals = rows.flatMap(r => (r.ci ? r.ci : r.v != null ? [r.v] : []));
  if (!vals.length) return '<p class="muted">No metrics yet.</p>';
  let lo = Math.max(0, Math.floor((Math.min(...vals) - 0.03) * 20) / 20), hi = Math.min(1, Math.ceil((Math.max(...vals) + 0.03) * 20) / 20);
  if (hi - lo < 0.1) { lo = Math.max(0, lo - 0.05); hi = Math.min(1, hi + 0.05); }
  const W = 560, L = 150, R = 16, rowH = 18, headH = 22;
  let y = 6;
  const pos = rows.map(r => { const at = y; y += r.head ? headH : rowH; return at; });
  const H = y + 22;
  const x = v => L + ((v - lo) / (hi - lo)) * (W - L - R);
  const ticks = [];
  for (let t = Math.ceil(lo * 20) / 20; t <= hi + 1e-9; t += 0.05) ticks.push(+t.toFixed(2));
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Confidence intervals by system and metric">
    <g class="grid">${ticks.map(t => `<line x1="${x(t)}" x2="${x(t)}" y1="0" y2="${H - 20}"/>`).join('')}</g>
    ${ticks.map(t => `<text x="${x(t)}" y="${H - 6}" text-anchor="middle">${Math.round(t * 100)}</text>`).join('')}
    ${rows.map((r, j) => r.head
      ? `<text class="lbl" x="0" y="${pos[j] + 15}" style="font-weight:700">${esc(r.head)}</text>`
      : `<g class="s${Math.min(r.i, 4)}" data-tip="${esc(shortSys(systems[r.k], r.k))} · ${esc(r.label)}<br>${r.v == null ? 'n/a' : (r.v * 100).toFixed(1) + '%'}${r.ci ? ` (95% CI ${(r.ci[0] * 100).toFixed(1)}–${(r.ci[1] * 100).toFixed(1)})` : ''}">
          <rect x="0" y="${pos[j]}" width="${W}" height="${rowH}" fill="transparent"/>
          <text x="10" y="${pos[j] + 13}">${esc(shortSys(systems[r.k], r.k)).slice(0, 22)}</text>
          ${r.ci ? `<line x1="${x(r.ci[0])}" x2="${x(r.ci[1])}" y1="${pos[j] + 9}" y2="${pos[j] + 9}" stroke="var(--s)" stroke-width="2.5" stroke-linecap="round"/>` : ''}
          ${r.v != null ? `<circle cx="${x(r.v)}" cy="${pos[j] + 9}" r="4.5" fill="var(--s)" stroke="var(--panel)" stroke-width="1.5"/>` : ''}
        </g>`).join('')}
  </svg>`;
}

// Comparisons come in two shapes. rr/evaluate.py writes one entry per pair of systems: "delta" is the accuracy gap,
// delta_macro_f1 / delta_critical_recall sit alongside, the bootstrap holds a *_delta_ci95 per metric, and
// bootstrap.a_wins counts macro-F1 wins. guide/API.md sketches one entry per metric. Both become one row per metric.
const METRIC_NAMES = { macro_f1: 'Macro-F1', accuracy: 'Accuracy', critical_recall: 'Critical recall' };
function compRows(c) {
  const bs = c.bootstrap || {};
  const on = (side, m) => g(c, `${side}_on_shared.${m}`);
  const embedded = c.delta_macro_f1 != null || c.delta_critical_recall != null || 'macro_f1_delta_ci95' in bs;
  if (!embedded) {
    const m = c.metric || 'accuracy';
    return [{ metric: m, delta: c.delta, ci: bs.delta_ci95, wins: bs.a_wins, a: on('a', m), b: on('b', m) }];
  }
  return [
    { metric: 'macro_f1', delta: c.delta_macro_f1, ci: bs.macro_f1_delta_ci95, wins: bs.a_wins, a: on('a', 'macro_f1'), b: on('b', 'macro_f1') },
    { metric: 'accuracy', delta: c.delta, ci: bs.delta_ci95, a: on('a', 'accuracy'), b: on('b', 'accuracy') },
    { metric: 'critical_recall', delta: c.delta_critical_recall, ci: bs.critical_recall_delta_ci95, a: on('a', 'critical_recall'), b: on('b', 'critical_recall') },
  ];
}
function comparisons(res, systems) {
  const comps = (res.comparisons || []).filter(c => c && c.a && c.b);
  if (!comps.length) {
    return '<p>Paired significance tests appear here once Rescue Radar and the frontier baselines are scored on the same posts.</p>';
  }
  const hl = res.headline || {};
  const rank = c => (c.b === hl.frontier ? 0 : c.b === hl.base ? 1 : 2);
  const sorted = comps.slice().sort((x, y) => rank(x) - rank(y));
  const nm = k => esc(shortSys(systems[k], k));
  const pct = v => (v == null ? 'n/a' : `${(v * 100).toFixed(1)}%`);
  const gap = v => (v == null ? 'n/a' : `${v >= 0 ? '+' : '−'}${(Math.abs(v) * 100).toFixed(1)} pts`);
  const one = c => {
    const a = nm(c.a), b = nm(c.b);
    const bs = c.bootstrap || {}, mc = c.mcnemar || {};
    const rows = compRows(c);
    let s = `<p><b>${a}</b> vs <b>${b}</b>${c.n != null ? `, paired on the <b>${fmtInt(c.n)}</b> posts both answered` : ''}.</p>`;
    s += `<div class="table-wrap"><table class="data"><thead><tr><th>Metric</th><th class="num">${a}</th><th class="num">${b}</th><th class="num">Gap</th><th class="num">95% CI of gap</th><th>Verdict</th></tr></thead><tbody>${rows.map(r => {
      const verdict = !r.ci ? '<span class="muted">n/a</span>'
        : r.ci[0] > 0 ? `<b>${a}</b> better` : r.ci[1] < 0 ? `<b>${b}</b> better` : '<span class="muted">no clear winner</span>';
      return `<tr><td>${esc(METRIC_NAMES[r.metric] || r.metric)}</td><td class="num">${pct(r.a)}</td><td class="num">${pct(r.b)}</td><td class="num">${gap(r.delta)}</td>
        <td class="num">${r.ci ? `${gap(r.ci[0])} to ${gap(r.ci[1])}` : 'n/a'}</td><td>${verdict}</td></tr>`;
    }).join('')}</tbody></table></div>`;
    const w = rows.find(r => r.wins != null);
    if (w && bs.n) s += `<p class="muted">Bootstrap: ${fmtInt(bs.n)} resamples${bs.unit ? ` (${esc(bs.unit)})` : ''}; ${a} came out ahead on ${esc(METRIC_NAMES[w.metric] || w.metric)} in ${fmtInt(w.wins)} of them.</p>`;
    if (mc.a_only != null && mc.b_only != null) {
      const sig = mc.p != null && mc.p < 0.05;
      s += `<p>McNemar's test on per-post correctness looks only at posts where the two disagree: ${a} alone was right on <b>${fmtInt(mc.a_only)}</b>, ${b} alone on <b>${fmtInt(mc.b_only)}</b>. ${mc.p != null ? `p = ${mc.p < 1e-4 ? Number(mc.p).toExponential(1) : Number(mc.p).toFixed(4)}, so ${sig ? 'the gap is <b>very unlikely to be chance</b>' : 'the gap <b>could be chance</b>'} (threshold 0.05).` : ''}</p>`;
    }
    return s;
  };
  const hr = '<hr style="border:0;border-top:1px solid var(--line);margin:10px 0">';
  const head = sorted.filter(c => rank(c) < 2);
  const lead = head.length ? head : sorted.slice(0, 1);
  const rest = sorted.filter(c => !lead.includes(c));
  return lead.map(one).join(hr) + (rest.length
    ? `${hr}<details><summary>Other comparisons (${rest.length})</summary>${rest.map(one).join(hr)}</details>` : '');
}

function perClass(keys, systems) {
  const labels = LABELS.size ? Array.from(LABELS.keys()) : Object.keys(g(systems[keys[0]], 'per_class') || {});
  if (!labels.length || !keys.some(k => systems[k].per_class)) return '<p class="muted">Per-class scores n/a.</p>';
  const W = 560, L = 150, R = 40, barH = 7, gap = 2, groupGap = 9;
  const gh = keys.length * (barH + gap) + groupGap;
  const H = labels.length * gh + 24;
  const x = v => L + v * (W - L - R);
  let out = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="F1 per category">`;
  out += `<g class="grid">${[0, 0.25, 0.5, 0.75, 1].map(t => `<line x1="${x(t)}" x2="${x(t)}" y1="0" y2="${H - 20}"/>`).join('')}</g>`;
  out += [0, 0.25, 0.5, 0.75, 1].map(t => `<text x="${x(t)}" y="${H - 6}" text-anchor="middle">${t.toFixed(2)}</text>`).join('');
  labels.forEach((lab, li) => {
    const y0 = li * gh + 4;
    out += `<text class="lbl${isCritical(lab) ? ' lbl--crit' : ''}" x="${L - 8}" y="${y0 + (keys.length * (barH + gap)) / 2 + 3}" text-anchor="end">${esc(shortName(lab))}</text>`;
    keys.forEach((k, i) => {
      const pc = g(systems[k], `per_class.${lab}`);
      const f1 = pc && pc.f1;
      const y = y0 + i * (barH + gap);
      const tip = `${esc(labelName(lab))} · ${esc(shortSys(systems[k], k))}<br>F1 ${fmtNum(f1, 3)} · P ${fmtNum(pc && pc.precision, 3)} · R ${fmtNum(pc && pc.recall, 3)}<br>support ${fmtInt(pc && pc.support)}`;
      out += `<g class="s${Math.min(i, 4)}" data-tip="${tip}"><rect x="${L}" y="${y}" width="${W - L - R}" height="${barH}" fill="transparent"/>
        <rect x="${L}" y="${y}" width="${Math.max(0, (f1 || 0) * (W - L - R))}" height="${barH}" rx="1.5" fill="var(--s)" opacity="${i === 0 ? 1 : 0.75}"/>
        ${i === 0 && f1 != null ? `<text x="${x(f1) + 4}" y="${y + barH - 0.5}" style="font-size:9.5px">${f1.toFixed(2)}</text>` : ''}</g>`;
    });
  });
  return out + '</svg>';
}

function confusion(s) {
  const c = s && s.confusion;
  if (!c || !Array.isArray(c.matrix) || !c.matrix.length) return '<p class="muted">Confusion matrix n/a.</p>';
  const labs = c.labels || [];
  const n = labs.length;
  const cell = 36, L = 128, T = 96;
  const W = L + n * cell + 4, H = T + n * cell + 4;
  let out = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Confusion matrix">`;
  labs.forEach((lab, j) => {
    out += `<text class="lbl${isCritical(lab) ? ' lbl--crit' : ''}" transform="translate(${L + j * cell + cell / 2 + 3},${T - 6}) rotate(-50)" style="font-size:10px">${esc(shortName(lab))}</text>`;
  });
  c.matrix.forEach((row, i) => {
    const tot = row.reduce((a, b) => a + b, 0) || 1;
    out += `<text class="lbl${isCritical(labs[i]) ? ' lbl--crit' : ''}" x="${L - 6}" y="${T + i * cell + cell / 2 + 4}" text-anchor="end" style="font-size:10px">${esc(shortName(labs[i]))}</text>`;
    row.forEach((v, j) => {
      const share = v / tot;
      const diag = i === j;
      const fill = diag ? 'var(--accent)' : (isCritical(labs[i]) ? `var(--cat-${labs[i]}, var(--critical))` : 'var(--text-2)');
      out += `<g data-tip="Human: ${esc(labelName(labs[i]))}<br>Predicted: ${esc(labelName(labs[j]))}<br>${fmtInt(v)} posts · ${(share * 100).toFixed(1)}% of row">
        <rect x="${L + j * cell + 1}" y="${T + i * cell + 1}" width="${cell - 2}" height="${cell - 2}" rx="2" fill="var(--panel-3)"/>
        <rect x="${L + j * cell + 1}" y="${T + i * cell + 1}" width="${cell - 2}" height="${cell - 2}" rx="2" fill="${fill}" opacity="${v ? (0.12 + share * 0.85).toFixed(3) : 0}"/>
        ${v ? `<text class="cell-v" x="${L + j * cell + cell / 2}" y="${T + i * cell + cell / 2 + 4}" text-anchor="middle" style="font-size:10px">${v}</text>` : ''}</g>`;
    });
  });
  return out + '</svg>';
}

function perEvent(keys, systems) {
  const evs = new Set();
  keys.forEach(k => Object.keys(systems[k].per_event || {}).forEach(e => evs.add(e)));
  if (!evs.size) return '<p class="muted" style="padding:12px">Per-event scores n/a.</p>';
  const evName = e => (EVENT_NAMES.get(e) || e.replace(/_\d{4}$/, '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()));
  const cell = v => (v == null ? '<span class="muted">n/a</span>' : (v * 100).toFixed(1));
  return `<table class="data"><thead><tr><th>Disaster</th><th class="num">Posts</th>${keys.map(k => `<th class="num" colspan="3">${esc(shortSys(systems[k], k))}</th>`).join('')}</tr>
    <tr><th></th><th></th>${keys.map(() => '<th class="num">Acc</th><th class="num">F1</th><th class="num">Crit R</th>').join('')}</tr></thead>
    <tbody>${Array.from(evs).map(e => {
      const n = keys.map(k => g(systems[k], `per_event.${e}.n`)).find(v => v != null);
      return `<tr><td>${esc(evName(e))}</td><td class="num">${fmtInt(n)}</td>${keys.map(k => {
        const pe = g(systems[k], `per_event.${e}`) || {};
        return `<td class="num">${cell(pe.accuracy)}</td><td class="num">${cell(pe.macro_f1)}</td><td class="num">${cell(pe.critical_recall)}</td>`;
      }).join('')}</tr>`;
    }).join('')}</tbody></table>`;
}

function lossChart(runs) {
  const entries = Object.entries(runs || {}).filter(([, v]) => Array.isArray(v) && v.length);
  if (!entries.length) return '<p class="muted">No training steps logged yet.</p>';
  const W = 960, H = 240, L = 44, R = 16, T = 12, B = 28;
  const all = entries.flatMap(([, v]) => v);
  const maxStep = Math.max(...all.map(d => d.step));
  const maxLoss = Math.max(...all.map(d => d.loss));
  const minLoss = Math.min(0, ...all.map(d => d.loss));
  const x = s => L + ((s - 1) / Math.max(1, maxStep - 1)) * (W - L - R);
  const y = v => T + (1 - (v - minLoss) / ((maxLoss - minLoss) || 1)) * (H - T - B);
  const yt = [];
  const stepY = niceStep((maxLoss - minLoss) / 4);
  for (let t = 0; t <= maxLoss + 1e-9; t += stepY) yt.push(t);
  const xt = [];
  const stepX = niceStep(maxStep / 6);
  for (let t = stepX; t <= maxStep; t += stepX) xt.push(t);
  let out = `<div class="legend" style="margin-bottom:8px">${entries.map(([tag, v], i) => `<span class="s${i === 0 ? 1 : i === 1 ? 0 : Math.min(i, 4)}"><i></i>${esc(tag)} run · ${fmtInt(v.length)} steps · last loss ${fmtNum(v[v.length - 1].loss, 2)}</span>`).join('')}<span class="muted">faint = per step, bold = moving average</span></div>`;
  out += `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Training loss by step">
    <g class="grid">${yt.map(t => `<line x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}"/>`).join('')}</g>
    ${yt.map(t => `<text x="${L - 6}" y="${y(t) + 3}" text-anchor="end">${t}</text>`).join('')}
    ${xt.map(t => `<text x="${x(t)}" y="${H - 8}" text-anchor="middle">${t}</text>`).join('')}
    <text x="${W - R}" y="${H - 8}" text-anchor="end" style="fill:var(--muted)">step</text>`;
  entries.forEach(([tag, v], i) => {
    const cls = `s${i === 0 ? 1 : i === 1 ? 0 : Math.min(i, 4)}`;
    const pts = v.map(d => `${x(d.step).toFixed(1)},${y(d.loss).toFixed(1)}`).join(' ');
    let ema = null;
    const sm = v.map(d => { ema = ema == null ? d.loss : ema * 0.8 + d.loss * 0.2; return `${x(d.step).toFixed(1)},${y(ema).toFixed(1)}`; }).join(' ');
    out += `<g class="${cls}"><polyline points="${pts}" fill="none" stroke="var(--s)" stroke-width="1" opacity=".35"/>
      <polyline points="${sm}" fill="none" stroke="var(--s)" stroke-width="2.4" stroke-linejoin="round"/>
      ${v.map(d => `<circle cx="${x(d.step).toFixed(1)}" cy="${y(d.loss).toFixed(1)}" r="5" fill="transparent" data-tip="${esc(tag)} run · step ${d.step}<br>loss ${fmtNum(d.loss, 2)}${d.secs != null ? ` · ${fmtNum(d.secs, 1)} s/step` : ''}${d.at ? `<br>at ${esc(d.at)}` : ''}"/>`).join('')}</g>`;
  });
  return out + '</svg>';
}
function niceStep(raw) {
  if (!(raw > 0)) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const m = raw / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p;
}
