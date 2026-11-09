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
      const lvlIn = h('input', { type: 'number', min: 0, max: buddy?.max_level ?? 999, value: s.forced_level ?? '', placeholder: `auto (1–${buddy?.max_level ?? '?'})`, style: 'width:110px' });

      const save = async () => {
        try {
          await api.patch(`/students/${s.id}`, {
            name: nameIn.value.trim(), color: colorIn.value, active: activeIn.checked ? 1 : 0,
            sprite_set: setSel.value ? Number(setSel.value) : null,
            forced_level: lvlIn.value ? Number(lvlIn.value) : null,
          });
          toast('Saved'); load();
        } catch (e) { toast(e.message, true); }
      };
      card.append(
        h('div', { class: 'row between' },
          h('div', { class: 'row' }, h('span', { class: 'swatch', style: `background:${s.color || '#38bdf8'}` }), h('h2', { style: 'margin:0' }, s.name),
            buddy ? h('span', { class: 'badge' }, `Lv ${buddy.level} · ${buddy.steps} steps`) : null,
            buddy?.evolved_today ? h('span', { class: 'badge ok' }, 'evolved today') : null,
            s.active ? null : h('span', { class: 'badge danger' }, 'inactive')),
          h('div', { class: 'row' },
            h('button', { class: 'sm danger', onClick: async () => { if (await confirmDlg(`Delete ${s.name} and ALL their records?`)) { await api.del(`/students/${s.id}`); load(); } } }, 'Delete'))),
        stats ? h('p', { class: 'muted small' }, `${stats.days_completed} days completed · best streak ${stats.best_streak} · ${Math.round(stats.total_practice_seconds / 60)} min total · ${stats.sessions} sessions`) : null,
        stats ? h('div', { class: 'strip' }, ...last30(stats.last_30_days)) : null,
        h('div', { class: 'row', style: 'margin-top:12px' },
          h('label', { class: 'field' }, 'Name', nameIn), h('label', { class: 'field' }, 'Colour', colorIn),
          h('label', { class: 'field' }, 'Sprite set', setSel), h('label', { class: 'field' }, 'Active', activeIn)),
        h('div', { class: 'row', style: 'margin-top:8px' },
          h('label', { class: 'field' }, 'Force level (leave empty for the road)', lvlIn),
          h('button', { class: 'primary', style: 'align-self:end', onClick: save }, 'Save')),
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
