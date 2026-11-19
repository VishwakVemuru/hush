/* hush. study check: is someone at the desk, and are they on their phone?
   Runs only during focus (or while you're testing it), entirely on this laptop. Frames stay in memory and are
   never saved or sent anywhere.
   Models (Google MediaPipe, Apache-2.0, bundled in ui/models):
     - BlazeFace short-range: a face in view
     - EfficientDet-Lite0 (COCO): "person" (covers reading with your head down) and "cell phone" */
window.Presence = (() => {
  const TICK_MS = 1500;          // background check rate
  const TICK_LIVE_MS = 350;      // while the live view is on screen, so the boxes keep up
  const FACE_GRACE = 3200;       // face out of view longer than this = not counted (covers a missed frame or two)
  const PHONE_HOLD = 4000;       // a phone sighting counts for this long
  let tasks = null, loading = null, stream = null, video = null, timer = null, live = 0;
  let lastSeen = 0, lastPhone = 0, state = '', ts = 0, listeners = [];
  let detail = { face: false, person: false, phone: false, boxes: [], w: 320, h: 240 };

  async function load() {
    if (tasks) return tasks;
    if (!loading) loading = (async () => {
      const m = await import('./vendor/tasks-vision/vision_bundle.mjs');
      const fs = await m.FilesetResolver.forVisionTasks('vendor/tasks-vision/wasm');
      const face = await m.FaceDetector.createFromOptions(fs, {
        baseOptions: { modelAssetPath: 'models/blaze_face_short_range.tflite', delegate: 'CPU' },
        runningMode: 'VIDEO', minDetectionConfidence: 0.5 });
      const obj = await m.ObjectDetector.createFromOptions(fs, {
        baseOptions: { modelAssetPath: 'models/efficientdet_lite0.tflite', delegate: 'CPU' },
        runningMode: 'VIDEO', scoreThreshold: 0.4, maxResults: 5, categoryAllowlist: ['person', 'cell phone'] });
      tasks = { face, obj };
      return tasks;
    })();
    try { return await loading; } catch (e) { loading = null; throw e; }
  }

  function emit() { listeners.forEach(fn => { try { fn(state, detail); } catch (e) {} }); }

  const box = (kind, b, score) => ({ kind, x: b.originX, y: b.originY, w: b.width, h: b.height, score });

  function tick() {
    if (!video || video.readyState < 2 || !tasks) return;
    const t = ++ts * 50;   // detectors want strictly increasing timestamps
    let face = false, person = false, phone = false;
    const boxes = [];
    try {
      for (const d of tasks.face.detectForVideo(video, t).detections) {
        face = true;
        boxes.push(box('face', d.boundingBox, d.categories[0] ? d.categories[0].score : 1));
      }
      for (const d of tasks.obj.detectForVideo(video, t).detections) {
        const c = d.categories[0];
        if (!c) continue;
        if (c.categoryName === 'person' && c.score >= 0.5) { person = true; boxes.push(box('person', d.boundingBox, c.score)); }
        if (c.categoryName === 'cell phone' && c.score >= 0.45) { phone = true; boxes.push(box('phone', d.boundingBox, c.score)); }
      }
    } catch (e) { return; }
    const now = Date.now();
    // only a visible face counts: a body or chair in view without a face means you're not studying at the screen
    if (face) lastSeen = now;
    if (phone) lastPhone = now;
    detail = { face, person, phone, boxes, w: video.videoWidth || 320, h: video.videoHeight || 240 };
    state = now - lastPhone < PHONE_HOLD ? 'phone' : now - lastSeen < FACE_GRACE ? 'present' : 'away';
    emit();
  }

  function schedule() {
    clearInterval(timer);
    // setInterval, not requestAnimationFrame, so it keeps going while hush is minimized
    if (stream) timer = setInterval(tick, live > 0 ? TICK_LIVE_MS : TICK_MS);
  }

  async function start() {
    if (stream) return true;
    await load();
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, frameRate: { ideal: 15, max: 30 } }, audio: false });
    video = document.createElement('video');
    video.muted = true; video.playsInline = true; video.srcObject = stream;
    await video.play();
    lastSeen = 0; lastPhone = 0; state = '';
    schedule();
    tick();
    emit();
    return true;
  }

  function stop() {
    clearInterval(timer); timer = null;
    if (stream) stream.getTracks().forEach(t => t.stop());
    stream = null;
    if (video) { video.srcObject = null; video = null; }
    state = ''; detail = { face: false, person: false, phone: false, boxes: [], w: 320, h: 240 };
    emit();
  }

  return {
    load, start, stop,
    get running() { return !!stream; },
    get state() { return state; },
    get detail() { return detail; },
    get stream() { return stream; },
    on(fn) { listeners.push(fn); return () => { listeners = listeners.filter(f => f !== fn); }; },
    /** A live view is on screen: check faster so the boxes track movement. Returns a function to call when it closes. */
    watch() { live++; schedule(); let done = false; return () => { if (done) return; done = true; live = Math.max(0, live - 1); schedule(); }; },
  };
})();

