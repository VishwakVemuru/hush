"""Turns raw usage chunks into the numbers the Stats screen shows."""
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from .names import CAT_COLORS


def bounds(d):
    a = datetime.combine(d, datetime.min.time()).timestamp()
    return a, a + 86400


def _split(rows, a, b, categorize):
    """Yield (date, hour, key, category, seconds) for each usage row clipped to [a,b)."""
    for r in rows:
        s, e = max(r["start"], a), min(r["end"], b)
        if e <= s:
            continue
        # websites are not shown in screen time; older rows that recorded a site count as their browser
        key = r["app"]
        cat = categorize(r["app"], r["exe"], None)
        t = s
        while t < e:
            dt = datetime.fromtimestamp(t)
            nxt = datetime(dt.year, dt.month, dt.day, dt.hour).timestamp() + 3600
            chunk = min(e, nxt) - t
            yield dt.date(), dt.hour, key, cat, chunk
            t += chunk


def _focus_by_day(db, a, b):
    out = defaultdict(lambda: {"tracked": 0.0, "distracted": 0.0})
    for f in db.focus_between(a, b):
        d = datetime.fromtimestamp(f["start"]).date()
        out[d]["tracked"] += f["tracked"] or 0
        out[d]["distracted"] += f["distracted"] or 0
    return out


def _fmt_delta(v, avg):
    diff = v - avg
    m = round(abs(diff) / 60)
    if m < 1:
        return "same as avg"
    h, mm = divmod(m, 60)
    txt = f"{h}h {mm}m" if h else f"{mm}m"
    return ("↑ " if diff > 0 else "↓ ") + txt + " vs avg"


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


def compute(db, rng, categorize):
    today = date.today()
    n = {"day": 1, "week": 7, "month": 30}.get(rng, 1)
    first = today - timedelta(days=n - 1)
    hist_first = first - timedelta(days=7) if rng == "day" else first
    a, _ = bounds(hist_first)
    _, b = bounds(today)
    ra, _ = bounds(first)
    rows = db.usage_between(a, b)

    per_day = defaultdict(float)
    hours = [defaultdict(float) for _ in range(24)]
    cats = defaultdict(float)
    apps = defaultdict(lambda: {"secs": 0.0, "cat": "Other"})
    for d, h, key, cat, secs in _split(rows, a, b, categorize):
        per_day[d] += secs
        if d < first:
            continue
        cats[cat] += secs
        apps[key]["secs"] += secs
        apps[key]["cat"] = cat
        if rng == "day":
            hours[h][cat] += secs

    fb = _focus_by_day(db, a, b)
    blocks = db.events_between(ra, b, "block")

    def focus_of(d):
        v = fb.get(d)
        return max(0, v["tracked"] - v["distracted"]) if v else 0

    days = [first + timedelta(days=i) for i in range(n)]
    screen = sum(per_day[d] for d in days)
    focus = sum(focus_of(d) for d in days)
    tracked = sum(fb[d]["tracked"] for d in days if d in fb)
    distracted = sum(fb[d]["distracted"] for d in days if d in fb)
    score = round(100 * (1 - distracted / tracked)) if tracked else None

    cards = []
    if rng == "day":
        prev = [today - timedelta(days=i) for i in range(1, 8)]
        prev_s = [per_day[d] for d in prev if per_day[d] > 0]
        prev_f = [focus_of(d) for d in prev if per_day[d] > 0]
        avg_s = sum(prev_s) / len(prev_s) if prev_s else None
        avg_f = sum(prev_f) / len(prev_f) if prev_f else None
        peak = None
        if blocks:
            hc = defaultdict(int)
            for e in blocks:
                hc[datetime.fromtimestamp(e["ts"]).hour] += 1
            h = max(hc, key=hc.get)
            fmt = lambda x: f"{(x % 12) or 12}{'am' if x < 12 else 'pm'}"
            peak = f"mostly {fmt(h)}–{fmt((h + 1) % 24)}"
        cards = [
            {"label": "Screen time", "value": screen, "fmt": "dur",
             "sub": _fmt_delta(screen, avg_s) if avg_s else "first day tracked", "tone": "good" if avg_s and screen <= avg_s else "muted"},
            {"label": "Focused", "value": focus, "fmt": "dur",
             "sub": _fmt_delta(focus, avg_f) if avg_f is not None and avg_s else "keep going", "tone": "good" if avg_f is not None and focus >= avg_f else "muted"},
            {"label": "Focus score", "value": score, "fmt": "pct", "sub": "no sessions yet" if score is None else
             ("excellent" if score >= 90 else "solid" if score >= 75 else "room to grow"), "tone": "muted"},
            {"label": "Blocked", "value": len(blocks), "fmt": "num", "sub": peak or "nothing tried", "tone": "warn" if blocks else "muted"},
        ]
    else:
        active_days = max(1, sum(1 for d in days if per_day[d] > 0))
        cards = [
            {"label": "Screen time", "value": screen, "fmt": "dur", "sub": f"avg {round(screen / active_days / 60)}m / day", "tone": "muted"},
            {"label": "Focused", "value": focus, "fmt": "dur", "sub": f"avg {round(focus / active_days / 60)}m / day", "tone": "muted"},
            {"label": "Focus score", "value": score, "fmt": "pct", "sub": "across all sessions", "tone": "muted"},
            {"label": "Blocked", "value": len(blocks), "fmt": "num", "sub": f"{len(blocks) / n:.1f} per day", "tone": "warn" if blocks else "muted"},
        ]

    out = {"range": rng, "cards": cards,
           "cats": sorted([{"name": k, "secs": v, "color": CAT_COLORS.get(k, "#D6CFC1")} for k, v in cats.items() if v >= 30],
                          key=lambda c: -c["secs"]),
           "apps": sorted([{"name": k, "secs": v["secs"], "cat": v["cat"], "color": CAT_COLORS.get(v["cat"], "#D6CFC1")}
                           for k, v in apps.items() if v["secs"] >= 30], key=lambda x: -x["secs"])[:8]}
    if rng == "day":
        out["hours"] = [{c: round(s) for c, s in h.items()} for h in hours]
    else:
        out["days"] = [{"label": d.strftime("%a") if n == 7 else d.strftime("%d").lstrip("0"),
                        "focus": round(focus_of(d)), "other": round(max(0, per_day[d] - focus_of(d))),
                        "today": d == today} for d in days]
    return out
