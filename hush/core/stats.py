"""Turns usage into the numbers the Stats screen shows, for the laptop, the phone (synced) or both combined."""
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from .names import CAT_COLORS

SOURCES = ("laptop", "phone", "all")


def bounds(d):
    a = datetime.combine(d, datetime.min.time()).timestamp()
    return a, a + 86400


def fmt_dur(secs):
    m = round((secs or 0) / 60)
    h, mm = divmod(m, 60)
    return f"{h}h {mm}m" if h else f"{mm}m"


def _split(rows, a, b, categorize):
    """Yield (date, hour, app, category, seconds) for each usage row clipped to [a,b)."""
    for r in rows:
        s, e = max(r["start"], a), min(r["end"], b)
        if e <= s:
            continue
        # websites are not part of screen time; older rows that recorded a site count as their browser
        key = r["app"]
        cat = categorize(r["app"], r["exe"], None)
        t = s
        while t < e:
            dt = datetime.fromtimestamp(t)
            nxt = datetime(dt.year, dt.month, dt.day, dt.hour).timestamp() + 3600
            chunk = min(e, nxt) - t
            yield dt.date(), dt.hour, key, cat, chunk
            t += chunk


def _blank_day():
    return {"apps": defaultdict(lambda: ["Other", 0.0]), "hours": [defaultdict(float) for _ in range(24)], "total": 0.0}


def laptop_days(db, first, last, categorize):
    """{date: day} for the laptop, built from the local usage table."""
    a, _ = bounds(first)
    _, b = bounds(last)
    out = defaultdict(_blank_day)
    for d, h, app, cat, secs in _split(db.usage_between(a, b), a, b, categorize):
        day = out[d]
        day["apps"][app][0] = cat
        day["apps"][app][1] += secs
        day["hours"][h][cat] += secs
        day["total"] += secs
    return out


def day_payload(day):
    """Laptop day -> the compact shape that is synced to the cloud (no titles, no websites)."""
    return {"apps": [[n, v[0], round(v[1])] for n, v in sorted(day["apps"].items(), key=lambda x: -x[1][1]) if v[1] >= 1],
            "hours": [{c: round(s) for c, s in h.items() if s >= 1} for h in day["hours"]],
            "total": round(day["total"])}


def phone_days(cache, first, last, recategorize):
    """{date: day} for the phone, from the synced cache ({'YYYY-MM-DD': payload})."""
    out = {}
    d = first
    while d <= last:
        p = (cache or {}).get(d.isoformat())
        if p:
            day = _blank_day()
            for name, cat, secs in p.get("apps", []):
                cat = recategorize(name, cat)
                day["apps"][name][0] = cat
                day["apps"][name][1] += secs
                day["total"] += secs
            for h, bucket in enumerate((p.get("hours") or [])[:24]):
                for c, s in bucket.items():
                    day["hours"][h][c] += s
            day["unlocks"] = p.get("unlocks")
            out[d] = day
        d += timedelta(days=1)
    return out


def _focus_by_day(db, a, b):
    out = defaultdict(lambda: {"tracked": 0.0, "distracted": 0.0})
    for f in db.focus_between(a, b):
        d = datetime.fromtimestamp(f["start"]).date()
        out[d]["tracked"] += f["tracked"] or 0
        out[d]["distracted"] += f["distracted"] or 0
    return out


def _fmt_delta(v, avg):
    diff = v - avg
    if abs(diff) < 60:
        return "same as usual"
    return ("↑ " if diff > 0 else "↓ ") + fmt_dur(abs(diff)) + " vs avg"


def overview(db, goal_hours):
    today = date.today()
    a, _ = bounds(today - timedelta(days=60))
    fb = _focus_by_day(db, a, time.time() + 1)
    focus = {d: max(0, v["tracked"] - v["distracted"]) for d, v in fb.items()}
    goal = goal_hours * 3600
    streak = 0
    d = today if focus.get(today, 0) >= 25 * 60 else today - timedelta(days=1)
    while focus.get(d, 0) >= 25 * 60:
        streak += 1
        d -= timedelta(days=1)
    dots = []
    for i in range(6, -1, -1):
        v = focus.get(today - timedelta(days=i), 0)
        dots.append(2 if v >= goal else (1 if v >= 60 else 0))
    return {"streak": streak, "dots": dots, "focus_today": focus.get(today, 0), "goal": goal}


KEEP_DAYS = 30  # screen time is kept for today + the 29 days before it


