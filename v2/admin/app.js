// Piano Studio Admin — tiny hash router + API helper. No build step, no dependencies.
import * as dashboard from './pages/dashboard.js';
import * as students from './pages/students.js';
import * as sessions from './pages/sessions.js';
import * as lessons from './pages/lessons.js';
import * as songs from './pages/songs.js';
import * as sprites from './pages/sprites.js';
import * as game from './pages/game.js';
import * as releases from './pages/releases.js';
import * as settings from './pages/settings.js';

const routes = {
  '/': dashboard, '/students': students, '/sessions': sessions, '/lessons': lessons,
  '/songs': songs, '/sprites': sprites, '/game': game, '/releases': releases, '/settings': settings,
};

// ---------------------------------------------------------------- API
const TOKEN_KEY = 'piano_admin_token';
export const api = {
  base: '/api/v1',
  token() { return localStorage.getItem(TOKEN_KEY) || ''; },
  setToken(t) { localStorage.setItem(TOKEN_KEY, t); },
  headers(extra = {}) { const h = { ...extra }; if (this.token()) h['X-Admin-Token'] = this.token(); return h; },
  async req(method, path, body, isForm = false) {
    const opts = { method, headers: this.headers(isForm ? {} : (body ? { 'Content-Type': 'application/json' } : {})) };
    if (body) opts.body = isForm ? body : JSON.stringify(body);
    const r = await fetch(this.base + path, opts);
    if (r.status === 204) return null;
    const text = await r.text();
    let data = null; try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!r.ok) throw new Error((data && data.detail) || `HTTP ${r.status}`);
    return data;
  },
  get(p) { return this.req('GET', p); },
  post(p, b) { return this.req('POST', p, b); },
  put(p, b) { return this.req('PUT', p, b); },
  patch(p, b) { return this.req('PATCH', p, b); },
  del(p) { return this.req('DELETE', p); },
  upload(p, formData) { return this.req('POST', p, formData, true); },
};

// ---------------------------------------------------------------- helpers
export const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'html') el.innerHTML = v;
    else if (v !== null && v !== undefined && v !== false) el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
};
export const fmtTime = (s) => { s = Math.round(s || 0); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
export const fmtDate = (unix) => new Date(unix * 1000).toLocaleString();
export const fmtDay = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });

let toastTimer;
export function toast(msg, isErr = false) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'show' + (isErr ? ' err' : '');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.className = ''), 2600);
}
export const confirmDlg = (msg) => Promise.resolve(window.confirm(msg));

// ---------------------------------------------------------------- sprite preview (shared by dashboard & sprites page)
// Animates a canonical frames.json animation on a canvas. Returns a stop() function.
export function animateSprite(canvas, atlasImg, spec, animName, scaleTo = 96) {
  // spec is either a single-animation file {loop, frames} or a legacy multi-animation file {animations:{...}}
  const anim = spec.frames ? spec : ((spec.animations || {})[animName] || (spec.animations || {}).idle_happy);
  if (!anim) return () => {};
  const ctx = canvas.getContext('2d');
  canvas.width = scaleTo; canvas.height = scaleTo;
  let i = 0, alive = true, timer;
  const step = () => {
    if (!alive) return;
    const f = anim.frames[i % anim.frames.length];
    ctx.clearRect(0, 0, scaleTo, scaleTo);
    const s = Math.min(scaleTo / f.w, scaleTo / f.h);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(atlasImg, f.x, f.y, f.w, f.h, (scaleTo - f.w * s) / 2, (scaleTo - f.h * s) / 2, f.w * s, f.h * s);
    i++;
    if (!anim.loop && i >= anim.frames.length) i = anim.frames.length - 1;
    timer = setTimeout(step, f.ms || 100);
  };
  step();
  return () => { alive = false; clearTimeout(timer); };
}
const imgCache = new Map();
export function loadImage(url) {
  if (!imgCache.has(url)) imgCache.set(url, new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = url; }));
  return imgCache.get(url);
}
export async function buddyCanvas(level, mood = 'idle', size = 96) {
  const canvas = h('canvas', { width: size, height: size, title: `Level ${level}` });
  try {
    const m = await (window.__manifest ||= api.get('/sprites/manifest'));
    let entry = null;
    for (const l of m.levels) if (l.animations && l.animations.idle && l.level <= level && (!entry || l.level > entry.level)) entry = l;
    if (!entry) { placeholder(canvas, level); return canvas; }
    const a = entry.animations[mood === 'dance' ? 'dance' : 'idle'] || entry.animations.idle;
    const [img, spec] = await Promise.all([loadImage(a.atlas_url), fetch(a.frames_url).then(r => r.json())]);
    animateSprite(canvas, img, spec, null, size);
  } catch { placeholder(canvas, level); }
  return canvas;
}
function placeholder(canvas, level) {
  const ctx = canvas.getContext('2d'), s = canvas.width;
  ctx.fillStyle = '#243042'; ctx.beginPath(); ctx.arc(s / 2, s / 2, s * 0.34, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#94a3b8'; ctx.font = `bold ${s / 4}px system-ui`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(level, s / 2, s / 2);
}

// ---------------------------------------------------------------- router
let currentCleanup = null;
async function render() {
  const path = (location.hash.slice(1) || '/').split('?')[0];
  const page = routes[path] || dashboard;
  document.querySelectorAll('.side a').forEach(a => a.classList.toggle('active', a.dataset.route === path));
  if (currentCleanup) { try { currentCleanup(); } catch {} currentCleanup = null; }
  const view = document.getElementById('view');
  view.innerHTML = '';
  const wrap = h('div', { class: 'fade-in' });
  view.append(wrap);
  try { currentCleanup = await page.render(wrap) || null; }
  catch (e) { wrap.append(h('div', { class: 'card' }, h('h2', {}, 'Error'), h('p', { class: 'muted' }, e.message))); }
}
window.addEventListener('hashchange', render);
render();

async function health() {
  const el = document.getElementById('health');
  try {
    const hlt = await api.get('/health');
    const live = await api.get('/live');
    const inp = hlt.midi.input || {}; el.textContent = `backend ${hlt.version} · piano ${inp.connected ? '✓ ' + (inp.name || '') : '✗ not found'} · ${hlt.midi.selected_output ? 'MIDI out ✓' : 'no MIDI out'}` + (live.session_active ? ` · ${live.student} practicing` : '');
  } catch { el.textContent = 'backend unreachable'; }
}
health(); setInterval(health, 10000);
