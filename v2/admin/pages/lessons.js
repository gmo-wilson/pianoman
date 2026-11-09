import { api, h, toast, confirmDlg } from '../app.js';

export async function render(root) {
  root.append(h('h1', {}, 'Lessons'));
  const list = h('div', { class: 'grid cols-2' });
  root.append(h('p', { class: 'muted' }, 'Lessons are what students can play along to on the kiosk. Create them from an uploaded song (Songs page) or edit the chord list here.'), list);

  async function load() {
    list.innerHTML = '';
    for (const l of await api.get('/lessons')) {
      const nameIn = h('input', { value: l.name });
      const chordsIn = h('input', { value: l.chords.join(', '), placeholder: 'Am, E, C, G' });
      list.append(h('div', { class: 'card' },
        h('div', { class: 'row between' }, h('h2', {}, l.name), h('span', { class: 'muted small' }, `${Math.round(l.events_count / 2)} notes`)),
        h('div', { class: 'row' }, h('label', { class: 'field' }, 'Name', nameIn), h('label', { class: 'field', style: 'flex:1' }, 'Chords', chordsIn)),
        h('div', { class: 'row', style: 'margin-top:10px' },
          h('button', { class: 'primary sm', onClick: async () => {
            const full = await api.get(`/lessons/${l.id}`);
            await api.put(`/lessons/${l.id}`, { ...full, name: nameIn.value, chords: chordsIn.value.split(',').map(s => s.trim()).filter(Boolean) });
            toast('Saved'); load();
          } }, 'Save'),
          h('button', { class: 'sm', onClick: () => api.post('/player/load', { lesson_id: l.id, autoplay: true }).then(() => toast('Playing on piano')).catch(e => toast(e.message, true)) }, '▶ Play on piano'),
          h('button', { class: 'sm', onClick: () => api.post('/player/stop') }, '■'),
          h('button', { class: 'sm danger', onClick: async () => { if (await confirmDlg(`Delete lesson "${l.name}"?`)) { await api.del(`/lessons/${l.id}`); load(); } } }, 'Delete')),
      ));
    }
  }
  load();
}
