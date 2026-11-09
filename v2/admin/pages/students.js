import { api, h, toast, confirmDlg, fmtTime } from '../app.js';


export async function render(root) {
  root.append(h('h1', {}, 'Students'));
  const list = h('div', { class: 'grid cols-2' });
  root.append(list);

  const addCard = h('div', { class: 'card' }, h('h2', {}, 'Add student'));
  const nameIn = h('input', { placeholder: 'Name' });
  const colorIn = h('input', { type: 'color', value: '#38bdf8' });
  addCard.append(h('div', { class: 'row' }, nameIn, colorIn, h('button', { class: 'primary', onClick: async () => {
    if (!nameIn.value.trim()) return;
    try { await api.post('/students', { name: nameIn.value.trim(), color: colorIn.value }); nameIn.value = ''; toast('Student added'); load(); }
    catch (e) { toast(e.message, true); }
  } }, 'Add')));
  root.append(addCard);

  async function load() {
    list.innerHTML = '';
    const [students, sets] = await Promise.all([api.get('/students?include_inactive=true'), api.get('/sprites/sets')]);
    for (const s of students) {
      const buddy = await api.get(`/students/${s.id}/buddy`).catch(() => null);
      const stats = await api.get(`/students/${s.id}/stats`).catch(() => null);
      const card = h('div', { class: 'card' });
      const nameIn = h('input', { value: s.name });
      const colorIn = h('input', { type: 'color', value: s.color || '#38bdf8' });
      const activeIn = h('input', { type: 'checkbox', checked: !!s.active });
      const setSel = h('select', {}, h('option', { value: '' }, 'default set'), ...sets.map(x => h('option', { value: x.id, selected: s.sprite_set === x.id }, x.name)));

      const save = async () => {
        try {
          await api.patch(`/students/${s.id}`, {
            name: nameIn.value.trim(), color: colorIn.value, active: activeIn.checked ? 1 : 0,
            sprite_set: setSel.value ? Number(setSel.value) : null,
          });
          toast('Saved'); load();
        } catch (e) { toast(e.message, true); }
      };
      card.append(
        h('div', { class: 'row between' },
          h('div', { class: 'row' }, h('span', { class: 'swatch', style: `background:${s.color || '#38bdf8'}` }), h('h2', { style: 'margin:0' }, s.name),
            buddy ? h('span', { class: 'badge' }, `Lv ${buddy.level} · ${buddy.level_name} · ${buddy.steps} steps`) : null,
            buddy?.anchor_date ? h('span', { class: 'badge warn', title: 'Position set by admin; history before this date is ignored' }, `placed ${buddy.anchor_date}`) : null,
            buddy?.evolved_today ? h('span', { class: 'badge ok' }, 'evolved today') : null,
            s.active ? null : h('span', { class: 'badge danger' }, 'inactive')),
          h('div', { class: 'row' },
            h('button', { class: 'sm danger', onClick: async () => { if (await confirmDlg(`Delete ${s.name} and ALL their records?`)) { await api.del(`/students/${s.id}`); load(); } } }, 'Delete'))),
        stats ? h('p', { class: 'muted small' }, `${stats.days_completed} days completed · best streak ${stats.best_streak} · ${Math.round(stats.total_practice_seconds / 60)} min total · ${stats.sessions} sessions`) : null,
        stats ? h('div', { class: 'strip' }, ...last30(stats.last_30_days)) : null,
        h('div', { class: 'row', style: 'margin-top:12px' },
          h('label', { class: 'field' }, 'Name', nameIn), h('label', { class: 'field' }, 'Colour', colorIn),
          h('label', { class: 'field' }, 'Sprite set', setSel), h('label', { class: 'field' }, 'Active', activeIn)),
        h('div', { class: 'row', style: 'margin-top:8px' }, h('button', { class: 'primary', onClick: save }, 'Save')),
        roadControls(s, buddy, load),
      );
      list.append(card);
    }
  }
  load();
}

function last30(days) {
  const by = Object.fromEntries((days || []).map(d => [d.day, d]));
  const out = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date(); d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    const rec = by[key];
    out.push(h('i', { class: rec ? (rec.completed ? 'done' : rec.seconds > 0 ? 'some' : '') : '', title: `${key}${rec ? ' · ' + fmtTime(rec.seconds) : ''}` }));
  }
  return out;
}


// --- Road position + resets -------------------------------------------------------------------
function roadControls(s, buddy, reload) {
  const spl = buddy?.steps_per_level ?? 3;
  const maxLevel = buddy?.max_level ?? 32;
  const levelIn = h('input', { type: 'number', min: 1, max: maxLevel, value: buddy?.level ?? 1, style: 'width:80px' });
  const stepIn = h('input', { type: 'number', min: 0, max: spl - 1, value: buddy?.steps_in_level ?? 0, style: 'width:80px' });
  const place = async () => {
    try {
      const r = await api.post(`/students/${s.id}/road`, { level: +levelIn.value, steps_in_level: +stepIn.value });
      toast(`${s.name} placed at level ${r.level} (${r.steps} steps). The road continues from today.`); reload();
    } catch (e) { toast(e.message, true); }
  };
  const unplace = async () => { await api.del(`/students/${s.id}/road`); toast('Placement removed — road computed from full history'); reload(); };
  const reset = async (flags, label) => {
    if (!(await confirmDlg(`${label} for ${s.name}? This cannot be undone.`))) return;
    try { await api.post(`/students/${s.id}/reset`, flags); toast('Done'); reload(); } catch (e) { toast(e.message, true); }
  };
  return h('details', { style: 'margin-top:12px' },
    h('summary', { class: 'muted', style: 'cursor:pointer' }, 'Road position & resets'),
    h('div', { class: 'row', style: 'margin-top:10px' },
      h('label', { class: 'field' }, `Level (1–${maxLevel})`, levelIn),
      h('label', { class: 'field' }, `Steps into it (0–${spl - 1})`, stepIn),
      h('button', { class: 'primary sm', style: 'align-self:end', onClick: place }, 'Place on the road'),
      buddy?.anchor_date ? h('button', { class: 'sm ghost', style: 'align-self:end', onClick: unplace }, 'Remove placement') : null),
    h('p', { class: 'small muted' }, 'Placing sets where the student is today; practising still moves forward and missed days still cost a step. Earlier history is ignored from that date.'),
    h('div', { class: 'row', style: 'margin-top:6px' },
      h('button', { class: 'sm danger', onClick: () => reset({ road: true }, 'Send the buddy back to the start of the road') }, 'Reset road'),
      h('button', { class: 'sm danger', onClick: () => reset({ runs: true }, 'Delete all Runner scores') }, 'Reset game scores'),
      h('button', { class: 'sm danger', onClick: () => reset({ sessions: true }, 'Delete all recorded sessions') }, 'Delete sessions'),
      h('button', { class: 'sm danger', onClick: () => reset({ practice: true, sessions: true, runs: true }, 'Delete ALL stats (practice days, sessions, scores)') }, 'Wipe all stats')));
}
