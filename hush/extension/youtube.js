// Blocks YouTube Shorts (and hides Shorts shelves) during focus, keeps normal YouTube usable.
(() => {
  let st = { focus: false, shorts: false };
  const style = document.createElement('style');
  style.textContent = `
    html.hush-noshorts ytd-reel-shelf-renderer, html.hush-noshorts ytd-rich-shelf-renderer[is-shorts],
    html.hush-noshorts ytd-rich-section-renderer:has(ytd-rich-shelf-renderer[is-shorts]),
    html.hush-noshorts a[title="Shorts"], html.hush-noshorts ytd-guide-entry-renderer:has(a[title="Shorts"]),
    html.hush-noshorts ytd-mini-guide-entry-renderer[aria-label="Shorts"],
    html.hush-noshorts ytd-reel-item-renderer, html.hush-noshorts grid-shelf-view-model:has(a[href^="/shorts"]),
    html.hush-noshorts ytm-shorts-lockup-view-model, html.hush-noshorts ytm-shorts-lockup-view-model-v2,
    html.hush-noshorts ytd-video-renderer:has(a[href^="/shorts"]) { display: none !important; }`;
  (document.head || document.documentElement).appendChild(style);
  const on = () => st.focus && st.shorts;
  function check() {
    document.documentElement.classList.toggle('hush-noshorts', on());
    if (on() && location.pathname.startsWith('/shorts')) {
      chrome.runtime.sendMessage({ type: 'blocked', site: 'YouTube Shorts' });
      location.replace(chrome.runtime.getURL('blocked.html') + '?site=YouTube%20Shorts&back=' + encodeURIComponent('https://www.youtube.com/'));
    }
  }
  chrome.storage.local.get('hush', d => { if (d.hush) st = d.hush; check(); });
  chrome.storage.onChanged.addListener(ch => { if (ch.hush) { st = ch.hush.newValue || st; check(); } });
  window.addEventListener('yt-navigate-finish', check);
  setInterval(check, 1000);
})();