def day_totals(db, categorize, source="laptop", phone_cache=None, recategorize=None):
    """Screen time for each of the last KEEP_DAYS days, newest first (for the day picker)."""
    today = date.today()
    first = today - timedelta(days=KEEP_DAYS - 1)
    lap = laptop_days(db, first, today, categorize) if source in ("laptop", "all") else {}
    pho = phone_days(phone_cache, first, today, recategorize or (lambda n, c: c)) if source in ("phone", "all") else {}
    out = []
    for i in range(KEEP_DAYS):
        d = today - timedelta(days=i)
        t = (lap[d]["total"] if d in lap else 0) + (pho[d]["total"] if d in pho else 0)
        out.append({"offset": i, "date": d.isoformat(), "total": round(t),
                    "label": "Today" if i == 0 else "Yesterday" if i == 1 else d.strftime("%a %d").replace(" 0", " "),
                    "long": "Today" if i == 0 else "Yesterday" if i == 1 else d.strftime("%A, %d %B").replace(" 0", " ")})
    return out


def compute(db, rng, categorize, source="laptop", phone_cache=None, recategorize=None, offset=0):
    # offset picks an earlier day in the Day view (0 = today, 1 = yesterday, ...)
    offset = max(0, min(KEEP_DAYS - 1, int(offset or 0))) if rng == "day" else 0
    today = date.today() - timedelta(days=offset)
    source = source if source in SOURCES else "laptop"
    n = {"day": 1, "week": 7, "month": 30}.get(rng, 1)
    first = today - timedelta(days=n - 1)
    hist_first = first - timedelta(days=7) if rng == "day" else first
    days = [first + timedelta(days=i) for i in range(n)]
    recat = recategorize or (lambda name, cat: cat)

    lap = laptop_days(db, hist_first, today, categorize) if source in ("laptop", "all") else {}
    pho = phone_days(phone_cache, hist_first, today, recat) if source in ("phone", "all") else {}
    has_phone = bool(phone_cache)

    def total(d, which=source):
        t = 0.0
        if which in ("laptop", "all") and d in lap:
            t += lap[d]["total"]
        if which in ("phone", "all") and d in pho:
            t += pho[d]["total"]
        return t

    cats = defaultdict(float)
    apps = {}
    hours = [defaultdict(float) for _ in range(24)]
    for dev, table in (("laptop", lap), ("phone", pho)):
        for d in days:
            day = table.get(d)
            if not day:
                continue
            for name, (cat, secs) in day["apps"].items():
                cats[cat] += secs
                k = (name, dev) if source == "all" else (name, None)
                a = apps.setdefault(k, {"name": name, "secs": 0.0, "cat": cat, "device": dev})
                a["secs"] += secs
                a["cat"] = cat
            if rng == "day":
                for h in range(24):
                    for c, s in day["hours"][h].items():
                        hours[h][c] += s

    a, _ = bounds(hist_first)
    _, b = bounds(today)
    ra, _ = bounds(first)
    fb = _focus_by_day(db, a, b)
    blocks = db.events_between(ra, b, "block")
    phone_blocks = [e for e in blocks if str(e["target"]).endswith("(phone)")]

    def focus_of(d):
        v = fb.get(d)
        return max(0, v["tracked"] - v["distracted"]) if v else 0

    screen = sum(total(d) for d in days)
    focus = sum(focus_of(d) for d in days)
    tracked = sum(fb[d]["tracked"] for d in days if d in fb)
    distracted = sum(fb[d]["distracted"] for d in days if d in fb)
    score = round(100 * (1 - distracted / tracked)) if tracked else None
    prev = [today - timedelta(days=i) for i in range(1, 8)]
    prev_s = [total(d) for d in prev if total(d) > 0]
    avg_s = sum(prev_s) / len(prev_s) if prev_s else None
    active_days = max(1, sum(1 for d in days if total(d) > 0))

    if rng == "day":
        screen_sub = _fmt_delta(screen, avg_s) if avg_s else "first day tracked"
        screen_tone = "good" if avg_s and screen <= avg_s else "muted"
    else:
        screen_sub, screen_tone = f"avg {fmt_dur(screen / active_days)} a day", "muted"

    peak = None
    if blocks:
        hc = defaultdict(int)
        for e in blocks:
            hc[datetime.fromtimestamp(e["ts"]).hour] += 1
        h = max(hc, key=hc.get)
        fm = lambda x: f"{(x % 12) or 12}{'am' if x < 12 else 'pm'}"
        peak = f"mostly {fm(h)}–{fm((h + 1) % 24)}"

    focus_card = {"label": "Focused", "value": focus, "fmt": "dur",
                  "sub": f"avg {fmt_dur(focus / active_days)} a day" if rng != "day" else ("on the laptop" if focus else "no focus yet"),
                  "tone": "good" if focus else "muted"}
    score_card = {"label": "Focus score", "value": score, "fmt": "pct", "sub": "no sessions yet" if score is None else
                  ("excellent" if score >= 90 else "solid" if score >= 75 else "room to grow"), "tone": "muted"}
    if source == "laptop":
        cards = [{"label": "Screen time", "value": screen, "fmt": "dur", "sub": screen_sub, "tone": screen_tone, "hero": True},
                 focus_card, score_card,
                 {"label": "Blocked", "value": len(blocks), "fmt": "num", "sub": peak or "nothing tried", "tone": "warn" if blocks else "muted"}]
    elif source == "phone":
        unlocks = [pho[d].get("unlocks") for d in days if d in pho and pho[d].get("unlocks") is not None]
        top = max(apps.values(), key=lambda x: x["secs"]) if apps else None
        social = cats.get("Social", 0) + cats.get("Entertainment", 0)
        cards = [{"label": "Phone screen time", "value": screen, "fmt": "dur", "sub": screen_sub if has_phone else "phone not synced yet",
                  "tone": screen_tone, "hero": True},
                 {"label": "Unlocks", "value": sum(unlocks) if unlocks else None, "fmt": "num",
                  "sub": (f"avg {round(sum(unlocks) / max(1, len(unlocks)))} a day" if rng != "day" else "times you picked it up") if unlocks else "not tracked yet", "tone": "muted"},
                 {"label": "Social & video", "value": social, "fmt": "dur",
                  "sub": f"{round(100 * social / screen)}% of phone time" if screen else "nothing yet", "tone": "warn" if screen and social / screen > 0.5 else "muted"},
                 {"label": "Blocked on phone", "value": len(phone_blocks), "fmt": "num",
                  "sub": "sent home during focus" if phone_blocks else "nothing tried", "tone": "warn" if phone_blocks else "muted"}]
        if top:
            out_top = top["name"]  # noqa: F841 (kept simple: top app shows first in the list)
    else:
        lap_t = sum(total(d, "laptop") for d in days)
        pho_t = sum(total(d, "phone") for d in days)
        cards = [{"label": "Total screen time", "value": screen, "fmt": "dur", "sub": screen_sub, "tone": screen_tone, "hero": True},
                 {"label": "Laptop", "value": lap_t, "fmt": "dur", "sub": f"{round(100 * lap_t / screen)}% of total" if screen else "–", "tone": "muted"},
                 {"label": "Phone", "value": pho_t, "fmt": "dur", "sub": (f"{round(100 * pho_t / screen)}% of total" if screen else "–") if has_phone else "phone not synced yet", "tone": "muted"},
                 focus_card]

    out = {"range": rng, "source": source, "has_phone": has_phone, "cards": cards, "total": screen,
           "cats": sorted([{"name": k, "secs": v, "color": CAT_COLORS.get(k, "#D6CFC1")} for k, v in cats.items() if v >= 30],
                          key=lambda c: -c["secs"]),
           "apps": sorted([{"name": v["name"], "secs": v["secs"], "cat": v["cat"], "device": v["device"],
                            "color": CAT_COLORS.get(v["cat"], "#D6CFC1")} for v in apps.values() if v["secs"] >= 30],
                          key=lambda x: -x["secs"])[:12]}
    if rng == "day":
        out["hours"] = [{c: round(s) for c, s in h.items()} for h in hours]
    else:
        def split(d):
            if source == "laptop":
                f = focus_of(d)
                return {"a": round(f), "b": round(max(0, total(d) - f))}
            if source == "phone":
                return {"a": 0, "b": round(total(d))}
            return {"a": round(total(d, "laptop")), "b": round(total(d, "phone"))}
        out["days"] = [{"label": d.strftime("%a") if n == 7 else d.strftime("%d").lstrip("0"), "date": d.isoformat(),
                        **split(d), "today": d == today} for d in days]
        out["avg"] = round(screen / active_days)
    out["series"] = {"laptop": ["Focused", "Other"], "phone": ["", "Phone"], "all": ["Laptop", "Phone"]}[source]
    return out
