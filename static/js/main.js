/* =========================================================
   FinancialOS Kenya — main.js
   Theme toggle, Chart.js global defaults, shared utilities
   ========================================================= */

// ── Theme toggle ──────────────────────────────────────────────
(function () {
  const STORAGE_KEY = 'fos_theme';
  const root = document.documentElement;
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) root.setAttribute('data-theme', saved);

  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('themeToggle');
    if (!btn) return;
    btn.addEventListener('click', () => {
      const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      localStorage.setItem(STORAGE_KEY, next);
      if (typeof updateChartTheme === 'function') updateChartTheme(next);
    });
  });
})();

// ── Chart.js global defaults ──────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (typeof Chart === 'undefined') return;

  const isDark = () => document.documentElement.getAttribute('data-theme') !== 'light';
  const gridColor  = () => isDark() ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.07)';
  const tickColor  = () => isDark() ? '#8b90a7' : '#5c6280';
  const legendColor= () => isDark() ? '#8b90a7' : '#5c6280';

  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.font.size   = 12;
  Chart.defaults.color       = tickColor();
  Chart.defaults.plugins.legend.labels.color = legendColor();
  Chart.defaults.plugins.tooltip.backgroundColor = isDark() ? '#1e2336' : '#ffffff';
  Chart.defaults.plugins.tooltip.titleColor      = isDark() ? '#e6e8f0' : '#1a2040';
  Chart.defaults.plugins.tooltip.bodyColor       = isDark() ? '#8b90a7' : '#5c6280';
  Chart.defaults.plugins.tooltip.borderColor     = isDark() ? '#2a3047' : '#dde1ee';
  Chart.defaults.plugins.tooltip.borderWidth     = 1;
  Chart.defaults.plugins.tooltip.padding         = 10;
  Chart.defaults.plugins.tooltip.cornerRadius    = 6;
  Chart.defaults.animation.duration              = 400;
});

// ── Auto-dismiss flash messages after 5s ─────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => el.remove(), 5000);
  });
});

// ── Sidebar mobile toggle ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  // On narrow screens the toggle button opens/closes
  window.toggleSidebar = () => {
    sidebar.classList.toggle('open');
    sidebar.classList.toggle('collapsed');
  };
});

// ── Utility: format KES millions ──────────────────────────────
window.fmtM = function (v) {
  if (v === null || v === undefined) return '—';
  return v >= 1000
    ? `KES ${(v / 1000).toFixed(1)}B`
    : `KES ${v.toFixed(0)}M`;
};

// ── Utility: opinion badge HTML ───────────────────────────────
window.opinionBadge = function (op) {
  if (!op) return '<span class="badge badge-neutral">—</span>';
  const map = {
    unqualified: ['badge-success',  'Clean'],
    qualified:   ['badge-warning',  'Qualified'],
    adverse:     ['badge-danger',   'Adverse'],
    disclaimer:  ['badge-critical', 'Disclaimer'],
  };
  const [cls, label] = map[op] || ['badge-neutral', op];
  return `<span class="badge ${cls}">${label}</span>`;
};
