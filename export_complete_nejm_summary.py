import sqlite3
import pandas as pd
import re
import html
import json
import os

DB_FILE = "validator_data.db"
KODY_FILE = "kody.xlsx"
OUTPUT_HTML = "summary_table_nejm.html"
INFO_FILE = "batch_job_info.json"

def generate_complete_nejm_summary(show_pending_banner=False):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    df_kody = pd.read_excel(KODY_FILE)
    name_map = {}
    for _, r in df_kody.iterrows():
        c = str(r["Kód"]).strip().zfill(5)
        name_map[c] = str(r["Název výkonu"]) if pd.notna(r["Název výkonu"]) else ""

    # Fetch ADDITION details (Suggestions to add codes)
    cursor.execute("SELECT DISTINCT code FROM reviews WHERE type = 'ADDITION'")
    distinct_codes = [r["code"] for r in cursor.fetchall()]

    evidence_rows_raw = []
    for cd in sorted(distinct_codes):
        cursor.execute("""
        SELECT 
            rev.id as review_id, 
            r.id as report_id,
            r.row_idx, 
            rev.code, 
            rev.code_name, 
            rev.source, 
            rev.exact_text_snippet, 
            rev.reason, 
            r.text, 
            r.date_str, 
            r.time_str,
            d.action
        FROM reviews rev
        JOIN reports r ON rev.report_id = r.id
        LEFT JOIN decisions d ON d.review_id = rev.id
        WHERE rev.type = 'ADDITION' AND rev.code = ?
        ORDER BY r.id ASC
        LIMIT 150
        """, (cd,))
        evidence_rows_raw.extend(cursor.fetchall())

    conn.close()

    batch_id_str = "batches/7r2xcjgcjem3acmeqjxhf0e8b3yd9iy4gcba"

    if show_pending_banner:
        evidence_html_rows = f"""
        <tr>
          <td colspan="3" style="text-align:center; padding: 50px 24px; background-color: #FFFDE7; border: 2px dashed #F57F17; border-radius: 6px;">
            <div style="font-family: 'Merriweather', serif; font-size: 1.3rem; font-weight: 700; color: #7A0016; margin-bottom: 10px;">
              ⏳ ČEKÁ SE NA DOKONČENÍ VÝPOČTU BATCH DÁVKY (GEMINI 3.8 FLASH)
            </div>
          </td>
        </tr>
        """
        code_options_html = '<option value="ALL">Všechny kódy (Čeká se na dávku)</option>'
    else:
        # Full interactive evidence rows generation for ADDITION suggestions
        evidence_html_rows = ""
        code_options = ['<option value="ALL">Všechny kódy (Všechny výkony)</option>']
        seen_codes_options = set()

        for idx, er in enumerate(evidence_rows_raw, 1):
            rev_id = er["review_id"]
            row_idx = er["row_idx"]
            code = er["code"]
            c_name = er["code_name"] or name_map.get(code, "Výkon")
            source = er["source"] or ""
            snippet = (er["exact_text_snippet"] or "").strip()
            text = (er["text"] or "").strip()
            date_str = er["date_str"] or ""
            time_str = er["time_str"] or ""
            action = er["action"] or ""
            reason = er["reason"] or ""

            if code not in seen_codes_options:
                seen_codes_options.add(code)
                code_options.append(f'<option value="{code}">Kód {code} – {html.escape(c_name)}</option>')

            if "ČASOVÉ" in source:
                source_badge = '<span class="detail-badge time-badge">🛡️ Pohotovost & Čas</span>'
                windowed_display = f'<mark class="yellow-highlight">📅 Vyšetření dne {html.escape(date_str)} v čase {html.escape(time_str)} ({html.escape(er["reason"] or "")})</mark>'
            else:
                source_badge = '<span class="detail-badge ai-badge">⚡ VERTEX AI (GEMINI 3.8 FLASH)</span>'
                
                if snippet and snippet.lower() in text.lower():
                    m = re.search(re.escape(snippet), text, re.IGNORECASE)
                    if m:
                        start_i, end_i = m.span()
                        pre = text[max(0, start_i - 60) : start_i]
                        post = text[end_i : min(len(text), end_i + 60)]
                        quote_matched = text[start_i:end_i]
                        
                        prefix_str = ("..." if max(0, start_i - 60) > 0 else "") + html.escape(pre)
                        suffix_str = html.escape(post) + ("..." if min(len(text), end_i + 60) < len(text) else "")
                        
                        windowed_display = f'{prefix_str}<mark class="yellow-highlight">{html.escape(quote_matched)}</mark>{suffix_str}'
                    else:
                        windowed_display = f'...<mark class="yellow-highlight">{html.escape(snippet)}</mark>...'
                elif snippet:
                    windowed_display = f'...<mark class="yellow-highlight">{html.escape(snippet)}</mark>...'
                else:
                    windowed_display = html.escape(text[:160]) + "..."

            if action == 'ACCEPT':
                status_attr = 'ACCEPT'
                status_badge_html = '<span class="status-badge status-accepted">✓ PŘIJATO (P)</span>'
            elif action == 'REJECT_PAST':
                status_attr = 'REJECT_PAST'
                status_badge_html = '<span class="status-badge status-past">📜 MINULOST (I)</span>'
            elif action == 'REJECT':
                status_attr = 'REJECT'
                status_badge_html = '<span class="status-badge status-rejected">✗ ODMÍTNUTO (O)</span>'
            else:
                status_attr = 'PENDING'
                status_badge_html = '<span class="status-badge status-pending">⏳ ČEKÁ (P/I/O)</span>'

            active_class = "active-row" if idx == 1 else ""

            evidence_html_rows += f"""
            <tr id="rev-row-{rev_id}" class="evidence-row {active_class}" data-review-id="{rev_id}" data-code="{code}" data-status="{status_attr}">
              <td class="col-code">
                <div style="font-weight:700; color:#1B5E20; font-size:8.5pt;">+ Kód {code}</div>
                <div style="font-weight:600; color:#1A1A1A; font-size:8pt; margin-top:2px;">{html.escape(c_name)}</div>
                <div style="margin-top:4px;">{source_badge}</div>
                <div style="color:#777; font-size:6.5pt; margin-top:3px;">Zpráva #{row_idx}</div>
                <div class="active-indicator-tag">▶ AKTUÁLNÍ ŘÁDEK</div>
              </td>
              <td class="col-text">
                <div class="snippet-box">{windowed_display}</div>
              </td>
              <td class="col-actions">
                <div class="action-btn-group">
                  <button type="button" class="btn-act btn-prijmout" onclick="event.stopPropagation(); saveDecision({rev_id}, 'ACCEPT', this)" title="Dnešní reálně provedený výkon (Doplnit kód)">✓ Dnes (P)</button>
                  <button type="button" class="btn-act btn-minulost" onclick="event.stopPropagation(); saveDecision({rev_id}, 'REJECT_PAST', this)" title="Minulé vyšetření / st.p. / Anamnéza">📜 Minulé (I)</button>
                  <button type="button" class="btn-act btn-odmitnout" onclick="event.stopPropagation(); saveDecision({rev_id}, 'REJECT', this)" title="Nedoplňovat (Jiný důvod)">✗ Jiné (O)</button>
                </div>
                <div style="margin-top:6px; text-align:center;">
                  {status_badge_html}
                </div>
              </td>
            </tr>
            """
        code_options_html = "\n".join(code_options)

    html_content = f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8">
  <title>VFN Evidence Grounding Validace Návrhů | NEJM Style</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Merriweather:ital,wght@0,300;0,400;0,700;1,300&family=Source+Sans+3:wght@400;600;700&display=swap');
    
    body {{
      background-color: #FAF8F5;
      color: #1A1A1A;
      font-family: 'Source Sans 3', system-ui, sans-serif;
      padding: 30px;
      margin: 0;
    }}
    .container {{
      max-width: 1240px;
      margin: 0 auto;
      background: #FFFFFF;
      border-top: 5px solid #7A0016;
      border-bottom: 2px solid #B5AD9C;
      box-shadow: 0 4px 16px rgba(0,0,0,0.08);
      padding: 36px 40px;
      border-radius: 4px;
    }}
    .nejm-masthead {{
      border-bottom: 2px solid #7A0016;
      padding-bottom: 16px;
      margin-bottom: 24px;
    }}
    .journal-title {{
      font-family: 'Merriweather', serif;
      font-size: 1.6rem;
      font-weight: 700;
      color: #7A0016;
      letter-spacing: -0.5px;
      text-transform: uppercase;
    }}
    .journal-subtitle {{
      font-size: 0.88rem;
      color: #4A4A4A;
      font-weight: 600;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      margin-top: 4px;
    }}
    .summary-cards {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 32px;
    }}
    .card {{
      background: #FAF8F5;
      border: 1px solid #D8D2C2;
      border-radius: 4px;
      padding: 16px;
    }}
    .card-label {{
      font-size: 0.75rem;
      font-weight: 700;
      color: #717171;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .card-val {{
      font-family: 'Merriweather', serif;
      font-size: 1.35rem;
      font-weight: 700;
      color: #7A0016;
      margin-top: 4px;
    }}
    .section-header {{
      font-family: 'Merriweather', serif;
      font-size: 1.15rem;
      font-weight: 700;
      color: #7A0016;
      border-bottom: 2px solid #7A0016;
      padding-bottom: 8px;
      margin-top: 24px;
      margin-bottom: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    /* Section 3 Detail Table (Font 8pt, Windowed Text & Actions) */
    table.detail-evidence-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 8pt;
      line-height: 1.5;
      font-family: 'Source Sans 3', -apple-system, sans-serif;
    }}
    table.detail-evidence-table th {{
      background-color: #7A0016;
      color: #FFFFFF;
      font-weight: 700;
      font-size: 8pt;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 9px 12px;
      text-align: left;
    }}
    table.detail-evidence-table td {{
      padding: 10px 12px;
      border-bottom: 1px solid #E2DDD3;
      vertical-align: middle;
    }}
    
    table.detail-evidence-table tr.evidence-row {{
      cursor: pointer;
      transition: background-color 0.15s ease, border-left 0.15s ease, box-shadow 0.15s ease;
    }}
    table.detail-evidence-table tr.evidence-row:nth-child(even) {{
      background-color: #FAF8F5;
    }}
    table.detail-evidence-table tr.evidence-row:hover {{
      background-color: #F4EFE6;
    }}
    table.detail-evidence-table tr.evidence-row.active-row {{
      background-color: #FFFDE7 !important; /* Golden active highlight */
      border-left: 6px solid #7A0016 !important; /* Deep NEJM crimson left border */
      box-shadow: 0 4px 14px rgba(122, 0, 22, 0.18);
    }}

    .col-code {{
      width: 220px;
      background-color: #F9F7F1;
      border-right: 1px solid #E2DDD3;
      vertical-align: top !important;
    }}
    .col-text {{
      color: #1A1A1A;
      word-wrap: break-word;
      font-size: 8.5pt;
    }}
    .col-actions {{
      width: 240px;
      border-left: 1px solid #E2DDD3;
      vertical-align: middle !important;
      background-color: #FAF8F5;
    }}

    mark.yellow-highlight {{
      background-color: #FFF59D;
      color: #332700;
      font-weight: 700;
      padding: 1px 5px;
      border-radius: 2px;
      border-bottom: 2px solid #F57F17;
    }}

    .detail-badge {{
      display: inline-block;
      font-size: 6.5pt;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 2px;
      text-transform: uppercase;
    }}
    .detail-badge.time-badge {{
      background-color: #FFF8E1;
      color: #7B5200;
      border: 1px solid #FFE082;
    }}
    .detail-badge.ai-badge {{
      background-color: #E3F2FD;
      color: #0D47A1;
      border: 1px solid #BBDEFB;
    }}

    .active-indicator-tag {{
      display: none;
      background-color: #7A0016;
      color: #FFFFFF;
      font-size: 6pt;
      font-weight: 700;
      padding: 1px 5px;
      border-radius: 2px;
      margin-top: 4px;
      letter-spacing: 0.5px;
    }}
    table.detail-evidence-table tr.evidence-row.active-row .active-indicator-tag {{
      display: inline-block !important;
    }}

    /* Action Buttons & Badges */
    .action-btn-group {{
      display: flex;
      gap: 4px;
      justify-content: center;
    }}
    .btn-act {{
      font-family: 'Source Sans 3', sans-serif;
      font-size: 7pt;
      font-weight: 700;
      padding: 5px 7px;
      border-radius: 3px;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.15s ease;
      outline: none;
      white-space: nowrap;
    }}
    .btn-prijmout {{
      background-color: #E8F5E9;
      color: #1B5E20;
      border-color: #A5D6A7;
    }}
    .btn-prijmout:hover {{
      background-color: #C8E6C9;
      border-color: #66BB6A;
      transform: translateY(-1px);
    }}
    .btn-minulost {{
      background-color: #FFF3E0;
      color: #E65100;
      border-color: #FFE0B2;
    }}
    .btn-minulost:hover {{
      background-color: #FFE0B2;
      border-color: #FFB74D;
      transform: translateY(-1px);
    }}
    .btn-odmitnout {{
      background-color: #FFEBEE;
      color: #B71C1C;
      border-color: #EF9A9A;
    }}
    .btn-odmitnout:hover {{
      background-color: #FFCDD2;
      border-color: #E57373;
      transform: translateY(-1px);
    }}

    .status-badge {{
      display: inline-block;
      font-size: 7pt;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 3px;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }}
    .status-badge.status-accepted {{
      background-color: #C8E6C9;
      color: #1B5E20;
      border: 1px solid #81C784;
    }}
    .status-badge.status-past {{
      background-color: #FFE0B2;
      color: #E65100;
      border: 1px solid #FFB74D;
    }}
    .status-badge.status-rejected {{
      background-color: #FFCDD2;
      color: #B71C1C;
      border: 1px solid #E57373;
    }}
    .status-badge.status-pending {{
      background-color: #F5F5F5;
      color: #616161;
      border: 1px solid #E0E0E0;
    }}
    .status-badge.status-saving {{
      background-color: #FFF9C4;
      color: #F57F17;
      border: 1px solid #FBC02D;
    }}
    .status-badge.status-error {{
      background-color: #FFEBEE;
      color: #D32F2F;
      border: 1px solid #FF8A80;
    }}

    kbd.key-hint {{
      background-color: #F4F1EA;
      border: 1px solid #C8C2B4;
      border-radius: 3px;
      box-shadow: 0 1px 1px rgba(0,0,0,0.12);
      color: #7A0016;
      display: inline-block;
      font-family: monospace;
      font-size: 0.85em;
      font-weight: 700;
      padding: 1px 5px;
    }}

    .toolbar-container {{
      background: #F9F7F1;
      border: 1px solid #E2DDD3;
      border-radius: 4px;
      padding: 12px 18px;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 20px;
      flex-wrap: wrap;
    }}
    .filter-group {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.85rem;
      font-weight: 600;
      color: #4A4A4A;
    }}
    .filter-group select {{
      font-family: inherit;
      font-size: 0.85rem;
      padding: 4px 10px;
      border: 1px solid #C8C2B4;
      border-radius: 3px;
      background-color: #FFFFFF;
      color: #1A1A1A;
    }}
    .keyboard-instruction {{
      margin-left: auto;
      font-size: 0.82rem;
      color: #555;
    }}
    .stat-counter {{
      display: inline-block;
      font-size: 0.78rem;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 3px;
      margin-left: 6px;
    }}
    .badge-accepted {{ background:#E8F5E9; color:#1B5E20; border:1px solid #A5D6A7; }}
    .badge-past {{ background:#FFF3E0; color:#E65100; border:1px solid #FFE0B2; }}
    .badge-rejected {{ background:#FFEBEE; color:#B71C1C; border:1px solid #EF9A9A; }}
    .badge-pending {{ background:#F5F5F5; color:#616161; border:1px solid #E0E0E0; }}

    .footer-note {{
      margin-top: 32px;
      font-size: 0.82rem;
      color: #717171;
      border-top: 1px solid #D8D2C2;
      padding-top: 12px;
      display: flex;
      justify-content: space-between;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="nejm-masthead">
      <div class="journal-title">VFN Clinical Coding Journal</div>
      <div class="journal-subtitle">Interaktivní Evidence Grounding Validace Návrhů Kódů (+ Podvykázané Výkony) • 21 468 lékařských zpráv</div>
    </div>

    <div class="summary-cards">
      <div class="card">
        <div class="card-label">Analyzováno zpráv</div>
        <div class="card-val">21 468</div>
      </div>
      <div class="card">
        <div class="card-label">Návrhy k doplnění</div>
        <div class="card-val" style="color:#1B5E20">+{len(evidence_rows_raw):,}×</div>
        <div style="font-size:0.75rem; color:#717171; margin-top:2px;">Podvykázané výkony</div>
      </div>
      <div class="card" style="background:#E8F5E9; border-color:#C8E6C9;">
        <div class="card-label" style="color:#1B5E20">Model Anotátoru</div>
        <div class="card-val" style="color:#1B5E20; font-size:1.1rem; margin-top:6px;">Gemini 3.8 Flash</div>
        <div style="font-size:0.75rem; color:#2E7D32; margin-top:2px;">Aplikována nová pravidla</div>
      </div>
      <div class="card">
        <div class="card-label">Klávesové zkratky</div>
        <div class="card-val" style="font-size:0.95rem; color:#1A1A1A; margin-top:6px;"><kbd class="key-hint">P</kbd> Dnes | <kbd class="key-hint">I</kbd> Minulé | <kbd class="key-hint">O</kbd> Jiné</div>
        <div style="font-size:0.75rem; color:#717171; margin-top:2px;">Automatický posun fokusu</div>
      </div>
    </div>

    <!-- DETAIL EVIDENCE TABLE (Interactive 1-Row Validation) -->
    <div class="section-header">
      <div>
        <span>VALIDACE NAVRŽENÝCH KÓDŮ K DOPLNĚNÍ (+ PODVYKÁZANÉ VÝKONY)</span>
        <div style="font-size:0.82rem; color:#555; font-family:'Source Sans 3', sans-serif; margin-top:3px;">
          Posuzování po 1 řádku • <kbd class="key-hint">P</kbd> = Dnešní výkon (Doplnit) • <kbd class="key-hint">I</kbd> = Minulé / st.p. • <kbd class="key-hint">O</kbd> = Nedoplňovat • Šipky <kbd class="key-hint">↑</kbd><kbd class="key-hint">↓</kbd> = Posun
        </div>
      </div>
      <div style="text-align:right;">
        <span class="stat-counter badge-accepted" id="counter-accepted">0 Dnes (P)</span>
        <span class="stat-counter badge-past" id="counter-past">0 Minulé (I)</span>
        <span class="stat-counter badge-rejected" id="counter-rejected">0 Jiné (O)</span>
        <span class="stat-counter badge-pending" id="counter-pending">0 Čeká</span>
      </div>
    </div>

    <div class="toolbar-container">
      <div class="filter-group">
        <label for="filter-code">Filtr výkonu:</label>
        <select id="filter-code" onchange="applyFilters()">
          {code_options_html}
        </select>
      </div>
      <div class="filter-group">
        <label for="filter-status">Stav schválení:</label>
        <select id="filter-status" onchange="applyFilters()">
          <option value="ALL">Všechny stavy</option>
          <option value="PENDING" selected>Jen čekající (ČEKÁ)</option>
          <option value="ACCEPT">Jen dnešní výkony (P)</option>
          <option value="REJECT_PAST">Jen minulá vyšetření / st.p. (I)</option>
          <option value="REJECT">Jen ostatní odmítnutá (O)</option>
        </select>
      </div>
      <div class="keyboard-instruction">
        💡 <strong>Rychlá validace:</strong> Stiskněte <strong>P</strong> (Dnešní výkon), <strong>I</strong> (Minulé vyšetření / st.p.) nebo <strong>O</strong> (Jiné) – <u>posune na další řádek</u>!
      </div>
    </div>

    <table class="detail-evidence-table">
      <thead>
        <tr>
          <th class="col-code">Navržený Kód & Název Výkonu</th>
          <th class="col-text">Kontextový výsek textu s vyznačeným důkazem podkladu</th>
          <th class="col-actions" style="text-align:center;">Rozhodnutí auditora</th>
        </tr>
      </thead>
      <tbody id="evidence-tbody">
        {evidence_html_rows}
      </tbody>
    </table>

    <div class="footer-note">
      <span>Zdroj dat: VFN Ambulantní zprávy (ambu_anonymized.xlsx) & Katalog ÚZIS (kody.xlsx)</span>
      <span>Generováno: Google Vertex AI Model Gemini 3.8 Flash & Addition Suggestions</span>
    </div>
  </div>

  <script>
    let activeRowIndex = 0;

    function getVisibleRows() {{
      return Array.from(document.querySelectorAll('tr.evidence-row')).filter(r => r.style.display !== 'none');
    }}

    function focusRow(index) {{
      const visibleRows = getVisibleRows();
      if (visibleRows.length === 0) return;
      
      if (index < 0) index = 0;
      if (index >= visibleRows.length) index = visibleRows.length - 1;
      
      document.querySelectorAll('tr.evidence-row.active-row').forEach(r => r.classList.remove('active-row'));
      
      const targetRow = visibleRows[index];
      targetRow.classList.add('active-row');
      activeRowIndex = index;
      
      targetRow.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    }}

    async function saveDecision(reviewId, action, triggerEl, autoAdvance = false) {{
      let row = triggerEl ? triggerEl.closest('tr.evidence-row') : document.getElementById('rev-row-' + reviewId);
      if (!row) return;

      const badgeEl = row.querySelector('.status-badge');
      if (badgeEl) {{
        badgeEl.className = 'status-badge status-saving';
        badgeEl.textContent = '⏳ UKLÁDÁM...';
      }}

      try {{
        const res = await fetch('/api/save_review_decision', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ review_id: parseInt(reviewId), action: action }})
        }});
        
        if (res.ok) {{
          row.setAttribute('data-status', action);
          if (badgeEl) {{
            if (action === 'ACCEPT') {{
              badgeEl.className = 'status-badge status-accepted';
              badgeEl.innerHTML = '✓ PŘIJATO (P)';
            }} else if (action === 'REJECT_PAST') {{
              badgeEl.className = 'status-badge status-past';
              badgeEl.innerHTML = '📜 MINULOST (I)';
            }} else {{
              badgeEl.className = 'status-badge status-rejected';
              badgeEl.innerHTML = '✗ ODMÍTNUTO (O)';
            }}
          }}
          updateCounters();
          
          if (autoAdvance) {{
            focusRow(activeRowIndex + 1);
          }}
        }} else {{
          if (badgeEl) {{
            badgeEl.className = 'status-badge status-error';
            badgeEl.textContent = '❌ CHYBA ULOŽENÍ';
          }}
        }}
      }} catch (err) {{
        console.error(err);
        if (badgeEl) {{
          badgeEl.className = 'status-badge status-error';
          badgeEl.textContent = '❌ CHYBA SÍTĚ';
        }}
      }}
    }}

    function updateCounters() {{
      const rows = Array.from(document.querySelectorAll('tr.evidence-row'));
      let acc = 0, past = 0, rej = 0, pend = 0;
      rows.forEach(r => {{
        const st = r.getAttribute('data-status');
        if (st === 'ACCEPT') acc++;
        else if (st === 'REJECT_PAST') past++;
        else if (st === 'REJECT') rej++;
        else pend++;
      }});
      
      const elAcc = document.getElementById('counter-accepted');
      const elPast = document.getElementById('counter-past');
      const elRej = document.getElementById('counter-rejected');
      const elPend = document.getElementById('counter-pending');
      
      if (elAcc) elAcc.textContent = acc + ' Dnes (P)';
      if (elPast) elPast.textContent = past + ' Minulé (I)';
      if (elRej) elRej.textContent = rej + ' Jiné (O)';
      if (elPend) elPend.textContent = pend + ' Čeká';
    }}

    function applyFilters() {{
      const codeVal = document.getElementById('filter-code').value;
      const statusVal = document.getElementById('filter-status').value;
      
      const rows = document.querySelectorAll('tr.evidence-row');
      rows.forEach(r => {{
        const rCode = r.getAttribute('data-code');
        const rStatus = r.getAttribute('data-status') || 'PENDING';
        
        let matchCode = (codeVal === 'ALL' || rCode === codeVal);
        let matchStatus = (statusVal === 'ALL' || 
                          (statusVal === 'PENDING' && (rStatus !== 'ACCEPT' && rStatus !== 'REJECT_PAST' && rStatus !== 'REJECT')) ||
                          (statusVal === rStatus));
                          
        if (matchCode && matchStatus) {{
          r.style.display = '';
        }} else {{
          r.style.display = 'none';
        }}
      }});
      
      focusRow(0);
    }}

    window.addEventListener('DOMContentLoaded', () => {{
      updateCounters();
      
      document.querySelectorAll('tr.evidence-row').forEach(row => {{
        row.addEventListener('click', function() {{
          const visibleRows = getVisibleRows();
          const idx = visibleRows.indexOf(this);
          if (idx !== -1) {{
            focusRow(idx);
          }}
        }});
      }});

      focusRow(0);
    }});

    window.addEventListener('keydown', function(e) {{
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
      
      const key = e.key.toLowerCase();
      const visibleRows = getVisibleRows();
      if (visibleRows.length === 0) return;
      
      if (key === 'p') {{
        e.preventDefault();
        const currentRow = visibleRows[activeRowIndex];
        if (currentRow) {{
          const revId = currentRow.getAttribute('data-review-id');
          saveDecision(revId, 'ACCEPT', currentRow, true);
        }}
      }} else if (key === 'i') {{
        e.preventDefault();
        const currentRow = visibleRows[activeRowIndex];
        if (currentRow) {{
          const revId = currentRow.getAttribute('data-review-id');
          saveDecision(revId, 'REJECT_PAST', currentRow, true);
        }}
      }} else if (key === 'o') {{
        e.preventDefault();
        const currentRow = visibleRows[activeRowIndex];
        if (currentRow) {{
          const revId = currentRow.getAttribute('data-review-id');
          saveDecision(revId, 'REJECT', currentRow, true);
        }}
      }} else if (e.key === 'ArrowDown') {{
        e.preventDefault();
        focusRow(activeRowIndex + 1);
      }} else if (e.key === 'ArrowUp') {{
        e.preventDefault();
        focusRow(activeRowIndex - 1);
      }}
    }});
  </script>
</body>
</html>
"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Successfully regenerated ADDITION suggestions Evidence Grounding HTML report: '{OUTPUT_HTML}'")

if __name__ == "__main__":
    generate_complete_nejm_summary(show_pending_banner=False)
