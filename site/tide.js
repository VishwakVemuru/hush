/* The Tide timer: water level = time left. Digits split colour exactly at the waterline. */
(function () {
  const BLUE = [62, 106, 158], MOSS = [94, 138, 90], BACKB = [143, 166, 196], BACKM = [160, 190, 150];
  const NAVY = '#1F3550', CREAM = '#F3EFE7', TRACK = '#DDD5C4', BG = '#FBF8F2';
  const lerp = (a, b, t) => a + (b - a) * t;
  const mix = (c1, c2, t) => c1.map((v, i) => Math.round(lerp(v, c2[i], t)));
  const rgb = (c, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

  class Tide {
    constructor(canvas, opts = {}) {
      this.cv = canvas; this.ctx = canvas.getContext('2d');
      this.size = opts.size || 300; this.mini = !!opts.mini;
      this.level = 1; this.target = 1;
      this.amp = 5; this.ampT = 5; this.speed = 0.6; this.speedT = 0.6;
      this.moss = 0; this.mossT = 0; // 0 = blue, 1 = moss
      this.text = '50:00'; this.caption = 'ready';
      this.phase = 0; this.last = performance.now(); this.reduce = false; this.rings = []; this.drops = [];
      this.surf = null; // last drawn waterline, for hit-testing clicks
      this.resize();
      requestAnimationFrame(t => this.frame(t));
    }
    resize(size) {
      if (size) this.size = size;
      const dpr = window.devicePixelRatio || 1, s = this.size;
      this.cv.width = s * dpr; this.cv.height = s * dpr;
      this.cv.style.width = s + 'px'; this.cv.style.height = s + 'px';
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    set(o) { Object.assign(this, o); }
    fillFromZero() { this.level = 0; }
    /** Is (x, y), in canvas pixels, inside the circle and under the water? */
    inWater(x, y) {
      const s = this.size, r = s / 2 - (this.mini ? 2 : 4);
      if (Math.hypot(x - s / 2, y - s / 2) > r || !this.surf) return false;
      return y >= this.surfaceAt(x) - 2;
    }
    surfaceAt(x) {
      const p = this.surf, i = Math.max(0, Math.min(p.length - 1, Math.round(x / 3)));
      return p[i][1];
    }
    /** Ripple from the point that was tapped. Returns false (and does nothing) if it missed the water. */
    poke(x, y) {
      if (x === undefined) { x = this.size / 2; y = this.size * 0.7; } else if (!this.inWater(x, y)) return false;
      const k = this.size / 300;
      this.amp += 2.5 * k;
      this.rings.push({ t: 0, x, y }); if (this.rings.length > 5) this.rings.shift();
      this.drops.push({ t: 0, x, depth: Math.max(0, Math.min(1, (y - this.surfaceAt(x)) / (this.size * 0.5))) });
      if (this.drops.length > 6) this.drops.shift();
      return true;
    }
    /** Extra height from tap splashes: two crests running outward from where you tapped. */
    splash(x) {
      if (!this.drops.length) return 0;
      const k = this.size / 300, w = 26 * k, v = 150 * k;
      let off = 0;
      for (const d of this.drops) {
        const a = 9 * k * (1 - 0.55 * d.depth) * Math.exp(-d.t * 1.8), dx = x - d.x, run = v * d.t;
        const g = u => Math.exp(-(u * u) / (w * w));
        off -= a * (g(dx - run) + g(dx + run)) * Math.cos(d.t * 9);
      }
      return off;
    }
    wave(lvl, amp, freq, phase, splashK = 1) {
      const s = this.size, pts = [];
      for (let x = 0; x <= s; x += 3) pts.push([x, lvl + Math.sin(x / (s * 0.12) * freq + phase) * amp + this.splash(x) * splashK]);
      return pts;
    }
    path(pts) {
      const c = this.ctx, s = this.size;
      c.beginPath(); c.moveTo(0, s + 2);
      for (const [x, y] of pts) c.lineTo(x, y);
      c.lineTo(s, s + 2); c.closePath();
    }
    label(color) {
      const c = this.ctx, s = this.size;
      c.fillStyle = color; c.textAlign = 'center'; c.textBaseline = 'middle';
      if (this.mini) {
        c.font = `italic ${s * 0.36}px "Instrument Serif", Georgia, serif`;
        return;
      }
      c.font = `italic ${Math.round(s * 0.235)}px "Instrument Serif", Georgia, serif`;
      c.fillText(this.text, s / 2, s * 0.47);
      c.font = `500 ${Math.round(s * 0.043)}px "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif`;
      c.fillText(this.caption, s / 2, s * 0.62);
    }
    frame(now) {
      const dt = Math.min(0.05, (now - this.last) / 1000); this.last = now;
      const k = 1 - Math.exp(-dt * 4.5);
      this.level += (this.target - this.level) * k;
      this.amp += (this.ampT - this.amp) * k * 0.6;
      this.speed += (this.speedT - this.speed) * k * 0.6;
      this.moss += (this.mossT - this.moss) * (1 - Math.exp(-dt * 2.2));
      this.phase += dt * this.speed * (this.reduce ? 0.3 : 1) * 2.4;
      this.rings.forEach(r => { r.t += dt; }); this.rings = this.rings.filter(r => r.t < 1.4);
      this.drops.forEach(d => { d.t += dt; }); this.drops = this.drops.filter(d => d.t < 2.6);
      this.draw();
      requestAnimationFrame(t => this.frame(t));
    }
    draw() {
      const c = this.ctx, s = this.size, r = s / 2 - (this.mini ? 2 : 4);
      const front = mix(BLUE, MOSS, this.moss), back = mix(BACKB, BACKM, this.moss);
      c.clearRect(0, 0, s, s);
      c.save();
      c.beginPath(); c.arc(s / 2, s / 2, r, 0, Math.PI * 2); c.fillStyle = BG; c.fill(); c.clip();
      const top = s / 2 - r, h = 2 * r;
      const lvl = top + h * 0.07 + (h * 0.93 + 8) * (1 - Math.max(0, Math.min(1, this.level)));
      const amp = (this.reduce ? 0.4 : 1) * this.amp * (s / 300);
      const back_ = this.wave(lvl - amp * 0.6, amp * 1.25, 1.3, this.phase * 0.7 + 2, 0.5);
      const front_ = this.wave(lvl, amp, 1, this.phase);
      this.surf = front_;
      this.path(back_); c.fillStyle = rgb(back, 0.5); c.fill();
      if (!this.mini) this.label(NAVY);
      this.path(front_); c.fillStyle = rgb(front); c.fill();
      if (!this.mini) { c.save(); this.path(front_); c.clip(); this.label(CREAM); c.restore(); }
      // rings spread from the tap point, clipped to the water so they never draw in the air
      if (this.rings.length) {
        c.save(); this.path(front_); c.clip();
        for (const ring of this.rings) {
          const p = ring.t / 1.4, rx = ring.x ?? s / 2, ry = ring.y ?? s / 2;
          for (const [lag, alpha] of [[0, 0.5], [0.22, 0.28]]) {
            const q = Math.max(0, p - lag), ee = 1 - Math.pow(1 - q, 3);
            if (q <= 0) continue;
            c.beginPath(); c.arc(rx, ry, r * 0.8 * ee, 0, Math.PI * 2);
            c.strokeStyle = `rgba(243,239,231,${alpha * (1 - q)})`; c.lineWidth = (2.6 * (1 - q) + 0.4) * (s / 300); c.stroke();
          }
        }
        c.restore();
      }
      c.restore();
      c.beginPath(); c.arc(s / 2, s / 2, r, 0, Math.PI * 2);
      c.strokeStyle = TRACK; c.lineWidth = this.mini ? 1.5 : 3; c.stroke();
    }
  }
  window.Tide = Tide;
})();
