/* =========================================================
   FinancialOS Kenya — Document Review (review.js)
   PDF.js viewer + AI chat with [[PDF:id:page]] directives
   Loaded as an ES module from review.html
   ========================================================= */

// ── PDF.js worker setup ───────────────────────────────────────
import * as pdfjsLib from 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.4.168/build/pdf.min.mjs';
pdfjsLib.GlobalWorkerOptions.workerSrc =
  'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.4.168/build/pdf.worker.min.mjs';

// ── Viewer state ─────────────────────────────────────────────
let _pdfDoc      = null;
let _pageNum     = 1;
let _pageCount   = 0;
let _scale       = 1.4;
let _rendering   = false;
let _activeDocId = null;
let _activeDocTitle = '';
let _pendingPage = null;

const canvas  = document.getElementById('reviewCanvas');
const ctx     = canvas ? canvas.getContext('2d') : null;

// ── Chat state ───────────────────────────────────────────────
let _rvMode    = 'simple';
let _rvHistory = [];
const MAX_HIST = 20;

// ── DOM refs ─────────────────────────────────────────────────
const elDocList    = document.getElementById('reviewDocList');
const elMessages   = document.getElementById('rvMessages');
const elInput      = document.getElementById('rvInput');
const elSendBtn    = document.getElementById('rvSendBtn');
const elSuggestions= document.getElementById('rvSuggestions');
const elDocContext = document.getElementById('rvDocContext');
const elDocCtxName = document.getElementById('rvDocContextName');
const elPlaceholder= document.getElementById('reviewPlaceholder');
const elPageNum    = document.getElementById('viewerPageNum');
const elPageCount  = document.getElementById('viewerPageCount');
const elZoom       = document.getElementById('viewerZoom');
const elTitle      = document.getElementById('viewerDocTitle');

// ════════════════════════════════════════════════════════════
// PDF VIEWER
// ════════════════════════════════════════════════════════════

async function _renderPage(num) {
  if (!_pdfDoc || _rendering) return;
  _rendering = true;
  try {
    const page     = await _pdfDoc.getPage(num);
    const viewport = page.getViewport({ scale: _scale });
    canvas.width   = viewport.width;
    canvas.height  = viewport.height;
    await page.render({ canvasContext: ctx, viewport }).promise;
    elPageNum.textContent   = num;
    elPageCount.textContent = _pageCount;
    elZoom.textContent      = Math.round(_scale * 100) + '%';
  } finally {
    _rendering = false;
    if (_pendingPage !== null) {
      const p = _pendingPage; _pendingPage = null;
      _goToPage(p);
    }
  }
}

function _goToPage(n) {
  if (!_pdfDoc) return;
  const target = Math.max(1, Math.min(n, _pageCount));
  if (_rendering) { _pendingPage = target; return; }
  _pageNum = target;
  _renderPage(_pageNum);
}

window.reviewPrevPage = () => _goToPage(_pageNum - 1);
window.reviewNextPage = () => _goToPage(_pageNum + 1);
window.reviewZoomIn   = () => { _scale = Math.min(_scale + 0.2, 3.0); _renderPage(_pageNum); };
window.reviewZoomOut  = () => { _scale = Math.max(_scale - 0.2, 0.5); _renderPage(_pageNum); };
window.reviewFitWidth = () => {
  const wrap = document.getElementById('reviewCanvasWrap');
  if (!wrap || !_pdfDoc) return;
  _pdfDoc.getPage(_pageNum).then(page => {
    const vp  = page.getViewport({ scale: 1 });
    _scale = (wrap.clientWidth - 40) / vp.width;
    _renderPage(_pageNum);
  });
};

// Load a document by its Flask doc ID
window.reviewLoadDoc = async function (docId, title) {
  _activeDocId    = docId;
  _activeDocTitle = title;

  // Mark active in list
  document.querySelectorAll('.review-doc-item').forEach(el => {
    el.classList.toggle('active', parseInt(el.dataset.docId) === docId);
  });

  // Update toolbar
  elTitle.textContent = title;
  elPlaceholder.style.display = 'none';
  canvas.style.display = 'block';

  // Update chat context pill
  elDocContext.style.display = 'flex';
  elDocCtxName.textContent   = title;

  // Build suggestions for this doc
  _buildRvSuggestions(true);

  // Announce to chat
  _appendBubble('assistant',
    `Loading **${title}**… Ask me anything about it.`);

  try {
    const url      = `/api/document/${docId}/file`;
    const loadTask = pdfjsLib.getDocument(url);
    _pdfDoc        = await loadTask.promise;
    _pageCount     = _pdfDoc.numPages;
    _pageNum       = 1;
    await _renderPage(1);
  } catch (err) {
    console.error('PDF load error:', err);
    _appendBubble('error', 'Could not load PDF. The file may be missing on disk.');
  }
};

