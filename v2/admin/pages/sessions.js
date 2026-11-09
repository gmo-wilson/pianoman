import { api, h, toast, confirmDlg, fmtTime, fmtDate } from '../app.js';

export async function render(root) {
  root.append(h('h1', {}, 'Sessions'));
  const students = await api.get('/students?include_inactive=true');
  const filter = h('select', {}, h('option', { value: '' }, 'All students'), ...students.map(s => h('option', { value: s.id }, s.name)));
  const table = h('table');
  const detail = h('div', { class: 'card', style: 'margin-top:16px; display:none' });
  root.append(h('div', { class: 'card' }, h('div', { class: 'row between' }, h('h2', {}, 'History'), filter), table), detail);
  filter.addEventListener('change', load);

  async function load() {
    const q = filter.value ? `&student_id=${filter.value}` : '';
    const rows = await api.get(`/sessions?limit=200${q}`);
    table.innerHTML = '';
    table.append(h('thead', {}, h('tr', {}, ...['Student', 'Started', 'Length', 'Practice', 'Notes', 'Mode', 'Goal', ''].map(t => h('th', {}, t)))));
    table.append(h('tbody', {}, ...rows.map(s => h('tr', {},
      h('td', {}, s.student_name), h('td', {}, fmtDate(s.started_at)), h('td', {}, fmtTime(s.duration_seconds)),
      h('td', {}, fmtTime(s.practice_seconds)), h('td', {}, s.total_notes ?? '–'), h('td', {}, s.lesson_name || 'free'),
      h('td', {}, s.goal_reached ? h('span', { class: 'badge ok' }, '✔') : ''),
      h('td', {}, h('div', { class: 'row' },
        h('button', { class: 'sm', onClick: () => show(s.id) }, 'View'),
        h('button', { class: 'sm', onClick: () => replay(s.id) }, '▶ Replay on piano'),
        h('button', { class: 'sm danger', onClick: async () => { if (await confirmDlg('Delete this session?')) { await api.del(`/sessions/${s.id}`); load(); } } }, '✕'))),
    ))));
  }

  async function show(id) {
    const s = await api.get(`/sessions/${id}`);
    detail.style.display = '';
    detail.innerHTML = '';
    const chords = Object.entries(s.chords_played || {}).sort((a, b) => b[1] - a[1]).map(([c, n]) => `${c} ×${n}`).join(', ') || '–';
    detail.append(
      h('div', { class: 'row between' }, h('h2', {}, `${s.student_name} · ${fmtDate(s.started_at)}`), h('button', { class: 'sm ghost', onClick: () => (detail.style.display = 'none') }, 'Close')),
      h('p', { class: 'muted' }, `Practice ${fmtTime(s.practice_seconds)} of ${fmtTime(s.duration_seconds)} · ${s.total_notes} notes · chords: ${chords}`),
      pianoRoll(s.events || []),
    );
  }

  async function replay(id) {
    const s = await api.get(`/sessions/${id}`);
    const events = (s.events || []).map(e => ({ time: e.time ?? e.t, type: e.type, note: e.note, vel: e.vel }));
    try { await api.post('/player/load', { events, label: `Replay ${s.student_name}`, autoplay: true }); toast('Playing on the piano'); }
    catch (e) { toast(e.message, true); }
  }
  load();
}

// Simple piano-roll: x = time, y = pitch.
function pianoRoll(events) {
  const c = h('canvas', { width: 1000, height: 220, style: 'width:100%; height:220px; background:#0f141c; border-radius:12px' });
  const ctx = c.getContext('2d');
  const ons = {}; const notes = [];
  let maxT = 1;
  for (const e of events) {
    const t = e.time ?? e.t ?? 0; maxT = Math.max(maxT, t);
    if (e.type === 'on') ons[e.note] = t;
    else if (e.type === 'off' && ons[e.note] !== undefined) { notes.push({ n: e.note, a: ons[e.note], b: t }); delete ons[e.note]; }
  }
  for (const [n, a] of Object.entries(ons)) notes.push({ n: +n, a, b: maxT });
  const lo = Math.min(36, ...notes.map(x => x.n)), hi = Math.max(96, ...notes.map(x => x.n));
  const rowH = 220 / (hi - lo + 1);
  for (const x of notes) {
    ctx.fillStyle = '#38bdf8';
    ctx.fillRect((x.a / maxT) * 1000, 220 - (x.n - lo + 1) * rowH, Math.max(2, ((x.b - x.a) / maxT) * 1000), Math.max(2, rowH - 1));
  }
  return c;
}
