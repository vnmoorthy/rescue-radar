// Shared dispatcher queue store. Persists through the API adapter (server in live mode, localStorage in static).
import { toast, errMessage, csvCell, downloadText, labelName } from './ui.js';

const MAX_INFLIGHT = 4;

export class QueueStore {
  constructor(api) {
    this.api = api;
    this.items = [];            // newest first
    this.byPost = new Map();    // post_id -> item
    this.pending = new Map();   // post_id -> Promise<item>
    this.waiting = [];          // add requests waiting for a slot
    this.inflight = 0;
    this.listeners = new Set();
    this.errorShown = false;
  }
  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  emit(change) { for (const fn of this.listeners) fn(change); }

  async load() {
    try {
      const items = await this.api.queueList();
      this.items = items;
      this.byPost = new Map(items.map(i => [i.post_id, i]));
      this.emit({ type: 'load' });
    } catch (e) {
      toast(`Could not load the queue: ${errMessage(e)}`, 'error');
    }
  }

  has(postId) { return this.byPost.has(postId); }

  // Optimistic add: shows instantly, persists in the background with bounded concurrency. Idempotent on post_id.
  add(post, { silent = false } = {}) {
    if (this.byPost.has(post.post_id)) return this.pending.get(post.post_id) || Promise.resolve(this.byPost.get(post.post_id));
    const t = new Date().toISOString();
    const local = { qid: null, ...post, status: 'open', note: '', created_at: t, updated_at: t, _pending: true };
    this.items.unshift(local);
    this.byPost.set(post.post_id, local);
    this.emit({ type: 'add', item: local });
    const p = new Promise((resolve, reject) => this.waiting.push({ post, local, resolve, reject }));
    this.pending.set(post.post_id, p);
    p.catch(() => {});
    this.pump();
    if (!silent) toast(`Added to priority queue: ${labelName(post.label)}`, 'ok', { timeout: 2400 });
    return p;
  }
  pump() {
    while (this.inflight < MAX_INFLIGHT && this.waiting.length) {
      const job = this.waiting.shift();
      this.inflight++;
      this.api.queueAdd(job.post).then(saved => {
        const cur = this.byPost.get(job.post.post_id);
        if (cur) {
          Object.assign(cur, saved, { _pending: false });
        }
        job.resolve(cur || saved);
        this.emit({ type: 'update', item: cur || saved });
      }).catch(e => {
        // Drop the optimistic item so the queue never shows a 'ghost' the server does not have, and add() can retry.
        job.local._pending = false;
        job.local._error = errMessage(e);
        if (this.byPost.get(job.post.post_id) === job.local) this.byPost.delete(job.post.post_id);
        const at = this.items.indexOf(job.local);
        if (at >= 0) this.items.splice(at, 1);
        if (!this.errorShown) { this.errorShown = true; toast(`Queue sync failed: ${errMessage(e)}`, 'error'); setTimeout(() => { this.errorShown = false; }, 8000); }
        this.emit({ type: 'load' });
        job.reject(e);
      }).finally(() => {
        this.inflight--;
        this.pending.delete(job.post.post_id);
        this.pump();
      });
    }
  }

  async patch(item, patch) {
    const prev = { status: item.status, note: item.note };
    Object.assign(item, patch, { updated_at: new Date().toISOString() });
    this.emit({ type: 'update', item });
    try {
      if (!item.qid) await this.pending.get(item.post_id);
      if (!item.qid) throw new Error('item was not saved to the queue');
      const saved = await this.api.queuePatch(item.qid, patch);
      Object.assign(item, saved);
      this.emit({ type: 'update', item });
      return item;
    } catch (e) {
      Object.assign(item, prev);
      this.emit({ type: 'update', item });
      toast(`Could not update the queue item: ${errMessage(e)}`, 'error');
      throw e;
    }
  }

  async clear() {
    try {
      await this.api.queueClear();
      this.items = [];
      this.byPost.clear();
      this.waiting.length = 0;
      this.emit({ type: 'load' });
      toast('Priority queue cleared', 'ok');
    } catch (e) {
      toast(`Could not clear the queue: ${errMessage(e)}`, 'error');
    }
  }

  exportCsv() {
    const url = this.api.queueCsvUrl();
    if (url) {
      const a = document.createElement('a');
      a.href = url;
      a.download = 'rescue-radar-queue.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      toast('Queue CSV download started', 'ok', { timeout: 2400 });
      return;
    }
    const cols = ['qid', 'post_id', 'status', 'label', 'event', 'place', 'lat', 'lng', 'note', 'created_at', 'updated_at', 'text'];
    const rows = this.items.map(i => [i.qid, i.post_id, i.status, i.label, i.event,
      i.place && typeof i.place === 'object' ? i.place.name : i.place, i.place && i.place.lat, i.place && i.place.lng,
      i.note, i.created_at, i.updated_at, i.text]);
    downloadText('rescue-radar-queue.csv', [cols, ...rows].map(r => r.map(csvCell).join(',')).join('\n'));
    toast(`Exported ${this.items.length} queue items to CSV`, 'ok', { timeout: 2400 });
  }

  counts() {
    const c = { open: 0, dispatched: 0, resolved: 0, dismissed: 0, all: this.items.length };
    for (const i of this.items) c[i.status] = (c[i.status] || 0) + 1;
    return c;
  }
}
