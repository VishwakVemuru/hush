// hush. companion: talks to the desktop app on 127.0.0.1:47321
const API = 'http://127.0.0.1:47321';
const HDR = { 'X-Hush': '1', 'Content-Type': 'application/json' };
let state = { focus: false, sites: [], shorts: false, connected: false };

const hostOf = url => { try { const u = new URL(url); return /^https?:$/.test(u.protocol) ? u.hostname.toLowerCase() : null; } catch { return null; } };
const matches = (host, list) => !!host && list.some(d => host === d || host.endsWith('.' + d));
const blockedUrl = site => chrome.runtime.getURL('blocked.html') + '?site=' + encodeURIComponent(site);

async function fetchState() {
  try {
    const r = await fetch(API + '/state', { headers: HDR, cache: 'no-store' });
    const j = await r.json();
    state = { ...j, connected: true };
  } catch {
    state = { focus: false, sites: [], shorts: false, connected: false };
  }
  await chrome.storage.local.set({ hush: state });
  await applyRules();
  chrome.action.setBadgeText({ text: state.focus ? '●' : '' });
  chrome.action.setBadgeBackgroundColor({ color: '#3E6A9E' });
  return state;
}

async function applyRules() {
  const old = await chrome.declarativeNetRequest.getDynamicRules();
  const addRules = [];
  if (state.focus) {
    state.sites.forEach((d, i) => addRules.push({
      id: i + 1, priority: 1,
      action: { type: 'redirect', redirect: { extensionPath: '/blocked.html?site=' + encodeURIComponent(d) } },
      condition: { requestDomains: [d], resourceTypes: ['main_frame'] }
    }));
    if (state.shorts) addRules.push({
      id: 9000, priority: 2,
      action: { type: 'redirect', redirect: { extensionPath: '/blocked.html?site=YouTube%20Shorts' } },
      condition: { regexFilter: '^https?://([a-z0-9-]+\\.)?youtube\\.com/shorts', resourceTypes: ['main_frame'] }
    });
  }
  await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: old.map(r => r.id), addRules });
}

async function report(tab) {
  if (!tab || !tab.active) return;
  const host = hostOf(tab.url);
  try { await fetch(API + '/activity', { method: 'POST', headers: HDR, body: JSON.stringify({ domain: host || '' }) }); } catch {}
}

async function reportActive() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  report(tab);
}

// Fallback for anything the network rules miss (e.g. tabs restored from before focus started)
async function enforce(tabId, url) {
  if (!state.focus) return;
  const host = hostOf(url);
  if (matches(host, state.sites)) chrome.tabs.update(tabId, { url: blockedUrl(host) });
}

chrome.runtime.onInstalled.addListener(() => { chrome.alarms.create('hush', { periodInMinutes: 0.5 }); fetchState(); });
chrome.runtime.onStartup.addListener(() => { chrome.alarms.create('hush', { periodInMinutes: 0.5 }); fetchState(); });
chrome.alarms.onAlarm.addListener(async () => {
  const wasFocus = state.focus;
  await fetchState();
  reportActive();
  if (state.focus && !wasFocus) {
    const tabs = await chrome.tabs.query({});
    tabs.forEach(t => enforce(t.id, t.url));
  }
});
chrome.tabs.onActivated.addListener(async ({ tabId }) => { await fetchState(); const t = await chrome.tabs.get(tabId); report(t); enforce(t.id, t.url); });
chrome.tabs.onUpdated.addListener(async (tabId, info, tab) => {
  if (info.url || info.status === 'complete') { await fetchState(); report(tab); if (info.url) enforce(tabId, info.url); }
});
chrome.windows.onFocusChanged.addListener(wid => { if (wid !== chrome.windows.WINDOW_ID_NONE) reportActive(); });

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg && msg.type === 'blocked') {
    fetch(API + '/blocked', { method: 'POST', headers: HDR, body: JSON.stringify({ site: msg.site }) }).catch(() => {});
  }
  if (msg && msg.type === 'state') { fetchState().then(reply); return true; }
});

fetchState();
