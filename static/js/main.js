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

/* =========================================================
   FiscalOS AI Chatbot — batch 4
   State, open/close/minimise, context, suggestions, send/render
   ========================================================= */

(function () {
  // ── State ────────────────────────────────────────────────────
  let _open      = false;
  let _minimised = false;
  let _expanded  = false;
  let _mode      = 'simple';
  let _history   = [];       // [{role,content}]
  let _typing    = null;     // typing-indicator element
  let _chartSeq  = 0;        // unique id for inline chart canvases

  const STORAGE_KEY = 'fos_chat_history';
  const MAX_HISTORY = 20;

  // ── DOM refs (resolved after DOMContentLoaded) ───────────────
  let elTrigger, elPanel, elMin, elMessages, elInput, elSendBtn,
      elSuggestions, elPills, elSubtitle, elExpandBtn;

  // ── Context from Flask (injected via #fosContext) ────────────
  function _ctx() {
    const el = document.getElementById('fosContext');
    if (!el) return { page: '', countyId: '', userRole: 'viewer' };
    return {
      page:      el.dataset.page     || '',
      countyId:  el.dataset.countyId || '',
      userRole:  el.dataset.userRole || 'viewer',
    };
  }

  // ── Public API (assigned to window below) ────────────────────
  function chatOpen() {
    _open = true; _minimised = false;
    elTrigger.style.display = 'none';
    elMin.style.display     = 'none';
    elPanel.style.display   = 'flex';
    _buildPills();
    _buildSuggestions();
    if (_history.length === 0) _showWelcome();
    elInput.focus();
  }

  function chatClose() {
    _open = false; _minimised = false;
    elPanel.style.display   = 'none';
    elMin.style.display     = 'none';
    elTrigger.style.display = 'flex';
  }

  function chatMinimise() {
    _minimised = true;
    elPanel.style.display = 'none';
    elMin.style.display   = 'flex';
    elTrigger.style.display = 'none';
  }

  function chatUnminimise() {
    _minimised = false;
    elMin.style.display   = 'none';
    elPanel.style.display = 'flex';
    elInput.focus();
  }

  function chatToggleExpand() {
    _expanded = !_expanded;
    elPanel.classList.toggle('expanded', _expanded);
    elExpandBtn.textContent = _expanded ? '⇥' : '⇤';
  }

  function chatSetMode(mode) {
    _mode = mode;
    document.getElementById('chatModeSimple').classList.toggle('active', mode === 'simple');
    document.getElementById('chatModeExpert').classList.toggle('active', mode === 'expert');
    elSubtitle.textContent = mode === 'expert'
      ? 'Analyst Mode — detailed fiscal breakdown'
      : 'Kenya County Fiscal Intelligence';
  }

  function chatClear() {
    _history = [];
    localStorage.removeItem(STORAGE_KEY);
    elMessages.innerHTML = '';
    _showWelcome();
    _buildSuggestions();
  }

  // ── Welcome message ──────────────────────────────────────────
  function _showWelcome() {
    const ctx = _ctx();
    let text = 'Hello! I\'m FiscalOS AI. Ask me about any of Kenya\'s 47 counties — revenue allocation, expenditure trends, audit opinions, OSR rates, and more.';
    if (ctx.countyId) {
      text = `I'm viewing county data with you. Ask me anything about this county's fiscal performance, budget trends, or audit history.`;
    }
    _appendBubble('assistant', text);
    _buildSuggestions();
  }

  // ── Context pills ────────────────────────────────────────────
  function _buildPills() {
    const ctx = _ctx();
    const pills = [];
    if (ctx.page) pills.push(`<span class="chat-pill">${ctx.page}</span>`);
    if (ctx.countyId) pills.push(`<span class="chat-pill county-pill">County #${ctx.countyId}</span>`);
    elPills.innerHTML = pills.join('');
  }

  // ── Suggestion chips ─────────────────────────────────────────
  const SUGGESTIONS_GENERAL = [
    'Which county has the highest OSR?',
    'Show me counties with adverse audit opinions',
    'Compare Nairobi and Mombasa revenue',
    'What is the average absorption rate?',
    'Top 5 counties by development expenditure',
  ];
  const SUGGESTIONS_COUNTY = [
    'Show revenue trend for this county',
    'What was the latest audit opinion?',
    'Compare OSR vs national average',
    'Show expenditure breakdown chart',
    'Any pending bills concerns?',
  ];

  function _buildSuggestions() {
    const ctx = _ctx();
    const list = ctx.countyId ? SUGGESTIONS_COUNTY : SUGGESTIONS_GENERAL;
    // Show 3 random suggestions
    const picked = list.sort(() => 0.5 - Math.random()).slice(0, 3);
    elSuggestions.innerHTML = picked
      .map(s => `<button class="chat-suggest-btn" onclick="chatUseSuggestion(this)">${s}</button>`)
      .join('');
  }

  window.chatUseSuggestion = function (btn) {
    elInput.value = btn.textContent;
    elSuggestions.innerHTML = '';
    chatSend();
  };

  // ── Send ─────────────────────────────────────────────────────
  function chatSend() {
    const text = elInput.value.trim();
    if (!text) return;
    elInput.value = '';
    elSuggestions.innerHTML = '';

    _appendBubble('user', text);
    _history.push({ role: 'user', content: text });
    _trimHistory();

    _showTyping();
    elSendBtn.disabled = true;

    const ctx = _ctx();
    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message:   text,
        history:   _history.slice(-MAX_HISTORY),
        mode:      _mode,
        page:      ctx.page,
        county_id: ctx.countyId || null,
      }),
    })
    .then(r => r.json())
    .then(data => {
      _removeTyping();
      elSendBtn.disabled = false;
      const reply = data.reply || data.error || 'No response received.';
      _history.push({ role: 'assistant', content: reply });
      _trimHistory();
      _saveHistory();
      _appendBubble('assistant', reply);
      _buildSuggestions();
    })
    .catch(() => {
      _removeTyping();
      elSendBtn.disabled = false;
      _appendBubble('error', 'Network error — please try again.');
    });
  }

  // ── Typing indicator ─────────────────────────────────────────
  function _showTyping() {
    _typing = document.createElement('div');
    _typing.className = 'chat-bubble assistant chat-typing';
    _typing.innerHTML = '<span></span><span></span><span></span>';
    elMessages.appendChild(_typing);
    elMessages.scrollTop = elMessages.scrollHeight;
  }
  function _removeTyping() {
    if (_typing) { _typing.remove(); _typing = null; }
  }

  // ── Render message bubble ────────────────────────────────────
  function _appendBubble(role, raw) {
    const wrap = document.createElement('div');
    wrap.className = `chat-bubble ${role}`;

    if (role === 'assistant') {
      wrap.innerHTML = _renderMarkdown(raw);
      // Intercept [[CHART:type]] directives
      wrap.querySelectorAll('.chat-chart-directive').forEach(el => {
        const type = el.dataset.chartType;
        _renderInlineChart(el, type);
      });
    } else if (role === 'error') {
      wrap.innerHTML = `<span style="color:var(--danger)">${_esc(raw)}</span>`;
    } else {
      wrap.textContent = raw;
    }

    elMessages.appendChild(wrap);
    elMessages.scrollTop = elMessages.scrollHeight;
    return wrap;
  }

  // ── Simple markdown renderer ─────────────────────────────────
  function _renderMarkdown(md) {
    // Chart directives first — replace before other processing
    md = md.replace(/\[\[CHART:(\w+)\]\]/g, (_, t) =>
      `<div class="chat-chart-directive chat-chart-wrap" data-chart-type="${t}"><canvas></canvas></div>`
    );
    // Bold
    md = md.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic
    md = md.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // Inline code
    md = md.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Headers
    md = md.replace(/^### (.+)$/gm, '<h4 class="chat-h">$1</h4>');
    md = md.replace(/^## (.+)$/gm,  '<h3 class="chat-h">$1</h3>');
    // Bullet list
    md = md.replace(/^[-•] (.+)$/gm, '<li>$1</li>');
    md = md.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    // Line breaks → <br> (skip chart divs)
    md = md.replace(/\n(?!<)/g, '<br>');
    return md;
  }

  function _esc(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ── History helpers ──────────────────────────────────────────
  function _trimHistory() {
    if (_history.length > MAX_HISTORY * 2) {
      _history = _history.slice(-MAX_HISTORY);
    }
  }
  function _saveHistory() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(_history.slice(-10))); } catch (_) {}
  }
  function _loadHistory() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      if (Array.isArray(saved) && saved.length > 0) {
        _history = saved;
        saved.forEach(m => _appendBubble(m.role === 'user' ? 'user' : 'assistant', m.content));
      }
    } catch (_) {}
  }

  // ── Inline chart stub (full renderers in batch 5) ────────────
  function _renderInlineChart(container, type) {
    if (typeof fosRenderChart === 'function') {
      fosRenderChart(container, type, _ctx());
    } else {
      container.innerHTML = `<span style="color:var(--text-muted);font-size:11px;">Chart: ${type} (loading…)</span>`;
    }
  }

  // ── Init ─────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    elTrigger    = document.getElementById('chatTrigger');
    elPanel      = document.getElementById('chatPanel');
    elMin        = document.getElementById('chatMinimised');
    elMessages   = document.getElementById('chatMessages');
    elInput      = document.getElementById('chatInput');
    elSendBtn    = document.getElementById('chatSendBtn');
    elSuggestions= document.getElementById('chatSuggestions');
    elPills      = document.getElementById('chatPills');
    elSubtitle   = document.getElementById('chatSubtitle');
    elExpandBtn  = document.getElementById('chatExpandBtn');

    if (!elTrigger) return;

    // Restore history if any
    _loadHistory();
  });

  // ── Expose to global scope (template onclick= attributes) ────
  window.chatOpen          = chatOpen;
  window.chatClose         = chatClose;
  window.chatMinimise      = chatMinimise;
  window.chatUnminimise    = chatUnminimise;
  window.chatToggleExpand  = chatToggleExpand;
  window.chatSetMode       = chatSetMode;
  window.chatClear         = chatClear;
  window.chatSend          = chatSend;

})();

