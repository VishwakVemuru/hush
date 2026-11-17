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
  const settings = { name: 'Alex', goal_hours: 4, idle_min: 3, custom_focus: 45, custom_break: 10, unlock: 'both', countdown_label: 'exams', countdown_date: '2027-03-01', reduce_motion: false, volume: 0.5, last_preset: [50, 10, 4], last_mode: 'soft', doh_off: false };
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
    stats: async r => {
      const hours = Array.from({ length: 24 }, (_, h) => h < 15 || h > 22 ? {} : { Study: 900 + (h % 3) * 600, Code: h % 2 ? 1200 : 300, Games: h === 21 ? 1500 : 0, Social: 200 });
      const N = r === 'week' ? 7 : 30; const days = Array.from({ length: N }, (_, i) => ({ label: r === 'week' ? ['Wed', 'Thu', 'Fri', 'Sat', 'Sun', 'Mon', 'Tue'][i] : String(i + 1), focus: 3600 + (i * 1733) % 7200, other: 7200 + (i * 977) % 9000, today: i === N - 1 }));
      return { range: r, cards: [{ label: 'Screen time', value: 18720, fmt: 'dur', sub: '↓ 38m vs avg', tone: 'good' }, { label: 'Focused', value: 9600, fmt: 'dur', sub: '↑ 22m vs avg', tone: 'good' }, { label: 'Focus score', value: 86, fmt: 'pct', sub: 'solid', tone: 'muted' }, { label: 'Blocked', value: 7, fmt: 'num', sub: 'mostly 9pm–10pm', tone: 'warn' }],
        hours, days, cats: [{ name: 'Study', secs: 8000, color: colors.Study }, { name: 'Code', secs: 5200, color: colors.Code }, { name: 'Games', secs: 1900, color: colors.Games }, { name: 'Social', secs: 1300, color: colors.Social }],
        apps: [{ name: 'VS Code', secs: 6480, cat: 'Code', color: colors.Code }, { name: 'docs.google.com', secs: 4440, cat: 'Study', color: colors.Study }, { name: 'Notion', secs: 2760, cat: 'Study', color: colors.Study }, { name: 'VALORANT', secs: 1920, cat: 'Games', color: colors.Games }, { name: 'instagram.com', secs: 900, cat: 'Social', color: colors.Social }] };
    },
    set_category: async () => true, export_csv: async () => 'C:\\Users\\you\\Downloads',
    blocklist: async () => cfg, set_app: async () => cfg, set_source: async () => cfg, add_app: async () => ({ ok: true, cfg }), remove_app: async () => cfg,
    add_site: async d => { cfg.sites.unshift({ domain: d, enabled: true }); return { ok: true, cfg }; }, set_site: async () => cfg, remove_site: async () => cfg, set_block_flag: async () => cfg,
    rescan_games: async () => ({ found: 2, cfg }), running_apps: async () => [{ exe: 'chrome.exe', name: 'Chrome' }],
    app_icons: async () => ({}), create_shortcut: async () => true,
    set_setting: async () => true, set_startup: async () => true, set_doh: async () => true, restart_admin: async () => false, open_extension_folder: async () => true, show_main: async () => true,
  };
})();
