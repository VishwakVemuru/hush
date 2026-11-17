/* Browser-only mock of the Python API, for previewing the UI without Windows. Open index.html?mock */
(() => {
  const now = () => Date.now() / 1000;
  let st = { phase: 'idle', label: '', mode: 'soft', paused: false, left: 0, ends_at: 0, total: 0, index: 1, sessions: 4, focus_min: 50, break_min: 10, blocked: 0, tracked: 0, distracted: 0, grace: 0, summary: null };
  let tasks = [{ id: 1, text: 'Maths · Ch 8 trig', done: 1 }, { id: 2, text: 'Physics · Ch 10 light', done: 0 }, { id: 3, text: 'SS · Nationalism in India', done: 0 }];
  const colors = { Study: '#3E6A9E', Code: '#8FA6C4', Games: '#C9A15A', Social: '#C49A8A', Entertainment: '#A99BC4', Browsing: '#B5AD9E', Music: '#7FA7A0', Other: '#D6CFC1' };
  const cfg = { apps: [{ id: 'path:v', kind: 'path', value: 'C:\\Riot Games\\VALORANT', name: 'VALORANT', source: 'game', store: 'Riot', enabled: true }, { id: 'path:m', kind: 'path', value: 'D:\\Steam\\steamapps\\common\\Rocket League', name: 'Rocket League', source: 'game', store: 'Steam', enabled: true },
    { id: 'exe:steam.exe', kind: 'exe', value: 'steam.exe', name: 'Steam', source: 'launcher', enabled: true }, { id: 'exe:epicgameslauncher.exe', kind: 'exe', value: 'epicgameslauncher.exe', name: 'Epic Games Launcher', source: 'launcher', enabled: true },
    { id: 'exe:discord.exe', kind: 'exe', value: 'discord.exe', name: 'Discord', source: 'custom', enabled: false }],
    sites: [{ domain: 'instagram.com', enabled: true }, { domain: 'reddit.com', enabled: true }, { domain: 'x.com', enabled: true }, { domain: 'youtube.com', enabled: false }], shorts: true, hosts: true, admin: false, ext: true };
  const settings = { name: 'Alex', goal_hours: 4, idle_min: 3, custom_focus: 45, custom_break: 10, unlock: 'both', countdown_label: 'exams', countdown_date: '2027-03-01', reduce_motion: false, volume: 0.5, last_preset: [50, 10, 4], last_mode: 'soft', doh_off: false, onboarded: true, mini_mode: 'minimized' };
  const left = () => st.phase === 'idle' ? 0 : st.paused ? st.left : Math.max(0, st.ends_at - now());
  window.MockApi = {
    boot: async () => ({ settings, categories: Object.keys(colors), colors, phrase: 'i am choosing to stop focusing right now', admin: false, startup: false, last_event: 0 }),
    poll: async () => ({ state: { ...st, left: left(), now: now() }, events: [], now_using: { app: 'VS Code', site: null, category: 'Code' }, ext: true }),
    overview: async () => ({ streak: 12, dots: [2, 2, 1, 2, 2, 1, 0], focus_today: 9600, goal: 14400 }),
    start_focus: async o => { st = { ...st, ...o, phase: 'focus', index: 1, ends_at: now() + o.focus_min * 60, total: o.focus_min * 60, grace: 0 }; return { ok: true }; },
    pause: async () => { st.left = left(); st.paused = true; return { ok: true }; },
    resume: async () => { st.ends_at = now() + st.left; st.paused = false; return { ok: true }; },
    skip: async () => ({ ok: true }), request_stop: async () => 'tok', stop: async () => { st.phase = 'idle'; return { ok: true }; }, clear_summary: async () => true,
    tasks: async () => tasks, add_task: async t => { tasks.push({ id: Date.now(), text: t, done: 0 }); return tasks; },
    toggle_task: async id => { tasks.forEach(t => { if (t.id == id) t.done = 1 - t.done; }); return tasks; }, delete_task: async id => (tasks = tasks.filter(t => t.id != id)), clear_done: async () => (tasks = tasks.filter(t => !t.done)),
    stats: async (r, src = 'laptop') => {
      const ph = src === 'phone', all = src === 'all';
      const hours = Array.from({ length: 24 }, (_, h) => h < 9 || h > 22 ? {} : ph ? { Social: 600 + (h % 4) * 300, Entertainment: h > 19 ? 900 : 0 } : { Study: 900 + (h % 3) * 600, Code: h % 2 ? 1200 : 300, Games: h === 21 ? 1500 : 0, Social: 200 });
      const N = r === 'week' ? 7 : 30; const days = Array.from({ length: N }, (_, i) => ({ label: r === 'week' ? ['Wed', 'Thu', 'Fri', 'Sat', 'Sun', 'Mon', 'Tue'][i] : String(i + 1), a: ph ? 0 : 3600 + (i * 1733) % 7200, b: 4200 + (i * 977) % 6000, today: i === N - 1 }));
      const lapApps = [{ name: 'VS Code', secs: 6480, cat: 'Code', color: colors.Code, device: 'laptop' }, { name: 'Brave', secs: 4440, cat: 'Browsing', color: '#B5AD9E', device: 'laptop' }, { name: 'Notion', secs: 2760, cat: 'Study', color: colors.Study, device: 'laptop' }, { name: 'VALORANT', secs: 1920, cat: 'Games', color: colors.Games, device: 'laptop' }];
      const phApps = [{ name: 'Instagram', secs: 3100, cat: 'Social', color: colors.Social, device: 'phone' }, { name: 'WhatsApp', secs: 2200, cat: 'Social', color: colors.Social, device: 'phone' }, { name: 'YouTube', secs: 1500, cat: 'Entertainment', color: '#A99BC4', device: 'phone' }];
      const apps = ph ? phApps : all ? [...lapApps, ...phApps].sort((x, y) => y.secs - x.secs) : lapApps;
      const total = apps.reduce((a, b) => a + b.secs, 0);
      const cards = ph ? [{ label: 'Phone screen time', value: total, fmt: 'dur', sub: '↓ 22m vs avg', tone: 'good' }, { label: 'Unlocks', value: 58, fmt: 'num', sub: 'times you picked it up', tone: 'muted' }, { label: 'Social & video', value: 6800, fmt: 'dur', sub: '100% of phone time', tone: 'warn' }, { label: 'Blocked on phone', value: 4, fmt: 'num', sub: 'sent home during focus', tone: 'warn' }]
        : all ? [{ label: 'Total screen time', value: total, fmt: 'dur', sub: '↑ 40m vs avg', tone: 'muted' }, { label: 'Laptop', value: 15600, fmt: 'dur', sub: '70% of total', tone: 'muted' }, { label: 'Phone', value: 6800, fmt: 'dur', sub: '30% of total', tone: 'muted' }, { label: 'Focused', value: 9600, fmt: 'dur', sub: 'on the laptop', tone: 'good' }]
        : [{ label: 'Screen time', value: total, fmt: 'dur', sub: '↓ 38m vs avg', tone: 'good' }, { label: 'Focused', value: 9600, fmt: 'dur', sub: 'on the laptop', tone: 'good' }, { label: 'Focus score', value: 86, fmt: 'pct', sub: 'solid', tone: 'muted' }, { label: 'Blocked', value: 7, fmt: 'num', sub: 'mostly 9pm–10pm', tone: 'warn' }];
      const cats = ph ? [{ name: 'Social', secs: 5300, color: colors.Social }, { name: 'Entertainment', secs: 1500, color: '#A99BC4' }] : [{ name: 'Code', secs: 6480, color: colors.Code }, { name: 'Browsing', secs: 4440, color: '#B5AD9E' }, { name: 'Study', secs: 2760, color: colors.Study }, { name: 'Games', secs: 1920, color: colors.Games }].concat(all ? [{ name: 'Social', secs: 5300, color: colors.Social }] : []);
      return { range: r, source: src, has_phone: true, total, cards, hours, days, avg: 9800, series: ph ? ['', 'Phone'] : all ? ['Laptop', 'Phone'] : ['Focused', 'Other'], cats, apps };
    },
    cloud_refresh: async () => ({ changed: false, status: { enabled: true, ok: true, last_ok: Date.now() / 1000 - 120, phone_days: 6 } }),
    save_image: async () => 'C:\\Users\\you\\Downloads\\hush.png', set_fullscreen: async () => true,
    phone_link: async () => ({ ip: '192.168.1.20', port: 47322, code: '12345678', connected: true, phone: 'Pixel', running: true }),
    set_category: async () => true, export_csv: async () => 'C:\\Users\\you\\Downloads',
    blocklist: async () => cfg, set_app: async () => cfg, set_source: async () => cfg, add_app: async () => ({ ok: true, cfg }), remove_app: async () => cfg,
    add_site: async d => { cfg.sites.unshift({ domain: d, enabled: true }); return { ok: true, cfg }; }, set_site: async () => cfg, remove_site: async () => cfg, set_block_flag: async () => cfg,
    rescan_games: async () => ({ found: 2, cfg }), running_apps: async () => [{ exe: 'chrome.exe', name: 'Chrome' }],
    app_icons: async () => ({}), create_shortcut: async () => true,
    set_setting: async () => true, set_startup: async () => true, set_doh: async () => true, restart_admin: async () => false, open_extension_folder: async () => true, show_main: async () => true,
  };
})();
