/* hush. study check: is someone at the desk, and are they on their phone?
   Runs only during focus, entirely on this laptop. Frames stay in memory and are never saved or sent anywhere.
   Models (Google MediaPipe, Apache-2.0, bundled in ui/models):
     - BlazeFace short-range: a face in view
     - EfficientDet-Lite0 (COCO): "person" (covers reading with your head down) and "cell phone" */
window.Presence = (() => {
  const TICK_MS = 1500;          // one check every 1.5 s
  const AWAY_GRACE = 12000;      // nobody seen for this long = away
  const PHONE_HOLD = 4000;       // a phone sighting counts for this long
  let tasks = null, loading = null, stream = null, video = null, timer = null;
  let lastSeen = 0, lastPhone = 0, state = '', ts = 0, listeners = [], previewEl = null;
  let detail = { face: false, person: false, phone: false };

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

  function tick() {
    if (!video || video.readyState < 2 || !tasks) return;
    const t = ++ts * 50;   // detectors want strictly increasing timestamps
    let face = false, person = false, phone = false;
    try {
      face = tasks.face.detectForVideo(video, t).detections.length > 0;
      for (const d of tasks.obj.detectForVideo(video, t).detections) {
        const c = d.categories[0];
        if (!c) continue;
        if (c.categoryName === 'person' && c.score >= 0.5) person = true;
        if (c.categoryName === 'cell phone' && c.score >= 0.45) phone = true;
      }
    } catch (e) { return; }
    const now = Date.now();
    if (face || person) lastSeen = now;
    if (phone) lastPhone = now;
    detail = { face, person, phone };
    state = now - lastPhone < PHONE_HOLD ? 'phone' : now - lastSeen < AWAY_GRACE ? 'present' : 'away';
    emit();
  }

  async function start() {
    if (stream) return true;
    await load();
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240, frameRate: { ideal: 5, max: 10 } }, audio: false });
    video = document.createElement('video');
    video.muted = true; video.playsInline = true; video.srcObject = stream;
    await video.play();
    if (previewEl) previewEl.srcObject = stream;
    lastSeen = Date.now(); lastPhone = 0; state = 'present';
    // setInterval, not requestAnimationFrame, so it keeps going while hush is minimized
    timer = setInterval(tick, TICK_MS);
    emit();
    return true;
  }

  function stop() {
    clearInterval(timer); timer = null;
    if (stream) stream.getTracks().forEach(t => t.stop());
    stream = null;
    if (video) { video.srcObject = null; video = null; }
    if (previewEl) previewEl.srcObject = null;
    state = ''; emit();
  }

  return {
    load, start, stop,
    get running() { return !!stream; },
    get state() { return state; },
    get detail() { return detail; },
    on(fn) { listeners.push(fn); return () => { listeners = listeners.filter(f => f !== fn); }; },
    preview(el) { previewEl = el; if (el && stream) el.srcObject = stream; },
  };
})();
