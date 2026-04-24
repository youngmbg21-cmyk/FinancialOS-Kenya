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