// Jump to a specific page (used by [[PDF:id:page]] directive)
async function _jumpToDocPage(docId, page) {
  if (_activeDocId !== docId) {
    // Need to load a different doc first — fetch its title from the list
    const item = document.querySelector(`.review-doc-item[data-doc-id="${docId}"]`);
    const title = item ? item.querySelector('.review-doc-name').textContent : `Document #${docId}`;
    await window.reviewLoadDoc(docId, title);
  }
  _goToPage(page || 1);
}

// ── Keyboard nav ─────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.target === elInput) return;
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') reviewNextPage();
  if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   reviewPrevPage();
});

// ════════════════════════════════════════════════════════════
// DOCUMENT LIST FILTER
// ════════════════════════════════════════════════════════════

window.reviewFilter = function () {
  const q      = (document.getElementById('reviewSearch').value || '').toLowerCase().trim();
  const county = document.getElementById('reviewCountyFilter').value;
  document.querySelectorAll('.review-doc-item').forEach(el => {
    const matchQ = !q || (el.dataset.title || '').includes(q);
    const matchC = !county || el.dataset.countyId === county;
    el.style.display = matchQ && matchC ? '' : 'none';
  });
};

window.reviewToggleDocs = function () {
  const panel = document.getElementById('reviewDocsPanel');
  const btn   = document.getElementById('docsCollapseBtn');
  panel.classList.toggle('collapsed');
  btn.textContent = panel.classList.contains('collapsed') ? '›' : '‹';
};

// ════════════════════════════════════════════════════════════
// REVIEW CHAT
// ════════════════════════════════════════════════════════════

window.rvSetMode = function (mode) {
  _rvMode = mode;
  document.getElementById('rvModeSimple').classList.toggle('active', mode === 'simple');
  document.getElementById('rvModeExpert').classList.toggle('active', mode === 'expert');
};

window.rvClear = function () {
  _rvHistory = [];
  elMessages.innerHTML = '';
  _appendBubble('assistant', 'Chat cleared. Select a document or ask a question to continue.');
  _buildRvSuggestions(!!_activeDocId);
};

// ── Suggestions ──────────────────────────────────────────────
const SUGG_DOC = [
  'Summarise the key findings in this document',
  'What is the audit opinion?',
  'Show revenue figures mentioned in this document',
  'Are there any pending bills concerns?',
  'What fiscal year does this document cover?',
];
const SUGG_GENERAL = [
  'Which county has the highest pending bills?',
  'Compare Nairobi and Mombasa revenue',
  'Load the Nairobi audit report',
  'Which counties had adverse opinions?',
  'Show revenue trend chart',
];

function _buildRvSuggestions(hasDoc) {
  const list   = hasDoc ? SUGG_DOC : SUGG_GENERAL;
  const picked = list.sort(() => 0.5 - Math.random()).slice(0, 3);
  elSuggestions.innerHTML = picked
    .map(s => `<button class="chat-suggest-btn" onclick="rvUseSuggestion(this)">${s}</button>`)
    .join('');
}

window.rvUseSuggestion = function (btn) {
  elInput.value = btn.textContent;
  elSuggestions.innerHTML = '';
  rvSend();
};

// ── Send ─────────────────────────────────────────────────────
window.rvSend = function () {
  const text = elInput.value.trim();
  if (!text) return;
  elInput.value = '';
  elSuggestions.innerHTML = '';

  _appendBubble('user', text);
  _rvHistory.push({ role: 'user', content: text });

  _showTyping();
  elSendBtn.disabled = true;

  fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages:  _rvHistory.slice(-MAX_HIST),
      mode:      _rvMode,
      page:      'Document Review',
      county_id: null,
      doc_id:    _activeDocId,
      doc_title: _activeDocTitle || null,
    }),
  })
  .then(r => r.json())
  .then(data => {
    _removeTyping();
    elSendBtn.disabled = false;
    const reply = data.reply || data.error || 'No response received.';
    _rvHistory.push({ role: 'assistant', content: reply });
    if (_rvHistory.length > MAX_HIST * 2) _rvHistory = _rvHistory.slice(-MAX_HIST);
    const bubble = _appendBubble('assistant', reply);
    _handlePdfDirectives(bubble);
    _buildRvSuggestions(!!_activeDocId);
  })
  .catch(() => {
    _removeTyping();
    elSendBtn.disabled = false;
    _appendBubble('error', 'Network error — please try again.');
  });
};

