// How it works: architecture, evaluation loop, data split, sponsors, limitations.
import { esc, fmtInt } from '../ui.js';

export function createHow(root, ctx) {
  const { meta } = ctx;
  // What the live console serves vs what the Benchmark scored (rr.server: live model = the scored checkpoint unless
  // RR_LIVE_MODEL says otherwise; model.scored tells which).
  function servingNote() {
    const m = { ...(meta.model || {}), ...((ctx.health && ctx.health.model) || {}) };
    const name = esc(m.name || 'Rescue Radar');
    if (!ctx.api || ctx.api.mode !== 'live') return `This recorded demo replays the predictions the benchmark scored (${name}).`;
    return m.scored === true
      ? `The live console serves exactly the checkpoint the Benchmark scored (${name}), through the same SamplerClassifier code path.`
      : `Right now the live console serves ${name}, a training checkpoint that has not been scored; the Benchmark numbers belong to the scored run.`;
  }
  let painted = false;
  function paint(res) {
    const ev = (res && res.eval) || {};
    const events = meta.events || [];
    const nEval = ev.n ?? (events.length ? events.reduce((a, e) => a + (e.n_posts || 0), 0) : null);
    const nCrit = events.length ? events.reduce((a, e) => a + (e.n_critical || 0), 0) : null;
    // training-set size from the training log header (rr.server meta.training), else metrics.json
    const nTrain = (meta.training && meta.training.examples) ?? ev.train_examples;
    const fact = (v, k) => `<div class="fact"><div class="fact__v num">${v == null ? 'n/a' : esc(typeof v === 'number' ? fmtInt(v) : v)}</div><div class="fact__k">${esc(k)}</div></div>`;
    root.innerHTML = `
      <div class="view-head"><div><div class="eyebrow">View 5 · architecture</div><h1>How it works</h1>
        <p>Rescue Radar classifies every post (a replay of recorded 2019 posts, or text you paste or upload; live stream ingestion is not built yet) into the 10 HumAID humanitarian categories, redacts personal data before a dispatcher reads it, and pushes rescue-critical ones to a priority queue. A human makes every call.</p></div></div>
      <div class="how">
        <section class="panel" aria-label="Architecture diagram">
          <div class="panel__head"><h2 class="panel__title">Pipeline</h2><span class="panel__meta">serving path on top, evaluation loop below</span></div>
          <div class="panel__body">${diagram(ev, nEval, nTrain)}</div>
          <div class="facts">
            ${fact(ev.train_events, 'training disasters, 2016–2018')}
            ${fact(nTrain, 'training examples (LoRA SFT)')}
            ${fact(ev.test_events ?? (events.length || null), 'unseen 2019 disasters held out')}
            ${fact(nEval, 'held-out posts scored')}
            ${fact(nCrit, 'of them rescue-critical (human label)')}
            ${fact(10, 'HumAID categories, 3 rescue-critical')}
          </div>
        </section>
        <div class="cols-3">
          <section class="panel sponsor"><div class="eyebrow">Training + serving</div><h3>Fireworks</h3>
            <p>LoRA supervised fine-tuning on Fireworks serverless training, served through Fireworks serverless sampling. ${servingNote()}</p></section>
          <section class="panel sponsor"><div class="eyebrow">Base model</div><h3>NVIDIA</h3>
            <p>NVIDIA Nemotron 3.5 Super is the open base model. The fine-tune teaches it the HumAID label set; the untuned base is scored too, as the "before".</p></section>
          <section class="panel sponsor"><div class="eyebrow">Privacy</div><h3>Microsoft Presidio</h3>
            <p>PII redaction before human review: Microsoft Presidio (spaCy NER) plus regexes masks names, phones, emails, handles, links and street addresses before a dispatcher reads a post (best effort). Deploying on Microsoft Foundry is a next step, not implemented yet.</p></section>
        </div>
        <div class="cols-3" style="grid-template-columns:minmax(0,1.3fr) minmax(0,1fr) minmax(0,1fr)">
          <section class="panel"><div class="panel__head"><h2 class="panel__title">Responsible use</h2></div><div class="panel__body">
            <ul class="list">
              <li><b>Human in the loop.</b> The model orders attention; a dispatcher decides. Nothing is dispatched automatically.</li>
              <li><b>Never drops posts.</b> Every post stays in the feed and on the map. Classification only changes what is surfaced first.</li>
              <li><b>Missed rescues are the expensive error.</b> We report rescue-critical recall with 95% intervals, and the ground-truth toggle shows mistakes live.</li>
              <li><b>Privacy first.</b> Names, handles, phone numbers, emails, links and street addresses are redacted before display (best effort), and map pins are placed from the redacted text.</li>
            </ul></div></section>
          <section class="panel"><div class="panel__head"><h2 class="panel__title">Limitations</h2></div><div class="panel__body">
            <ul class="list">
              <li>English tweets from 2016–2019; new platforms, languages or disaster types will shift accuracy.</li>
              <li>Place names come from a small gazetteer, so pins are approximate and many posts have no place.</li>
              <li>Some categories are rare (missing or found people), so their scores are noisy.</li>
              <li>Redaction lowers PII exposure but does not guarantee it is gone. It applies to what the dispatcher sees: the raw post is sent to the model providers (Fireworks; Anthropic or OpenAI for the frontier comparison).</li>
              <li>No live stream ingestion yet: the console replays recorded 2019 posts or classifies pasted and uploaded text.</li>
            </ul></div></section>
          <section class="panel"><div class="panel__head"><h2 class="panel__title">Data</h2></div><div class="panel__body">
            <ul class="list">
              <li><b>HumAID</b> (Alam et al., ICWSM 2021): human-labelled disaster tweets, licensed <b>CC BY-NC-SA 4.0</b>. Non-commercial use, share alike.</li>
              <li>Split by disaster, not by tweet: no 2019 event appears in our fine-tuning data. We cannot rule out that a model saw these public tweets in pretraining.</li>
              <li>${esc(ev.split || 'Train on 2016–2018 disasters, test on 4 unseen 2019 disasters.')}</li>
            </ul></div></section>
        </div>
      </div>`;
  }
  window.addEventListener('rr:themechange', () => { if (painted) paint(ctx.resultsNow()); });
  return {
    activate() {
      if (painted) return;
      painted = true;
      paint(ctx.resultsNow());
      Promise.resolve(ctx.results).then(r => paint(r)).catch(() => {});
    },
    deactivate() {},
  };
}

