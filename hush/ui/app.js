/* hush. UI */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const ic = (id, cls = 'i') => `<svg class="${cls}"><use href="#i-${id}"/></svg>`;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const clock = s => { s = Math.max(0, Math.ceil(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return (h ? h + ':' + String(m).padStart(2, '0') : String(m).padStart(2, '0')) + ':' + String(x).padStart(2, '0'); };
  const dur = s => { const m = Math.round((s || 0) / 60); const h = Math.floor(m / 60); return h ? `${h}h ${m % 60}m` : `${m}m`; };
  const ease = t => 1 - Math.pow(1 - t, 3);
  const isSite = n => /\.[a-z]{2,}$/i.test(n) && !/\.exe$/i.test(n) && !n.includes(' ');
  function avatar(name, color, size = 30, glyph = null) {
    const bg = (color || '#B5AD9E') + '22', fg = color === '#D6CFC1' ? '#6E685C' : (color || '#6E685C');
    const letter = glyph || esc(String(name).replace(/^www\./, '')[0].toUpperCase());
    return `<div class="avatar" data-icon="${esc(name)}" style="width:${size}px;height:${size}px;background:${bg};color:${fg}">${letter}</div>`;
  }
  const iconMem = {};
  async function hydrateIcons(root) {
    const els = $$('.avatar[data-icon]', root);
    const want = [];
    els.forEach(el => {
      const n = el.dataset.icon;
      if (isSite(n)) {
        const img = new Image(); img.alt = ''; img.referrerPolicy = 'no-referrer';
        img.onload = () => { if (img.naturalWidth > 1) { el.innerHTML = ''; el.appendChild(img); el.classList.add('has-img'); } };
        img.src = `https://icons.duckduckgo.com/ip3/${encodeURIComponent(n.replace(/^www\./, ''))}.ico`;
      } else if (iconMem[n]) { el.innerHTML = `<img alt="" src="${iconMem[n]}">`; el.classList.add('has-img'); }
      else want.push(n);
    });
    if (!want.length) return;
    let got = {}; try { got = await api.app_icons([...new Set(want)]); } catch (e) {}
    Object.assign(iconMem, got);
    els.forEach(el => { const u = got[el.dataset.icon]; if (u && document.body.contains(el)) { el.innerHTML = `<img alt="" src="${u}">`; el.classList.add('has-img'); } });
    if (want.some(n => !got[n])) setTimeout(() => { if (document.body.contains(els[0] || document.body)) hydrateIconsOnce(root, want.filter(n => !got[n])); }, 2500);
  }
  async function hydrateIconsOnce(root, names) {
    let got = {}; try { got = await api.app_icons(names); } catch (e) {}
    Object.assign(iconMem, got);
    $$('.avatar[data-icon]', root).forEach(el => { const u = got[el.dataset.icon]; if (u) { el.innerHTML = `<img alt="" src="${u}">`; el.classList.add('has-img'); } });
  }

  let api, B = {}, S = null, lastEv = 0, offset = 0, view = 'focus', range = 'day', source = 'laptop', blockTab = 'apps', lastStats = null;
  let settings = {}, preset = [50, 10, 4], mode = 'soft', summaryShown = null, tide, prevPhase = null, tasksCache = [];

  /* ---------- small animation helpers ---------- */
  function countTo(el, to, fmt, ms = 800) {
    const from = el._v ?? 0; el._v = to;
    if (to == null) { el.textContent = fmt(null); return; }
    const t0 = performance.now();
    const step = now => { const p = Math.min(1, (now - t0) / ms); el.textContent = fmt(from + (to - from) * ease(p)); if (p < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  function stagger(container) {
    container.classList.remove('stagger'); [...container.children].forEach((c, i) => c.style.setProperty('--i', i));
    void container.offsetWidth; container.classList.add('stagger');
  }
  function segPill(seg) {
    const on = $('button.on', seg), pill = $('.seg-pill', seg); if (!on || !pill) return;
    pill.style.width = on.offsetWidth + 'px'; pill.style.transform = `translateX(${on.offsetLeft}px)`;
  }
  function tabLine() {
    const on = $('#blockTabs button.on'), l = $('#blockTabs .tab-line');
    l.style.width = on.offsetWidth + 'px'; l.style.transform = `translateX(${on.offsetLeft}px)`;
  }

  /* ---------- toasts & modals ---------- */
  const toastIcon = { block: 'shield', success: 'check', break: 'leaf', info: 'bell' };
  function toast(text, kind = 'info') {
    const t = document.createElement('div'); t.className = 'toast ' + kind;
    t.innerHTML = ic(toastIcon[kind] || 'bell') + `<span>${esc(text)}</span>`;
    $('#toasts').appendChild(t);
    const kill = () => { if (t._gone) return; t._gone = 1; t.classList.add('out'); setTimeout(() => t.remove(), 320); };
    t.onclick = kill; setTimeout(kill, kind === 'block' ? 4200 : 3600);
    while ($('#toasts').children.length > 4) $('#toasts').firstChild.remove();
  }
  function modal(html, onMount) {
    const s = document.createElement('div'); s.className = 'scrim';
    s.innerHTML = `<div class="modal">${html}</div>`; document.body.appendChild(s);
    const close = () => { s.classList.add('out'); setTimeout(() => s.remove(), 260); };
    s.addEventListener('mousedown', e => { if (e.target === s && !s.dataset.sticky) close(); });
    const esc = e => { if (e.key === 'Escape' && document.body.contains(s) && !s.dataset.sticky) { close(); document.removeEventListener('keydown', esc); } };
    document.addEventListener('keydown', esc);
    onMount && onMount(s, close);
    return close;
  }

  /* ---------- boot ---------- */
  async function boot() {
    B = await api.boot();
    settings = B.settings; lastEv = B.last_event;
    preset = settings.last_preset || [50, 10, 4]; mode = settings.last_mode || 'soft';
    document.body.classList.toggle('reduce', !!settings.reduce_motion);
    Sound.setVolume(settings.volume ?? 0.5); $('#vol').value = settings.volume ?? 0.5;
    SFX.enabled = settings.sfx !== false; SFX.volume = settings.sfx_volume ?? 0.35; SFX.init();
    tide = new Tide($('#tide'), { size: 300 }); tide.reduce = !!settings.reduce_motion;
    if (location.search.includes('mock')) window.__tide = tide; // UI preview only
    await document.fonts.ready;
    wire(); renderPresets(); setMode(mode, true); greet(); loadTasks(); loadOverview();
    requestAnimationFrame(() => { moveNavPill(); segPill($('#modeSeg')); segPill($('#rangeSeg')); segPill($('#srcSeg')); });
    stagger($('.focus-grid .side-col'));
    poll(); setInterval(poll, 500); setInterval(loadOverview, 30000); setInterval(greet, 60000);
    if (!settings.onboarded) setTimeout(onboarding, 700);
    requestAnimationFrame(tickTimer);
  }

  function greet() {
    const h = new Date().getHours(), name = settings.name ? `, ${settings.name}` : '';
    const g = h < 5 ? 'Still up' : h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
    $('#greet').innerHTML = `${g}<em>${esc(name)}</em>`;
    const d = new Date(); let line = d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
    if (settings.countdown_date && settings.countdown_label) {
      const days = Math.ceil((new Date(settings.countdown_date + 'T00:00') - new Date(d.toDateString())) / 864e5);
      if (days > 0) line += ` · ${days} day${days > 1 ? 's' : ''} to ${settings.countdown_label}`;
      else if (days === 0) line += ` · ${settings.countdown_label} today, you've got this`;
    }
    $('#dateLine').textContent = line;
  }

  /* ---------- navigation ---------- */
  function moveNavPill() {
    const on = $('.nav-item.on'); $('#navPill').style.transform = `translateY(${on.offsetTop}px)`;
  }
  function go(v) {
    if (v === view) return;
    SFX.play('click');
    $$('.nav-item').forEach(b => b.classList.toggle('on', b.dataset.view === v));
    moveNavPill();
    $$('.view').forEach(s => s.classList.toggle('on', s.id === 'v-' + v));
    view = v;
    if (v === 'stats') loadStats();
    if (v === 'block') loadBlock();
    if (v === 'settings') renderSettings();
    if (v === 'focus') stagger($('.focus-grid .side-col'));
  }

  /* ---------- wiring ---------- */
  function wire() {
    document.addEventListener('click', e => {
      const t = e.target.closest('.toggle, .chip, .seg button, .tabs button, .stepper button, .btn:not(.primary)');
      if (!t) return;
      if (t.classList.contains('toggle')) SFX.play(t.classList.contains('on') ? 'toggle_off' : 'toggle_on');
      else SFX.play('click');
    }, true);
    $('#tide').addEventListener('click', e => {
      const b = e.currentTarget.getBoundingClientRect(), k = tide.size / b.width;
      if (tide.poke((e.clientX - b.left) * k, (e.clientY - b.top) * k)) SFX.play('click', 0.8);
    });
    $('#tide').addEventListener('mousemove', e => {
      const b = e.currentTarget.getBoundingClientRect(), k = tide.size / b.width;
      e.currentTarget.style.cursor = tide.inWater((e.clientX - b.left) * k, (e.clientY - b.top) * k) ? 'pointer' : 'default';
    });
    $$('.nav-item').forEach(b => b.onclick = () => go(b.dataset.view));
    $$('#modeSeg button').forEach(b => b.onclick = () => { if (!S || S.phase === 'idle') setMode(b.dataset.mode); });
    $$('#rangeSeg button').forEach(b => b.onclick = () => { range = b.dataset.r; $$('#rangeSeg button').forEach(x => x.classList.toggle('on', x === b)); segPill($('#rangeSeg')); loadStats(); });
    $$('#srcSeg button').forEach(b => b.onclick = () => { source = b.dataset.s; $$('#srcSeg button').forEach(x => x.classList.toggle('on', x === b)); segPill($('#srcSeg')); loadStats(true); });
    $('#shareBtn').onclick = () => shareStats();
    $$('#blockTabs button').forEach(b => b.onclick = () => { blockTab = b.dataset.t; $$('#blockTabs button').forEach(x => x.classList.toggle('on', x === b)); tabLine(); renderBlock(); });
    $('#sMinus').onclick = () => { preset[2] = Math.max(1, preset[2] - 1); $('#sCount').textContent = preset[2]; renderDots(); };
    $('#sPlus').onclick = () => { preset[2] = Math.min(12, preset[2] + 1); $('#sCount').textContent = preset[2]; renderDots(); };
    $('#bMain').onclick = mainAction;
    $('#bSkip').onclick = async () => { const r = await api.skip(); if (r.error) toast(r.error, 'block'); poll(); };
    $('#bStop').onclick = stopFlow;
    $('#taskInput').onkeydown = async e => { if (e.key === 'Enter' && e.target.value.trim()) { renderTasks(await api.add_task(e.target.value)); e.target.value = ''; } };
    $('#clearDone').onclick = async () => renderTasks(await api.clear_done());
    $$('#ambient .chip').forEach(c => c.onclick = () => {
      const k = c.dataset.snd;
      if (Sound.playing === k) { Sound.stop(); c.classList.remove('on'); }
      else { Sound.play(k); $$('#ambient .chip').forEach(x => x.classList.toggle('on', x === c)); }
    });
    $('#vol').oninput = e => Sound.setVolume(+e.target.value);
    $('#vol').onchange = e => api.set_setting('volume', +e.target.value);
    window.addEventListener('resize', () => { moveNavPill(); segPill($('#modeSeg')); segPill($('#rangeSeg')); segPill($('#srcSeg')); if (view === 'block') tabLine(); });
    $('#zenBtn').onclick = () => zen(true);
    $('#zenExit').onclick = () => zen(false);
    $('#zenMain').onclick = () => mainAction();
    addEventListener('resize', () => { if (zenOn) sizeZen(); });
    document.addEventListener('keydown', e => {
      if (e.target.tagName === 'INPUT') return;
      if (e.key === 'Escape' && zenOn && !$('.scrim')) { zen(false); return; }
      if ((e.key === 'f' || e.key === 'F') && !e.ctrlKey && !e.altKey && !$('.scrim') && (view === 'focus' || zenOn)) { zen(!zenOn); return; }
      if (e.code === 'Space' && zenOn && !$('.scrim')) { e.preventDefault(); mainAction(); return; }
      if (e.code === 'Space' && view === 'focus' && !$('.scrim')) { e.preventDefault(); mainAction(); }
      if (!e.ctrlKey && !e.altKey && !e.metaKey && ['1', '2', '3', '4'].includes(e.key) && !$('.scrim')) go(['focus', 'stats', 'block', 'settings'][+e.key - 1]);
    });
  }

  /* ---------- full-screen timer ---------- */
  let zenOn = false;
  function sizeZen() {
    const s = Math.floor(Math.max(260, Math.min(innerWidth * 0.86, innerHeight - 230)));
    tide.resize(s);
  }
  function zen(on) {
    if (on === zenOn) return;
    zenOn = on;
    const cv = $('#tide');
    if (on) { $('#zenTide').appendChild(cv); sizeZen(); }
    else { $('#tideWrap').appendChild(cv); tide.resize(300); }
    document.body.classList.toggle('zen-on', on);
    $('#zen').setAttribute('aria-hidden', String(!on));
    try { api.set_fullscreen && api.set_fullscreen(on); } catch (e) {}
    renderFocusState && S && renderFocusState();
  }

  /* ---------- focus ---------- */
  function renderPresets() {
    const list = [[25, 5], [50, 10], [90, 15], [settings.custom_focus || 45, settings.custom_break || 10, 'custom']];
    $('#presets').innerHTML = list.map(([f, b, c]) => `<button class="chip ${preset[0] == f && preset[1] == b ? 'on' : ''}" data-f="${f}" data-b="${b}">${c ? `Custom ${f}/${b}` : `${f}/${b}`}</button>`).join('');
    $$('#presets .chip').forEach(ch => ch.onclick = () => {
      preset[0] = +ch.dataset.f; preset[1] = +ch.dataset.b;
      $$('#presets .chip').forEach(x => x.classList.toggle('on', x === ch));
    });
    $('#sCount').textContent = preset[2];
  }
  function setMode(m, silent) {
    mode = m; $$('#modeSeg button').forEach(b => b.classList.toggle('on', b.dataset.mode === m)); segPill($('#modeSeg'));
    if (!silent) api.set_setting('last_mode', m);
  }
  async function mainAction() {
    if (!S) return;
    if (S.phase === 'idle') {
      const start = async () => {
        const r = await api.start_focus({ label: $('#labelInput').value, focus_min: preset[0], break_min: preset[1], sessions: preset[2], mode });
        if (!r.ok) toast(r.error || 'Could not start', 'block'); else { tide.fillFromZero(); }
        poll();
      };
      if (mode === 'hard') {
        modal(`<h2>Hard mode?</h2><p>For the next <b>${preset[2]} × ${preset[0]} min</b> you can't pause, stop, or quit hush. Blocked apps close on sight.</p>
          <div class="acts"><button class="btn" data-x>Not now</button><button class="btn primary" data-go>${ic('lock')}Lock in</button></div>`,
          (s, close) => { $('[data-x]', s).onclick = close; $('[data-go]', s).onclick = () => { close(); start(); }; });
      } else start();
      return;
    }
    const wasPaused = S.paused;
    const r = wasPaused ? await api.resume() : await api.pause();
    if (r.error) toast(r.error, 'block'); else SFX.play(wasPaused ? 'resume' : 'pause');
    poll();
  }
  async function stopFlow() {
    if (!S || S.phase === 'idle') return;
    if (S.mode === 'hard') return toast('Hard mode is locked until the cycle ends', 'block');
    if (S.phase === 'break') { await api.stop({}); return poll(); }
    const both = settings.unlock === 'both', phraseOK = both || settings.unlock === 'phrase', waitOK = both || settings.unlock === 'wait';
    const token = waitOK ? await api.request_stop() : null;
    let timer;
    modal(`<h2>End early?</h2><p>Take a breath first. If you still want to stop:</p>
      ${phraseOK ? `<div class="label" style="margin-bottom:6px">Type this exactly</div><div class="phrase">${esc(B.phrase)}</div><input class="phrase-input" type="text" placeholder="Start typing…">` : ''}
      ${waitOK ? `<div class="label" style="margin:14px 0 4px">${phraseOK ? 'or wait it out' : 'Wait it out'}</div><div class="wait-bar"><div></div></div><div class="label" id="waitTxt">60s</div>` : ''}
      <div class="acts"><button class="btn primary" data-x>Keep focusing</button><button class="btn danger-soft" data-stop style="opacity:.45">Stop session</button></div>`,
      (s, close) => {
        s.dataset.sticky = 1;
        let ready = false;
        const btn = $('[data-stop]', s), inp = $('.phrase-input', s);
        const setReady = v => { ready = v; btn.style.opacity = v ? 1 : .45; };
        if (inp) { inp.focus(); inp.oninput = () => { const m = inp.value.toLowerCase().replace(/[^a-z ]/g, '').trim() === B.phrase; inp.classList.toggle('match', m); if (m) setReady(true); }; }
        if (waitOK) {
          const bar = $('.wait-bar div', s), t0 = Date.now();
          timer = setInterval(() => { const p = Math.min(1, (Date.now() - t0) / 60000); bar.style.width = p * 100 + '%'; $('#waitTxt', s).textContent = p >= 1 ? 'Unlocked' : Math.ceil(60 - p * 60) + 's'; if (p >= 1) { clearInterval(timer); setReady(true); } }, 200);
        }
        $('[data-x]', s).onclick = () => { clearInterval(timer); close(); };
        btn.onclick = async () => {
          if (!ready) return toast('Not unlocked yet', 'info');
          const proof = inp && inp.classList.contains('match') ? { type: 'phrase', text: inp.value } : { type: 'wait', token };
          const r = await api.stop(proof); clearInterval(timer);
          if (!r.ok) return toast(r.error || 'Not yet', 'block');
          close(); poll();
        };
      });
  }

  function renderDots() {
    const n = S && S.phase !== 'idle' ? S.sessions : preset[2], idx = S && S.phase !== 'idle' ? S.index : 0;
    let h = '';
    for (let i = 1; i <= n; i++) h += `<i class="${i < idx ? 'done' : i === idx ? 'cur' + (S.phase === 'break' ? ' brk' : '') : ''}"></i>`;
    const txt = !S || S.phase === 'idle' ? `${n} session${n > 1 ? 's' : ''} · ${preset[0]}/${preset[1]}` : S.phase === 'break' ? `break after ${idx} of ${n}` : `session ${idx} of ${n}`;
    $('#sessDots').innerHTML = h + `<small>${txt}</small>`;
  }

  function renderFocusState() {
    const idle = S.phase === 'idle', hard = S.mode === 'hard';
    $('#v-focus').classList.toggle('focusing', S.phase === 'focus' && !S.paused);
    document.body.classList.toggle('zen-focus', S.phase === 'focus' && !S.paused);
    $('#setup').classList.toggle('hide', !idle);
    $('#modeSeg').style.opacity = idle ? 1 : .5;
    if (!idle && mode !== S.mode) setMode(S.mode, true);
    const main = $('#bMain');
    const label = idle ? 'Start focus' : S.paused ? 'Resume' : 'Pause';
    const icon = idle || S.paused ? 'play' : 'pause';
    if (main.dataset.l !== label) { main.dataset.l = label; main.innerHTML = ic(icon) + `<span>${label}</span>`; }
    main.classList.toggle('gone', !idle && hard && S.phase === 'focus');
    $('#bSkip').classList.toggle('gone', idle || (hard && S.phase === 'focus'));
    $('#bSkip').title = S.phase === 'break' ? 'Skip break' : 'Skip to break';
    $('#bStop').classList.toggle('gone', idle || hard);
    const ln = $('#lockNote');
    ln.innerHTML = !idle && hard ? ic('lock') + `Hard mode · locked until ${S.sessions} session${S.sessions > 1 ? 's' : ''} finish`
      : S.grace > 0 ? ic('bell') + `Blocking starts in ${Math.ceil(S.grace)}s, save your stuff`
      : idle ? '<span style="opacity:.8">Space to start · Ctrl+Alt+H from anywhere</span>' : '';
    const li = $('#labelInput');
    if (document.activeElement !== li && !idle && li.value !== S.label) li.value = S.label;
    li.readOnly = !idle;
    renderDots();
    // full-screen view mirrors the main button and session dots (both are our own markup)
    if (zenOn) { $('#zenMain').innerHTML = $('#bMain').innerHTML; $('#zenDots').innerHTML = $('#sessDots').innerHTML; }
    // blocked card
    $('#blockedTxt').innerHTML = S.phase === 'focus'
      ? (S.blocked ? `Blocked <b>${S.blocked}</b> attempt${S.blocked > 1 ? 's' : ''} this session. Stay with it.` : 'Blocking is on. Nothing tried yet, nice.')
      : S.phase === 'break' ? 'Break time. Blocks are off, but maybe touch grass.' : 'Blocking turns on when focus starts';
    // brand waves ripple while focusing
    document.querySelector('.brand-mark').classList.toggle('alive', S.phase === 'focus' && !S.paused);
    if (prevPhase && prevPhase !== S.phase) {
      loadOverview();
      const vis = document.visibilityState === 'visible';
      if (S.phase === 'focus') { tide.fillFromZero(); vis && SFX.play('start'); }
      else if (S.phase === 'break') vis && SFX.play('break');
      else if (S.phase === 'idle') vis && SFX.play('complete');
    }
    prevPhase = S.phase;
  }

  function tickTimer() {
    if (S && tide) {
      const now = Date.now() / 1000 + offset;
      const left = S.phase === 'idle' ? preset[0] * 60 : S.paused ? S.left : Math.max(0, S.ends_at - now);
      const frac = S.total ? left / S.total : 1;
      if (S.phase === 'idle') tide.set({ target: 1, ampT: 5, speedT: 0.6, mossT: 0, caption: $('#labelInput').value ? 'ready when you are' : 'ready' });
      else if (S.phase === 'focus') tide.set({ target: frac, ampT: S.paused ? 2.5 : 7, speedT: S.paused ? 0.25 : 1, mossT: 0, caption: S.paused ? 'paused' : (S.label ? S.label.slice(0, 26) : 'focus') });
      else tide.set({ target: 1 - frac, ampT: S.paused ? 2.5 : 6, speedT: S.paused ? 0.25 : 0.8, mossT: 1, caption: S.paused ? 'paused' : 'break · breathe' });
      tide.text = clock(left);
      const lastMin = S.phase === 'focus' && !S.paused && left < 60 && left > 0;
      $('#tideWrap').classList.toggle('breathe', lastMin);
      if (lastMin && !tide._warned) { tide._warned = true; SFX.play('warn'); }
      if (!lastMin && left > 61) tide._warned = false;
      document.title = S.phase === 'idle' ? 'hush.' : `${clock(left)} · hush.`;
    }
    requestAnimationFrame(tickTimer);
  }

  async function poll() {
    let r; try { r = await api.poll(lastEv); } catch (e) { return; }
    S = r.state; offset = S.now - Date.now() / 1000;
    for (const e of r.events) { lastEv = Math.max(lastEv, e.id); toast(e.text, e.kind); if (e.kind === 'block' && document.visibilityState === 'visible' && Date.now() / 1000 - e.ts < 4) SFX.play('block'); }
    renderFocusState();
    const u = r.now_using;
    $('#using').innerHTML = u ? `<span class="live"></span>${esc(u.site || u.app)} · ${esc(u.category)}` : '';
    if (S.summary && S.summary.id !== summaryShown) { summaryShown = S.summary.id; showSummary(S.summary); }
    if (view === 'block' && r.ext !== blockExt) { blockExt = r.ext; if (blockCfg) renderBlock(); }
  }

  function showSummary(m) {
    modal(`<h2>${m.early ? 'Ended early' : 'Session complete'}</h2><p>${m.label ? esc(m.label) + ' · ' : ''}${m.done} of ${m.sessions} session${m.sessions > 1 ? 's' : ''} done.${m.early ? ' Rest, then go again.' : ' That was real work.'}</p>
      <div class="sum-grid"><div><b data-c="f">0m</b><span>focused</span></div><div><b data-c="s">–</b><span>focus score</span></div><div><b data-c="b">0</b><span>blocked</span></div></div>
      <div class="acts"><button class="btn" data-x>Done</button><button class="btn primary" data-again>${ic('play')}Another round</button></div>`,
      (s, close) => {
        countTo($('[data-c=f]', s), m.focused, dur, 1100);
        countTo($('[data-c=s]', s), m.score, v => v == null ? '–' : Math.round(v) + '%', 1100);
        countTo($('[data-c=b]', s), m.blocked, v => String(Math.round(v)), 900);
        const done = () => { api.clear_summary(); close(); };
        $('[data-x]', s).onclick = done;
        $('[data-again]', s).onclick = () => { done(); setTimeout(mainAction, 300); };
      });
  }

  /* ---------- tasks & overview ---------- */
  async function loadTasks() { renderTasks(await api.tasks()); }
  function renderTasks(list) {
    tasksCache = list;
    const cur = $('#labelInput').value.trim();
    $('#tasks').innerHTML = list.length ? list.map(t => `<div class="task ${t.done ? 'done' : ''} ${t.text === cur ? 'active' : ''}" data-id="${t.id}">
      <button class="tick">${ic('check')}</button><span class="txt" title="Use as session label">${esc(t.text)}</span><button class="x">${ic('x')}</button></div>`).join('')
      : `<div class="sub" style="padding:6px 2px">Add what you want to get through today.</div>`;
    $$('#tasks .task').forEach(el => {
      const id = el.dataset.id;
      $('.tick', el).onclick = async () => { if (!el.classList.contains('done')) SFX.play('task'); el.classList.toggle('done'); setTimeout(async () => renderTasks(await api.toggle_task(id)), 380); };
      $('.x', el).onclick = async () => renderTasks(await api.delete_task(id));
      $('.txt', el).onclick = () => { if (S && S.phase !== 'idle') return; $('#labelInput').value = $('.txt', el).textContent; renderTasks(tasksCache); };
    });
  }
  async function loadOverview() {
    const o = await api.overview();
    $('#streakV').textContent = `${o.streak} day${o.streak === 1 ? '' : 's'}`;
    $('#streakDots').innerHTML = o.dots.map((d, i) => `<span class="l${d}" style="animation-delay:${i * 50}ms"></span>`).join('');
    const p = Math.min(1, o.focus_today / (o.goal || 1));
    $('#goalBar').style.transform = `scaleX(${p})`;
    $('#goalTxt').textContent = `${dur(o.focus_today)} / ${Math.round(o.goal / 360) / 10}h`;
  }

  /* ---------- stats ---------- */
  const SRC_NAME = { laptop: 'Laptop', phone: 'Phone', all: 'Laptop + phone' };
  const DEV_COL = { laptop: '#3E6A9E', phone: '#C9A15A' };
  const niceMax = v => { const steps = [900, 1800, 3600, 5400, 7200, 10800, 14400, 21600, 28800, 43200]; return steps.find(s => s >= v) || Math.ceil(v / 3600) * 3600; };
  const tickLabel = s => s >= 3600 ? (s % 3600 ? (s / 3600).toFixed(1) + 'h' : s / 3600 + 'h') : Math.round(s / 60) + 'm';
  const hourName = h => `${(h % 12) || 12}${h < 12 ? 'am' : 'pm'}`;

  async function loadStats(fresh) {
    if (fresh || !lastStats || Date.now() - (loadStats._pulled || 0) > 60000) {
      // pull the phone's latest numbers in the background, then re-render if anything arrived
      loadStats._pulled = Date.now();
      if (api.cloud_refresh) api.cloud_refresh().then(r => { if (r && r.changed && view === 'stats') loadStats(); syncNote(r && r.status); }).catch(() => {});
    }
    const st = await api.stats(range, source);
    lastStats = st;
    const today = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });
    $('#statsTitle').textContent = { day: 'Today', week: 'This week', month: 'Last 30 days' }[range];
    $('#statsSub').textContent = (range === 'day' ? today : 'Where your time went') + ' · ' + SRC_NAME[source];
    renderCards(st);
    if (source === 'phone' && !st.has_phone) { renderNoPhone(); return; }
    $$('.stats-grid, #apps').forEach(e => e.closest('.card, .stats-grid').style.display = '');
    renderBars(st); renderCats(st); renderApps(st);
  }

  function renderNoPhone() {
    $('.stats-grid').style.display = 'none';
    $('#apps').innerHTML = `<div class="empty-state"><div class="h">No phone data yet</div>
      Open the hush. app on your phone, pair it (Settings → Phone here), and allow <b>Usage access</b> when it asks.<br>Your phone's screen time then shows up here, from anywhere.</div>`;
  }

  function renderCards(st) {
    const fmts = { dur, pct: v => v == null ? '–' : Math.round(v) + '%', num: v => v == null ? '–' : String(Math.round(v)) };
    const el = $('#cards');
    const sig = st.cards.map(c => c.label).join('|');
    if (el.dataset.sig !== sig) {
      el.dataset.sig = sig;
      el.innerHTML = st.cards.map((c, i) => `<div class="card metric ${i === 0 ? 'hero' : ''}"><p class="label"></p><div class="v">0</div><div class="d"></div>${i === 0 ? '<div class="split" id="heroSplit"></div>' : ''}</div>`).join('');
      stagger(el);
    }
    st.cards.forEach((c, i) => {
      const card = el.children[i];
      $('.label', card).textContent = c.label;
      const d = $('.d', card); d.textContent = c.sub; d.className = 'd ' + c.tone;
      const v = $('.v', card); v.classList.toggle('warn', c.fmt === 'num' && /Blocked/.test(c.label) && !!c.value);
      countTo(v, c.value, fmts[c.fmt]);
    });
    // hero: a thin bar showing where the time went (devices in combined, categories otherwise)
    const split = $('#heroSplit'); if (!split) return;
    let parts;
    if (st.source === 'all') {
      const lap = st.cards[1].value || 0, pho = st.cards[2].value || 0;
      parts = [{ n: 'Laptop', s: lap, c: DEV_COL.laptop }, { n: 'Phone', s: pho, c: DEV_COL.phone }];
    } else parts = st.cats.slice(0, 6).map(c => ({ n: c.name, s: c.secs, c: c.color }));
    const tot = parts.reduce((a, b) => a + b.s, 0);
    split.innerHTML = tot ? `<div class="split-bar">${parts.filter(p => p.s > 0).map(p => `<span style="flex:${p.s};background:${p.c}" title="${esc(p.n)} · ${dur(p.s)}"></span>`).join('')}</div>
      <div class="split-key">${parts.filter(p => p.s > 0).slice(0, 4).map(p => `<span><i style="background:${p.c}"></i>${esc(p.n)} <b>${Math.round(p.s / tot * 100)}%</b></span>`).join('')}</div>` : '';
  }

  function renderBars(st) {
    const bars = $('#bars'); bars.classList.remove('grown');
    const colors = B.colors;
    let cols, max, axis, legend;
    if (st.range === 'day') {
      // only show the part of the day you were actually up (at least 8 hours wide)
      const active = st.hours.map((h, i) => Object.values(h).reduce((a, b) => a + b, 0) > 30 ? i : -1).filter(i => i >= 0);
      let a = active.length ? Math.max(0, active[0] - 1) : 8, b = active.length ? Math.min(23, active[active.length - 1] + 1) : 22;
      while (b - a < 8) { if (a > 0) a--; if (b - a < 8 && b < 23) b++; if (a === 0 && b === 23) break; }
      $('#chartTitle').textContent = 'By hour';
      cols = [];
      for (let i = a; i <= b; i++) {
        const h = st.hours[i], tot = Object.values(h).reduce((x, y) => x + y, 0);
        cols.push({ segs: Object.entries(h).map(([c, s]) => ({ c: colors[c] || '#D6CFC1', s, name: c })), tip: `${hourName(i)}–${hourName((i + 1) % 24)} · ${dur(tot)}`, lab: hourName(i), showLab: (i - a) % Math.ceil((b - a + 1) / 8) === 0 });
      }
      max = niceMax(Math.max(900, ...cols.map(c => c.segs.reduce((x, y) => x + y.s, 0))));
      const used = [...new Set(st.hours.flatMap(h => Object.keys(h)))];
      legend = used.slice(0, 5).map(c => `<span><i style="background:${colors[c] || '#D6CFC1'}"></i>${esc(c)}</span>`).join('');
    } else {
      const [na, nb] = st.series, ca = st.source === 'all' ? DEV_COL.laptop : '#3E6A9E', cb = st.source === 'all' ? DEV_COL.phone : st.source === 'phone' ? '#C9A15A' : '#D3CBBB';
      $('#chartTitle').textContent = st.source === 'laptop' ? 'Focus vs everything else' : st.source === 'phone' ? 'Phone time per day' : 'Laptop and phone per day';
      cols = st.days.map((d, i) => ({ segs: [{ c: ca, s: d.a, name: na }, { c: cb, s: d.b, name: nb }], today: d.today,
        tip: `${d.label} · ${dur(d.a + d.b)}${na && d.a ? ` · ${dur(d.a)} ${na.toLowerCase()}` : ''}`, lab: d.label, showLab: st.range === 'week' || i % 5 === 0 || d.today }));
      max = niceMax(Math.max(1800, ...st.days.map(d => d.a + d.b)));
      legend = [[na, ca], [nb, cb]].filter(x => x[0]).map(([n, c]) => `<span><i style="background:${c}"></i>${n}</span>`).join('')
        + (st.avg ? `<span><i class="avg-key"></i>avg ${dur(st.avg)}</span>` : '');
    }
    // gridlines
    const ticks = [0, max / 2, max];
    $('#grid').innerHTML = ticks.map(t => `<div class="gl" style="bottom:${t / max * 100}%"><span>${t ? tickLabel(t) : ''}</span></div>`).join('')
      + (st.range !== 'day' && st.avg ? `<div class="gl avg" style="bottom:${Math.min(100, st.avg / max * 100)}%"></div>` : '');
    bars.style.gap = st.range === 'month' ? '3px' : '6px';
    bars.innerHTML = cols.map((col, i) => {
      const tot = col.segs.reduce((a, b) => a + b.s, 0);
      const h = Math.min(100, tot / max * 100);
      const segs = col.segs.filter(x => x.s > 0).sort((a, b) => b.s - a.s).map(x => `<span style="height:${x.s / (tot || 1) * 100}%;background:${x.c}"></span>`).join('');
      return `<div class="bar-col ${col.today ? 'today' : ''}">${tot > 30 ? `<div class="stack" style="height:${Math.max(2, h)}%;transition-delay:${i * (st.range === 'month' ? 12 : 22)}ms">${segs}</div>` : '<div class="empty"></div>'}<div class="tip">${esc(col.tip)}</div></div>`;
    }).join('');
    $('#axis').className = 'axis cols'; $('#axis').style.gap = bars.style.gap;
    $('#axis').innerHTML = cols.map(c => `<span>${c.showLab ? esc(c.lab) : ''}</span>`).join('');
    $('#legend').innerHTML = legend;
    requestAnimationFrame(() => requestAnimationFrame(() => bars.classList.add('grown')));
  }

  function renderCats(st) {
    const tot = st.cats.reduce((a, b) => a + b.secs, 0);
    $('#catTotal').textContent = tot ? dur(tot) : '';
    $('#catStack').innerHTML = tot ? st.cats.map(c => `<span style="flex:${c.secs};background:${c.color}" title="${esc(c.name)}"></span>`).join('') : '';
    const max = st.cats[0] ? st.cats[0].secs : 1;
    $('#catList').innerHTML = st.cats.slice(0, 7).map((c, i) => `<div class="cat-row" style="--i:${i}">
        <span class="nm"><i style="background:${c.color}"></i>${esc(c.name)}</span>
        <span class="track"><span style="width:${c.secs / max * 100}%;background:${c.color}"></span></span>
        <span class="pc">${Math.round(c.secs / tot * 100)}%</span><b>${dur(c.secs)}</b></div>`).join('')
      || '<div class="sub" style="padding:14px 0">Nothing yet</div>';
  }

  function renderApps(st) {
    const el = $('#apps');
    $('#appsTitle').textContent = st.source === 'all' ? 'Top apps on both' : st.source === 'phone' ? 'Top phone apps' : 'Top apps';
    if (!st.apps.length) { el.innerHTML = `<div class="empty-state"><div class="h">Nothing tracked yet</div>Leave hush. running and your day fills in here.</div>`; return; }
    const max = st.apps[0].secs, tot = st.total || 1;
    el.innerHTML = st.apps.map((a, i) => `<div class="app-row" style="--i:${i}">
      ${avatar(a.name, a.color)}
      <div class="nm" title="${esc(a.name)}">${esc(a.name)}${st.source === 'all' ? `<span class="dev ${a.device}">${ic(a.device === 'phone' ? 'phone' : 'desktop')}</span>` : ''}</div>
      <div class="track"><div style="width:${a.secs / max * 100}%;background:${a.color}"></div></div>
      <div class="tm">${dur(a.secs)}<small>${Math.round(a.secs / tot * 100)}%</small></div>
      <button class="cat-chip" data-name="${esc(a.name)}" style="--c:${a.color}">${esc(a.cat)}</button></div>`).join('');
    hydrateIcons(el);
    $$('#apps .cat-chip').forEach(b => b.onclick = e => { e.stopPropagation(); catMenu(b); });
  }

  function catMenu(btn) {
    $$('.cat-menu').forEach(m => m.remove());
    const m = document.createElement('div'); m.className = 'cat-menu';
    m.innerHTML = B.categories.map(c => `<button data-c="${esc(c)}" class="${c === btn.textContent ? 'on' : ''}"><i style="background:${B.colors[c] || '#D6CFC1'}"></i>${esc(c)}</button>`).join('');
    document.body.appendChild(m);
    const r = btn.getBoundingClientRect();
    m.style.left = Math.min(innerWidth - m.offsetWidth - 12, r.right - m.offsetWidth) + 'px';
    m.style.top = (r.bottom + m.offsetHeight + 8 > innerHeight ? r.top - m.offsetHeight - 6 : r.bottom + 6) + 'px';
    const close = () => { m.remove(); document.removeEventListener('mousedown', out); };
    const out = e => { if (!m.contains(e.target)) close(); };
    setTimeout(() => document.addEventListener('mousedown', out), 0);
    $$('button', m).forEach(b => b.onclick = async () => { close(); await api.set_category(btn.dataset.name, b.dataset.c); toast(`${btn.dataset.name} is now ${b.dataset.c}`, 'success'); loadStats(); });
  }

  function syncNote(s) {
    const n = $('#syncNote'); if (!n) return;
    if (!s || !s.enabled) { n.innerHTML = ''; return; }
    const ago = s.last_ok ? Math.round((Date.now() / 1000 - s.last_ok) / 60) : null;
    n.innerHTML = `${ic('cloud')}${s.ok ? `Synced${ago ? ` ${ago} min ago` : ' just now'}` : 'Offline, showing the last synced numbers'}${s.phone_days ? ` · ${s.phone_days} day${s.phone_days > 1 ? 's' : ''} of phone data` : ''}`;
  }

  /* ---------- share card ---------- */
  function drawShareCard(st) {
    const W = 1080, H = 1350, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const c = cv.getContext('2d');
    const serif = '"Instrument Serif", Georgia, serif', sans = '"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif';
    const g = c.createLinearGradient(0, 0, 0, H); g.addColorStop(0, '#FBF8F2'); g.addColorStop(1, '#EFE8DC'); c.fillStyle = g; c.fillRect(0, 0, W, H);
    // soft water at the bottom
    c.fillStyle = 'rgba(62,106,158,.10)'; c.beginPath(); c.moveTo(0, H - 170);
    for (let x = 0; x <= W; x += 10) c.lineTo(x, H - 170 + Math.sin(x / 90) * 14); c.lineTo(W, H); c.lineTo(0, H); c.fill();
    c.fillStyle = 'rgba(62,106,158,.16)'; c.beginPath(); c.moveTo(0, H - 120);
    for (let x = 0; x <= W; x += 10) c.lineTo(x, H - 120 + Math.sin(x / 70 + 2) * 12); c.lineTo(W, H); c.lineTo(0, H); c.fill();
    const P = 90;
    c.fillStyle = '#1F3550'; c.font = `italic 64px ${serif}`; c.textBaseline = 'alphabetic'; c.fillText('hush.', P, 150);
    c.fillStyle = '#8A8274'; c.font = `500 30px ${sans}`;
    const when = { day: new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' }), week: 'This week', month: 'Last 30 days' }[st.range];
    c.fillText(`${SRC_NAME[st.source]} screen time · ${when}`, P, 215);
    c.fillStyle = '#1F3550'; c.font = `italic 190px ${serif}`; c.fillText(dur(st.total), P - 6, 420);
    c.fillStyle = st.cards[0].tone === 'good' ? '#5E8A5A' : '#6E685C'; c.font = `500 32px ${sans}`; c.fillText(st.cards[0].sub, P, 480);
    // split bar
    let y = 550;
    const parts = st.source === 'all' ? [{ n: 'Laptop', s: st.cards[1].value || 0, c: DEV_COL.laptop }, { n: 'Phone', s: st.cards[2].value || 0, c: DEV_COL.phone }]
      : st.cats.slice(0, 5).map(x => ({ n: x.name, s: x.secs, c: x.color }));
    const tot = parts.reduce((a, b) => a + b.s, 0) || 1;
    let x = P; const bw = W - 2 * P;
    c.save(); c.beginPath(); c.roundRect(P, y, bw, 26, 13); c.clip();
    parts.forEach(p => { const w = p.s / tot * bw; c.fillStyle = p.c; c.fillRect(x, y, w + 1, 26); x += w; }); c.restore();
    y += 70; x = P; c.font = `500 28px ${sans}`;
    parts.slice(0, 4).forEach(p => { c.fillStyle = p.c; c.beginPath(); c.arc(x + 9, y - 9, 9, 0, 7); c.fill(); c.fillStyle = '#2B3440'; const t = `${p.n} ${Math.round(p.s / tot * 100)}%`; c.fillText(t, x + 28, y); x += c.measureText(t).width + 64; });
    // top apps
    y += 90; c.fillStyle = '#8A8274'; c.font = `600 26px ${sans}`; c.fillText('TOP APPS', P, y); y += 30;
    const apps = st.apps.slice(0, 5), amax = apps[0] ? apps[0].secs : 1;
    apps.forEach(a => {
      y += 72;
      c.fillStyle = '#2B3440'; c.font = `500 36px ${sans}`;
      let nm = a.name; while (c.measureText(nm).width > 430 && nm.length > 3) nm = nm.slice(0, -2) + '…';
      c.fillText(nm, P, y);
      c.fillStyle = '#E6DFD1'; c.beginPath(); c.roundRect(P + 460, y - 20, 330, 14, 7); c.fill();
      c.fillStyle = a.color; c.beginPath(); c.roundRect(P + 460, y - 20, Math.max(14, 330 * a.secs / amax), 14, 7); c.fill();
      c.fillStyle = '#6E685C'; c.font = `500 32px ${sans}`; c.textAlign = 'right'; c.fillText(dur(a.secs), W - P, y); c.textAlign = 'left';
    });
    c.fillStyle = '#1F3550'; c.globalAlpha = .55; c.font = `italic 34px ${serif}`; c.fillText('made with hush. · calm focus', P, H - 54); c.globalAlpha = 1;
    return cv;
  }

  async function shareStats() {
    let st = lastStats; if (!st) return;
    const pick = { laptop: st.source === 'laptop', phone: st.source === 'phone', all: st.source === 'all' };
    modal(`<h2>Share your screen time</h2>
      <div class="seg share-seg" id="shareSrc"><div class="seg-pill"></div>${['laptop', 'phone', 'all'].map(s => `<button data-s="${s}" class="${pick[s] ? 'on' : ''}">${SRC_NAME[s].replace('Laptop + phone', 'Combined')}</button>`).join('')}</div>
      <div class="share-prev"><img id="shareImg" alt="Screen time card"></div>
      <div class="acts"><button class="btn" data-copy>${ic('copy')}Copy image</button><button class="btn primary" data-save>${ic('download')}Save image</button></div>`, (s, close) => {
      let cur = st, cv;
      const draw = async () => { cv = drawShareCard(cur); $('#shareImg', s).src = cv.toDataURL('image/png'); };
      draw(); requestAnimationFrame(() => segPill($('#shareSrc', s)));
      $$('#shareSrc button', s).forEach(b => b.onclick = async () => {
        $$('#shareSrc button', s).forEach(x => x.classList.toggle('on', x === b)); segPill($('#shareSrc', s));
        cur = await api.stats(range, b.dataset.s); draw();
      });
      $('[data-save]', s).onclick = async () => {
        const p = await api.save_image(cv.toDataURL('image/png'), `hush-${cur.source}-${cur.range}`);
        if (p) { toast('Saved to Downloads', 'success'); close(); } else toast('Could not save the image', 'block');
      };
      $('[data-copy]', s).onclick = async () => {
        try {
          const blob = await new Promise(r => cv.toBlob(r, 'image/png'));
          await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
          toast('Copied. Paste it into WhatsApp, Discord or anywhere.', 'success');
        } catch (e) { toast('Copy isn\'t available here. Use Save image instead.', 'block'); }
      };
    });
  }

  /* ---------- blocklist ---------- */
  let blockCfg = null, blockExt = null, running = null;
  async function loadBlock() { blockCfg = await api.blocklist(); blockExt = blockCfg.ext; renderBlock(); requestAnimationFrame(tabLine); }
  const sw = (on, attrs) => `<button class="toggle ${on ? 'on' : ''}" ${attrs}></button>`;
  function renderBlock() {
    const c = blockCfg; if (!c) return;
    const main = $('#blockMain'), side = $('#blockSide');
    if (blockTab === 'apps') {
      const games = c.apps.filter(a => a.source === 'game'), launch = c.apps.filter(a => a.source === 'launcher'), custom = c.apps.filter(a => a.source === 'custom');
      const row = (a, i) => `<div class="row" style="--i:${i}">${a.kind === 'exe' ? avatar(a.value, '#C9A15A', 28) : avatar(a.name, '#C9A15A', 28, ic('game'))}
        <div class="nm">${esc(a.name)}<div class="meta">${esc(a.kind === 'path' ? a.value : a.value)}</div></div>${a.store ? `<span class="tag amber">${esc(a.store)}</span>` : ''}
        ${a.source === 'custom' ? `<button class="rm" data-rm="${esc(a.id)}" title="Remove">${ic('x')}</button>` : ''}${sw(a.enabled, `data-app="${esc(a.id)}"`)}</div>`;
      const allOn = l => l.length && l.every(a => a.enabled);
      main.innerHTML = `
        <div class="sec-title"><b>Games · auto-detected (${games.length})</b><span style="display:flex;gap:8px;align-items:center"><button class="btn ghost sm" id="rescan">${ic('refresh')}Rescan</button>${games.length ? sw(allOn(games), 'data-src="game"') : ''}</span></div>
        <div class="list">${games.map(row).join('') || '<div class="sub" style="padding:8px 0 14px">No Steam, Epic, Riot or Xbox games found. Hit rescan after installing one.</div>'}</div>
        <div class="sec-title" style="margin-top:14px"><b>Launchers</b>${sw(allOn(launch), 'data-src="launcher"')}</div>
        <div class="list">${launch.map(row).join('')}</div>
        <div class="sec-title" style="margin-top:14px"><b>Your picks</b></div>
        <div class="list">${custom.map(row).join('')}</div>
        <div class="add-row"><select id="runSel"><option value="">Pick a running app…</option></select><input id="exeIn" type="text" placeholder="or type an exe, e.g. chrome.exe"><button class="btn sm" id="addApp">${ic('plus')}Add</button></div>`;
      side.innerHTML = `<div class="card"><p class="label"><span>How app blocking works</span></p><p class="sub" style="line-height:1.6;margin-top:8px">When focus starts you get <b>10 seconds</b> to save, then anything on this list is closed the moment it opens. Games are found in your Steam, Epic, Riot and Xbox folders, so new installs get caught automatically after a rescan.</p></div>
        <div class="card"><p class="label"><span>Honest limit</span></p><p class="sub" style="line-height:1.6;margin-top:8px">You're the admin of your own laptop, so a determined you can always get around it. hush. stops the impulse, not the heist.</p></div>`;
      $$('[data-app]', main).forEach(t => t.onclick = async () => { t.classList.toggle('on'); blockCfg = await api.set_app(t.dataset.app, t.classList.contains('on')); });
      $$('[data-src]', main).forEach(t => t.onclick = async () => { blockCfg = await api.set_source(t.dataset.src, !t.classList.contains('on')); renderBlock(); });
      $$('[data-rm]', main).forEach(b => b.onclick = async () => { blockCfg = await api.remove_app(b.dataset.rm); renderBlock(); });
      $('#rescan').onclick = async () => { const r = await api.rescan_games(); blockCfg = r.cfg; toast(`Found ${r.found} game${r.found === 1 ? '' : 's'}`, 'success'); renderBlock(); };
      const fill = list => { $('#runSel').innerHTML = '<option value="">Pick a running app…</option>' + list.map(a => `<option value="${esc(a.exe)}">${esc(a.name)} (${esc(a.exe)})</option>`).join(''); };
      if (running) fill(running); api.running_apps().then(l => { running = l; if ($('#runSel')) fill(l); });
      $('#addApp').onclick = async () => {
        const v = $('#exeIn').value.trim() || $('#runSel').value; if (!v) return;
        const r = await api.add_app(v); if (!r.ok) return toast("Can't block that one (system app)", 'block');
        blockCfg = r.cfg; toast(`${v} added`, 'success'); renderBlock();
      };
    } else {
      const quick = ['youtube.com', 'instagram.com', 'reddit.com', 'x.com', 'netflix.com', 'discord.com', 'twitch.tv', 'snapchat.com'].filter(d => !c.sites.some(s => s.domain === d));
      main.innerHTML = `
        <div class="sec-title"><b>Blocked during focus</b><span>${c.sites.filter(s => s.enabled).length} on</span></div>
        <div class="add-row" style="margin:4px 0 10px"><input id="siteIn" type="text" placeholder="Add a site, e.g. primevideo.com"><button class="btn sm" id="addSite">${ic('plus')}Add</button></div>
        ${quick.length ? `<div class="chips" style="margin-bottom:10px">${quick.map(d => `<button class="chip" data-q="${d}">${ic('plus')}${d}</button>`).join('')}</div>` : ''}
        <div class="list">${c.sites.map((s, i) => `<div class="row" style="--i:${i}">${avatar(s.domain, '#3E6A9E', 28, ic('globe'))}<div class="nm">${esc(s.domain)}</div>
          <button class="rm" data-rms="${esc(s.domain)}" title="Remove">${ic('x')}</button>${sw(s.enabled, `data-site="${esc(s.domain)}"`)}</div>`).join('')}</div>`;
      side.innerHTML = `
        <div class="card"><div class="status"><span class="dot ${blockExt ? 'on' : ''}"></span><b style="font-weight:500">${blockExt ? 'Browser extension connected' : 'Browser extension not connected'}</b></div>
          ${blockExt ? `<p class="sub" style="margin-top:8px;line-height:1.6">Blocks sites instantly in your browser and powers per-site screen time.</p>` :
          `<ol class="steps"><li>Open <code>brave://extensions</code> (or chrome:// / edge://)</li><li>Turn on <b>Developer mode</b></li><li>Click <b>Load unpacked</b> and pick the <code>extension</code> folder</li></ol><button class="btn sm" id="openExt" style="margin-top:10px">${ic('puzzle')}Open extension folder</button>`}</div>
        <div class="card"><div class="set-row" style="padding:0;border:0"><div><div class="t">Block YouTube Shorts only</div><div class="d">YouTube stays open for study videos. Shorts get blocked and hidden. Needs the extension.</div></div>${sw(c.shorts, 'data-flag="shorts"')}</div></div>
        <div class="card"><div class="set-row" style="padding:0;border:0"><div><div class="t">System-wide block</div><div class="d">${c.admin ? 'Also blocks these sites in every app through the hosts file. Cleaned up automatically after focus.' : 'Uses the hosts file to block sites in every app. Needs hush. running as admin.'}</div></div>${c.admin ? sw(c.hosts, 'data-flag="hosts"') : `<button class="btn sm" id="adminBtn">${ic('lock')}Restart as admin</button>`}</div></div>`;
      $$('[data-site]', main).forEach(t => t.onclick = async () => { t.classList.toggle('on'); blockCfg = await api.set_site(t.dataset.site, t.classList.contains('on')); });
      $$('[data-rms]', main).forEach(b => b.onclick = async () => { blockCfg = await api.remove_site(b.dataset.rms); renderBlock(); });
      $$('[data-q]', main).forEach(b => b.onclick = async () => { const r = await api.add_site(b.dataset.q); blockCfg = r.cfg; renderBlock(); });
      const add = async () => { const v = $('#siteIn').value; if (!v.trim()) return; const r = await api.add_site(v); if (!r.ok) return toast('That doesn’t look like a website', 'block'); blockCfg = r.cfg; renderBlock(); };
      $('#addSite').onclick = add; $('#siteIn').onkeydown = e => { if (e.key === 'Enter') add(); };
      $$('[data-flag]', side).forEach(t => t.onclick = async () => { t.classList.toggle('on'); blockCfg = await api.set_block_flag(t.dataset.flag, t.classList.contains('on')); });
      $('#openExt') && ($('#openExt').onclick = () => api.open_extension_folder());
      $('#adminBtn') && ($('#adminBtn').onclick = async () => { if (!(await api.restart_admin())) toast('Admin restart was cancelled', 'info'); });
    }
    stagger(side);
    hydrateIcons(main);
  }

  /* ---------- settings ---------- */
  function renderSettings() {
    const s = settings, g = $('#settingsGrid');
    g.innerHTML = `
      <div class="card">
        <p class="label"><span>You</span></p>
        <div class="set-row"><div><div class="t">Your name</div><div class="d">Used in the greeting</div></div><input type="text" data-k="name" value="${esc(s.name)}" style="width:160px"></div>
        <div class="set-row"><div><div class="t">Daily focus goal</div><div class="d"><span id="goalOut">${s.goal_hours}</span> hours</div></div><input type="range" data-k="goal_hours" min="0.5" max="10" step="0.5" value="${s.goal_hours}" style="width:160px"></div>
        <div class="set-row"><div><div class="t">Countdown</div><div class="d">Shown under the greeting</div></div><div style="display:flex;gap:6px"><input type="text" data-k="countdown_label" value="${esc(s.countdown_label)}" style="width:110px" placeholder="exams"><input type="date" data-k="countdown_date" value="${esc(s.countdown_date)}"></div></div>
      </div>
      <div class="card">
        <p class="label"><span>Timer</span></p>
        <div class="set-row"><div><div class="t">Custom preset</div><div class="d">Focus / break minutes</div></div><div style="display:flex;gap:6px;align-items:center"><input type="number" data-k="custom_focus" min="1" max="240" value="${s.custom_focus}"> / <input type="number" data-k="custom_break" min="1" max="60" value="${s.custom_break}"></div></div>
        <div class="set-row"><div><div class="t">Soft-mode unlock</div><div class="d">What it takes to end a session early</div></div><select data-k="unlock"><option value="both" ${s.unlock === 'both' ? 'selected' : ''}>Sentence or wait 60s</option><option value="phrase" ${s.unlock === 'phrase' ? 'selected' : ''}>Type sentence only</option><option value="wait" ${s.unlock === 'wait' ? 'selected' : ''}>Wait 60s only</option></select></div>
        <div class="set-row"><div><div class="t">Global shortcut</div><div class="d">Start, pause or resume from anywhere</div></div><span><span class="kbd">Ctrl</span> <span class="kbd">Alt</span> <span class="kbd">H</span></span></div>
      </div>
      <div class="card">
        <p class="label"><span>Tracking</span></p>
        <div class="set-row"><div><div class="t">Idle after</div><div class="d">Stop counting when there's no input (fullscreen video still counts)</div></div><div style="display:flex;gap:6px;align-items:center"><input type="number" data-k="idle_min" min="1" max="30" value="${s.idle_min}"> min</div></div>
        <div class="set-row"><div><div class="t">Export data</div><div class="d">Usage and focus sessions as CSV, saved to Downloads</div></div><button class="btn sm" id="exportBtn">${ic('download')}Export CSV</button></div>
      </div>
      <div class="card">
        <p class="label"><span>Sound</span></p>
        <div class="set-row"><div><div class="t">Sound effects</div><div class="d">Soft chimes for start, breaks, blocks and finishing</div></div>${sw(s.sfx !== false, 'id="sfxT"')}</div>
        <div class="set-row"><div><div class="t">Effects volume</div><div class="d">Kept quiet on purpose</div></div><div style="display:flex;gap:8px;align-items:center"><input type="range" id="sfxVol" min="0" max="1" step="0.01" value="${s.sfx_volume ?? 0.35}" style="width:130px"><button class="btn sm icon" id="sfxTest" title="Preview" style="width:32px">${ic('play')}</button></div></div>
      </div>
      <div class="card" id="phoneCard">
        <p class="label"><span>Phone</span></p>
        <div class="set-row"><div><div class="t">hush. on your Android phone</div><div class="d">While the laptop is in focus, the phone closes the apps you pick (Instagram and others). WhatsApp, Telegram and Discord always stay open. Phone and laptop need the same Wi-Fi.</div></div><span class="tag" id="phoneStatus">…</span></div>
        <div class="set-row"><div><div class="t">1 · Get the app</div><div class="d" id="phoneApk">On your phone's browser, open <b class="mono" id="phoneUrl">…</b></div></div></div>
        <div class="set-row"><div><div class="t">2 · Pairing code</div><div class="d">Type this into the phone app. A new code unpairs old phones.</div></div><div style="display:flex;gap:8px;align-items:center"><b id="phoneCode" style="font-size:20px;letter-spacing:2px">…</b><button class="btn sm icon" id="phoneNew" title="New code" style="width:32px">${ic('refresh')}</button></div></div>
      </div>
      <div class="card">
        <p class="label"><span>System</span></p>
        <div class="set-row"><div><div class="t">Start with Windows</div><div class="d">Opens quietly in the tray</div></div>${sw(B.startup, 'id="startupT"')}</div>
        <div class="set-row"><div><div class="t">Reduce motion</div><div class="d">Calmer, near-instant transitions</div></div>${sw(s.reduce_motion, 'id="motionT"')}</div>
        <div class="set-row"><div><div class="t">Turn off browser Secure DNS</div><div class="d">${B.admin ? 'Lets the system-wide site block work in Chrome, Brave, Edge and Firefox' : 'Needs admin. Only matters for the system-wide block.'}</div></div>${B.admin ? sw(s.doh_off, 'id="dohT"') : '<span class="tag">admin only</span>'}</div>
        <div class="set-row"><div><div class="t">Mini timer</div><div class="d">A small floating timer while a session runs, shown only when you minimize hush.</div></div>${sw(s.mini_mode !== 'off', 'id="miniT"')}</div>
        <div class="set-row"><div><div class="t">Keep running in the tray</div><div class="d">Closing the window hides hush. so tracking continues. Quit from the tray icon.</div></div><span class="tag">always on</span></div>
        <div class="set-row"><div><div class="t">Desktop shortcut</div><div class="d">Adds hush. to your desktop and Start menu</div></div><button class="btn sm" id="shortcutBtn">${ic('desktop')}Add again</button></div>
      </div>
      <div class="card">
        <p class="label"><span>About</span></p>
        <div class="set-row"><div><div class="t" style="font-family:var(--serif);font-style:italic;font-size:22px;color:var(--navy)">hush.</div><div class="d">Version 1.3 · made for deep work</div></div><button class="btn sm ghost" id="replayIntro">${ic('sparkle')}Replay intro</button></div>
        <div class="set-row"><div><div class="t">Keyboard</div><div class="d"><span class="kbd">Space</span> start / pause · <span class="kbd">1</span>–<span class="kbd">4</span> switch screens · <span class="kbd">Esc</span> close</div></div></div>
      </div>`;
    stagger(g);
    $$('[data-k]', g).forEach(inp => {
      const k = inp.dataset.k, save = () => {
        let v = inp.type === 'number' || inp.type === 'range' ? +inp.value : inp.value;
        settings[k] = v; api.set_setting(k, v);
        if (k === 'goal_hours') { $('#goalOut').textContent = v; loadOverview(); }
        if (['name', 'countdown_label', 'countdown_date'].includes(k)) greet();
        if (k.startsWith('custom_')) renderPresets();
      };
      inp.addEventListener(inp.type === 'range' ? 'input' : 'change', save);
    });
    $('#sfxT').onclick = e => { const on = !e.target.classList.contains('on'); e.target.classList.toggle('on', on); SFX.enabled = on; settings.sfx = on; api.set_setting('sfx', on); if (on) SFX.play('task'); };
    $('#sfxVol').oninput = e => { SFX.volume = +e.target.value; };
    $('#sfxVol').onchange = e => { settings.sfx_volume = +e.target.value; api.set_setting('sfx_volume', +e.target.value); SFX.play('start'); };
    $('#sfxTest').onclick = () => { const seq = ['start', 'block', 'break', 'complete']; seq.forEach((n, i) => setTimeout(() => SFX.play(n), i * 1100)); };
    $('#shortcutBtn').onclick = async () => toast((await api.create_shortcut()) ? 'Shortcut added to your desktop and Start menu' : 'Could not create the shortcut', 'success');
    $('#replayIntro').onclick = () => onboarding();
    const showPhone = p => {
      if (!p || !$('#phoneCode')) return;
      $('#phoneCode').textContent = p.code.replace(/(\d{4})(\d{4})/, '$1 $2');
      $('#phoneUrl').textContent = `http://${p.ip}:${p.port}`;
      $('#phoneStatus').textContent = !p.running ? 'off' : p.connected ? 'connected' + (p.phone ? ' · ' + p.phone : '') : 'not connected';
      $('#phoneStatus').classList.toggle('on', !!p.connected);
    };
    const pollPhone = async () => { if (!$('#phoneCode')) return; try { showPhone(await api.phone_link()); } catch (e) {} if (document.body.contains($('#phoneCard'))) setTimeout(pollPhone, 5000); };
    if (api.phone_link) pollPhone();
    $('#phoneNew').onclick = async () => { showPhone(await api.phone_new_code()); toast('New pairing code. Enter it on your phone.', 'success'); };
    $('#exportBtn').onclick = async () => { const p = await api.export_csv(); toast('Exported to ' + p, 'success'); };
    $('#startupT').onclick = async e => { const on = !e.target.classList.contains('on'); if (await api.set_startup(on)) { e.target.classList.toggle('on', on); B.startup = on; } else toast('Could not change startup', 'block'); };
    $('#miniT').onclick = e => { const on = !e.target.classList.contains('on'); e.target.classList.toggle('on', on); settings.mini_mode = on ? 'minimized' : 'off'; api.set_setting('mini_mode', settings.mini_mode); };
    $('#motionT').onclick = e => { const on = !e.target.classList.contains('on'); e.target.classList.toggle('on', on); settings.reduce_motion = on; api.set_setting('reduce_motion', on); document.body.classList.toggle('reduce', on); tide.reduce = on; };
    $('#dohT') && ($('#dohT').onclick = async e => { const on = !e.target.classList.contains('on'); if (await api.set_doh(on)) { e.target.classList.toggle('on', on); toast(on ? 'Secure DNS turned off. Restart your browser.' : 'Secure DNS policy removed', 'success'); } });
  }

  /* ---------- first run ---------- */
  function onboarding() {
    let step = 0;
    const steps = [
      () => `<div class="ob-art">${obArt()}</div><h2>Welcome to <em>hush.</em></h2><p>A quiet place to focus. It tracks your screen time, keeps games and feeds closed while you work, and stays out of the way.</p>
        <div class="label" style="margin-bottom:6px">What should we call you?</div><input type="text" id="obName" value="${esc(settings.name || '')}" style="width:100%">`,
      () => `<h2>Your daily goal</h2><p>How many hours of real focus do you want each day? You can change this later.</p>
        <div class="ob-goal"><b id="obGoalV">${settings.goal_hours}</b><span>hours</span></div><input type="range" id="obGoal" min="0.5" max="10" step="0.5" value="${settings.goal_hours}" style="width:100%">`,
      () => `<h2>Two tips</h2><p>${ic('puzzle')} Load the <b>browser extension</b> (Blocklist → Websites) for site blocking and per-site screen time.</p>
        <p>${ic('keyboard')} Press <span class="kbd">Ctrl</span> <span class="kbd">Alt</span> <span class="kbd">H</span> anywhere to start or pause. Closing the window keeps hush. running in the tray.</p>`
    ];
    modal(`<div class="ob-body"></div><div class="ob-dots"><i></i><i></i><i></i></div><div class="acts"><button class="btn ghost" data-back>Back</button><button class="btn primary" data-next>Next</button></div>`, (s, close) => {
      s.dataset.sticky = 1;
      const body = $('.ob-body', s), next = $('[data-next]', s), back = $('[data-back]', s);
      const save = () => {
        const n = $('#obName', s); if (n) { settings.name = n.value.trim(); api.set_setting('name', settings.name); greet(); }
        const g = $('#obGoal', s); if (g) { settings.goal_hours = +g.value; api.set_setting('goal_hours', +g.value); loadOverview(); }
      };
      const render = dir => {
        body.classList.remove('in-l', 'in-r'); void body.offsetWidth;
        body.innerHTML = steps[step](); body.classList.add(dir < 0 ? 'in-l' : 'in-r');
        $$('.ob-dots i', s).forEach((d, i) => d.classList.toggle('on', i === step));
        back.style.visibility = step ? 'visible' : 'hidden';
        next.textContent = step === steps.length - 1 ? 'Start focusing' : 'Next';
        const g = $('#obGoal', s); if (g) g.oninput = () => { $('#obGoalV', s).textContent = g.value; };
        const n = $('#obName', s); if (n) { n.focus(); n.onkeydown = e => { if (e.key === 'Enter') next.click(); }; }
      };
      next.onclick = () => { save(); if (step < steps.length - 1) { step++; render(1); } else { settings.onboarded = true; api.set_setting('onboarded', true); SFX.play('start'); close(); } };
      back.onclick = () => { save(); step--; render(-1); };
      render(1);
    });
  }
  function obArt() {
    return `<svg viewBox="0 0 120 120" width="88" height="88"><defs><clipPath id="obc"><circle cx="60" cy="60" r="54"/></clipPath></defs><circle cx="60" cy="60" r="54" fill="#F3EFE7"/>
      <g clip-path="url(#obc)"><path class="obw2" d="M-60 62 Q-45 54 -30 62 T0 62 T30 62 T60 62 T90 62 T120 62 T150 62 T180 62 V140 H-60Z" fill="#8FA6C4" opacity=".55"/>
      <path class="obw1" d="M-60 68 Q-45 60 -30 68 T0 68 T30 68 T60 68 T90 68 T120 68 T150 68 T180 68 V140 H-60Z" fill="#3E6A9E"/></g>
      <circle cx="60" cy="60" r="54" fill="none" stroke="#DDD5C4" stroke-width="2"/></svg>`;
  }

  /* ---------- start ---------- */
  function start(a) { api = a; boot().catch(e => { console.error(e); toast('Something went wrong: ' + e, 'block'); }); }
  if (window.pywebview && window.pywebview.api) start(window.pywebview.api);
  else window.addEventListener('pywebviewready', () => start(window.pywebview.api));
  // Browser preview (no Python): load a mock so the UI can be checked in a normal browser.
  setTimeout(() => { if (!api && location.search.includes('mock')) { const s = document.createElement('script'); s.src = 'mock.js'; s.onload = () => start(window.MockApi); document.body.appendChild(s); } }, 1200);
})();
