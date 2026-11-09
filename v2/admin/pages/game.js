// Runner mini-game: leaderboard, recent runs, per-student credits, rules.
import { api, h, toast, confirmDlg } from '../app.js';

export async function render(root) {
  root.append(h('h1', {}, 'Runner game'));
  const [settings, students] = await Promise.all([api.get('/settings'), api.get('/students')]);
  const g = settings.game || { runs_per_day: 3, bonus_minutes: 10, enabled: true };

  // ---- rules
  const enabled = h('input', { type: 'checkbox', checked: !!g.enabled });
  const runs = h('input', { type: 'number', min: 0, max: 20, value: g.runs_per_day, style: 'width:90px' });
  const bonus = h('input', { type: 'number', min: 1, max: 120, value: g.bonus_minutes, style: 'width:90px' });
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Rules'),
    h('div', { class: 'row' },
      h('label', { class: 'field' }, 'Enabled', enabled),
      h('label', { class: 'field' }, 'Runs per finished practice', runs),
      h('label', { class: 'field' }, 'Extra minutes for a bonus run', bonus),
      h('button', { class: 'primary', style: 'align-self:end', onClick: async () => {
        await api.put('/settings', { game: { ...g, enabled: enabled.checked, runs_per_day: +runs.value, bonus_minutes: +bonus.value } });
        toast('Saved');
      } }, 'Save')),
    h('p', { class: 'small muted' }, 'The game unlocks once the daily goal is reached. After the last base run, practising the extra minutes right away earns one bonus run. Scores are validated server-side.')));

  // ---- leaderboard
  const period = h('select', {}, ...[['all', 'All time'], ['week', 'This week'], ['today', 'Today']].map(([v, t]) => h('option', { value: v }, t)));
  const lbTable = h('table');
  const recentTable = h('table');
  root.append(h('div', { class: 'grid cols-2', style: 'margin-top:16px' },
    h('div', { class: 'card' }, h('div', { class: 'row between' }, h('h2', {}, 'Leaderboard'), period), lbTable),
    h('div', { class: 'card' }, h('h2', {}, 'Recent runs'), recentTable)));
  period.addEventListener('change', load);

  // ---- credits per student
  const credTable = h('table');
  root.append(h('div', { class: 'card', style: 'margin-top:16px' }, h('h2', {}, "Today's credits"), credTable));

  async function load() {
    const lb = await api.get(`/game/leaderboard?period=${period.value}&limit=25`);
    lbTable.innerHTML = '';
    lbTable.append(h('thead', {}, h('tr', {}, ...['#', 'Student', 'Best', 'Runs', 'Last run'].map(t => h('th', {}, t)))));
    lbTable.append(h('tbody', {}, ...lb.entries.map((e, i) => h('tr', {},
      h('td', {}, i + 1), h('td', {}, h('span', { class: 'swatch', style: `background:${e.color || '#38bdf8'}` }), e.name),
      h('td', {}, h('strong', {}, e.best)), h('td', {}, e.runs), h('td', { class: 'small muted' }, e.last_run)))));
    recentTable.innerHTML = '';
    recentTable.append(h('thead', {}, h('tr', {}, ...['Student', 'Score', 'Day', 'Lv', '', ''].map(t => h('th', {}, t)))));
    recentTable.append(h('tbody', {}, ...lb.recent.map(r => h('tr', {},
      h('td', {}, r.name), h('td', {}, h('strong', {}, r.score)), h('td', { class: 'small muted' }, r.day), h('td', {}, r.level ?? '–'),
      h('td', {}, r.is_bonus ? h('span', { class: 'badge warn' }, 'bonus') : ''),
      h('td', {}, h('button', { class: 'sm danger', onClick: async () => { if (await confirmDlg('Delete this run?')) { await api.del(`/game/runs/${r.id}`); load(); } } }, '✕'))))));

    credTable.innerHTML = '';
    credTable.append(h('thead', {}, h('tr', {}, ...['Student', 'Goal done', 'Used', 'Remaining', 'Bonus', ''].map(t => h('th', {}, t)))));
    const rows = await Promise.all(students.map(s => api.get(`/students/${s.id}/game/credits`).then(c => [s, c]).catch(() => [s, null])));
    credTable.append(h('tbody', {}, ...rows.map(([s, c]) => h('tr', {},
      h('td', {}, s.name),
      h('td', {}, c?.unlocked ? h('span', { class: 'badge ok' }, 'yes') : h('span', { class: 'badge' }, 'no')),
      h('td', {}, c ? `${c.used}/${c.runs_per_day}` : '–'),
      h('td', {}, c ? c.remaining : '–'),
      h('td', {}, !c ? '–' : c.bonus_used ? 'used' : c.bonus_unlocked ? h('span', { class: 'badge ok' }, 'unlocked') : c.bonus_available ? `practise until ${Math.round(c.bonus_target_seconds / 60)} min` : '–'),
      h('td', {}, h('button', { class: 'sm', onClick: async () => { await api.post(`/students/${s.id}/game/reset`, {}); toast(`Runs restored for ${s.name}`); load(); } }, 'Give runs back'))))));
  }
  load();
}
