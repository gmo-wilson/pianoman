import { api, h, toast } from '../app.js';

export async function render(root) {
  root.append(h('h1', {}, 'Settings'));
  const s = await api.get('/settings');
  const goal = h('input', { type: 'number', min: 1, max: 120, value: s.goal_minutes });
  const slow = h('input', { type: 'number', value: s.metronome.slow });
  const normal = h('input', { type: 'number', value: s.metronome.normal });
  const fast = h('input', { type: 'number', value: s.metronome.fast });
  const idle = h('input', { type: 'number', value: s.inactivity_timeout_seconds });
  const limit = h('input', { type: 'number', value: s.session_history_limit });
  const trans = h('input', { type: 'number', value: s.kiosk?.transition_ms ?? 320 });
  const token = h('input', { type: 'password', value: api.token(), placeholder: 'leave empty if backend has none' });

  root.append(h('div', { class: 'grid cols-2' },
    h('div', { class: 'card' }, h('h2', {}, 'Practice'),
      h('div', { class: 'row' }, h('label', { class: 'field' }, 'Daily goal (minutes)', goal), h('label', { class: 'field' }, 'Auto-end after silence (s)', idle), h('label', { class: 'field' }, 'Sessions to keep', limit)),
      h('h2', { style: 'margin-top:16px' }, 'Metronome (bpm)'),
      h('div', { class: 'row' }, h('label', { class: 'field' }, 'Slow', slow), h('label', { class: 'field' }, 'Normal', normal), h('label', { class: 'field' }, 'Fast', fast)),
      h('h2', { style: 'margin-top:16px' }, 'Kiosk'),
      h('div', { class: 'row' }, h('label', { class: 'field' }, 'Transition (ms)', trans)),
      h('button', { class: 'primary', style: 'margin-top:16px', onClick: async () => {
        try {
          await api.put('/settings', { goal_minutes: +goal.value, inactivity_timeout_seconds: +idle.value, session_history_limit: +limit.value,
            metronome: { slow: +slow.value, normal: +normal.value, fast: +fast.value }, kiosk: { ...(s.kiosk || {}), transition_ms: +trans.value } });
          toast('Saved — the kiosk picks it up on its next boot or session');
        } catch (e) { toast(e.message, true); }
      } }, 'Save')),
    h('div', { class: 'card' }, h('h2', {}, 'System'),
      h('label', { class: 'field' }, 'Admin token (stored in this browser)', token),
      h('button', { class: 'sm', style: 'margin-top:8px', onClick: () => { api.setToken(token.value); toast('Token saved'); } }, 'Save token'),
      h('h2', { style: 'margin-top:20px' }, 'Backend update'),
      h('p', { class: 'small muted' }, 'Runs deploy/update.sh on the Pi: git pull, pip install, DB migrations, service restart. Records are untouched.'),
      h('button', { class: 'danger', onClick: async () => { if (!confirm('Update backend now? The admin will be unavailable for ~30 s.')) return; try { await api.post('/system/update'); toast('Update started'); } catch (e) { toast(e.message, true); } } }, 'Update backend'),
      h('h2', { style: 'margin-top:20px' }, 'MIDI'),
      h('pre', { class: 'small mono muted', id: 'midi-ports' }, 'loading…')),
  ));
  api.get('/midi/ports').then(p => (document.getElementById('midi-ports').textContent = JSON.stringify(p, null, 2))).catch(() => {});
}
