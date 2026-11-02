// Head-to-Head: one post through both systems live, plus a recorded 20-post race (no live calls).
import { esc, txt, chip, fmtMs, fmtUsd, fmtPct, fmtInt, toast, errMessage, isCritical, reducedMotion, labelName } from '../ui.js';
import { staticNote } from './triage.js';

const EXAMPLES = [
  'Please help, my parents are stuck on the roof in Treasure Cay and the water keeps rising. No phone signal, last message 2 hours ago',
  'Our church is collecting blankets, water and baby formula for families displaced by the floods. Drop off at 5th and Main',
  'Confirmed: 3 dead and dozens injured in Mirpur after the 5.8 quake, hospitals overwhelmed',
];
const TIME_SCALE = 0.25; // the recorded race plays at 4x speed

export function createH2H(root, ctx) {
  const { api, meta } = ctx;
  const oursName = (meta.model && meta.model.name) || 'Rescue Radar';
  const frName = (meta.frontier && meta.frontier.name) || 'Claude Opus 5.5';
  root.innerHTML = `
    <div class="view-head">
      <div><div class="eyebrow">View 3 · same prompt, same post</div><h1>Head-to-head</h1>
      <p>Our fine-tuned open model against the frontier model on the same post: label, latency and what each call costs.</p></div>
    </div>
    <section class="panel" aria-label="Live comparison">
      <div class="panel__head"><h2 class="panel__title">Live comparison</h2><span class="panel__meta">2 live model calls per run</span></div>
      <div class="panel__body">
        <div class="h2h-input">
          <label class="sr-only" for="h2h-text">Post to compare</label>
          <textarea id="h2h-text" rows="3" placeholder="Paste one post…">${esc(EXAMPLES[0])}</textarea>
          <div class="stack">
            <button type="button" class="btn btn--primary" id="h2h-go">Compare</button>
            <button type="button" class="btn btn--ghost btn--sm" id="h2h-ex">Another example</button>
          </div>
        </div>
        <div id="h2h-out">${versusHTML(null, null)}</div>
      </div>
    </section>
    <section class="panel race" aria-label="Recorded race">
      <div class="panel__head"><h2 class="panel__title">Recorded race · 20 random test posts</h2>
        <span class="panel__meta"><span>replays recorded predictions at 4x speed, no live calls</span><button type="button" class="btn btn--primary btn--sm" id="race-go">Run 20 random test posts</button></span></div>
      <div class="lanes" id="lanes">
        ${laneHTML('ours', 'Rescue Radar', 'recorded predictions on the held-out set')}
        ${laneHTML('fr', 'Claude Opus 5.5', 'recorded 20-shot predictions (opus_few)')}
      </div>
      <div class="table-wrap" id="race-table"></div>
    </section>`;
  const $ = s => root.querySelector(s);
  const ta = $('#h2h-text'), out = $('#h2h-out'), go = $('#h2h-go');
  let exI = 0;
  $('#h2h-ex').addEventListener('click', () => { exI = (exI + 1) % EXAMPLES.length; ta.value = EXAMPLES[exI]; ta.focus(); });
  ta.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); compare(); } });
  go.addEventListener('click', compare);

  function costPerCall(sysKey) {
    const r = ctx.resultsNow();
    if (!r || !r.systems) return { v: null, tag: null };
    const hl = r.headline || {};
    const s = r.systems[hl[sysKey] || (sysKey === 'ours' ? 'rescue_radar' : 'opus_few')];
    if (!s || s.cost_per_1m_usd == null) return { v: null, tag: null, note: null };
    return { v: s.cost_per_1m_usd / 1e6, tag: s.cost_measured === true || /^measured/i.test(s.cost_note || '') ? 'measured' : 'estimated', note: s.cost_note };
  }

  function versusHTML(ours, fr, state = 'idle') {
    const oc = costPerCall('ours');
    const card = (who, name, model, r, cost, costTag, costNote) => `
      <div class="panel fighter fighter--${who}">
        <div class="fighter__who"><span class="fighter__name">${esc(name)}</span></div>
        <div class="fighter__model">${esc(model)}</div>
        <div class="fighter__label">${state === 'loading' ? '<span class="spinner"></span><span class="muted">classifying…</span>'
          : r ? `${chip(r.label, { full: true })}${(r.critical ?? isCritical(r.label)) ? '<span class="crit-flag">● rescue-critical</span>' : ''}` : '<span class="muted">Run a comparison to see the label.</span>'}</div>
        <div class="fighter__stats">
          <div class="fstat"><div class="fstat__k">Latency</div><div class="fstat__v num">${r ? esc(fmtMs(r.latency_ms)) : '·'}</div><div class="fstat__n">end to end</div></div>
          <div class="fstat"><div class="fstat__k">Cost / call</div><div class="fstat__v num">${r ? esc(fmtUsd(cost, { small: true })) : '·'}</div>
            <div class="fstat__n" title="${esc(costNote || '')}">${r && cost != null ? `<span class="tag tag--${costTag}">${costTag}</span>` : r ? 'n/a' : ''}</div></div>
          <div class="fstat"><div class="fstat__k">Per 1M posts</div><div class="fstat__v num">${r && cost != null ? esc(fmtUsd(cost * 1e6)) : '·'}</div><div class="fstat__n">at this rate</div></div>
        </div>
      </div>`;
    const agree = ours && fr ? (ours.label === fr.label ? `Both say <b>${esc(labelName(ours.label))}</b>.` : `They disagree: ${esc(labelName(ours.label))} vs ${esc(labelName(fr.label))}.`) : '';
    return `<div class="versus">
      ${card('ours', 'Rescue Radar', (ours && ours.model) || oursName, ours, oc.v, oc.tag, oc.note)}
      <div class="versus__vs" aria-hidden="true">VS</div>
      ${card('frontier', ((fr && fr.model) || frName).replace(/\s*\(.*\)\s*$/, ''), (fr && fr.model) || frName, fr, fr ? fr.cost_usd : null, 'measured', 'This call: API token counts x the provider list price')}
    </div>${agree ? `<div class="agree">${agree}</div>` : ''}`;
  }

  async function compare() {
    const text = ta.value.trim();
    if (!text) { toast('Paste a post to compare', 'warn'); ta.focus(); return; }
    go.disabled = true;
    out.innerHTML = versusHTML(null, null, 'loading');
    try {
      const res = await api.compare(text);
      out.innerHTML = versusHTML(res.ours, res.frontier);
    } catch (e) {
      if (e.isStatic) out.innerHTML = staticNote('A live head-to-head');
      else { out.innerHTML = `<div class="err-note"><b>Comparison failed.</b> ${esc(errMessage(e))}</div>${versusHTML(null, null)}`; toast(errMessage(e), 'error'); }
    } finally {
      go.disabled = false;
    }
  }

  // ---------- recorded race ----------
  let racing = null;
  $('#race-go').addEventListener('click', race);
  async function race() {
    if (racing) { racing.cancel = true; }
    const token = { cancel: false };
    racing = token;
    const btn = $('#race-go');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Loading posts…';
    let pool = [];
    try {
      const all = await Promise.all((meta.events || []).map(e => ctx.getReplay(e.id).then(d => d.posts || []).catch(() => [])));
      pool = all.flat().filter(p => p.frontier || p.ours);
    } catch (e) { toast(`Could not load recorded predictions: ${errMessage(e)}`, 'error'); }
    btn.disabled = false;
    btn.textContent = 'Run 20 random test posts';
    if (!pool.length) { toast('No recorded predictions available for the race yet', 'warn'); racing = null; return; }
    const both = pool.filter(p => p.frontier && p.ours);
    const src = both.length >= 20 ? both : pool;
    const picks = [];
    const used = new Set();
    while (picks.length < Math.min(20, src.length)) {
      const i = Math.floor(Math.random() * src.length);
      if (!used.has(i)) { used.add(i); picks.push(src[i]); }
    }
    const oursCost = costPerCall('ours');
    const frCostFallback = costPerCall('frontier');
    const lanes = {
      ours: { done: 0, ok: 0, cost: 0, t: 0, el: root.querySelector('[data-lane="ours"]'), costTag: oursCost.tag },
      fr: { done: 0, ok: 0, cost: 0, t: 0, el: root.querySelector('[data-lane="fr"]'), costTag: 'measured' },
    };
    for (const l of Object.values(lanes)) {
      l.el.querySelectorAll('.lane__track i').forEach(c => { c.className = ''; c.removeAttribute('data-tip'); });
      paintTally(l, picks.length);
    }
    const table = $('#race-table');
    table.innerHTML = `<table class="data race-table"><thead><tr><th>#</th><th>Post</th><th>Human label</th><th>Rescue Radar</th><th>Claude Opus 5.5</th></tr></thead><tbody>
      ${picks.map((p, i) => `<tr data-row="${i}"><td class="num">${i + 1}</td><td>${txt(p.text.length > 140 ? p.text.slice(0, 140) + '…' : p.text)}</td><td>${chip(p.truth)}</td><td data-c="ours"><span class="muted">·</span></td><td data-c="fr"><span class="muted">·</span></td></tr>`).join('')}
    </tbody></table>`;
    const runLane = async (key) => {
      const l = lanes[key];
      const cells = l.el.querySelectorAll('.lane__track i');
      for (let i = 0; i < picks.length; i++) {
        const p = picks[i];
        const r = key === 'ours' ? p.ours : p.frontier;
        if (!r) {
          l.missing = (l.missing || 0) + 1;
          paintTally(l, picks.length);
          cells[i].className = 'pending';
          cells[i].setAttribute('data-tip', 'No recorded prediction yet');
          table.querySelector(`[data-row="${i}"] [data-c="${key}"]`).innerHTML = '<span class="chip chip--none">pending</span>';
          continue;
        }
        const lat = r.latency_ms ?? 0;
        if (!reducedMotion()) await sleep(Math.max(60, lat * TIME_SCALE));
        if (token.cancel) return;
        l.done++;
        l.t += lat;
        const ok = r.label === p.truth;
        if (ok) l.ok++;
        const c = key === 'ours' ? oursCost.v : (r.cost_usd ?? frCostFallback.v);
        if (c != null) l.cost += c; else l.costMissing = true;
        cells[i].className = ok ? 'ok' : 'bad';
        cells[i].setAttribute('data-tip', `#${i + 1} ${esc(labelName(r.label))}<br>human: ${esc(labelName(p.truth))}<br>${esc(fmtMs(lat))}`);
        table.querySelector(`[data-row="${i}"] [data-c="${key}"]`).innerHTML = `${chip(r.label)} ${ok ? '<span class="tag tag--ok">✓</span>' : '<span class="tag tag--bad">✗</span>'}`;
        paintTally(l, picks.length);
      }
    };
    await Promise.all([runLane('ours'), runLane('fr')]);
    if (token.cancel) return;
    racing = null;
    const o = lanes.ours, f = lanes.fr;
    if (o.done && f.done) toast(`Race done: Rescue Radar ${o.ok}/${o.done} correct, Claude Opus 5.5 ${f.ok}/${f.done} correct`, 'ok');
    else toast(`Race done: Claude Opus 5.5 ${f.ok}/${f.done} correct; Rescue Radar predictions pending`, 'info');
  }
  function paintTally(l, n) {
    const acc = l.done ? l.ok / l.done : null;
    l.el.querySelector('.lane__tally').innerHTML = l.done
      ? `<b>${fmtInt(l.ok)}/${fmtInt(l.done)}</b> correct (${fmtPct(acc, 0)}) · ${esc(fmtMs(l.t))} total<br>cost ${l.costMissing && !l.cost ? 'n/a' : esc(fmtUsd(l.cost, { small: true }))} ${l.costTag ? `<span class="tag tag--${l.costTag}">${l.costTag}</span>` : ''}`
      : l.missing ? `<span class="muted">no recorded predictions yet for ${fmtInt(l.missing)} of ${n} posts (pending)</span>` : `<span class="muted">0/${n} · waiting</span>`;
  }

  return { activate() {}, deactivate() {} };
}

function laneHTML(key, name, model) {
  return `<div class="lane" data-lane="${key}">
    <div class="lane__name">${esc(name)}<small>${esc(model)}</small></div>
    <div class="lane__track" aria-label="${esc(name)} results">${'<i></i>'.repeat(20)}</div>
    <div class="lane__tally"><span class="muted">press Run to start</span></div></div>`;
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