function box(x, y, w, h, eyebrow, title, sub, cls = '') {
  const subs = Array.isArray(sub) ? sub : [sub];
  return `<g><rect class="box ${cls}" x="${x}" y="${y}" width="${w}" height="${h}" rx="6"/>
    <text class="t3" x="${x + 12}" y="${y + 18}">${esc(eyebrow)}</text>
    <text class="t1" x="${x + 12}" y="${y + 38}">${esc(title)}</text>
    ${subs.map((s, i) => `<text class="t2" x="${x + 12}" y="${y + 56 + i * 14}">${esc(s)}</text>`).join('')}</g>`;
}

function diagram(ev, nEval, nTrain) {
  const nTr = ev.train_events ?? 'n/a', nTe = ev.test_events ?? 'n/a';
  return `<svg class="diagram" viewBox="0 0 1100 430" role="img" aria-label="Posts go to the Rescue Radar model; its labels and the PII-redacted text go on to the priority queue and map for a human dispatcher; the model is trained on ${esc(nTr)} HumAID disasters with LoRA and evaluated on ${esc(nTe)} unseen disasters against frontier models">
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="arrowhead" d="M0 0 10 5 0 10z"/></marker>
      <marker id="arrow-muted" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="arrowhead--muted" d="M0 0 10 5 0 10z"/></marker>
    </defs>
    <text class="t3" x="10" y="16">Serving path · live</text>
    ${box(10, 30, 170, 92, 'Input', 'Posts', ['2019 replay, or paste /', 'upload; none dropped'])}
    ${box(220, 22, 250, 108, 'Classifier', 'Rescue Radar', ['Nemotron 3.5 Super + LoRA', 'served on Fireworks', '10 HumAID categories'], 'box--accent')}
    ${box(510, 30, 170, 92, 'Privacy', 'PII redaction', ['before a human reads it:', 'names, phones, links'])}
    ${box(730, 10, 170, 74, 'Rescue-critical', 'Priority queue', ['dispatch, resolve, notes'], 'box--crit')}
    ${box(730, 98, 170, 74, 'Everything', 'Feed + map', ['all posts, pinned if placed'])}
    ${box(940, 50, 150, 82, 'Human', 'Dispatcher', ['decides every call', 'notes, CSV export'])}
    <path class="flow flow--anim" d="M180 76 H218"/>
    <path class="flow flow--anim" d="M470 76 H508"/>
    <path class="flow flow--anim" d="M680 62 C705 62 705 47 728 47"/>
    <path class="flow" d="M680 96 C705 96 705 135 728 135"/>
    <path class="flow flow--anim" d="M900 47 C920 47 920 80 938 80"/>
    <path class="flow" d="M900 135 C920 135 920 105 938 105"/>
    <rect class="region" x="4" y="214" width="1092" height="208" rx="8"/>
    <text class="t3" x="16" y="234">Evaluation loop · offline, pre-registered</text>
    ${box(20, 250, 200, 92, 'HumAID train', `${nTr} disasters`, ['2016–2018 hurricanes, floods,', `quakes, fires${nTrain ? ` · ${fmtInt(nTrain)} examples` : ''}`])}
    ${box(260, 250, 200, 92, 'Fine-tune', 'LoRA SFT', ['Fireworks serverless training', 'base: Nemotron 3.5 Super'])}
    ${box(500, 250, 228, 92, 'Held out', `${nTe} unseen disasters`, ['2019: Dorian, Idai, Pakistan', `quake, Midwest floods${nEval ? ` · ${fmtInt(nEval)} posts` : ''}`])}
    ${box(750, 250, 160, 92, 'Frontier baselines', 'Claude Opus 5.5', ['+ GPT-6.1 Terra; same', 'instructions + 20 shots'])}
    ${box(750, 356, 160, 66, 'Also scored', 'Nemotron base', ['the untuned "before"'])}
    ${box(945, 250, 145, 92, 'Scorecard', 'Benchmark', ['F1, critical recall,', 'cost, latency,', 'McNemar, bootstrap'])}
    <path class="flow" d="M220 296 H258"/>
    <path class="flow" d="M360 250 C360 190 330 190 330 132" />
    <text class="t2" x="372" y="186">LoRA weights</text>
    <path class="flow flow--muted" d="M600 250 C600 190 430 190 430 132"/>
    <text class="t2" x="540" y="196">scored on</text>
    <path class="flow flow--muted" d="M728 296 H748"/>
    <path class="flow flow--muted" d="M910 296 H943"/>
    <path class="flow flow--muted" d="M910 385 C930 385 930 330 943 330"/>
    <path class="flow flow--muted" d="M470 120 C900 200 1015 190 1015 248"/>
  </svg>`;
}
