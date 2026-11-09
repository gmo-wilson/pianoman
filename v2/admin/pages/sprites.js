// Sprite manager: sets → an unbounded, orderable ladder of levels → per-level art (atlas.png + frames.json).
import { api, h, toast, confirmDlg, animateSprite, loadImage } from '../app.js';

const ANIMS = ['idle', 'dance', 'run', 'jump'];
const ANIM_HELP = {
  idle: 'Required. Front view loop — the buddy at rest everywhere in the app.',
  dance: 'Loop for celebrations: goal reached, step gained, milestone transformation (falls back to idle).',
  run: 'Running loop used by the Runner mini-game (falls back to dance → idle).',
  jump: 'Plays once when the buddy jumps in the Runner (falls back to run → idle).',
};
let stopPreviews = [];

export async function render(root) {
  root.append(h('h1', {}, 'Sprites'));
  let sets = await api.get('/sprites/sets');
  let setId = (sets.find(s => s.is_default) || sets[0])?.id;
  let selectedId = null;
  let levels = [];

  // ---------------------------------------------------------------- set bar
  const setSel = h('select');
  const newName = h('input', { placeholder: 'New set name', style: 'width:150px' });
  const seedChk = h('input', { type: 'checkbox', checked: true });
  const setBar = h('div', { class: 'card' }, h('div', { class: 'row between' },
    h('div', { class: 'row' },
      h('label', { class: 'field' }, 'Sprite set', setSel),
      h('button', { class: 'sm', onClick: async () => { await api.post(`/sprites/sets/${setId}/default`); toast('Default set updated'); await refreshSets(); } }, 'Make default'),
      h('button', { class: 'sm', onClick: async () => {
        const name = prompt('Rename set', sets.find(s => s.id === setId)?.name || '');
        if (name) { await api.patch(`/sprites/sets/${setId}`, { name }); await refreshSets(); }
      } }, 'Rename'),
      h('button', { class: 'sm danger', onClick: async () => {
        if (!(await confirmDlg('Delete this set and all its art? Students using it fall back to the default set.'))) return;
        try { await api.del(`/sprites/sets/${setId}`); setId = null; await refreshSets(); loadLevels(); } catch (e) { toast(e.message, true); }
      } }, 'Delete set')),
    h('div', { class: 'row' }, newName, h('label', { class: 'row small muted' }, seedChk, 'seed 32 default names'),
      h('button', { class: 'sm primary', onClick: async () => {
        if (!newName.value.trim()) return;
        const s = await api.post('/sprites/sets', { name: newName.value.trim(), seed_defaults: seedChk.checked });
        newName.value = ''; setId = s.id; await refreshSets(); loadLevels();
      } }, 'Create set'))));
  root.append(setBar);
  setSel.addEventListener('change', () => { setId = Number(setSel.value); selectedId = null; loadLevels(); });

  // ---------------------------------------------------------------- ladder + editor
  const ladder = h('div');
  const editor = h('div', { class: 'card' });
  const toolbar = h('div', { class: 'row between', style: 'margin-bottom:12px' },
    h('h2', { style: 'margin:0' }, 'Levels'),
    h('div', { class: 'row' },
      h('button', { class: 'sm primary', onClick: async () => { const l = await api.post(`/sprites/sets/${setId}/levels`, {}); selectedId = l.id; toast('Level added'); loadLevels(); } }, '+ Add level'),
      h('button', { class: 'sm', onClick: async () => {
        if (!confirm('Generate placeholder art for every level that has none yet?')) return;
        try { await api.post(`/sprites/sets/${setId}/placeholders`, { only_missing: true }); toast('Placeholders generated'); window.__manifest = null; loadLevels(); } catch (e) { toast(e.message, true); }
      } }, 'Placeholders for missing'),
      h('button', { class: 'sm', onClick: async () => {
        if (!confirm('Overwrite ALL levels of this set with placeholder art?')) return;
        try { await api.post(`/sprites/sets/${setId}/placeholders`, {}); toast('Placeholders generated'); window.__manifest = null; loadLevels(); } catch (e) { toast(e.message, true); }
      } }, 'Placeholders for all')));
  root.append(h('div', { class: 'grid', style: 'grid-template-columns: 1fr 400px; margin-top:16px; align-items:start' },
    h('div', { class: 'card' }, toolbar, h('p', { class: 'small muted' }, 'Every 3 steps on the road (one step per completed practice day, one back per missed day) the buddy transforms into the next level; the top level is wherever the ladder ends. Use the arrows to reorder.'), ladder),
    editor));

  async function refreshSets() {
    sets = await api.get('/sprites/sets');
    if (!sets.find(s => s.id === setId)) setId = (sets.find(s => s.is_default) || sets[0])?.id;
    setSel.innerHTML = '';
    sets.forEach(s => setSel.append(h('option', { value: s.id, selected: s.id === setId }, `${s.name}${s.is_default ? ' (default)' : ''} · ${s.levels_ready}/${s.levels_total} with art`)));
  }
  await refreshSets();

  async function loadLevels() {
    if (!setId) { ladder.innerHTML = ''; editor.innerHTML = ''; return; }
    levels = await api.get(`/sprites/sets/${setId}/levels`);
    if (!levels.find(l => l.id === selectedId)) selectedId = levels[0]?.id ?? null;
    ladder.innerHTML = '';
    const table = h('table');
    table.append(h('thead', {}, h('tr', {}, ...['#', '', 'Name', 'Colour', 'Art', ''].map(t => h('th', {}, t)))));
    const tbody = h('tbody');
    for (const l of levels) {
      const canvas = h('canvas', { width: 48, height: 48, style: 'width:48px;height:48px;image-rendering:pixelated;border-radius:8px;background:#0f141c' });
      const tr = h('tr', { style: l.id === selectedId ? 'outline:2px solid var(--accent); outline-offset:-2px' : '', onClick: () => { selectedId = l.id; loadLevels(); } },
        h('td', { class: 'mono muted' }, l.level),
        h('td', {}, canvas),
        h('td', {}, h('strong', {}, l.display_name || `Level ${l.level}`)),
        h('td', {}, h('span', { class: 'swatch', style: `background:${l.color}` }), h('span', { class: 'small mono muted' }, l.color)),
        h('td', {}, l.ready ? h('span', { class: 'badge ok' }, `${Object.keys(l.animations).length}/${ANIMS.length} anims`) : h('span', { class: 'badge warn' }, 'no art')),
        h('td', {}, h('div', { class: 'row', style: 'gap:6px' },
          h('button', { class: 'sm ghost', title: 'Move up', disabled: l.level === 1, onClick: e => { e.stopPropagation(); move(l, l.level - 1); } }, '↑'),
          h('button', { class: 'sm ghost', title: 'Move down', disabled: l.level === levels.length, onClick: e => { e.stopPropagation(); move(l, l.level + 1); } }, '↓'),
          h('button', { class: 'sm ghost', title: 'Insert a level above', onClick: async e => { e.stopPropagation(); const n = await api.post(`/sprites/sets/${setId}/levels`, { position: l.level }); selectedId = n.id; loadLevels(); } }, '+↑'),
          h('button', { class: 'sm danger', title: 'Delete level', disabled: levels.length <= 1, onClick: async e => {
            e.stopPropagation();
            if (!(await confirmDlg(`Delete level ${l.level} "${l.display_name}" and its art? Levels above shift down; students above this level drop one.`))) return;
            try { await api.del(`/sprites/levels/${l.id}`); window.__manifest = null; toast('Level deleted'); loadLevels(); } catch (err) { toast(err.message, true); }
          } }, '✕'))));
      tbody.append(tr);
      if (l.ready) previewAnim(canvas, l.animations.idle, 48);
      else { const ctx = canvas.getContext('2d'); ctx.fillStyle = l.color || '#243042'; ctx.globalAlpha = .35; ctx.beginPath(); ctx.arc(24, 24, 16, 0, Math.PI * 2); ctx.fill(); }
    }
    table.append(tbody);
    ladder.append(table);
    await refreshSets();
    renderEditor(levels.find(l => l.id === selectedId));
  }

  async function move(l, to) {
    await api.post(`/sprites/levels/${l.id}/move`, { to });
    window.__manifest = null;
    loadLevels();
  }

  function renderEditor(l) {
    stopPreviews.forEach(f => f()); stopPreviews = [];
    editor.innerHTML = '';
    if (!l) { editor.append(h('p', { class: 'muted' }, 'Select a level')); return; }
    const nameIn = h('input', { value: l.display_name || '' });
    const colorIn = h('input', { type: 'color', value: l.color || '#38bdf8' });
    const saveMeta = async () => {
      await api.patch(`/sprites/levels/${l.id}`, { display_name: nameIn.value.trim(), color: colorIn.value });
      window.__manifest = null; toast('Saved'); loadLevels();
    };
    editor.append(
      h('h2', {}, `Level ${l.level}`),
      h('div', { class: 'row' }, h('label', { class: 'field', style: 'flex:1' }, 'Name', nameIn), h('label', { class: 'field' }, 'Colour', colorIn),
        h('button', { class: 'sm primary', style: 'align-self:end', onClick: saveMeta }, 'Save')),
      h('h2', { style: 'margin-top:16px' }, 'Animations'),
      h('p', { class: 'small muted' }, 'One sheet per animation: drop the PNG and its JSON (your generator\u2019s export, or Aseprite/TexturePacker). Only idle is required; the rest fall back automatically. A tagged Aseprite sheet dropped on any slot is split into its tags.'),
    );
    const slots = h('div', { class: 'grid', style: 'gap:10px' });
    editor.append(slots);
    for (const name of ANIMS) slots.append(animSlot(l, name));
  }

  function animSlot(l, name) {
    const a = l.animations[name];
    const canvas = h('canvas', { width: 64, height: 64, style: 'width:64px;height:64px;image-rendering:pixelated;background:#0f141c;border-radius:10px;flex:none' });
    const pngIn = h('input', { type: 'file', accept: '.png', style: 'display:none' });
    const jsonIn = h('input', { type: 'file', accept: '.json', style: 'display:none' });
    const status = h('span', { class: 'small muted' }, a ? `${a.frame_count} frames · ${a.frame_w}×${a.frame_h}` : 'not uploaded');
    const drop = h('div', { class: 'dropzone', style: 'flex:1; padding:10px; text-align:left' },
      h('div', { class: 'row between' }, h('strong', {}, name, name === 'idle' ? h('span', { class: 'badge warn', style: 'margin-left:8px' }, 'required') : ''), status),
      h('div', { class: 'small muted', style: 'margin-top:4px' }, ANIM_HELP[name]),
      h('div', { class: 'row', style: 'margin-top:8px; gap:6px' },
        h('button', { class: 'sm', onClick: () => pngIn.click() }, pngIn.files[0] ? pngIn.files[0].name : 'PNG…'),
        h('button', { class: 'sm', onClick: () => jsonIn.click() }, 'JSON…'),
        h('button', { class: 'sm primary', onClick: () => upload() }, 'Upload'),
        a ? h('button', { class: 'sm danger', onClick: async () => { if (await confirmDlg(`Remove ${name} from level ${l.level}?`)) { await api.del(`/sprites/levels/${l.id}/animations/${name}`); window.__manifest = null; loadLevels(); } } }, '✕') : ''));
    const picked = () => { status.textContent = `${pngIn.files[0]?.name || '— .png'} + ${jsonIn.files[0]?.name || '— .json'}`; };
    pngIn.addEventListener('change', picked); jsonIn.addEventListener('change', picked);
    drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('over'));
    drop.addEventListener('drop', e => {
      e.preventDefault(); drop.classList.remove('over');
      for (const f of e.dataTransfer.files) { if (f.name.toLowerCase().endsWith('.png')) setFile(pngIn, f); else if (f.name.toLowerCase().endsWith('.json')) setFile(jsonIn, f); }
      picked();
      if (pngIn.files[0] && jsonIn.files[0]) upload();
    });
    const upload = async () => {
      if (!pngIn.files[0] || !jsonIn.files[0]) return toast('Need the PNG and its JSON', true);
      const fd = new FormData(); fd.append('atlas', pngIn.files[0]); fd.append('frames', jsonIn.files[0]);
      try { await api.upload(`/sprites/levels/${l.id}/animations/${name}`, fd); toast(`${name} uploaded`); window.__manifest = null; loadLevels(); }
      catch (e) { toast(e.message, true); }
    };
    const row = h('div', { class: 'row', style: 'align-items:stretch' }, canvas, drop);
    row.append(pngIn, jsonIn);
    if (a) previewAnim(canvas, a, 64).then(stop => stopPreviews.push(stop));
    else { const ctx = canvas.getContext('2d'); ctx.fillStyle = '#243042'; ctx.fillRect(0, 0, 64, 64); }
    return row;
  }

  async function previewAnim(canvas, a, size) {
    try {
      const [img, spec] = await Promise.all([loadImage(`/files/${a.atlas_path}?v=${a.etag}`), fetch(`/files/${a.frames_path}?v=${a.etag}`).then(r => r.json())]);
      return animateSprite(canvas, img, spec, null, size);
    } catch { return () => {}; }
  }

  loadLevels();
  return () => { stopPreviews.forEach(f => f()); };
}

function setFile(input, file) { const dt = new DataTransfer(); dt.items.add(file); input.files = dt.files; }
