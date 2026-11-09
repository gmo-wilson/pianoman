import { api, h, fmtTime, buddyCanvas, fmtDate } from '../app.js';

export async function render(root) {
  root.append(h('h1', {}, 'Dashboard'));
  const [buddies, sessions, settings] = await Promise.all([api.get('/buddies'), api.get('/sessions?limit=8'), api.get('/settings')]);

  const tiles = h('div', { class: 'grid auto' });
  for (const b of buddies) {
    const canvas = await buddyCanvas(b.level, b.today_completed ? 'dance' : 'idle');
    const pct = Math.min(100, Math.round((b.time_practiced_today / (settings.goal_minutes * 60)) * 100));
    tiles.append(h('div', { class: 'card buddy-tile' },
      canvas,
      h('strong', {}, b.student_name),
      h('span', { class: 'muted small' }, `Lv ${b.level} · ${b.level_name}`),
      road(b),
      h('span', { class: 'small muted' }, b.at_top ? 'top of the road' : `${b.steps_to_next} step${b.steps_to_next === 1 ? '' : 's'} to next evolution`),
      b.evolved_today ? h('span', { class: 'badge ok' }, 'evolved today ★') : b.lost_step_yesterday ? h('span', { class: 'badge warn' }, 'missed yesterday −1') : '',
      h('span', { class: 'small muted' }, b.today_completed ? '✔ goal done' : `${fmtTime(b.time_practiced_today)} today (${pct}%)`),
    ));
  }
  root.append(h('div', { class: 'card' }, h('h2', {}, "Today's buddies"), tiles));

  const rows = sessions.map(s => h('tr', {},
    h('td', {}, s.student_name), h('td', {}, fmtDate(s.started_at)), h('td', {}, fmtTime(s.practice_seconds)),
    h('td', {}, s.total_notes ?? '–'), h('td', {}, s.lesson_name || 'free'),
    h('td', {}, s.goal_reached ? h('span', { class: 'badge ok' }, 'goal') : ''),
  ));
  root.append(h('div', { class: 'card', style: 'margin-top:16px' },
    h('div', { class: 'row between' }, h('h2', {}, 'Recent sessions'), h('a', { href: '#/sessions' }, 'all sessions →')),
    h('table', {}, h('thead', {}, h('tr', {}, ...['Student', 'When', 'Practice', 'Notes', 'Mode', ''].map(t => h('th', {}, t)))), h('tbody', {}, rows)),
  ));
}


// Road widget: dots for the steps inside the current milestone.
export function road(b) {
  const dots = [];
  for (let i = 0; i < b.steps_per_level; i++) dots.push(h('i', { class: i < b.steps_in_level ? 'done' : '', style: 'width:14px;height:14px;border-radius:50%' }));
  return h('div', { class: 'strip', title: `${b.steps} steps total` }, ...dots);
}
