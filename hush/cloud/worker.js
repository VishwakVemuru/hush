// hush. sync — a tiny Cloudflare Worker + D1 database that lets the laptop and phone share
// daily screen-time totals (and the laptop's focus state) from anywhere.
// Only per-day aggregates are stored: app name, category, seconds, hourly totals. No titles, no websites.
// Every request except /ping needs `Authorization: Bearer <SYNC_KEY>` (a Worker secret).

const DEVICES = new Set(["laptop", "phone"]);
const DAY = /^\d{4}-\d{2}-\d{2}$/;

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

function sameKey(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

function cleanDay(data) {
  // keep the payload small and shaped: [[name, category, seconds]...], 24 hour buckets of {category: seconds}
  const apps = (Array.isArray(data.apps) ? data.apps : []).slice(0, 300)
    .map(a => [String(a[0] || "").slice(0, 80), String(a[1] || "Other").slice(0, 24), Math.max(0, Math.min(86400, Math.round(+a[2] || 0)))])
    .filter(a => a[0] && a[2] > 0);
  const hours = (Array.isArray(data.hours) ? data.hours : []).slice(0, 24).map(h => {
    const o = {};
    for (const [k, v] of Object.entries(h || {}).slice(0, 12)) o[String(k).slice(0, 24)] = Math.max(0, Math.min(3600, Math.round(+v || 0)));
    return o;
  });
  while (hours.length < 24) hours.push({});
  const total = apps.reduce((s, a) => s + a[2], 0);
  const out = { apps, hours, total };
  if (Number.isFinite(+data.unlocks)) out.unlocks = Math.max(0, Math.round(+data.unlocks));
  if (Number.isFinite(+data.blocked)) out.blocked = Math.max(0, Math.round(+data.blocked));
  return out;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/ping") return json({ app: "hush-sync", v: 1 });
    const auth = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
    if (!env.SYNC_KEY || !sameKey(auth, env.SYNC_KEY)) return json({ error: "unauthorized" }, 401);

    try {
      // ---- daily screen-time totals ----
      if (url.pathname === "/day" && req.method === "PUT") {
        const b = await req.json();
        if (!DEVICES.has(b.device) || !DAY.test(b.day || "")) return json({ error: "bad request" }, 400);
        const data = JSON.stringify(cleanDay(b.data || {}));
        if (data.length > 60000) return json({ error: "too big" }, 413);
        // full replace of one (device, day): retries can never double count
        await env.DB.prepare(
          "INSERT INTO days(device, day, data, updated) VALUES(?1, ?2, ?3, ?4) " +
          "ON CONFLICT(device, day) DO UPDATE SET data=excluded.data, updated=excluded.updated"
        ).bind(b.device, b.day, data, Date.now()).run();
        return json({ ok: true });
      }
      if (url.pathname === "/days" && req.method === "GET") {
        const from = url.searchParams.get("from") || "0000-00-00", to = url.searchParams.get("to") || "9999-99-99";
        const since = +(url.searchParams.get("since") || 0);
        const r = await env.DB.prepare(
          "SELECT device, day, data, updated FROM days WHERE day >= ?1 AND day <= ?2 AND updated > ?3 ORDER BY day LIMIT 500"
        ).bind(from, to, since).all();
        return json({ days: r.results.map(x => ({ device: x.device, day: x.day, updated: x.updated, data: JSON.parse(x.data) })), now: Date.now() });
      }

      // ---- laptop focus state (the phone uses this when it can't reach the laptop on Wi-Fi) ----
      if (url.pathname === "/focus" && req.method === "PUT") {
        const b = await req.json();
        const left = Math.max(0, Math.min(6 * 3600, +b.left || 0));
        const focus = b.focus ? 1 : 0, paused = b.paused ? 1 : 0;
        const until = focus ? Date.now() + left * 1000 : 0;
        await env.DB.prepare(
          "INSERT INTO focus(id, focus, paused, left_s, until, label, updated) VALUES(1, ?1, ?2, ?3, ?4, ?5, ?6) " +
          "ON CONFLICT(id) DO UPDATE SET focus=excluded.focus, paused=excluded.paused, left_s=excluded.left_s, until=excluded.until, label=excluded.label, updated=excluded.updated"
        ).bind(focus, paused, left, until, String(b.label || "").slice(0, 80), Date.now()).run();
        return json({ ok: true });
      }
      if (url.pathname === "/focus" && req.method === "GET") {
        const f = await env.DB.prepare("SELECT * FROM focus WHERE id = 1").first();
        if (!f) return json({ focus: false, left: 0, paused: false, label: "", age: null });
        const now = Date.now();
        // left is worked out from the Worker's own clock, so phone and laptop clocks never need to agree
        const left = f.focus ? (f.paused ? f.left_s : Math.max(0, (f.until - now) / 1000)) : 0;
        return json({ focus: !!f.focus && left > 0, left, paused: !!f.paused, label: f.label, age: (now - f.updated) / 1000 });
      }
    } catch (e) {
      return json({ error: "server error" }, 500);
    }
    return json({ error: "not found" }, 404);
  },
};
