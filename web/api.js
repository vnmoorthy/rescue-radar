// Data layer: one interface, two adapters.
//   live   -> the FastAPI backend at /api/* (rr/server.py)
//   static -> ./data/*.json (GitHub Pages export or dev fixtures), queue in localStorage
// URL overrides: ?static=1 forces static mode, ?api=http://127.0.0.1:8787 points the live adapter elsewhere
// (local hosts only: the server's CORS policy allows localhost origins, so GitHub Pages never probes a backend).

const params = new URLSearchParams(location.search);
const FORCE_STATIC = params.has('static');
const API_BASE = (params.get('api') || '').replace(/\/+$/, '');
const PAGES_HOST = /\.github\.io$/i.test(location.hostname);
// True when this page could have a live server next to it (or named by ?api=), i.e. static mode is a fallback that
// should switch back to live as soon as /api/health answers (see app.js).
export const CAN_GO_LIVE = !FORCE_STATIC && !PAGES_HOST && location.protocol !== 'file:';
export async function probeLive() {
  const live = liveAdapter(API_BASE);
  const health = await live.health();
  const meta = await live.meta();
  return !!(health && typeof health === 'object' && meta && !meta.static);
}
export const SERVER_CMD = '.venv/bin/python -m rr.server';

export class ApiError extends Error {
  constructor(message, status = 0, detail = null) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}
export class StaticModeError extends Error {
  constructor(what) {
    super(`${what} needs the live model server. This page is running on recorded data only.`);
    this.isStatic = true;
  }
}

async function fetchJSON(url, opts = {}, timeoutMs = 20000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(url, { ...opts, signal: ctrl.signal });
  } catch (e) {
    clearTimeout(timer);
    if (e.name === 'AbortError') throw new ApiError(`Request timed out after ${Math.round(timeoutMs / 1000)} s`, 0);
    throw new ApiError(`Network error: cannot reach ${url.replace(/\?.*/, '')}`, 0);
  }
  clearTimeout(timer);
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = null; }
  if (!res.ok) {
    let detail = body && body.detail;
    if (Array.isArray(detail)) detail = detail.map(d => d.msg || JSON.stringify(d)).join('; ');
    if (detail && typeof detail !== 'string') detail = JSON.stringify(detail);
    throw new ApiError(detail ? `${detail}` : `HTTP ${res.status} ${res.statusText || ''}`.trim(), res.status, detail || null);
  }
  if (body === null && text) throw new ApiError(`Unexpected non-JSON response from ${url}`, res.status);
  return body;
}
const jsonBody = (method, data) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

function liveAdapter(base) {
  const u = p => `${base}/api${p}`;
  return {
    mode: 'live',
    health: () => fetchJSON(u('/health'), {}, 4000),
    meta: () => fetchJSON(u('/meta')),
    replay: id => fetchJSON(u(`/replay/${encodeURIComponent(id)}`), {}, 60000),
    classify: text => fetchJSON(u('/classify'), jsonBody('POST', { text }), 90000),
    classifyBatch: texts => fetchJSON(u('/classify_batch'), jsonBody('POST', { texts }), 240000),
    compare: text => fetchJSON(u('/compare'), jsonBody('POST', { text }), 120000),
    queueList: () => fetchJSON(u('/queue')).then(r => (r && r.items) || []),
    queueAdd: item => fetchJSON(u('/queue'), jsonBody('POST', item)),
    queuePatch: (qid, patch) => fetchJSON(u(`/queue/${encodeURIComponent(qid)}`), jsonBody('PATCH', patch)),
    queueClear: () => fetchJSON(u('/queue'), { method: 'DELETE' }),
    queueCsvUrl: () => u('/queue.csv'),
    results: () => fetchJSON(u('/results')),
    trainLog: () => fetchJSON(u('/train_log')),
    liveSocial: () => fetchJSON(u('/live/social'), {}, 15000),
  };
}

const QKEY = 'rr-queue-v1';
function loadQ() {
  try { const v = JSON.parse(localStorage.getItem(QKEY) || '[]'); return Array.isArray(v) ? v : []; } catch { return []; }
}
function saveQ(items) {
  try { localStorage.setItem(QKEY, JSON.stringify(items)); } catch { /* storage blocked: queue lives in memory */ }
}

function staticAdapter(root) {
  let mem = loadQ();
  const get = p => fetchJSON(`${root}/${p}`, {}, 60000);
  const now = () => new Date().toISOString();
  let metaCache = null;
  return {
    mode: 'static',
    async health() {
      const m = metaCache || (metaCache = await get('meta.json'));
      return { ok: true, static: true, model: { ...(m.model || {}), ready: false }, frontier: { ...(m.frontier || {}), ready: false } };
    },
    async meta() { return metaCache || (metaCache = await get('meta.json')); },
    replay: id => get(`replay/${encodeURIComponent(id)}.json`),
    classify: async () => { throw new StaticModeError('Live classification'); },
    classifyBatch: async () => { throw new StaticModeError('Live classification'); },
    compare: async () => { throw new StaticModeError('A live head-to-head'); },
    async queueList() { mem = loadQ().length ? loadQ() : mem; return mem.slice(); },
    async queueAdd(item) {
      const hit = mem.find(x => x.post_id === item.post_id);
      if (hit) return hit;
      const t = now();
      const q = { qid: `q_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`, post_id: item.post_id,
        text: item.text, label: item.label, event: item.event || null, place: item.place || null,
        status: 'open', note: '', created_at: t, updated_at: t };
      mem.unshift(q);
      saveQ(mem);
      return q;
    },
    async queuePatch(qid, patch) {
      const q = mem.find(x => x.qid === qid);
      if (!q) throw new ApiError(`Queue item ${qid} not found`, 404);
      if (patch.status) q.status = patch.status;
      if (patch.note !== undefined && patch.note !== null) q.note = patch.note;
      q.updated_at = now();
      saveQ(mem);
      return { ...q };
    },
    async queueClear() { mem = []; saveQ(mem); return { ok: true }; },
    queueCsvUrl: () => null,
    results: () => get('results.json').catch(() => ({ status: 'pending' })),
    trainLog: () => get('train_log.json').catch(() => ({ runs: {} })),
    liveSocial: async () => ({ enabled: false, static: true, running: false, items: [], sources: [] }),
  };
}

// Decide which adapter to use. Live wins when /api/health answers and meta is not flagged static.
export async function connect() {
  // GitHub Pages never has the API next to it, so skip the probe there (no 404 noise). ?api= is ignored there too:
  // rr.server only allows localhost origins (CORS), so a Pages page could never reach a local backend anyway.
  if (!FORCE_STATIC && !PAGES_HOST) {
    const live = liveAdapter(API_BASE);
    try {
      const health = await live.health();
      if (health && typeof health === 'object') {
        const meta = await live.meta();
        if (meta && !meta.static) return { api: live, health, meta };
      }
    } catch { /* fall back to static */ }
  }
  const st = staticAdapter('./data');
  const meta = await st.meta();
  const health = await st.health();
  return { api: st, health, meta };
}
