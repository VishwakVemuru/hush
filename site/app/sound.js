/* Ambient sound generated live with Web Audio — no audio files needed. */
(function () {
  let ctx = null, master = null, current = null, nodes = [];
  function ensure() {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      master = ctx.createGain(); master.gain.value = 0; master.connect(ctx.destination);
    }
    if (ctx.state === 'suspended') ctx.resume();
  }
  function noiseBuffer(type) {
    const len = ctx.sampleRate * 4, buf = ctx.createBuffer(2, len, ctx.sampleRate);
    for (let ch = 0; ch < 2; ch++) {
      const d = buf.getChannelData(ch);
      let last = 0, b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
      for (let i = 0; i < len; i++) {
        const w = Math.random() * 2 - 1;
        if (type === 'brown') { last = (last + 0.02 * w) / 1.02; d[i] = last * 3.5; }
        else { // pink
          b0 = 0.99886 * b0 + w * 0.0555179; b1 = 0.99332 * b1 + w * 0.0750759; b2 = 0.969 * b2 + w * 0.153852;
          b3 = 0.8665 * b3 + w * 0.3104856; b4 = 0.55 * b4 + w * 0.5329522; b5 = -0.7616 * b5 - w * 0.016898;
          d[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11; b6 = w * 0.115926;
        }
      }
    }
    return buf;
  }
  function dropsBuffer() {
    // raindrops on a window: short bright ticks scattered in time, slightly different per ear
    const len = ctx.sampleRate * 6, buf = ctx.createBuffer(2, len, ctx.sampleRate), sr = ctx.sampleRate;
    for (let ch = 0; ch < 2; ch++) {
      const d = buf.getChannelData(ch);
      const n = 6 * 55;
      for (let k = 0; k < n; k++) {
        const at = Math.floor(Math.random() * (len - 2000)), f = 1800 + Math.random() * 4200, a = Math.pow(Math.random(), 2.2) * 0.5;
        const dec = 120 + Math.random() * 260, L = Math.floor(sr * 0.03);
        for (let i = 0; i < L; i++) { const t = i / sr; d[at + i] += a * Math.sin(2 * Math.PI * f * t * (1 - t * 6)) * Math.exp(-t * dec); }
      }
    }
    return buf;
  }
  function src(type) { const s = ctx.createBufferSource(); s.buffer = noiseBuffer(type); s.loop = true; return s; }
  function build(kind) {
    const out = ctx.createGain(); out.connect(master); const made = [out];
    if (kind === 'rain') {
      const s = src('pink'), hp = ctx.createBiquadFilter(), lp = ctx.createBiquadFilter();
      hp.type = 'highpass'; hp.frequency.value = 400; lp.type = 'lowpass'; lp.frequency.value = 6500;
      s.connect(hp); hp.connect(lp); lp.connect(out); out.gain.value = 0.55; s.start(); made.push(s);
      const s2 = src('brown'), g2 = ctx.createGain(); g2.gain.value = 0.35; s2.connect(g2); g2.connect(out); s2.start(); made.push(s2);
      const s3 = ctx.createBufferSource(); s3.buffer = dropsBuffer(); s3.loop = true;
      const hp3 = ctx.createBiquadFilter(); hp3.type = 'highpass'; hp3.frequency.value = 1200;
      const g3 = ctx.createGain(); g3.gain.value = 0.55; s3.connect(hp3); hp3.connect(g3); g3.connect(out); s3.start(); made.push(s3);
    } else if (kind === 'waves') {
      const s = src('brown'), lp = ctx.createBiquadFilter(), g = ctx.createGain();
      lp.type = 'lowpass'; lp.frequency.value = 900; s.connect(lp); lp.connect(g); g.connect(out);
      const lfo = ctx.createOscillator(), lg = ctx.createGain(); lfo.frequency.value = 0.09; lg.gain.value = 0.45;
      lfo.connect(lg); lg.connect(g.gain); g.gain.value = 0.55; s.start(); lfo.start(); made.push(s, lfo);
      out.gain.value = 0.9;
    } else {
      const s = src('brown'), lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 500;
      s.connect(lp); lp.connect(out); out.gain.value = 0.8; s.start(); made.push(s);
    }
    return made;
  }
  const Sound = {
    volume: 0.5,
    play(kind) {
      ensure();
      if (current === kind) return;
      this.stop(true);
      nodes = build(kind); current = kind;
      master.gain.cancelScheduledValues(ctx.currentTime);
      master.gain.setTargetAtTime(this.volume * 0.6, ctx.currentTime, 0.4);
    },
    stop(quick) {
      if (!ctx || !current) return;
      const old = nodes; current = null;
      master.gain.setTargetAtTime(0, ctx.currentTime, quick ? 0.05 : 0.35);
      setTimeout(() => old.forEach(n => { try { n.stop && n.stop(); n.disconnect(); } catch (e) {} }), quick ? 200 : 1400);
    },
    setVolume(v) { this.volume = v; if (ctx && current) master.gain.setTargetAtTime(v * 0.6, ctx.currentTime, 0.15); },
    get playing() { return current; }
  };
  window.Sound = Sound;
})();
