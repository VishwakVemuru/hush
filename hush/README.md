# hush.

A calm focus timer for Windows with screen time tracking and blocking built in.

## Setup (once)

1. Install **Python 3.10+** from python.org. Tick **"Add python.exe to PATH"** during install.
2. Unzip this folder somewhere permanent, e.g. `Documents\hush`.
3. Double-click **`hush.bat`**. The first run installs pywebview, psutil, pystray and Pillow (about a minute), then hush. opens.

### Browser extension (site blocking + per-site screen time)
1. Open `brave://extensions` (or `chrome://extensions` / `edge://extensions`).
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and pick the `extension` folder inside hush.
4. In hush., go to **Blocklist → Websites**. It should say *Browser extension connected*.

### Optional: system-wide site block
Run **`hush (admin).bat`** instead. hush. then also blocks sites in every app through the Windows hosts file, and cleans that up after each session (and on the next launch if it ever crashes). If you use this, turn on **Settings → Turn off browser Secure DNS**, otherwise Chrome, Brave and Edge skip the hosts file.

### Optional: phone app (Android)
While the laptop is in focus, the phone sends the apps you pick (Instagram, Reddit…) back to the home screen. WhatsApp, Telegram and Discord are never blocked. Phone and laptop need the same Wi-Fi.
1. Install `phone\hush.apk` over USB: `adb install -r phone\hush.apk`. Android 15 blocks installing it from the browser or Files.
2. In hush. on the laptop, open **Settings → Phone** and type the 8-digit code into the phone app.
3. On the phone: App info → ⋮ → **Allow restricted settings**, then Accessibility → Downloaded apps → **hush.** → on.
4. Xiaomi/HyperOS: set hush. to **Autostart on** and **Battery saver → No restrictions** so it isn't killed.

To rebuild the phone app run `phone-app\build.ps1` (needs the Android SDK and a JDK 17).

## New in 1.2
- **Desktop and Start menu shortcut** with the hush. icon, created automatically on first launch (Settings → Desktop shortcut to redo it)
- **Proper taskbar icon** instead of Python's
- **Sound effects**: soft chimes in one tonal family for start, pause, break, last minute, blocked, task done and session complete. Quiet by default; toggle and volume in Settings
- **Real app icons** in Stats and Blocklist (pulled from each app), site favicons
- **Tabler icon set** across the UI, a first-run intro, keyboard shortcuts (Space, 1–4, Esc), click the tide for a ripple, live timer in the window title
- Rain now has droplets layered on top

## What's inside

| | |
|---|---|
| **Tide timer** | The water drains as focus time passes and refills in moss green during breaks. The digits change colour right at the waterline. |
| **Soft / Hard mode** | Soft: pause is allowed, and stopping early means typing a sentence or waiting 60s. Hard: no pause, no stop and no quitting until every session is done. It even resumes if you kill the app and reopen it. |
| **App blocking** | Auto-detects Steam, Epic, Riot and Xbox games plus launchers. You get 10 seconds to save, then blocked apps close the moment they open. |
| **Site blocking** | Through the extension: instant redirect to a calm "this can wait" page. There's a YouTube **Shorts-only** block, so YouTube stays usable for study. |
| **Screen time** | Logs the active app every second, skips idle time (fullscreen video still counts), and shows per-site time in browsers when the extension is installed. |
| **Stats** | Day, week and month views. Includes screen time, focus time, focus score and blocked attempts, an hourly chart, categories and top apps. Click a category to retag an app. |
| **Extras** | Up-next tasks, generated ambient sound (rain, waves, brown noise), daily goal, streak, countdown, mini floating timer, tray icon that drains with the timer, **Ctrl+Alt+H** global shortcut, CSV export, start with Windows. |

Closing the window keeps hush. running in the tray, so tracking continues. Use **Quit** in the tray menu to fully exit (it's disabled during Hard mode).

## Data
Everything stays on your laptop in `%LOCALAPPDATA%\hush\hush.db` (SQLite). If something misbehaves, the log is at `%LOCALAPPDATA%\hush\hush.log`.

## Honest limits
- You're the admin of your own laptop, so Task Manager, Safe Mode or editing the hosts file by hand can always get around blocks. hush. stops impulses, not determined escapes.
- Without the extension, browsers show up as just "Brave" or "Chrome" in stats (no per-site breakdown).
- Window open, minimize and close animations are handled by Windows, not hush.

## Preview the UI without Windows
Serve the `ui` folder (`python -m http.server` inside it) and open `index.html?mock`.
