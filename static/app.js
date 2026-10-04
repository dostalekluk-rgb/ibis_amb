let currentFilter = 'PENDING';
let currentReports = [];
let currentIndex = 0;
let currentReportDetail = null;
let currentDecisions = {}; // review_id -> 'ACCEPT' or 'REJECT_PAST' or 'REJECT'
let focusedProposalIndex = 0;
let isSavingValidation = false;

document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  fetchStats();
  fetchReports();
});

function setupEventListeners() {
  // Filter buttons
  document.querySelectorAll('.btn-filter').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      currentFilter = e.target.getAttribute('data-filter');
      currentIndex = 0;
      fetchReports();
    });
  });

  // Save & Next button
  document.getElementById('btn-save-validation').addEventListener('click', (e) => {
    if (e.target && typeof e.target.blur === 'function') e.target.blur();
    saveCurrentValidation();
  });

  // Keyboard Shortcuts (P, O, Space, Enter, Up, Down)
  document.addEventListener('keydown', (e) => {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;

    const key = e.key ? e.key.toLowerCase() : '';
    const code = e.code || '';
    
    if (key === 'p') {
      e.preventDefault();
      setDecisionForFocused('ACCEPT');
    } else if (key === 'o') {
      e.preventDefault();
      setDecisionForFocused('REJECT_PAST');
    } else if (code === 'Space' || key === ' ' || key === 'spacebar' || code === 'Enter' || key === 'enter') {
      e.preventDefault();
      if (document.activeElement && typeof document.activeElement.blur === 'function') {
        document.activeElement.blur();
      }
      saveCurrentValidation();
    } else if (code === 'ArrowDown' || key === 'arrowdown') {
      e.preventDefault();
      moveProposalFocus(1);
    } else if (code === 'ArrowUp' || key === 'arrowup') {
      e.preventDefault();
      moveProposalFocus(-1);
    }
  });
}

async function fetchStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    if (document.getElementById('stat-since-tuning')) {
      document.getElementById('stat-since-tuning').innerText = data.validated_since_tuning || 0;
    }
    if (document.getElementById('stat-batch-rem')) {
      document.getElementById('stat-batch-rem').innerText = data.batch_remaining || 0;
    }
    if (document.getElementById('stat-batch-label')) {
      const total = data.batch_total || 200;
      document.getElementById('stat-batch-label').innerText = `Zbývá z batche (${total}):`;
    }
    if (document.getElementById('stat-validated')) {
      document.getElementById('stat-validated').innerText = data.validated_reports || 0;
    }
  } catch (err) {
    console.error('Error fetching stats:', err);
  }
}

async function fetchReports() {
  try {
    const res = await fetch(`/api/reports?filter_status=${currentFilter}&limit=100`);
    currentReports = await res.json();
    renderReportList();

    if (currentReports.length > 0) {
      if (currentIndex >= currentReports.length) currentIndex = 0;
      loadReportDetail(currentReports[currentIndex].id);
    } else {
      renderEmptyState();
    }
  } catch (err) {
    console.error('Error fetching reports:', err);
  }
}

function renderReportList() {
  const container = document.getElementById('report-list-container');
  container.innerHTML = '';

  currentReports.forEach((rep, idx) => {
    const itemEl = document.createElement('div');
    itemEl.className = `report-item ${idx === currentIndex ? 'active' : ''}`;
    
    const isVal = (rep.status === 'VALIDATED');
    const badgeClass = isVal ? 'badge-mini-validated' : 'badge-mini-pending';
    const badgeText = isVal ? 'VALIDOVÁNO' : 'K REVIZI';

    itemEl.innerHTML = `
      <div class="item-title">Případ #${idx + 1} (ID ${rep.id})</div>
      <div class="item-meta">${rep.date_str || ''} ${rep.time_str || ''}</div>
      <div class="item-badges">
        <span class="badge-mini ${badgeClass}">${badgeText}</span>
        ${rep.addition_count ? `<span style="font-size:10px; color:var(--color-add); font-weight:700;">+${rep.addition_count}</span>` : ''}
        ${rep.removal_count ? `<span style="font-size:10px; color:var(--color-rem); font-weight:700;">-${rep.removal_count}</span>` : ''}
      </div>
    `;

    itemEl.addEventListener('click', () => {
      currentIndex = idx;
      renderReportList();
      loadReportDetail(rep.id);
    });

    container.appendChild(itemEl);
  });
}

