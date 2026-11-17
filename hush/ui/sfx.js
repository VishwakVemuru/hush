/* Sound effects: one soft D-major-pentatonic family, quiet by default, low-latency via Web Audio. */
(function () {
  const NAMES = ['click', 'start', 'pause', 'resume', 'break', 'complete', 'block', 'task', 'warn', 'toggle_on', 'toggle_off'];
  const LEVEL = { click: 0.5, toggle_on: 0.6, toggle_off: 0.6, task: 0.8, block: 0.9, pause: 0.85, resume: 0.85, start: 1, warn: 0.9, break: 1, complete: 1 };
  let ctx = null, out = null, bufs = {}, loading = null, last = {};
  const SFX = {
    enabled: true, volume: 0.35,
    init() {
      if (loading) return loading;
      try { ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { return Promise.resolve(); }
      out = ctx.createGain(); out.gain.value = 1; out.connect(ctx.destination);
      loading = Promise.all(NAMES.map(n => fetch('sounds/' + n + '.wav').then(r => r.arrayBuffer()).then(a => ctx.decodeAudioData(a)).then(b => { bufs[n] = b; }).catch(() => {})));
      return loading;
    },
    play(name, gain = 1) {
      if (!this.enabled || !ctx || !bufs[name]) return;
      const now = performance.now();
      if (last[name] && now - last[name] < 60) return; // no machine-gun repeats
      last[name] = now;
      if (ctx.state === 'suspended') ctx.resume();
      const s = ctx.createBufferSource(), g = ctx.createGain();
      s.buffer = bufs[name]; g.gain.value = this.volume * (LEVEL[name] || 1) * gain;
      s.connect(g); g.connect(out); s.start();
    }
  };
  window.SFX = SFX;
  // Browsers only allow audio after a user gesture; unlock on the first one.
  const unlock = () => { SFX.init(); if (ctx && ctx.state === 'suspended') ctx.resume(); };
  window.addEventListener('pointerdown', unlock, { once: false, passive: true });
  window.addEventListener('keydown', unlock, { once: false });
})();
