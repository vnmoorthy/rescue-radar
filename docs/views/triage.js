// Triage Desk: paste posts (one per line), classify them live, push critical ones to the queue.
import { esc, chip, fmtMs, fmtInt, toast, errMessage, hashId, isCritical } from '../ui.js';
import { SERVER_CMD } from '../api.js';

const SAMPLES = {
  'Trapped / rising water': [
    'Water is up to the second floor at our house on Bay St in Marsh Harbour, 3 adults and 2 kids on the roof. Please send a boat',
    'My grandmother is stuck in her apartment in Freeport, no power, needs insulin and the road is flooded. Can anyone reach her?',
    'We are trapped in the attic with our dog in Freeport, water still rising. 41 Pine Ridge Rd. Call 242-555-0187',
  ],
  'Injured / missing': [
    'Two people injured after the roof collapsed at the school shelter in Beira, they need medical help urgently',
    'Still no word from my brother since the cyclone hit Chimanimani. Last seen near the bridge, wearing a red jacket #Idai',
    'Rescue teams just pulled a family of four alive from the rubble in Mirpur, one child taken to hospital',
  ],
  'Everyday noise': [
    'Praying for everyone in the path of the storm tonight. Stay safe Bahamas',
    'The governor has ordered mandatory evacuation for all coastal zones starting 6pm tomorrow',
    'Donate to the Red Cross flood relief fund here, every dollar goes to families in Nebraska',
    'Power lines down across Highway 34 near Pacific Junction, avoid the area',
    'Watching the game tonight no matter what lol',
  ],
};

export function createTriage(root, ctx) {
  const { api, queue } = ctx;
  root.innerHTML = `
    <div class="view-head">
      <div><div class="eyebrow">View 2 · live model</div><h1>Triage desk</h1>
      <p>Paste posts, one per line. Each is PII-scrubbed and classified by the live Rescue Radar model; rescue-critical ones can go straight to the dispatcher queue.</p></div>
    </div>
    <div class="triage">
      <section class="panel" aria-label="Posts to classify">
        <div class="panel__head"><h2 class="panel__title">Posts</h2><span class="panel__meta" id="tr-count">0 posts</span></div>
        <div class="panel__body">
          <label class="sr-only" for="tr-text">Posts, one per line</label>
          <textarea id="tr-text" spellcheck="false" placeholder="One post per line, up to 200.&#10;e.g. Trapped on the roof with two kids at 14 Shore Rd, water rising, please send help"></textarea>
          <div class="samples" role="group" aria-label="Sample posts">
            ${Object.keys(SAMPLES).map(k => `<button type="button" class="btn btn--sm btn--ghost" data-sample="${esc(k)}">+ ${esc(k)}</button>`).join('')}
          </div>
          <div class="triage__actions">
            <button type="button" class="btn btn--primary" id="tr-go">Classify</button>
            <span class="btn file-btn">Upload CSV / TXT<input type="file" id="tr-file" accept=".csv,.txt,text/csv,text/plain" aria-label="Upload CSV or TXT file"></span>
            <button type="button" class="btn btn--ghost" id="tr-clear">Clear</button>
            <span class="muted" id="tr-hint">Ctrl/⌘ + Enter to classify</span>
          </div>
        </div>
      </section>
      <section class="panel" aria-label="Results">
        <div class="panel__head"><h2 class="panel__title">Results</h2><span class="panel__meta" id="tr-meta"></span></div>
        <div class="panel__body" id="tr-out"><div class="feed__empty">Results appear here. Rescue-critical rows are highlighted.</div></div>
      </section>
    </div>`;
  const $ = s => root.querySelector(s);
  const ta = $('#tr-text'), out = $('#tr-out'), go = $('#tr-go'), meta = $('#tr-meta'), count = $('#tr-count');
  let rows = [];

  const lines = () => ta.value.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  const updateCount = () => { const n = lines().length; count.textContent = `${fmtInt(n)} post${n === 1 ? '' : 's'}${n > 200 ? ' (max 200)' : ''}`; };
  ta.addEventListener('input', updateCount);
  ta.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); run(); } });
  root.querySelectorAll('[data-sample]').forEach(b => b.addEventListener('click', () => {
    const add = SAMPLES[b.dataset.sample];
    ta.value = [...lines(), ...add].join('\n');
    updateCount();
    ta.focus();
  }));
  $('#tr-clear').addEventListener('click', () => {
    ta.value = ''; rows = []; updateCount(); meta.textContent = '';
    out.innerHTML = '<div class="feed__empty">Results appear here. Rescue-critical rows are highlighted.</div>';
  });
  $('#tr-file').addEventListener('change', async e => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    try {
      const text = await f.text();
      const got = /\.csv$/i.test(f.name) || f.type === 'text/csv' ? parseCsvPosts(text) : text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
      ta.value = got.slice(0, 200).join('\n');
      updateCount();
      toast(`Loaded ${fmtInt(Math.min(200, got.length))} posts from ${f.name}${got.length > 200 ? ' (first 200)' : ''}`, 'ok');
    } catch (err) {
      toast(`Could not read ${f.name}: ${err.message}`, 'error');
    } finally {
      e.target.value = '';
    }
  });
  go.addEventListener('click', run);

  async function run() {
    const texts = lines();
    if (!texts.length) { toast('Add at least one post, or click a sample', 'warn'); ta.focus(); return; }
    if (texts.length > 200) { toast('Up to 200 posts per batch: only the first 200 will be sent', 'warn'); }
    const batch = texts.slice(0, 200);
    go.disabled = true;
    go.innerHTML = '<span class="spinner"></span> Classifying…';
    meta.textContent = '';
    out.innerHTML = `<div class="feed__empty"><span class="spinner"></span> Classifying ${fmtInt(batch.length)} post${batch.length === 1 ? '' : 's'} with the live model…</div>`;
    const t0 = performance.now();
    try {
      const res = await api.classifyBatch(batch);
      rows = (res.results || []).map((r, i) => ({ ...r, text: batch[i] }));
      const crit = rows.filter(r => r.critical ?? isCritical(r.label)).length;
      meta.textContent = `${fmtInt(rows.length)} classified · ${fmtInt(crit)} critical · ${fmtMs(res.total_ms ?? performance.now() - t0)} total`;
      render();
      toast(`Classified ${fmtInt(rows.length)} posts: ${fmtInt(crit)} rescue-critical`, crit ? 'warn' : 'ok');
    } catch (e) {
      if (e.isStatic) {
        out.innerHTML = staticNote('Live classification');
      } else {
        out.innerHTML = `<div class="err-note"><b>Classification failed.</b> ${esc(errMessage(e))}</div>`;
        toast(errMessage(e), 'error');
      }
    } finally {
      go.disabled = false;
      go.textContent = 'Classify';
    }
  }

  function render() {
    out.innerHTML = `<div class="table-wrap"><table class="data">
      <thead><tr><th>Category</th><th>Critical</th><th class="num">Latency</th><th>Post (PII redacted)</th><th>Place</th><th></th></tr></thead>
      <tbody>${rows.map((r, i) => {
        const crit = r.critical ?? isCritical(r.label);
        const place = r.place ? (typeof r.place === 'object' ? r.place.name : r.place) : '';
        const pid = `triage-${hashId(r.redacted_text || r.text)}`;
        const inQ = queue.has(pid);
        return `<tr class="${crit ? 'row--crit' : ''}">
          <td>${chip(r.label)}</td>
          <td>${crit ? '<span class="crit-flag">● critical</span>' : '<span class="muted">no</span>'}</td>
          <td class="num">${esc(fmtMs(r.latency_ms))}</td>
          <td>${highlight(r.redacted_text ?? r.text, r.redactions)}</td>
          <td>${place ? `⌖ ${esc(place)}` : '<span class="muted">none</span>'}</td>
          <td>${crit ? `<button type="button" class="btn btn--sm" data-add="${i}" ${inQ ? 'disabled' : ''}>${inQ ? 'Queued' : 'Add to queue'}</button>` : ''}</td></tr>`;
      }).join('')}</tbody></table></div>`;
  }
  out.addEventListener('click', async e => {
    const b = e.target.closest('[data-add]');
    if (!b) return;
    const r = rows[Number(b.dataset.add)];
    const pid = `triage-${hashId(r.redacted_text || r.text)}`;
    b.disabled = true;
    b.textContent = 'Queued';
    try {
      await queue.add({ post_id: pid, text: r.redacted_text || r.text, label: r.label, event: 'triage', place: r.place || null });
    } catch (err) {
      b.disabled = false;
      b.textContent = 'Add to queue';
    }
  });

  return { activate() {}, deactivate() {} };
}