async function loadReportDetail(reportId) {
  try {
    const res = await fetch(`/api/reports/${reportId}`);
    currentReportDetail = await res.json();
    currentDecisions = {};
    focusedProposalIndex = 0;

    // Initialize decisions map from existing decisions or defaults
    const reviews = currentReportDetail.reviews || [];
    const decisions = currentReportDetail.decisions || [];
    const decisionMap = {};
    decisions.forEach(d => { decisionMap[d.review_id] = d.action; });

    reviews.forEach(r => {
      if (decisionMap[r.id]) {
        currentDecisions[r.id] = decisionMap[r.id];
      } else {
        // Default to ACCEPT for positive AI proposals
        currentDecisions[r.id] = 'ACCEPT';
      }
    });

    renderCurrentReport();
  } catch (err) {
    console.error(`Error loading report ${reportId}:`, err);
  }
}

function renderCurrentReport() {
  if (!currentReportDetail) return;

  const rep = currentReportDetail.report;
  const reviews = currentReportDetail.reviews || [];

  // Case Header
  document.getElementById('display-case-id').innerText = `Případ #${currentIndex + 1} (ID ${rep.id})`;
  document.getElementById('meta-date-time').innerText = `${rep.date_str || ''} ${rep.time_str || ''}`;

  // IS Codes (Render in both middle pane header and right text pane header)
  const isBox1 = document.getElementById('reported-codes-display');
  const isBox2 = document.getElementById('text-pane-is-codes');
  isBox1.innerHTML = '';
  if (isBox2) isBox2.innerHTML = '';

  if (rep.codes_raw && rep.codes_raw.trim()) {
    const parts = rep.codes_raw.split(',').map(c => c.trim()).filter(Boolean);
    parts.forEach(c => {
      const pill1 = document.createElement('span');
      pill1.className = 'is-pill';
      pill1.innerText = c;
      isBox1.appendChild(pill1);

      if (isBox2) {
        const pill2 = document.createElement('span');
        pill2.className = 'is-pill';
        pill2.innerText = c;
        isBox2.appendChild(pill2);
      }
    });
  } else {
    isBox1.innerHTML = '<span style="color:#888888; font-style:italic;">— Žádné kódové položky —</span>';
    if (isBox2) isBox2.innerHTML = '<span style="color:#888888; font-style:italic;">— Žádné kódy v IS —</span>';
  }

  // Right Column: Full Text
  const fulltextEl = document.getElementById('report-text-display');
  let fulltextHTML = escapeHtml(rep.text || '');

  // Highlight blue clinical keywords ("UZ", "odebr", "ultrazvuk", "odběr", "biop")
  const blueKeywordsRegex = /(\buz:?|\bultrazvuk[a-ž]*|\bodebr[a-ž]*|\bodběr[a-ž]*|\bodber[a-ž]*|\bbiop[a-ž]*)/gi;
  fulltextHTML = fulltextHTML.replace(blueKeywordsRegex, '<mark class="mark-blue">$1</mark>');

  // Highlight verbatim quotes in right-column fulltext
  reviews.forEach(rev => {
    if (rev.exact_text_snippet && rev.exact_text_snippet.trim()) {
      const snippet = escapeHtml(rev.exact_text_snippet.trim());
      if (snippet.length > 5 && fulltextHTML.includes(snippet)) {
        fulltextHTML = fulltextHTML.replace(snippet, `<mark>${snippet}</mark>`);
      }
    }
  });
  fulltextEl.innerHTML = fulltextHTML;

  // Center Column: Render Proposals Cards
  const cardsContainer = document.getElementById('eval-cards-container');
  cardsContainer.innerHTML = '';

  if (reviews.length === 0) {
    cardsContainer.innerHTML = `
      <div style="padding: 20px; text-align: center; color: #777777;">
        <span style="font-size: 24px;">✓</span>
        <p style="margin-top: 8px; font-weight: 600;">Žádné odchylky nenalezeny (Kódy v IS jsou v pořádku)</p>
      </div>
    `;
    return;
  }

  reviews.forEach((rev, idx) => {
    const isAdd = (rev.type === 'ADDITION');
    const cardCls = isAdd ? 'card-add' : 'card-remove';
    const flagCls = isAdd ? 'flag-add' : 'flag-remove';
    const flagIcon = isAdd ? '+' : '-';
    
    const cardEl = document.createElement('div');
    cardEl.className = `proposal-card ${cardCls} ${idx === focusedProposalIndex ? 'focused-card' : ''}`;
    cardEl.setAttribute('data-rev-id', rev.id);

    const currentAct = currentDecisions[rev.id] || 'ACCEPT';
    const isPSelected = (currentAct === 'ACCEPT');
    const isOSelected = (currentAct === 'REJECT_PAST' || currentAct === 'REJECT');

    const quoteHtml = rev.exact_text_snippet ? `
      <div class="verbatim-quote-box">
        <div class="verbatim-quote-label">💬 Verbatim citace zprávy (Důkaz):</div>
        <div class="verbatim-quote-text">"${escapeHtml(rev.exact_text_snippet)}"</div>
      </div>
    ` : '';

    cardEl.innerHTML = `
      <div class="proposal-header">
        <div class="code-title-group">
          <span class="code-flag-badge ${flagCls}">${flagIcon} ${escapeHtml(rev.code)}</span>
          <span class="code-name-str">${escapeHtml(rev.code_name || '')}</span>
        </div>
        <span class="source-tag">${escapeHtml(rev.source || 'AI')}</span>
      </div>

      ${quoteHtml}

      <div class="reason-text"><strong>Odůvodnění:</strong> ${escapeHtml(rev.reason || 'Sémanticky doložený výkon')}</div>

      <div class="po-action-buttons">
        <button class="btn-po btn-po-p ${isPSelected ? 'selected' : ''}" onclick="selectDecision(${rev.id}, 'ACCEPT', event)">
          <kbd>P</kbd> Provedeno dnes (Přijmout)
        </button>
        <button class="btn-po btn-po-o ${isOSelected ? 'selected' : ''}" onclick="selectDecision(${rev.id}, 'REJECT_PAST', event)">
          <kbd>O</kbd> Odmítnout / Anamnéza
        </button>
      </div>
    `;

    cardEl.addEventListener('click', () => {
      focusedProposalIndex = idx;
      updateProposalFocus();
    });

    cardsContainer.appendChild(cardEl);
  });
}