/* A live camera view with labelled boxes and a status chip. Used by the camera test and the floating view in focus. */
window.CamView = class {
  constructor(el, opts = {}) {
    this.el = el; this.counting = opts.counting || (() => true);
    el.classList.add('camview');
    el.innerHTML = `<video autoplay muted playsinline></video><canvas></canvas><div class="cv-status"><i></i><span>Starting camera…</span></div>`;
    this.video = el.querySelector('video'); this.cv = el.querySelector('canvas'); this.st = el.querySelector('.cv-status');
    this.off = Presence.on((s, d) => this.draw(s, d));
    this.unwatch = Presence.watch();
    this.attach();
  }
  attach() {
    if (Presence.stream && this.video.srcObject !== Presence.stream) this.video.srcObject = Presence.stream;
  }
  draw(state, d) {
    this.attach();
    const W = this.el.clientWidth, H = this.el.clientHeight;
    if (!W || !H) return;
    const dpr = window.devicePixelRatio || 1;
    if (this.cv.width !== Math.round(W * dpr)) { this.cv.width = Math.round(W * dpr); this.cv.height = Math.round(H * dpr); }
    const c = this.cv.getContext('2d');
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    // the video fills the view (object-fit: cover) and is mirrored like a selfie camera, so map boxes the same way
    const s = Math.max(W / d.w, H / d.h), ox = (W - d.w * s) / 2, oy = (H - d.h * s) / 2;
    const map = b => ({ x: W - (ox + (b.x + b.w) * s), y: oy + b.y * s, w: b.w * s, h: b.h * s });
    const counting = this.counting();
    const faces = d.boxes.filter(b => b.kind === 'face'), phones = d.boxes.filter(b => b.kind === 'phone');
    const people = faces.length ? [] : d.boxes.filter(b => b.kind === 'person');
    const studying = state === 'present';
    const COL = { ok: '#7FC27A', bad: '#E3A94A', soft: 'rgba(227,234,243,.75)' };
    const label = (r, text, col) => {
      c.font = '600 12px "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif';
      const tw = c.measureText(text).width + 14, th = 22, lx = Math.max(2, Math.min(W - tw - 2, r.x)), ly = r.y > th + 4 ? r.y - th - 4 : r.y + 4;
      c.fillStyle = col; c.beginPath(); c.roundRect(lx, ly, tw, th, 6); c.fill();
      c.fillStyle = '#16263A'; c.fillText(text, lx + 7, ly + 15);
    };
    const rect = (r, col, dash) => {
      c.lineWidth = 2.5; c.strokeStyle = col; c.setLineDash(dash ? [6, 5] : []);
      c.beginPath(); c.roundRect(r.x, r.y, r.w, r.h, 10); c.stroke(); c.setLineDash([]);
    };
    for (const b of people) { const r = map(b); rect(r, COL.soft, true); label(r, studying ? 'Face lost' : 'No face · not counted', COL.soft); }
    for (const b of faces) { const r = map(b); const ok = state !== 'phone'; rect(r, ok ? COL.ok : COL.bad); label(r, ok ? 'Studying' : 'Distracted', ok ? COL.ok : COL.bad); }
    for (const b of phones) { const r = map(b); rect(r, COL.bad); label(r, 'Phone', COL.bad); }
    // status chip
    let txt, cls;
    if (!counting) { txt = 'Not in focus · not counted'; cls = 'idle'; }
    else if (state === 'present') { txt = 'Studying · counts as verified'; cls = 'ok'; }
    else if (state === 'phone') { txt = 'Phone out · not counted'; cls = 'bad'; }
    else if (state === 'away') { txt = d.person ? 'Face not in view · not counted' : 'Away from desk · not counted'; cls = 'bad'; }
    else { txt = 'Starting camera…'; cls = 'idle'; }
    this.st.className = 'cv-status ' + cls; this.st.querySelector('span').textContent = txt;
  }
  destroy() { this.off(); this.unwatch(); this.video.srcObject = null; this.el.innerHTML = ''; this.el.classList.remove('camview'); }
};
