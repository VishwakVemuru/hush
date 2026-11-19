/* hush. site: the hero tide (same code as the app) and the live demo tabs. */
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---- hero tide: counts down a 25-minute session in real time; tap the water for ripples ----
  const cv = document.getElementById('tide');
  if (cv && window.Tide) {
    const size = () => Math.round(cv.getBoundingClientRect().width) || 420;
    const tide = new Tide(cv, { size: size() });
    tide.reduce = reduce;
    const TOTAL = 25 * 60, start = Date.now();
    const clock = s => { s = Math.max(0, Math.ceil(s)); return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0'); };
    const tick = () => {
      const left = TOTAL - ((Date.now() - start) / 1000) % TOTAL;
      tide.set({ target: left / TOTAL, ampT: 7, speedT: 1, caption: 'focus', text: clock(left) });
      setTimeout(tick, 250);
    };
    tide.level = 1; tick();
    addEventListener('resize', () => { const s = size(); if (s !== tide.size) tide.resize(s); });
    cv.addEventListener('pointerdown', e => {
      const b = cv.getBoundingClientRect(), k = tide.size / b.width;
      tide.poke((e.clientX - b.left) * k, (e.clientY - b.top) * k);
    });
    cv.addEventListener('pointermove', e => {
      const b = cv.getBoundingClientRect(), k = tide.size / b.width;
      cv.style.cursor = tide.inWater((e.clientX - b.left) * k, (e.clientY - b.top) * k) ? 'pointer' : 'default';
    });
  }

  // ---- demo tabs drive the real app inside the iframe ----
  const frame = document.getElementById('app');
  const tabs = [...document.querySelectorAll('.demo-tabs [data-view]')];
  tabs.forEach(t => t.addEventListener('click', () => {
    tabs.forEach(x => x.setAttribute('aria-selected', String(x === t)));
    try {
      // sample account in the demo, so Friends shows the leaderboard straight away
      if (t.dataset.view === 'friends') frame.contentWindow.__signed = 1;
      const btn = frame.contentDocument.querySelector(`.nav-item[data-view="${t.dataset.view}"]`);
      if (btn) btn.click();
    } catch (e) { /* demo not loaded yet */ }
  }));
  // keep the tabs in step when someone clicks inside the demo
  frame && frame.addEventListener('load', () => {
    try {
      frame.contentDocument.addEventListener('click', e => {
        const b = e.target.closest('.nav-item');
        if (b) tabs.forEach(x => x.setAttribute('aria-selected', String(x.dataset.view === b.dataset.view)));
      });
    } catch (e) {}
  });
})();