function selectDecision(reviewId, actionStr, event) {
  if (event && event.target && typeof event.target.blur === 'function') {
    event.target.blur();
  }
  if (document.activeElement && typeof document.activeElement.blur === 'function') {
    document.activeElement.blur();
  }
  currentDecisions[reviewId] = actionStr;
  renderCurrentReport();
  saveSingleDecision(reviewId, actionStr);
}

async function saveSingleDecision(reviewId, actionStr) {
  try {
    await fetch('/api/save_review_decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ review_id: reviewId, action: actionStr })
    });
    fetchStats();
  } catch (err) {
    console.error('Error saving single decision:', err);
  }
}

function setDecisionForFocused(actionStr) {
  if (!currentReportDetail || !currentReportDetail.reviews) return;
  const reviews = currentReportDetail.reviews;
  if (focusedProposalIndex >= 0 && focusedProposalIndex < reviews.length) {
    const revId = reviews[focusedProposalIndex].id;
    selectDecision(revId, actionStr);
    
    // Auto advance focus to next proposal card
    if (focusedProposalIndex < reviews.length - 1) {
      focusedProposalIndex++;
      updateProposalFocus();
    }
  }
}

function moveProposalFocus(delta) {
  if (!currentReportDetail || !currentReportDetail.reviews) return;
  const len = currentReportDetail.reviews.length;
  if (len === 0) return;
  focusedProposalIndex = (focusedProposalIndex + delta + len) % len;
  updateProposalFocus();
}

function updateProposalFocus() {
  const cards = document.querySelectorAll('.proposal-card');
  cards.forEach((c, idx) => {
    if (idx === focusedProposalIndex) {
      c.style.outline = '2px solid var(--nejm-red)';
      c.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
      c.style.outline = 'none';
    }
  });
}

