// hush. cloud — accounts, friends, a focus leaderboard, and per-user screen-time sync.
// Cloudflare Worker + D1. Only aggregates are stored: per-session focus minutes and per-day app totals.
// No window titles, no websites, never any camera data (the camera check runs entirely on the laptop).
//
// Auth: `Authorization: Bearer <session token>` from /auth/signup or /auth/login.
// Legacy: the old single-user SYNC_KEY still works for screen-time sync and maps to the account that claimed it,
// so phones on the previous version keep syncing until they sign in.

const DEVICES = new Set(["laptop", "phone"]);
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const USERNAME = /^[a-z0-9_]{3,20}$/;
const ITERS = 60000;          // PBKDF2-SHA256 rounds (Workers caps PBKDF2 at 100k)
const MAX_FAILS = 8, LOCK_MS = 15 * 60 * 1000;
const enc = new TextEncoder();

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
const bad = (msg, status = 400) => json({ error: msg }, status);

function sameKey(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}
const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
const randHex = n => hex(crypto.getRandomValues(new Uint8Array(n)));
const sha256 = async s => hex(await crypto.subtle.digest("SHA-256", enc.encode(s)));

async function hashPassword(password, saltHex, iters) {
  const key = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
  const salt = new Uint8Array(saltHex.match(/../g).map(h => parseInt(h, 16)));
  return hex(await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations: iters }, key, 256));
}

// ---------- screen-time payload (unchanged from v1.3) ----------
function cleanDay(data) {
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

// ---------- login throttling ----------
async function locked(env, k) {
  const r = await env.DB.prepare("SELECT until FROM login_fail WHERE k = ?1").bind(k).first();
  return r && r.until > Date.now();
}
async function fail(env, k) {
  const now = Date.now();
  const r = await env.DB.prepare("SELECT count, first FROM login_fail WHERE k = ?1").bind(k).first();
  let count = 1, first = now;
  if (r && now - r.first < LOCK_MS) { count = r.count + 1; first = r.first; }
  await env.DB.prepare("INSERT INTO login_fail(k, count, first, until) VALUES(?1, ?2, ?3, ?4) " +
    "ON CONFLICT(k) DO UPDATE SET count=excluded.count, first=excluded.first, until=excluded.until")
    .bind(k, count, first, count >= MAX_FAILS ? now + LOCK_MS : 0).run();
}

async function newSession(env, userId, device) {
  const token = randHex(32), now = Date.now();
  await env.DB.prepare("INSERT INTO sessions(token_hash, user_id, device, created, last_seen) VALUES(?1, ?2, ?3, ?4, ?4)")
    .bind(await sha256(token), userId, String(device || "").slice(0, 40), now).run();
  return token;
}

/** Signed-in user for this request, or null. Accepts a session token, or the legacy SYNC_KEY once it's been claimed. */
async function who(req, env) {
  const tok = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "").trim();
  if (!tok) return null;
  if (env.SYNC_KEY && sameKey(tok, env.SYNC_KEY)) {
    const m = await env.DB.prepare("SELECT v FROM meta WHERE k = 'legacy_owner'").first();
    if (!m) return { legacy: true, id: 0 };
    const u = await env.DB.prepare("SELECT id, username, display FROM users WHERE id = ?1").bind(+m.v).first();
    return u ? { ...u, legacy: true } : { legacy: true, id: 0 };
  }
  const th = await sha256(tok);
  const s = await env.DB.prepare("SELECT s.user_id, s.last_seen, u.username, u.display FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?1").bind(th).first();
  if (!s) return null;
  if (Date.now() - s.last_seen > 3600000) await env.DB.prepare("UPDATE sessions SET last_seen = ?1 WHERE token_hash = ?2").bind(Date.now(), th).run();
  return { id: s.user_id, username: s.username, display: s.display, token_hash: th };
}