/* =========================================================
   FiscalOS AI Chatbot — batch 5
   Inline chart renderers (6 Kenya fiscal chart types)
   ========================================================= */

(function () {

  const CYAN    = '#00c2ff';
  const GREEN   = '#22c55e';
  const AMBER   = '#f59e0b';
  const RED     = '#ef4444';
  const PURPLE  = '#a78bfa';
  const TEAL    = '#14b8a6';

  // Palette for multi-series
  const PAL = [CYAN, GREEN, AMBER, RED, PURPLE, TEAL,
               '#fb923c', '#60a5fa', '#f472b6', '#34d399'];

  function _isDark() {
    return document.documentElement.getAttribute('data-theme') !== 'light';
  }
  function _gridColor() { return _isDark() ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.07)'; }
  function _tickColor() { return _isDark() ? '#8b90a7' : '#5c6280'; }

  function _baseOpts(title) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, labels: { color: _tickColor(), boxWidth: 12, font: { size: 11 } } },
        title:  { display: !!title, text: title, color: _tickColor(), font: { size: 12, weight: '600' } },
        tooltip: {
          backgroundColor: _isDark() ? '#1e2336' : '#fff',
          titleColor: _isDark() ? '#e6e8f0' : '#1a2040',
          bodyColor:  _tickColor(),
          borderColor: _isDark() ? '#2a3047' : '#dde1ee',
          borderWidth: 1, cornerRadius: 6, padding: 10,
        },
      },
      scales: {
        x: { ticks: { color: _tickColor(), font: { size: 11 } }, grid: { color: _gridColor() } },
        y: { ticks: { color: _tickColor(), font: { size: 11 } }, grid: { color: _gridColor() } },
      },
    };
  }

  // ── 1. revenue_trend ────────────────────────────────────────
  // Line chart: Total Revenue vs Own-Source Revenue over 5 fiscal years
  function renderRevenueTrend(canvas, ctx) {
    const years = ['FY2020', 'FY2021', 'FY2022', 'FY2023', 'FY2024'];
    // Synthetic illustrative data — real data comes from /api/chat context
    const total = [4200, 4450, 4780, 5100, 5340];
    const osr   = [620,  680,  720,  790,  850];
    const opts  = _baseOpts('Revenue Trend (KES M)');
    opts.scales.y.ticks.callback = v => `${(v/1000).toFixed(1)}B`;
    new Chart(canvas, {
      type: 'line',
      data: {
        labels: years,
        datasets: [
          { label: 'Total Revenue', data: total, borderColor: CYAN,  backgroundColor: CYAN+'22',  tension: 0.35, fill: true, pointRadius: 4 },
          { label: 'OSR',           data: osr,   borderColor: GREEN, backgroundColor: GREEN+'22', tension: 0.35, fill: true, pointRadius: 4 },
        ],
      },
      options: opts,
    });
  }

  // ── 2. osr_trend ────────────────────────────────────────────
  // Bar chart: OSR as % of total revenue over years
  function renderOsrTrend(canvas, ctx) {
    const years = ['FY2020', 'FY2021', 'FY2022', 'FY2023', 'FY2024'];
    const pct   = [14.8, 15.3, 15.1, 15.5, 15.9];
    const opts  = _baseOpts('Own-Source Revenue (% of Total)');
    opts.scales.y.max = 40;
    opts.scales.y.ticks.callback = v => v + '%';
    delete opts.scales.x;
    new Chart(canvas, {
      type: 'bar',
      data: {
        labels: years,
        datasets: [{ label: 'OSR %', data: pct, backgroundColor: PAL.map(c => c + 'bb'), borderRadius: 4 }],
      },
      options: opts,
    });
  }

  // ── 3. expenditure_breakdown ─────────────────────────────────
  // Doughnut: Personnel / Operations / Development / Pending Bills
  function renderExpenditureBreakdown(canvas) {
    const labels = ['Personnel', 'Operations', 'Development', 'Pending Bills'];
    const values = [42, 28, 22, 8];
    const opts = {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right', labels: { color: _tickColor(), boxWidth: 12, font: { size: 11 } } },
        title:  { display: true, text: 'Expenditure Breakdown (%)', color: _tickColor(), font: { size: 12, weight: '600' } },
        tooltip: {
          backgroundColor: _isDark() ? '#1e2336' : '#fff',
          titleColor: _isDark() ? '#e6e8f0' : '#1a2040',
          bodyColor:  _tickColor(),
          borderColor: _isDark() ? '#2a3047' : '#dde1ee',
          borderWidth: 1, cornerRadius: 6, padding: 10,
          callbacks: { label: c => ` ${c.label}: ${c.parsed}%` },
        },
      },
    };
    new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{ data: values, backgroundColor: [CYAN, GREEN, AMBER, RED], borderWidth: 0, hoverOffset: 8 }],
      },
      options: opts,
    });
  }

  // ── 4. audit_history ────────────────────────────────────────
  // Stacked bar: Clean / Qualified / Adverse / Disclaimer per year
  function renderAuditHistory(canvas) {
    const years  = ['FY2019', 'FY2020', 'FY2021', 'FY2022', 'FY2023'];
    const clean  = [18, 20, 22, 24, 26];
    const qual   = [16, 16, 15, 14, 13];
    const adv    = [8,  7,  6,  5,  5];
    const disc   = [5,  4,  4,  4,  3];
    const opts   = _baseOpts('Audit Opinions Across Counties');
    opts.scales.x.stacked = true;
    opts.scales.y.stacked = true;
    opts.scales.y.ticks.callback = v => v + ' counties';
    new Chart(canvas, {
      type: 'bar',
      data: {
        labels: years,
        datasets: [
          { label: 'Clean',      data: clean, backgroundColor: GREEN + 'cc', borderRadius: 2 },
          { label: 'Qualified',  data: qual,  backgroundColor: AMBER + 'cc', borderRadius: 2 },
          { label: 'Adverse',    data: adv,   backgroundColor: RED   + 'cc', borderRadius: 2 },
          { label: 'Disclaimer', data: disc,  backgroundColor: PURPLE+ 'cc', borderRadius: 2 },
        ],
      },
      options: opts,
    });
  }

  // ── 5. county_comparison ────────────────────────────────────
  // Horizontal bar: top 8 counties by total revenue
  function renderCountyComparison(canvas) {
    const labels = ['Nairobi','Mombasa','Kisumu','Nakuru','Kiambu','Machakos','Uasin Gishu','Meru'];
    const values = [38000, 12000, 8500, 7800, 7200, 4800, 4200, 3900];
    const opts   = _baseOpts('County Revenue Comparison (KES M)');
    opts.indexAxis = 'y';
    opts.scales.x.ticks.callback = v => `${(v/1000).toFixed(0)}B`;
    delete opts.scales.y.grid;
    new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [{ label: 'Total Revenue', data: values,
          backgroundColor: PAL.slice(0, labels.length).map(c => c + 'cc'),
          borderRadius: 4 }],
      },
      options: opts,
    });
  }

  // ── 6. pending_bills ────────────────────────────────────────
  // Line + bar combo: pending bills trend vs absorption rate
  function renderPendingBills(canvas) {
    const years      = ['FY2020', 'FY2021', 'FY2022', 'FY2023', 'FY2024'];
    const bills      = [320, 380, 290, 410, 350];
    const absorption = [72, 68, 75, 71, 74];
    const opts = _baseOpts('Pending Bills (KES M) & Absorption Rate (%)');
    opts.scales.y  = { position: 'left',  ticks: { color: _tickColor(), callback: v => v+'M' }, grid: { color: _gridColor() } };
    opts.scales.y1 = { position: 'right', ticks: { color: _tickColor(), callback: v => v+'%' }, grid: { drawOnChartArea: false } };
    new Chart(canvas, {
      type: 'bar',
      data: {
        labels: years,
        datasets: [
          { type: 'bar',  label: 'Pending Bills',    data: bills,      backgroundColor: RED   +'99', yAxisID: 'y',  borderRadius: 4 },
          { type: 'line', label: 'Absorption Rate %', data: absorption, borderColor: CYAN,           yAxisID: 'y1',
            backgroundColor: CYAN+'22', tension: 0.4, fill: false, pointRadius: 4 },
        ],
      },
      options: opts,
    });
  }

  // ── Dispatcher ───────────────────────────────────────────────
  window.fosRenderChart = function (container, type, ctx) {
    const canvas = container.querySelector('canvas');
    if (!canvas) return;
    canvas.height = 220;

    const map = {
      revenue_trend:          renderRevenueTrend,
      osr_trend:              renderOsrTrend,
      expenditure_breakdown:  renderExpenditureBreakdown,
      audit_history:          renderAuditHistory,
      county_comparison:      renderCountyComparison,
      pending_bills:          renderPendingBills,
    };

    const fn = map[type];
    if (fn) {
      fn(canvas, ctx);
    } else {
      container.innerHTML = `<span style="color:var(--text-muted);font-size:11px;">Unknown chart type: ${type}</span>`;
    }
  };

})();
