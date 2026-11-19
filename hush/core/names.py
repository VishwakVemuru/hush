"""Friendly names, default categories and colours."""
import os

CATEGORIES = ["Study", "Code", "Games", "Social", "Entertainment", "Browsing", "Music", "Other"]
CAT_COLORS = {
    "Study": "#3E6A9E", "Code": "#8FA6C4", "Games": "#C9A15A", "Social": "#C49A8A",
    "Entertainment": "#A99BC4", "Browsing": "#B5AD9E", "Music": "#7FA7A0", "Other": "#D6CFC1",
}
DISTRACTING = {"Games", "Social", "Entertainment"}

BROWSERS = {"chrome.exe", "msedge.exe", "brave.exe", "firefox.exe", "opera.exe", "opera_gx.exe",
            "vivaldi.exe", "arc.exe", "zen.exe",
            # macOS process names
            "google chrome", "brave browser", "safari", "firefox", "microsoft edge", "opera", "arc", "vivaldi", "zen"}

PRETTY = {
    "code.exe": "VS Code", "cursor.exe": "Cursor", "devenv.exe": "Visual Studio", "pycharm64.exe": "PyCharm",
    "idea64.exe": "IntelliJ", "windowsterminal.exe": "Terminal", "wt.exe": "Terminal", "cmd.exe": "Command Prompt",
    "powershell.exe": "PowerShell", "pwsh.exe": "PowerShell", "chrome.exe": "Chrome", "msedge.exe": "Edge",
    "brave.exe": "Brave", "firefox.exe": "Firefox", "opera.exe": "Opera", "opera_gx.exe": "Opera GX",
    "explorer.exe": "File Explorer", "winword.exe": "Word", "excel.exe": "Excel", "powerpnt.exe": "PowerPoint",
    "onenote.exe": "OneNote", "notion.exe": "Notion", "obsidian.exe": "Obsidian", "acrobat.exe": "Acrobat",
    "acrord32.exe": "Acrobat Reader", "spotify.exe": "Spotify", "discord.exe": "Discord", "whatsapp.exe": "WhatsApp",
    "telegram.exe": "Telegram", "steam.exe": "Steam", "steamwebhelper.exe": "Steam",
    "epicgameslauncher.exe": "Epic Games", "riotclientux.exe": "Riot Client", "riotclientservices.exe": "Riot Client",
    "valorant-win64-shipping.exe": "Valorant", "valorant.exe": "Valorant", "leagueclient.exe": "League of Legends",
    "league of legends.exe": "League of Legends", "minecraft.exe": "Minecraft", "javaw.exe": "Java app",
    "robloxplayerbeta.exe": "Roblox", "fortniteclient-win64-shipping.exe": "Fortnite", "gta5.exe": "GTA V",
    "cs2.exe": "Counter-Strike 2", "blender.exe": "Blender", "photoshop.exe": "Photoshop", "figma.exe": "Figma",
    "claude.exe": "Claude", "chatgpt.exe": "ChatGPT", "vlc.exe": "VLC", "zoom.exe": "Zoom", "ms-teams.exe": "Teams",
    "xboxpcapp.exe": "Xbox", "battle.net.exe": "Battle.net", "eadesktop.exe": "EA app", "upc.exe": "Ubisoft Connect",
    "galaxyclient.exe": "GOG Galaxy", "python.exe": "Python", "pythonw.exe": "hush.", "taskmgr.exe": "Task Manager",
    "systemsettings.exe": "Settings", "applicationframehost.exe": "Windows app", "kicad.exe": "KiCad",
    "fusion360.exe": "Fusion 360", "xflr5.exe": "XFLR5", "matlab.exe": "MATLAB",
    # macOS process names
    "google chrome": "Chrome", "brave browser": "Brave", "safari": "Safari", "microsoft edge": "Edge",
    "code": "VS Code", "electron": "VS Code", "finder": "Finder", "terminal": "Terminal", "iterm2": "Terminal",
    "microsoft word": "Word", "microsoft excel": "Excel", "microsoft powerpoint": "PowerPoint",
    "microsoft onenote": "OneNote", "pages": "Pages", "keynote": "Keynote", "numbers": "Numbers", "preview": "Preview",
    "notes": "Notes", "xcode": "Xcode", "pycharm": "PyCharm", "steam_osx": "Steam", "minecraft": "Minecraft",
    "roblox": "Roblox", "robloxplayer": "Roblox", "messages": "Messages", "facetime": "FaceTime", "music": "Music",
    "tv": "Apple TV", "system settings": "Settings", "python": "Python", "hush": "hush.",
}