async function friendIds(env, uid) {
  const r = await env.DB.prepare("SELECT friend_id FROM friends WHERE user_id = ?1 AND status = 'accepted'").bind(uid).all();
  return r.results.map(x => x.friend_id);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url), path = url.pathname, M = req.method;
    if (path === "/ping") return json({ app: "hush-sync", v: 2 });
    try {
      const ip = req.headers.get("cf-connecting-ip") || "?";

      // ---------------- accounts ----------------
      if (path === "/auth/signup" && M === "POST") {
        const b = await req.json();
        const username = String(b.username || "").trim().toLowerCase(), password = String(b.password || "");
        if (!USERNAME.test(username)) return bad("Usernames are 3–20 letters, numbers or _");
        if (password.length < 8 || password.length > 200) return bad("Use a password of at least 8 characters");
        if (await locked(env, "signup:" + ip)) return bad("Too many sign-ups from here. Try again later.", 429);
        const exists = await env.DB.prepare("SELECT 1 FROM users WHERE username = ?1").bind(username).first();
        if (exists) return bad("That username is taken", 409);
        const salt = randHex(16);
        const display = String(b.display || username).trim().slice(0, 30) || username;
        const r = await env.DB.prepare("INSERT INTO users(username, display, pass_hash, salt, iters, created) VALUES(?1, ?2, ?3, ?4, ?5, ?6)")
          .bind(username, display, await hashPassword(password, salt, ITERS), salt, ITERS, Date.now()).run();
        await fail(env, "signup:" + ip); // counts sign-ups per address, so one person can't mass-create accounts
        const id = r.meta.last_row_id;
        return json({ token: await newSession(env, id, b.device), user: { username, display } });
      }
      if (path === "/auth/login" && M === "POST") {
        const b = await req.json();
        const username = String(b.username || "").trim().toLowerCase(), password = String(b.password || "");
        if (await locked(env, "u:" + username) || await locked(env, "ip:" + ip)) return bad("Too many wrong passwords. Try again in 15 minutes.", 429);
        const u = await env.DB.prepare("SELECT * FROM users WHERE username = ?1").bind(username).first();
        const ok = u && sameKey(await hashPassword(password, u.salt, u.iters), u.pass_hash);
        if (!ok) {
          await fail(env, "u:" + username); await fail(env, "ip:" + ip);
          return bad("Wrong username or password", 401);
        }
        await env.DB.prepare("DELETE FROM login_fail WHERE k = ?1").bind("u:" + username).run();
        return json({ token: await newSession(env, u.id, b.device), user: { username: u.username, display: u.display } });
      }

      const me = await who(req, env);
      if (!me) return bad("Please sign in", 401);
      const uid = me.id;

      // legacy key before anyone claimed it: only the old screen-time endpoints work, on the old tables
      if (me.legacy && !uid) return legacyRoutes(req, env, url);

      if (path === "/me" && M === "GET") return json({ user: { username: me.username, display: me.display }, legacy: !!me.legacy });
      if (path === "/auth/logout" && M === "POST") {
        if (me.token_hash) await env.DB.prepare("DELETE FROM sessions WHERE token_hash = ?1").bind(me.token_hash).run();
        return json({ ok: true });
      }
      if (path === "/auth/password" && M === "POST") {
        if (me.legacy) return bad("Sign in first", 403);
        const b = await req.json();
        const u = await env.DB.prepare("SELECT * FROM users WHERE id = ?1").bind(uid).first();
        if (!sameKey(await hashPassword(String(b.old || ""), u.salt, u.iters), u.pass_hash)) return bad("Current password is wrong", 401);
        const pw = String(b.new || "");
        if (pw.length < 8 || pw.length > 200) return bad("Use a password of at least 8 characters");
        const salt = randHex(16);
        await env.DB.prepare("UPDATE users SET pass_hash = ?1, salt = ?2, iters = ?3 WHERE id = ?4").bind(await hashPassword(pw, salt, ITERS), salt, ITERS, uid).run();
        await env.DB.prepare("DELETE FROM sessions WHERE user_id = ?1 AND token_hash != ?2").bind(uid, me.token_hash).run();
        return json({ ok: true });
      }
      if (path === "/auth/claim-legacy" && M === "POST") {
        // move the old single-user screen time into this account (owner only, once)
        if (me.legacy) return bad("Sign in first", 403);
        const b = await req.json();
        if (!env.SYNC_KEY || !sameKey(String(b.key || ""), env.SYNC_KEY)) return bad("That isn't the old sync key", 403);
        const m = await env.DB.prepare("SELECT v FROM meta WHERE k = 'legacy_owner'").first();
        if (m && +m.v !== uid) return bad("Already claimed by another account", 409);
        await env.DB.batch([
          env.DB.prepare("INSERT OR REPLACE INTO udays(user_id, device, day, data, updated) SELECT ?1, device, day, data, updated FROM days").bind(uid),
          env.DB.prepare("INSERT OR REPLACE INTO meta(k, v) VALUES('legacy_owner', ?1)").bind(String(uid)),
        ]);
        return json({ ok: true });
      }

      // ---------------- friends ----------------
      if (path === "/friends" && M === "GET") {
        const r = await env.DB.prepare(
          "SELECT f.friend_id AS id, f.status, u.username, u.display, 'out' AS dir FROM friends f JOIN users u ON u.id = f.friend_id WHERE f.user_id = ?1 " +
          "UNION ALL SELECT f.user_id AS id, f.status, u.username, u.display, 'in' AS dir FROM friends f JOIN users u ON u.id = f.user_id " +
          "WHERE f.friend_id = ?1 AND f.status = 'pending'").bind(uid).all();
        const friends = [], incoming = [], outgoing = [];
        for (const x of r.results) {
          const o = { username: x.username, display: x.display };
          if (x.status === "accepted" && x.dir === "out") friends.push(o);
          else if (x.dir === "in") incoming.push(o);
          else if (x.status === "pending") outgoing.push(o);
        }
        return json({ friends, incoming, outgoing });
      }
      if (path === "/friends/request" && M === "POST") {
        const b = await req.json();
        const name = String(b.username || "").trim().toLowerCase();
        const f = await env.DB.prepare("SELECT id, username, display FROM users WHERE username = ?1").bind(name).first();
        if (!f) return bad("No one with that username", 404);
        if (f.id === uid) return bad("That's you");
        const now = Date.now();
        const back = await env.DB.prepare("SELECT status FROM friends WHERE user_id = ?1 AND friend_id = ?2").bind(f.id, uid).first();
        if (back) {
          // they already asked you: adding them back accepts
          await env.DB.batch([
            env.DB.prepare("UPDATE friends SET status = 'accepted' WHERE user_id = ?1 AND friend_id = ?2").bind(f.id, uid),
            env.DB.prepare("INSERT OR REPLACE INTO friends(user_id, friend_id, status, created) VALUES(?1, ?2, 'accepted', ?3)").bind(uid, f.id, now),
          ]);
          return json({ ok: true, status: "accepted" });
        }
        const pending = await env.DB.prepare("SELECT COUNT(*) AS n FROM friends WHERE user_id = ?1 AND status = 'pending'").bind(uid).first();
        if (pending.n >= 50) return bad("Too many pending requests", 429);
        await env.DB.prepare("INSERT OR IGNORE INTO friends(user_id, friend_id, status, created) VALUES(?1, ?2, 'pending', ?3)").bind(uid, f.id, now).run();
        return json({ ok: true, status: "pending" });
      }
      if (path === "/friends/accept" && M === "POST") {
        const b = await req.json();
        const f = await env.DB.prepare("SELECT id FROM users WHERE username = ?1").bind(String(b.username || "").toLowerCase()).first();
        if (!f) return bad("No one with that username", 404);
        const req1 = await env.DB.prepare("SELECT 1 FROM friends WHERE user_id = ?1 AND friend_id = ?2").bind(f.id, uid).first();
        if (!req1) return bad("No request from them", 404);
        await env.DB.batch([
          env.DB.prepare("UPDATE friends SET status = 'accepted' WHERE user_id = ?1 AND friend_id = ?2").bind(f.id, uid),
          env.DB.prepare("INSERT OR REPLACE INTO friends(user_id, friend_id, status, created) VALUES(?1, ?2, 'accepted', ?3)").bind(uid, f.id, Date.now()),
        ]);
        return json({ ok: true });
      }
      if (path.startsWith("/friends/") && M === "DELETE") {
        const name = decodeURIComponent(path.slice(9)).toLowerCase();
        const f = await env.DB.prepare("SELECT id FROM users WHERE username = ?1").bind(name).first();
        if (f) await env.DB.prepare("DELETE FROM friends WHERE (user_id = ?1 AND friend_id = ?2) OR (user_id = ?2 AND friend_id = ?1)").bind(uid, f.id).run();
        return json({ ok: true });
      }

      // ---------------- focus log + leaderboard ----------------
      if (path === "/focus-log" && M === "POST") {
        const b = await req.json();
        const now = Date.now();
        const start = Math.round(+b.start), end = Math.round(+b.end);
        const wall = (end - start) / 1000;
        const n = k => Math.max(0, Math.round(+b[k] || 0));
        const focus_s = n("focus_s"), verified_s = n("verified_s"), phone_s = n("phone_s"), away_s = n("away_s"), planned_s = n("planned_s");
        const cid = String(b.client_id || "").slice(0, 64);
        if (!cid || !(start > 1.6e12) || !(end > start) || end > now + 5 * 60000) return bad("Bad session times");
        if (wall > 6 * 3600 || focus_s > wall + 60 || verified_s > focus_s || phone_s + away_s > focus_s + 60) return bad("Those numbers don't add up");
        const overlap = await env.DB.prepare("SELECT 1 FROM focus_log WHERE user_id = ?1 AND client_id != ?2 AND start < ?3 AND end > ?4 LIMIT 1")
          .bind(uid, cid, end, start).first();
        if (overlap) return bad("Overlaps another session", 409);
        const day = await env.DB.prepare("SELECT COALESCE(SUM(focus_s), 0) AS s FROM focus_log WHERE user_id = ?1 AND client_id != ?2 AND start > ?3")
          .bind(uid, cid, start - 86400000).first();
        if (day.s + focus_s > 16 * 3600) return bad("More than 16 hours in a day", 422);
        await env.DB.prepare(
          "INSERT INTO focus_log(user_id, client_id, start, end, planned_s, focus_s, verified_s, phone_s, away_s, camera, completed) " +
          "VALUES(?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11) ON CONFLICT(user_id, client_id) DO UPDATE SET " +
          "end=excluded.end, focus_s=excluded.focus_s, verified_s=excluded.verified_s, phone_s=excluded.phone_s, away_s=excluded.away_s, camera=excluded.camera, completed=excluded.completed")
          .bind(uid, cid, start, end, planned_s, focus_s, verified_s, phone_s, away_s, b.camera ? 1 : 0, b.completed ? 1 : 0).run();
        return json({ ok: true });
      }
      if (path === "/leaderboard" && M === "GET") {
        // `from` and `tz` come from the caller so "today" means the viewer's today
        const from = Math.max(0, +(url.searchParams.get("from") || 0));
        const tz = Math.max(-840, Math.min(840, +(url.searchParams.get("tz") || 0))); // minutes east of UTC
        const ids = [uid, ...(await friendIds(env, uid))];
        const ph = ids.map((_, i) => "?" + (i + 2)).join(",");
        const totals = await env.DB.prepare(
          `SELECT u.id, u.username, u.display, COALESCE(SUM(l.focus_s),0) AS focus_s, COALESCE(SUM(l.verified_s),0) AS verified_s, COUNT(l.id) AS sessions, ` +
          `COALESCE(MAX(l.camera),0) AS camera FROM users u LEFT JOIN focus_log l ON l.user_id = u.id AND l.start >= ?1 WHERE u.id IN (${ph}) GROUP BY u.id`)
          .bind(from, ...ids).all();
        // streak: consecutive days (in the viewer's timezone) with 25+ focused minutes
        const since = Date.now() - 62 * 86400000;
        const daily = await env.DB.prepare(
          `SELECT user_id, CAST((start / 1000 + ?1 * 60) / 86400 AS INTEGER) AS d, SUM(focus_s) AS s FROM focus_log WHERE user_id IN (${ids.map((_, i) => "?" + (i + 3)).join(",")}) AND start >= ?2 GROUP BY user_id, d`)
          .bind(tz, since, ...ids).all();
        const today = Math.floor((Date.now() / 1000 + tz * 60) / 86400);
        const good = {};
        for (const r of daily.results) if (r.s >= 25 * 60) (good[r.user_id] = good[r.user_id] || new Set()).add(r.d);
        const streak = id => { const g = good[id]; if (!g) return 0; let d = g.has(today) ? today : today - 1, n = 0; while (g.has(d)) { n++; d--; } return n; };
        const rows = totals.results.map(r => ({ username: r.username, display: r.display, me: r.id === uid, focus_s: r.focus_s, verified_s: r.verified_s,
          sessions: r.sessions, camera: !!r.camera, streak: streak(r.id) }));
        rows.sort((a, b) => b.verified_s - a.verified_s || b.focus_s - a.focus_s);
        return json({ rows });
      }

      // ---------------- per-user screen time + focus state ----------------
      if (path === "/day" && M === "PUT") {
        const b = await req.json();
        if (!DEVICES.has(b.device) || !DAY.test(b.day || "")) return bad("bad request");
        const data = JSON.stringify(cleanDay(b.data || {}));
        if (data.length > 60000) return bad("too big", 413);
        await env.DB.prepare("INSERT INTO udays(user_id, device, day, data, updated) VALUES(?1, ?2, ?3, ?4, ?5) " +
          "ON CONFLICT(user_id, device, day) DO UPDATE SET data=excluded.data, updated=excluded.updated").bind(uid, b.device, b.day, data, Date.now()).run();
        return json({ ok: true });
      }
      if (path === "/days" && M === "GET") {
        const from = url.searchParams.get("from") || "0000-00-00", to = url.searchParams.get("to") || "9999-99-99";
        const since = +(url.searchParams.get("since") || 0);
        const r = await env.DB.prepare("SELECT device, day, data, updated FROM udays WHERE user_id = ?1 AND day >= ?2 AND day <= ?3 AND updated > ?4 ORDER BY day LIMIT 500")
          .bind(uid, from, to, since).all();
        return json({ days: r.results.map(x => ({ device: x.device, day: x.day, updated: x.updated, data: JSON.parse(x.data) })), now: Date.now() });
      }
      if (path === "/focus" && M === "PUT") {
        const b = await req.json();
        const left = Math.max(0, Math.min(6 * 3600, +b.left || 0));
        const focus = b.focus ? 1 : 0, paused = b.paused ? 1 : 0;
        await env.DB.prepare("INSERT INTO ufocus(user_id, focus, paused, left_s, until, label, updated) VALUES(?1, ?2, ?3, ?4, ?5, ?6, ?7) " +
          "ON CONFLICT(user_id) DO UPDATE SET focus=excluded.focus, paused=excluded.paused, left_s=excluded.left_s, until=excluded.until, label=excluded.label, updated=excluded.updated")
          .bind(uid, focus, paused, left, focus ? Date.now() + left * 1000 : 0, String(b.label || "").slice(0, 80), Date.now()).run();
        return json({ ok: true });
      }
      if (path === "/focus" && M === "GET") {
        const f = await env.DB.prepare("SELECT * FROM ufocus WHERE user_id = ?1").bind(uid).first();
        if (!f) return json({ focus: false, left: 0, paused: false, label: "", age: null });
        const now = Date.now();
        const left = f.focus ? (f.paused ? f.left_s : Math.max(0, (f.until - now) / 1000)) : 0;
        return json({ focus: !!f.focus && left > 0, left, paused: !!f.paused, label: f.label, age: (now - f.updated) / 1000 });
      }
    } catch (e) {
      return bad("server error", 500);
    }
    return bad("not found", 404);
  },
};