// Highlight redaction spans. Spans index into redacted_text; if they do not line up, fall back to [TAG] tokens.
function highlight(text, spans) {
  const s = String(text || '');
  const valid = Array.isArray(spans) && spans.length && spans.every(r => Number.isInteger(r.start) && Number.isInteger(r.end) && r.start >= 0 && r.end <= s.length && r.start < r.end);
  if (valid) {
    let out = '', at = 0;
    for (const r of spans.slice().sort((a, b) => a.start - b.start)) {
      if (r.start < at) continue;
      out += esc(s.slice(at, r.start)) + `<mark class="redact" title="${esc(r.type || 'redacted')}">${esc(s.slice(r.start, r.end))}</mark>`;
      at = r.end;
    }
    return out + esc(s.slice(at));
  }
  return esc(s).replace(/\[(?:[A-Z_]{2,20})\]|@user|█+/g, m => `<mark class="redact">${m}</mark>`);
}

function parseCsvPosts(text) {
  const rows = [];
  let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (c === '"') q = false; else cell += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n' || c === '\r') { if (c === '\r' && text[i + 1] === '\n') i++; row.push(cell); rows.push(row); row = []; cell = ''; }
    else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  if (!rows.length) return [];
  const head = rows[0].map(h => h.trim().toLowerCase());
  let col = head.findIndex(h => ['text', 'post', 'tweet', 'tweet_text', 'message', 'content'].includes(h));
  const body = col >= 0 ? rows.slice(1) : rows;
  if (col < 0) {
    // no header: pick the column with the longest average text
    const widths = (rows[0] || []).map((_, j) => rows.reduce((a, r) => a + (r[j] || '').length, 0));
    col = widths.indexOf(Math.max(...widths));
  }
  return body.map(r => (r[col] || '').trim()).filter(Boolean);
}

export function staticNote(what) {
  return `<div class="static-note"><h3>${esc(what)} needs the local server</h3>
    <p>This copy of the console is running on recorded data (static mode), so it cannot call the models. Everything recorded still works: the live replay, the head-to-head race and the benchmark.</p>
    <p>To classify new posts live with Rescue Radar and the frontier baseline (Claude Opus 5.5, or GPT-6.1 Terra while the Anthropic account is capped; each card names the model that answered), run the backend from the repo root and open the console it serves:</p>
    <code>${esc(SERVER_CMD)}\nopen http://127.0.0.1:8787/</code></div>`;
}
