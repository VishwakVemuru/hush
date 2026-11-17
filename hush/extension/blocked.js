(() => {
  const q = new URLSearchParams(location.search);
  const site = q.get('site') || 'This';
  document.getElementById('site').textContent = site;
  chrome.runtime.sendMessage({ type: 'blocked', site });
  let st = null;
  const fmt = s => { s = Math.max(0, Math.ceil(s)); return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0'); };
  const load = () => chrome.runtime.sendMessage({ type: 'state' }, r => { st = r; });
  load(); setInterval(load, 5000);
  setInterval(() => {
    if (!st || !st.focus) { document.getElementById('time').textContent = ''; document.getElementById('lab').textContent = st && st.connected ? 'Focus is over, you are free.' : ''; return; }
    const left = st.paused ? st.left : st.endsAt - Date.now() / 1000;
    document.getElementById('time').textContent = fmt(left);
    document.getElementById('lab').textContent = (st.label ? st.label + ' · ' : '') + 'left in this session';
  }, 250);
  document.getElementById('back').onclick = () => {
    const back = q.get('back');
    if (back) location.href = back; else if (history.length > 1) history.back(); else window.close();
  };
})();
