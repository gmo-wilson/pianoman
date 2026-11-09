// Releases: upload a Godot .pck exported with the "Content only" preset; kiosks pull it when idle.
import { api, h, toast } from '../app.js';

export async function render(root) {
  root.append(h('h1', {}, 'Releases'));
  const file = h('input', { type: 'file', accept: '.pck' });
  const version = h('input', { placeholder: 'Version, e.g. 2.1.0' });
  const notes = h('input', { placeholder: 'Release notes (optional)', style: 'flex:1' });
  const current = h('input', { type: 'checkbox', checked: true });
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Upload kiosk release (.pck)'),
    h('div', { class: 'row' }, file, version, notes, h('label', { class: 'row small muted' }, current, 'make current'),
      h('button', { class: 'primary', onClick: async () => {
        if (!file.files[0] || !version.value.trim()) return toast('Need a .pck and a version', true);
        const fd = new FormData(); fd.append('file', file.files[0]); fd.append('version', version.value.trim()); fd.append('notes', notes.value); fd.append('make_current', current.checked);
        try { await api.upload('/releases', fd); toast('Release uploaded'); file.value = ''; version.value = ''; load(); } catch (e) { toast(e.message, true); }
      } }, 'Upload')),
    h('p', { class: 'small muted' }, 'Kiosks check for a new current release on boot and every 15 minutes while idle on the home screen. Student records are never touched by a release — they live in the backend database.')));
  const table = h('table');
  root.append(h('div', { class: 'card', style: 'margin-top:16px' }, table));

  async function load() {
    const rels = await api.get('/releases');
    table.innerHTML = '';
    table.append(h('thead', {}, h('tr', {}, ...['Version', 'Uploaded', 'Size', 'SHA-256', 'Notes', ''].map(t => h('th', {}, t)))));
    table.append(h('tbody', {}, ...rels.map(r => h('tr', {},
      h('td', {}, r.version, ' ', r.is_current ? h('span', { class: 'badge ok' }, 'current') : ''), h('td', {}, r.created_at),
      h('td', {}, `${(r.size / 1024 / 1024).toFixed(1)} MB`), h('td', { class: 'mono small' }, r.sha256.slice(0, 16) + '…'), h('td', {}, r.notes || ''),
      h('td', {}, r.is_current ? '' : h('button', { class: 'sm', onClick: async () => { await api.post(`/releases/${r.version}/current`); toast('Rolled to ' + r.version); load(); } }, 'Make current')),
    ))));
  }
  load();
}
