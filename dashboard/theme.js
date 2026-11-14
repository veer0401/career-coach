// Theme picker shared by index.html and practice.html. Loaded at the end of <body>; replaces the old light/dark toggle.
(function () {
  const THEMES = [
    {id: 'mono',       name: 'Mono',       mode: 'dark',  sw: ['#0a0a0a', '#ededed']},
    {id: 'midnight',   name: 'Midnight',   mode: 'dark',  sw: ['#0b1020', '#8ea2ff']},
    {id: 'forest',     name: 'Forest',     mode: 'dark',  sw: ['#0b120e', '#7fd1a8']},
    {id: 'mono-light', name: 'Mono light', mode: 'light', sw: ['#fafafa', '#111111']},
    {id: 'paper',      name: 'Paper',      mode: 'light', sw: ['#f5f0e6', '#b4532a']},
  ];
  const root = document.documentElement;
  const get = () => { try { return localStorage.getItem('coach.palette') || 'mono'; } catch (e) { return 'mono'; } };
  function apply(id) {
    const t = THEMES.find(x => x.id === id) || THEMES[0];
    root.dataset.theme = t.mode; root.dataset.palette = t.id;
    try { localStorage.setItem('coach.palette', t.id); localStorage.setItem('coach.theme', t.mode); } catch (e) {}
    document.querySelectorAll('.thm-opt').forEach(o => o.setAttribute('aria-checked', String(o.dataset.id === t.id)));
    if (typeof cm !== 'undefined' && cm && cm.refresh) cm.refresh();
  }
  const btn = document.getElementById('themeBtn');
  if (!btn) return;
  const menu = document.createElement('div');
  menu.className = 'thm-menu'; menu.hidden = true; menu.setAttribute('role', 'menu');
  menu.innerHTML = '<div class="thm-h">Theme</div>' + THEMES.map(t =>
    `<button class="thm-opt" role="menuitemradio" data-id="${t.id}"><span class="thm-sw" style="background:${t.sw[0]}"><i style="background:${t.sw[1]}"></i></span>${t.name}<span class="thm-ck">✓</span></button>`).join('');
  document.body.appendChild(menu);
  function place() {
    const r = btn.getBoundingClientRect();
    menu.style.top = (r.bottom + 8) + 'px';
    menu.style.right = Math.max(8, window.innerWidth - r.right) + 'px';
  }
  btn.title = 'Theme';
  btn.onclick = e => { e.stopPropagation(); menu.hidden = !menu.hidden; if (!menu.hidden) place(); };
  menu.addEventListener('click', e => { const o = e.target.closest('.thm-opt'); if (o) { apply(o.dataset.id); menu.hidden = true; } });
  document.addEventListener('click', e => { if (!menu.hidden && !menu.contains(e.target)) menu.hidden = true; });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') menu.hidden = true; });
  window.addEventListener('resize', () => { if (!menu.hidden) place(); });
  apply(get());
})();
