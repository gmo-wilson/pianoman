import { api, h, toast, confirmDlg } from '../app.js';

export async function render(root) {
  root.append(h('h1', {}, 'Songs'));
  const file = h('input', { type: 'file', accept: '.mid,.midi' });
  const title = h('input', { placeholder: 'Title (optional)' });
  const composer = h('input', { placeholder: 'Composer (optional)' });
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Upload MIDI'),
    h('div', { class: 'row' }, file, title, composer, h('button', { class: 'primary', onClick: async () => {
      if (!file.files[0]) return toast('Pick a .mid file', true);
      const fd = new FormData(); fd.append('file', file.files[0]); fd.append('title', title.value); fd.append('composer', composer.value);
      try { await api.upload('/songs/upload', fd); toast('Uploaded'); file.value = ''; load(); } catch (e) { toast(e.message, true); }
    } }, 'Upload'))));
  const table = h('table');
  root.append(h('div', { class: 'card', style: 'margin-top:16px' }, table));

  async function load() {
    const songs = await api.get('/songs');
    table.innerHTML = '';
    table.append(h('thead', {}, h('tr', {}, ...['Title', 'Composer', 'Length', 'Notes', 'Chords', ''].map(t => h('th', {}, t)))));
    table.append(h('tbody', {}, ...songs.map(s => h('tr', {},
      h('td', {}, s.title), h('td', {}, s.composer || '–'), h('td', {}, `${s.duration_seconds}s`), h('td', {}, s.notes_count), h('td', {}, s.chords.join(' ')),
      h('td', {}, h('div', { class: 'row' },
        h('button', { class: 'sm', onClick: () => api.post('/player/load', { song_id: s.id, autoplay: true }).then(() => toast('Playing')).catch(e => toast(e.message, true)) }, '▶'),
        h('button', { class: 'sm', onClick: () => api.post('/player/stop') }, '■'),
        h('button', { class: 'sm', onClick: async () => { await api.post(`/songs/${s.id}/to-lesson`, {}); toast('Lesson created'); } }, '→ Lesson'),
        h('a', { class: 'btn sm', href: `/files/songs/${s.filename}`, download: s.filename }, '⬇'),
        h('button', { class: 'sm danger', onClick: async () => { if (await confirmDlg(`Delete "${s.title}"?`)) { await api.del(`/songs/${s.id}`); load(); } } }, '✕'))),
    ))));
  }
  load();
}