async function saveCurrentValidation() {
  if (isSavingValidation) return;
  if (!currentReportDetail || !currentReportDetail.report) {
    console.warn('saveCurrentValidation: Není načtena žádná aktivní zpráva.');
    return;
  }

  isSavingValidation = true;
  const reportId = currentReportDetail.report.id;
  const reviews = currentReportDetail.reviews || [];

  const decisionsList = reviews.map(rev => ({
    review_id: rev.id,
    code: rev.code,
    type: rev.type,
    action: currentDecisions[rev.id] || 'ACCEPT'
  }));

  try {
    const res = await fetch(`/api/validate_report/${reportId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decisions: decisionsList })
    });

    if (!res.ok) {
      const errTxt = await res.text();
      alert(`⚠️ Chyba při uložení zprávy (HTTP ${res.status}): ${errTxt}`);
      isSavingValidation = false;
      return;
    }

    const result = await res.json();
    if (result.status === 'success') {
      console.log(`Zpráva #${reportId} byla úspěšně validována.`);
      fetchStats();

      if (currentFilter === 'PENDING') {
        currentReports.splice(currentIndex, 1);
        if (currentReports.length === 0) {
          await fetchReports();
        } else {
          if (currentIndex >= currentReports.length) {
            currentIndex = 0;
          }
          renderReportList();
          if (currentReports[currentIndex]) {
            loadReportDetail(currentReports[currentIndex].id);
          }
        }
      } else {
        if (currentReports[currentIndex]) {
          currentReports[currentIndex].status = 'VALIDATED';
        }
        if (currentIndex < currentReports.length - 1) {
          currentIndex++;
          renderReportList();
          loadReportDetail(currentReports[currentIndex].id);
        } else {
          fetchReports();
        }
      }
    } else {
      alert(`⚠️ Server vrátil chybu: ${result.message || 'Neznámý problém'}`);
    }
  } catch (err) {
    console.error('Error saving validation:', err);
    alert(`⚠️ Nelze se spojit se serverem na portu 8000: ${err.message || err}`);
  } finally {
    isSavingValidation = false;
  }
}

async function exportGoldDataset() {
  try {
    const res = await fetch('/api/export_gold_dataset');
    const data = await res.json();
    alert(`🎉 ${data.message}\n\nGold Standard dataset vytvořen v souboru '${data.file}'. Pripraven pro tuning ibis_amb3!`);
  } catch (err) {
    console.error('Error exporting gold dataset:', err);
    alert('Chyba při exportu trénovací sady.');
  }
}

function renderEmptyState() {
  document.getElementById('report-list-container').innerHTML = `
    <div style="padding:20px; text-align:center; color:#888888;">
      Žádné zprávy v této kategorii.
    </div>
  `;
}

async function addManualCode(codeStr) {
  if (!currentReportDetail || !currentReportDetail.report) return;
  const reportId = currentReportDetail.report.id;

  try {
    const res = await fetch('/api/add_manual_review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_id: reportId,
        code: codeStr,
        type: 'ADDITION',
        reason: 'Ručně doplněno auditorem z rychlé palety'
      })
    });

    const result = await res.json();
    if (result.status === 'success') {
      fetchStats();
      if (currentReports[currentIndex]) {
        currentReports[currentIndex].status = 'VALIDATED';
      }
      renderReportList();
      await loadReportDetail(reportId);

      // Toast notification
      showToast(`✅ Ručně přidán kód +${result.code} (${result.code_name || 'Zdravotní výkon'})`);

      // Highlight new card in middle pane
      setTimeout(() => {
        const cards = document.querySelectorAll('.proposal-card');
        if (cards.length > 0) {
          const lastCard = cards[cards.length - 1];
          lastCard.style.outline = '3px solid #10B981';
          lastCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      }, 100);
    } else {
      alert(`⚠️ Chyba při přidání kódu: ${result.message || 'Neznámý problém'}`);
    }
  } catch (err) {
    console.error('Error adding manual code:', err);
    alert(`⚠️ Nelze přidat kód: ${err.message || err}`);
  }
}

function showToast(message) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast-item';
  toast.innerText = message;
  container.appendChild(toast);
  setTimeout(() => {
    if (toast.parentNode) toast.parentNode.removeChild(toast);
  }, 3000);
}

function addCustomCode() {
  const inputEl = document.getElementById('custom-code-input');
  if (!inputEl) return;
  const val = inputEl.value.trim();
  if (!val) return;
  addManualCode(val);
  inputEl.value = '';
}

function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