// Old single-user behaviour, used only until the owner claims the legacy key.
async function legacyRoutes(req, env, url) {
  const path = url.pathname, M = req.method;
  if (path === "/day" && M === "PUT") {
    const b = await req.json();
    if (!DEVICES.has(b.device) || !DAY.test(b.day || "")) return bad("bad request");
    await env.DB.prepare("INSERT INTO days(device, day, data, updated) VALUES(?1, ?2, ?3, ?4) ON CONFLICT(device, day) DO UPDATE SET data=excluded.data, updated=excluded.updated")
      .bind(b.device, b.day, JSON.stringify(cleanDay(b.data || {})), Date.now()).run();
    return json({ ok: true });
  }
  if (path === "/days" && M === "GET") {
    const r = await env.DB.prepare("SELECT device, day, data, updated FROM days WHERE day >= ?1 AND day <= ?2 AND updated > ?3 ORDER BY day LIMIT 500")
      .bind(url.searchParams.get("from") || "0000-00-00", url.searchParams.get("to") || "9999-99-99", +(url.searchParams.get("since") || 0)).all();
    return json({ days: r.results.map(x => ({ device: x.device, day: x.day, updated: x.updated, data: JSON.parse(x.data) })), now: Date.now() });
  }
  if (path === "/focus" && M === "PUT") {
    const b = await req.json();
    const left = Math.max(0, Math.min(6 * 3600, +b.left || 0));
    await env.DB.prepare("INSERT INTO focus(id, focus, paused, left_s, until, label, updated) VALUES(1, ?1, ?2, ?3, ?4, ?5, ?6) " +
      "ON CONFLICT(id) DO UPDATE SET focus=excluded.focus, paused=excluded.paused, left_s=excluded.left_s, until=excluded.until, label=excluded.label, updated=excluded.updated")
      .bind(b.focus ? 1 : 0, b.paused ? 1 : 0, left, b.focus ? Date.now() + left * 1000 : 0, String(b.label || "").slice(0, 80), Date.now()).run();
    return json({ ok: true });
  }
  if (path === "/focus" && M === "GET") {
    const f = await env.DB.prepare("SELECT * FROM focus WHERE id = 1").first();
    if (!f) return json({ focus: false, left: 0, paused: false, label: "", age: null });
    const left = f.focus ? (f.paused ? f.left_s : Math.max(0, (f.until - Date.now()) / 1000)) : 0;
    return json({ focus: !!f.focus && left > 0, left, paused: !!f.paused, label: f.label, age: (Date.now() - f.updated) / 1000 });
  }
  return bad("Please sign in", 401);
}