DEFAULT_CATS = {
    # apps
    "VS Code": "Code", "Cursor": "Code", "Visual Studio": "Code", "PyCharm": "Code", "IntelliJ": "Code",
    "Terminal": "Code", "Command Prompt": "Code", "PowerShell": "Code", "Python": "Code", "Blender": "Code",
    "Word": "Study", "Excel": "Study", "PowerPoint": "Study", "OneNote": "Study", "Notion": "Study",
    "Obsidian": "Study", "Acrobat": "Study", "Acrobat Reader": "Study", "Claude": "Study", "ChatGPT": "Study",
    "KiCad": "Code", "Fusion 360": "Code", "XFLR5": "Study", "MATLAB": "Study",
    "Spotify": "Music", "Discord": "Social", "WhatsApp": "Social", "Telegram": "Social", "VLC": "Entertainment",
    "Steam": "Games", "Epic Games": "Games", "Riot Client": "Games", "Valorant": "Games",
    "League of Legends": "Games", "Minecraft": "Games", "Roblox": "Games", "Fortnite": "Games", "GTA V": "Games",
    "Counter-Strike 2": "Games", "Xbox": "Games", "Battle.net": "Games", "EA app": "Games",
    "Ubisoft Connect": "Games", "GOG Galaxy": "Games",
    "Chrome": "Browsing", "Edge": "Browsing", "Brave": "Browsing", "Firefox": "Browsing", "Opera": "Browsing",
    "Opera GX": "Browsing", "Safari": "Browsing", "Pages": "Study", "Keynote": "Study", "Numbers": "Study",
    "Preview": "Study", "Notes": "Study", "Xcode": "Code", "Messages": "Social", "FaceTime": "Social",
    "Music": "Music", "Apple TV": "Entertainment",
    # sites
    "youtube.com": "Entertainment", "netflix.com": "Entertainment", "primevideo.com": "Entertainment",
    "hotstar.com": "Entertainment", "twitch.tv": "Entertainment", "jiocinema.com": "Entertainment",
    "instagram.com": "Social", "reddit.com": "Social", "x.com": "Social", "twitter.com": "Social",
    "facebook.com": "Social", "snapchat.com": "Social", "web.whatsapp.com": "Social", "discord.com": "Social",
    "docs.google.com": "Study", "drive.google.com": "Study", "classroom.google.com": "Study",
    "khanacademy.org": "Study", "wikipedia.org": "Study", "claude.ai": "Study", "chatgpt.com": "Study",
    "ncert.nic.in": "Study", "byjus.com": "Study", "notion.so": "Study", "desmos.com": "Study",
    "wolframalpha.com": "Study", "physicswallah.live": "Study", "pw.live": "Study",
    "github.com": "Code", "stackoverflow.com": "Code", "localhost": "Code", "vercel.com": "Code",
    "open.spotify.com": "Music", "music.youtube.com": "Music", "mail.google.com": "Other",
}

LAUNCHERS = [
    ("steam.exe", "Steam"), ("epicgameslauncher.exe", "Epic Games Launcher"),
    ("riotclientservices.exe", "Riot Client"), ("riotclientux.exe", "Riot Client UI"),
    ("battle.net.exe", "Battle.net"), ("eadesktop.exe", "EA app"), ("upc.exe", "Ubisoft Connect"),
    ("galaxyclient.exe", "GOG Galaxy"), ("xboxpcapp.exe", "Xbox app"), ("robloxplayerbeta.exe", "Roblox"),
    ("minecraftlauncher.exe", "Minecraft Launcher"),
    # macOS
    ("steam_osx", "Steam"), ("epicgameslauncher", "Epic Games Launcher"), ("battle.net", "Battle.net"),
    ("robloxplayer", "Roblox"), ("minecraft", "Minecraft Launcher"),
]
SUGGESTED_OFF = [("discord.exe", "Discord"), ("spotify.exe", "Spotify"), ("whatsapp.exe", "WhatsApp")]

DEFAULT_SITES = [
    ("instagram.com", True), ("reddit.com", True), ("x.com", True), ("twitter.com", True),
    ("facebook.com", True), ("netflix.com", True), ("primevideo.com", True), ("hotstar.com", True),
    ("twitch.tv", True), ("youtube.com", False),
]

# processes we will never kill, even if someone adds them
PROTECTED = {"explorer.exe", "svchost.exe", "csrss.exe", "winlogon.exe", "lsass.exe", "dwm.exe", "services.exe",
             "smss.exe", "wininit.exe", "system", "python.exe", "pythonw.exe", "taskmgr.exe", "msedgewebview2.exe",
             # macOS
             "finder", "dock", "loginwindow", "windowserver", "systemuiserver", "python", "python3", "hush",
             "activity monitor", "system settings", "kernel_task", "launchd"}


def pretty(exe_name):
    if not exe_name:
        return "Unknown"
    k = exe_name.lower()
    if k in PRETTY:
        return PRETTY[k]
    stem = os.path.splitext(exe_name)[0].replace("_", " ").replace("-", " ")
    return stem[:1].upper() + stem[1:]


def site_key(domain):
    """Collapse subdomains to something readable: www.youtube.com -> youtube.com, keep docs.google.com."""
    if not domain:
        return None
    d = domain.lower().strip(".")
    if d.startswith("www."):
        d = d[4:]
    if d in DEFAULT_CATS:
        return d
    parts = d.split(".")
    keep_sub = {"docs", "drive", "mail", "classroom", "music", "open", "web"}
    if len(parts) > 2 and parts[0] in keep_sub:
        return ".".join(parts[-3:])
    if len(parts) > 2 and len(parts[-1]) == 2 and parts[-2] in ("co", "com", "ac", "gov", "nic", "org"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])