// ── [[PDF:doc_id:page]] directive handler ────────────────────
function _handlePdfDirectives(bubble) {
  bubble.querySelectorAll('.rv-pdf-directive').forEach(el => {
    const docId = parseInt(el.dataset.docId);
    const page  = parseInt(el.dataset.page) || 1;
    el.addEventListener('click', () => _jumpToDocPage(docId, page));
  });
}

// ── Typing indicator ─────────────────────────────────────────
let _typingEl = null;
function _showTyping() {
  _typingEl = document.createElement('div');
  _typingEl.className = 'chat-bubble assistant chat-typing';
  _typingEl.innerHTML = '<span></span><span></span><span></span>';
  elMessages.appendChild(_typingEl);
  elMessages.scrollTop = elMessages.scrollHeight;
}
function _removeTyping() {
  if (_typingEl) { _typingEl.remove(); _typingEl = null; }
}

// ── Render bubble ────────────────────────────────────────────
function _appendBubble(role, raw) {
  const wrap = document.createElement('div');
  wrap.className = `chat-bubble ${role}`;
  if (role === 'assistant') {
    wrap.innerHTML = _renderMarkdown(raw);
  } else if (role === 'error') {
    wrap.innerHTML = `<span style="color:var(--red)">${_esc(raw)}</span>`;
  } else {
    wrap.textContent = raw;
  }
  elMessages.appendChild(wrap);
  elMessages.scrollTop = elMessages.scrollHeight;
  return wrap;
}

// ── Markdown + directive renderer ────────────────────────────
function _renderMarkdown(md) {
  // [[PDF:doc_id:page]] → clickable link that jumps the viewer
  md = md.replace(/\[\[PDF:(\d+):?(\d*)\]\]/g, (_, id, pg) => {
    const page = pg || 1;
    return `<button class="rv-pdf-directive review-ctrl-btn"
              data-doc-id="${id}" data-page="${page}"
              style="margin:2px 0;cursor:pointer;">
              ↗ Open Document #${id}${pg ? ' p.' + pg : ''}
            </button>`;
  });
  // [[CHART:type]] — reuse fosRenderChart from main.js if available
  md = md.replace(/\[\[CHART:(\w+)\]\]/g, (_, t) =>
    `<div class="chat-chart-directive chat-chart-wrap" data-chart-type="${t}"><canvas></canvas></div>`
  );
  // Bold, italic, code, headers, lists
  md = md.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  md = md.replace(/\*(.+?)\*/g, '<em>$1</em>');
  md = md.replace(/`([^`]+)`/g, '<code>$1</code>');
  md = md.replace(/^### (.+)$/gm, '<h4 class="chat-h">$1</h4>');
  md = md.replace(/^## (.+)$/gm,  '<h3 class="chat-h">$1</h3>');
  md = md.replace(/^[-•] (.+)$/gm, '<li>$1</li>');
  md = md.replace(/(<li>[\s\S]*<\/li>)/m, '<ul>$1</ul>');
  md = md.replace(/\n(?!<)/g, '<br>');
  return md;
}

function _esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── After render: wire up chart directives ───────────────────
const _chartObserver = new MutationObserver(mutations => {
  mutations.forEach(m => m.addedNodes.forEach(node => {
    if (node.nodeType !== 1) return;
    node.querySelectorAll && node.querySelectorAll('.chat-chart-directive').forEach(el => {
      if (typeof fosRenderChart === 'function') {
        fosRenderChart(el, el.dataset.chartType, {});
      }
    });
  }));
});
if (elMessages) _chartObserver.observe(elMessages, { childList: true });

// ════════════════════════════════════════════════════════════
// INIT
// ════════════════════════════════════════════════════════════

(function init() {
  _appendBubble('assistant',
    'Welcome to **Document Review**. Select a PDF from the left panel, then ask me anything about it — I\'ll answer and can jump the viewer to relevant pages.');
  _buildRvSuggestions(false);
})();
