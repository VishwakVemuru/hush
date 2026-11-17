"""System tray icon whose waves fill/drain with the timer."""
import math

from PIL import Image, ImageDraw

try:
    import pystray
except Exception:  # pragma: no cover
    pystray = None

BLUE, MOSS, CREAM, LIGHT = (62, 106, 158, 255), (94, 138, 90, 255), (243, 239, 231, 255), (143, 166, 196, 255)


def make_icon(level=1.0, color=BLUE, size=64):
    """Rounded square with water at `level` (0..1) and two waves."""
    S = size * 4
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad, r = int(S * 0.06), int(S * 0.26)
    d.rounded_rectangle([pad, pad, S - pad, S - pad], r, fill=CREAM)
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([pad, pad, S - pad, S - pad], r, fill=255)
    water = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    wd = ImageDraw.Draw(water)
    top = pad + (S - 2 * pad) * (1 - max(0.0, min(1.0, level)))
    pts = [(x, top + S * 0.03 * math.sin(x / S * 2 * math.pi * 1.5)) for x in range(0, S + 1, 4)]
    wd.polygon(pts + [(S, S), (0, S)], fill=color)
    im.alpha_composite(Image.composite(water, Image.new("RGBA", (S, S)), mask))
    d.rounded_rectangle([pad, pad, S - pad, S - pad], r, outline=color, width=int(S * 0.035))
    return im.resize((size, size), Image.LANCZOS)


class Tray:
    def __init__(self, on_show, on_toggle, on_quit, can_quit, toggle_label):
        self.icon = None
        if pystray is None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Open hush.", lambda i, it: on_show(), default=True),
            pystray.MenuItem(lambda it: toggle_label(), lambda i, it: on_toggle()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda i, it: on_quit(), enabled=lambda it: can_quit()),
        )
        self.icon = pystray.Icon("hush", make_icon(1.0), "hush.", menu)
        self._last = None

    def start(self):
        if self.icon:
            self.icon.run_detached()

    def notify(self, text, title="hush."):
        if self.icon:
            self.icon.notify(text, title)

    def update(self, state):
        if not self.icon:
            return
        ph = state["phase"]
        if ph == "idle":
            key, level, color, tip = ("idle",), 1.0, BLUE, "hush. · ready"
        else:
            frac = state["left"] / state["total"] if state["total"] else 0
            level = frac if ph == "focus" else 1 - frac
            color = BLUE if ph == "focus" else MOSS
            m = int(state["left"] // 60)
            tip = f"hush. · {'paused · ' if state['paused'] else ''}{m} min {'focus' if ph == 'focus' else 'break'} left"
            key = (ph, round(level * 12))
        try:
            if key != self._last:
                self._last = key
                self.icon.icon = make_icon(level, color)
            self.icon.title = tip
            self.icon.update_menu()
        except Exception:
            pass

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
