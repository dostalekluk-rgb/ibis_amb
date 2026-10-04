import json
import os
import html

GOLD_FILE = "external_validation_gold.json"
RESULTS_FILE = "validation_results.json"
OUTPUT_HTML = "nejm_validation_report.html"

def load_data():
    if not os.path.exists(GOLD_FILE) or not os.path.exists(RESULTS_FILE):
        print("Required JSON files missing.")
        return [], {}
    
    with open(GOLD_FILE, "r", encoding="utf-8") as f:
        gold = json.load(f)
    
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        results = json.load(f)
        
    return gold, results

def format_codes_list(code_objs, type_flag="add"):
    """Format list or dict of code objects into HTML badges."""
    if not code_objs:
        return '<span class="text-muted">—</span>'
    
    if isinstance(code_objs, dict):
        items = list(code_objs.values())
    else:
        items = code_objs
        
    badges = []
    for c in items:
        code_str = str(c.get("code", "")).zfill(5)
        name_str = html.escape(c.get("name", ""))
        reason_str = html.escape(c.get("reason", ""))
        quote_str = html.escape(c.get("verbatim_quote", ""))
        
        badge_cls = "badge-add" if type_flag == "add" else "badge-remove"
        icon = "+" if type_flag == "add" else "-"
        
        tooltip = f"Kód: {code_str} | Název: {name_str}"
        if reason_str:
            tooltip += f"\nDůvod: {reason_str}"
        if quote_str:
            tooltip += f"\nCitace: \"{quote_str}\""
            
        b_html = f'<span class="code-badge {badge_cls}" title="{tooltip}"><strong>{icon} {code_str}</strong> {name_str[:35]}</span>'
        badges.append(b_html)
        
    return "".join(badges)

def format_verbatim_quotes(gt_additions, pred_additions):
    """Format verbatim text quotes for additions into HTML evidence cards."""
    all_add_codes = sorted(list(set(list(gt_additions.keys()) + list(pred_additions.keys()))))
    
    if not all_add_codes:
        return '<span class="text-muted">— (Žádná doplnění)</span>'
        
    quotes_html = []
    for code in all_add_codes:
        m_item = pred_additions.get(code)
        h_item = gt_additions.get(code)
        
        c_name = ""
        if m_item: c_name = m_item.get("name", "")
        elif h_item: c_name = h_item.get("name", "")
        
        m_quote = m_item.get("verbatim_quote", "").strip() if m_item else ""
        h_quote = h_item.get("verbatim_quote", "").strip() if h_item else ""
        
        q_block = f'<div class="verbatim-card"><div class="verbatim-card-header"><span class="verbatim-code-pill">+ {html.escape(code)}</span> <span class="verbatim-code-name">{html.escape(c_name[:35])}</span></div>'
        
        if m_quote and h_quote and m_quote == h_quote:
            q_block += f'<div class="quote-line quote-match"><strong>✓ Shoda citace:</strong> <em>"{html.escape(m_quote)}"</em></div>'
        else:
            if m_quote:
                q_block += f'<div class="quote-line quote-model"><strong>🤖 Model:</strong> <em>"{html.escape(m_quote)}"</em></div>'
            if h_quote:
                q_block += f'<div class="quote-line quote-human"><strong>👨‍⚕️ Auditor:</strong> <em>"{html.escape(h_quote)}"</em></div>'
            if not m_quote and not h_quote:
                q_block += f'<div class="quote-line text-muted"><em>(Citace neudána)</em></div>'
            
        q_block += '</div>'
        quotes_html.append(q_block)
        
    return "".join(quotes_html)

def generate_html():
    gold_data, results_data = load_data()
    if not gold_data:
        print("No gold data found.")
        return

    # Calculate metrics
    total_cases = len(gold_data)
    tp, fp, fn = 0, 0, 0
    perfect_matches = 0

    table_rows_html = []

    for idx, item in enumerate(gold_data):
        rep_id = str(item["report_id"])
        date_str = html.escape(item.get("date_str") or "—")
        time_str = html.escape(item.get("time_str") or "—")
        codes_raw = html.escape(item.get("codes_raw") or "Žádné")
        text_content = html.escape(item.get("text") or "")
        
        # Human Gold Standard
        gt = item.get("ground_truth_target", {})
        gt_additions = {str(c["code"]).zfill(5): c for c in gt.get("doporučení_k_doplnění", [])}
        gt_removals = {str(c["code"]).zfill(5): c for c in gt.get("doporučení_k_odebrání", [])}
        
        # Model Prediction
        res_item = results_data.get(rep_id, {})
        pred_additions = res_item.get("pred_additions", {})
        pred_removals = res_item.get("pred_removals", {})
        
        # Evaluate TP, FP, FN for additions
        item_tp = 0
        item_fp = 0
        item_fn = 0
        for p_code in pred_additions:
            if p_code in gt_additions:
                item_tp += 1
            else:
                item_fp += 1
        for g_code in gt_additions:
            if g_code not in pred_additions:
                item_fn += 1
                
        tp += item_tp
        fp += item_fp
        fn += item_fn
        
        # Check match status
        add_match = (set(pred_additions.keys()) == set(gt_additions.keys()))
        rem_match = (set(pred_removals.keys()) == set(gt_removals.keys()))
        
        if add_match and rem_match:
            match_status_html = '<span class="status-pill status-exact">✓ PŘESNÁ SHODA</span>'
            perfect_matches += 1
            match_cls = "row-exact"
        elif item_tp > 0:
            match_status_html = '<span class="status-pill status-partial">~ ČÁSTEČNÁ SHODA</span>'
            match_cls = "row-partial"
        else:
            match_status_html = '<span class="status-pill status-diff">⚠ ODCHYLKA</span>'
            match_cls = "row-diff"

        human_add_html = format_codes_list(gt_additions, "add")
        human_rem_html = format_codes_list(gt_removals, "remove")
        
        model_add_html = format_codes_list(pred_additions, "add")
        model_rem_html = format_codes_list(pred_removals, "remove")

        verbatim_quotes_html = format_verbatim_quotes(gt_additions, pred_additions)

        # Format IS raw codes into pills
        is_codes_html = ""
        if item.get("codes_raw"):
            raw_split = [c.strip() for c in item["codes_raw"].split(",") if c.strip()]
            for rc in raw_split:
                is_codes_html += f'<span class="is-code-pill">{html.escape(rc)}</span>'
        else:
            is_codes_html = '<span class="text-muted">—</span>'

        row = f"""
        <tr class="{match_cls}" data-rep-id="{rep_id}" data-match="{match_cls}">
            <td class="col-id">
                <div class="case-number">#{idx + 1}</div>
                <div class="report-id">ID {rep_id}</div>
                <div class="case-date">{date_str} <span class="case-time">{time_str}</span></div>
            </td>
            <td class="col-is">
                {is_codes_html}
            </td>
            <td class="col-human">
                <div class="section-sublabel">Doplnění (+):</div>
                <div class="badge-group">{human_add_html}</div>
                <div class="section-sublabel mt-1">Odebrání (-):</div>
                <div class="badge-group">{human_rem_html}</div>
            </td>
            <td class="col-model">
                <div class="section-sublabel">Doplnění (+):</div>
                <div class="badge-group">{model_add_html}</div>
                <div class="section-sublabel mt-1">Odebrání (-):</div>
                <div class="badge-group">{model_rem_html}</div>
            </td>
            <td class="col-verbatim">
                {verbatim_quotes_html}
            </td>
            <td class="col-status">
                {match_status_html}
                <button class="btn-toggle-text" onclick="toggleText('{rep_id}')">Text zprávy ▼</button>
            </td>
        </tr>
        <tr id="text-row-{rep_id}" class="text-detail-row" style="display: none;">
            <td colspan="6">
                <div class="text-detail-container">
                    <div class="text-detail-header">📄 Lékařská zpráva (ID {rep_id}):</div>
                    <div class="text-detail-body">{text_content}</div>
                </div>
            </td>
        </tr>
        """
        table_rows_html.append(row)

    prec = (tp / (tp + fp)) * 100 if (tp + fp) > 0 else 0.0
    rec = (tp / (tp + fn)) * 100 if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
    exact_pct = (perfect_matches / total_cases) * 100

    html_content = f"""<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NEJM Clinical Audit - Vertex AI Model Validation (244 Cases)</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Merriweather:ital,wght@0,300;0,400;0,700;1,300&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --nejm-red: #8C1515;
            --nejm-dark-red: #660000;
            --nejm-black: #1A1A1A;
            --nejm-paper: #FCFCFA;
            --nejm-border: #E2E2DC;
            --nejm-gray: #555555;
            --nejm-light-gray: #F4F4F0;
            
            --color-add: #1B7A43;
            --color-add-bg: #EAF6F0;
            --color-add-border: #A3D9B8;
            
            --color-rem: #B91C1C;
            --color-rem-bg: #FDF2F2;
            --color-rem-border: #F87171;
            
            --color-exact-bg: #F0FDF4;
            --color-exact-text: #166534;
            --color-exact-border: #BBF7D0;
            
            --color-partial-bg: #FEFCE8;
            --color-partial-text: #854D0E;
            --color-partial-border: #FEF08A;
            
            --color-diff-bg: #FEF2F2;
            --color-diff-text: #991B1B;
            --color-diff-border: #FECACA;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #F8F8F5;
            color: var(--nejm-black);
            line-height: 1.5;
            padding: 20px;
        }}

        .page-container {{
            max-width: 1400px;
            margin: 0 auto;
            background: #FFFFFF;
            border: 1px solid var(--nejm-border);
            box-shadow: 0 4px 20px rgba(0,0,0,0.05);
            border-radius: 4px;
            overflow: hidden;
        }}

        /* NEJM Masthead */
        header.nejm-masthead {{
            background: #FFFFFF;
            border-bottom: 3px double var(--nejm-red);
            padding: 24px 32px 16px 32px;
            text-align: center;
        }}

        .nejm-journal-title {{
            font-family: 'Merriweather', Georgia, serif;
            font-size: 26px;
            font-weight: 700;
            color: var(--nejm-red);
            letter-spacing: 0.5px;
            text-transform: uppercase;
            margin-bottom: 4px;
        }}

        .nejm-subhead {{
            font-family: 'Merriweather', Georgia, serif;
            font-size: 14px;
            font-style: italic;
            color: var(--nejm-gray);
            margin-bottom: 16px;
        }}

        .article-title {{
            font-family: 'Merriweather', Georgia, serif;
            font-size: 22px;
            font-weight: 700;
            color: var(--nejm-black);
            margin-bottom: 8px;
        }}

        .article-authors {{
            font-size: 13px;
            color: #666666;
            margin-bottom: 20px;
        }}

        /* Executive Metrics Panel */
        .metrics-banner {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            padding: 20px 32px;
            background: #FAF9F6;
            border-bottom: 1px solid var(--nejm-border);
        }}

        .metric-card {{
            background: #FFFFFF;
            border: 1px solid var(--nejm-border);
            border-radius: 6px;
            padding: 16px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }}

        .metric-card .val {{
            font-family: 'Merriweather', serif;
            font-size: 28px;
            font-weight: 700;
            color: var(--nejm-red);
        }}

        .metric-card .lbl {{
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            color: var(--nejm-gray);
            letter-spacing: 0.5px;
            margin-top: 4px;
        }}

        .metric-card .sub {{
            font-size: 11px;
            color: #888888;
            margin-top: 2px;
        }}

        /* Toolbar Controls */
        .toolbar {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            padding: 16px 32px;
            background: #FFFFFF;
            border-bottom: 1px solid var(--nejm-border);
        }}

        .search-box {{
            flex: 1;
            min-width: 280px;
            position: relative;
        }}

        .search-box input {{
            width: 100%;
            padding: 10px 14px 10px 36px;
            font-size: 14px;
            border: 1px solid var(--nejm-border);
            border-radius: 4px;
            outline: none;
            transition: border-color 0.2s;
        }}

        .search-box input:focus {{
            border-color: var(--nejm-red);
        }}

        .search-icon {{
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: #888888;
            font-size: 14px;
        }}

        .filter-buttons {{
            display: flex;
            gap: 8px;
        }}

        .btn-filter {{
            padding: 8px 14px;
            font-size: 13px;
            font-weight: 500;
            background: #FFFFFF;
            border: 1px solid var(--nejm-border);
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .btn-filter:hover {{
            background: var(--nejm-light-gray);
        }}

        .btn-filter.active {{
            background: var(--nejm-red);
            color: #FFFFFF;
            border-color: var(--nejm-red);
        }}

        /* Main Data Table */
        .table-responsive {{
            overflow-x: auto;
        }}

        table.nejm-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }}

        table.nejm-table th {{
            font-family: 'Merriweather', serif;
            font-size: 13px;
            font-weight: 700;
            color: var(--nejm-black);
            background: #F4F4F0;
            padding: 14px 16px;
            border-bottom: 2px solid var(--nejm-border);
            border-top: 1px solid var(--nejm-border);
        }}

        table.nejm-table td {{
            padding: 14px 16px;
            border-bottom: 1px solid var(--nejm-border);
            vertical-align: top;
        }}

        table.nejm-table tr:nth-child(4n+1) {{
            background-color: #FFFFFF;
        }}

        table.nejm-table tr:nth-child(4n+3) {{
            background-color: #FAF9F6;
        }}

        /* Columns Widths & Styling */
        .col-id {{ width: 110px; }}
        .col-is {{ width: 120px; }}
        .col-human {{ width: 230px; }}
        .col-model {{ width: 230px; }}
        .col-verbatim {{ width: 380px; }}
        .col-status {{ width: 140px; text-align: right; }}

        .verbatim-card {{
            background: #FBFBF9;
            border: 1px solid #E5E5E0;
            border-left: 3px solid var(--nejm-red);
            border-radius: 4px;
            padding: 6px 8px;
            margin-bottom: 6px;
            font-size: 12px;
        }}

        .verbatim-card-header {{
            margin-bottom: 3px;
            font-size: 11px;
        }}

        .verbatim-code-pill {{
            font-weight: 700;
            color: var(--color-add);
            background: var(--color-add-bg);
            border: 1px solid var(--color-add-border);
            padding: 1px 5px;
            border-radius: 3px;
            font-family: monospace;
        }}

        .verbatim-code-name {{
            color: var(--nejm-black);
            font-weight: 600;
        }}

        .quote-line {{
            font-family: 'Georgia', serif;
            font-size: 11.5px;
            color: #333333;
            margin-top: 3px;
            line-height: 1.35;
        }}

        .quote-line em {{
            color: #1A202C;
            background: #FFFBEB;
            padding: 1px 4px;
            border-radius: 2px;
        }}

        .quote-match em {{
            background: #F0FDF4;
            color: #166534;
        }}

        .quote-model strong {{
            color: #2563EB;
        }}

        .quote-human strong {{
            color: #D97706;
        }}

        .case-number {{
            font-weight: 700;
            color: var(--nejm-red);
            font-size: 14px;
        }}

        .report-id {{
            font-size: 12px;
            color: var(--nejm-gray);
            margin-top: 2px;
        }}

        .case-date {{
            font-size: 11px;
            color: #888888;
            margin-top: 4px;
        }}

        .case-time {{
            font-weight: 500;
        }}

        .is-code-pill {{
            display: inline-block;
            background: #EBF8FF;
            color: #2B6CB0;
            border: 1px solid #BEE3F8;
            padding: 2px 6px;
            font-size: 11px;
            font-weight: 600;
            border-radius: 3px;
            margin-right: 4px;
            margin-bottom: 4px;
            font-family: monospace;
        }}

        .section-sublabel {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: #777777;
            margin-bottom: 4px;
        }}

        .mt-1 {{ margin-top: 6px; }}

        .badge-group {{
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
        }}

        .code-badge {{
            display: inline-block;
            padding: 3px 8px;
            font-size: 11px;
            border-radius: 3px;
            line-height: 1.3;
            cursor: help;
        }}

        .badge-add {{
            background: var(--color-add-bg);
            color: var(--color-add);
            border: 1px solid var(--color-add-border);
        }}

        .badge-remove {{
            background: var(--color-rem-bg);
            color: var(--color-rem);
            border: 1px solid var(--color-rem-border);
        }}

        .status-pill {{
            display: inline-block;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 700;
            border-radius: 4px;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            margin-bottom: 8px;
        }}

        .status-exact {{
            background: var(--color-exact-bg);
            color: var(--color-exact-text);
            border: 1px solid var(--color-exact-border);
        }}

        .status-partial {{
            background: var(--color-partial-bg);
            color: var(--color-partial-text);
            border: 1px solid var(--color-partial-border);
        }}

        .status-diff {{
            background: var(--color-diff-bg);
            color: var(--color-diff-text);
            border: 1px solid var(--color-diff-border);
        }}

        .btn-toggle-text {{
            display: inline-block;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 500;
            background: #FFFFFF;
            border: 1px solid var(--nejm-border);
            border-radius: 3px;
            cursor: pointer;
            color: var(--nejm-black);
            transition: background 0.15s;
        }}

        .btn-toggle-text:hover {{
            background: var(--nejm-light-gray);
        }}

        /* Text Detail Drawer */
        .text-detail-row td {{
            padding: 0 !important;
            background: #FAFAFA !important;
            border-bottom: 2px solid var(--nejm-border) !important;
        }}

        .text-detail-container {{
            padding: 16px 24px;
            border-left: 4px solid var(--nejm-red);
            background: #FDFDFB;
        }}

        .text-detail-header {{
            font-family: 'Merriweather', serif;
            font-size: 13px;
            font-weight: 700;
            color: var(--nejm-red);
            margin-bottom: 8px;
        }}

        .text-detail-body {{
            font-family: 'Georgia', serif;
            font-size: 13px;
            color: #333333;
            white-space: pre-wrap;
            line-height: 1.6;
            background: #FFFFFF;
            padding: 14px;
            border: 1px solid #EAEAEA;
            border-radius: 4px;
        }}

        .text-muted {{ color: #A0A0A0; font-style: italic; }}

        footer.nejm-footer {{
            padding: 24px 32px;
            background: #FAF9F6;
            border-top: 1px solid var(--nejm-border);
            text-align: center;
            font-size: 12px;
            color: var(--nejm-gray);
        }}
    </style>
</head>
<body>

<div class="page-container">
    <!-- NEJM Header -->
    <header class="nejm-masthead">
        <div class="nejm-journal-title">The New England Journal of Medicine</div>
        <div class="nejm-subhead">Clinical Audit & Artificial Intelligence Research Supplement</div>
        <h1 class="article-title">Supervised Fine-Tuning Evaluation: Vertex AI Gemini Model vs. Human Gold Standard</h1>
        <div class="article-authors">VFN General University Hospital Prague • Clinical Audit Dataset (244 Holdout Validation Cases)</div>
    </header>

    <!-- Executive Metrics -->
    <section class="metrics-banner">
        <div class="metric-card">
            <div class="val">{total_cases}</div>
            <div class="lbl">Validační případy</div>
            <div class="sub">100% Holdout sada</div>
        </div>
        <div class="metric-card">
            <div class="val">{prec:.1f} %</div>
            <div class="lbl">Přesnost (Precision)</div>
            <div class="sub">TP: {tp} | FP: {fp}</div>
        </div>
        <div class="metric-card">
            <div class="val">{rec:.1f} %</div>
            <div class="lbl">Senzitivita (Recall)</div>
            <div class="sub">TP: {tp} | FN: {fn}</div>
        </div>
        <div class="metric-card">
            <div class="val">{f1:.1f} %</div>
            <div class="lbl">F1 Score</div>
            <div class="sub">Vyvážený výkon</div>
        </div>
        <div class="metric-card">
            <div class="val">{exact_pct:.1f} %</div>
            <div class="lbl">Přesná Shoda</div>
            <div class="sub">{perfect_matches} z {total_cases} případů</div>
        </div>
    </section>

    <!-- Toolbar -->
    <div class="toolbar">
        <div class="search-box">
            <span class="search-icon">🔍</span>
            <input type="text" id="searchInput" placeholder="Hledat podle kódů (např. 63022), ID zprávy nebo textu..." onkeyup="filterTable()">
        </div>
        <div class="filter-buttons">
            <button class="btn-filter active" onclick="setFilter('all', this)">Vše ({total_cases})</button>
            <button class="btn-filter" onclick="setFilter('row-exact', this)">Přesná shoda ({perfect_matches})</button>
            <button class="btn-filter" onclick="setFilter('row-partial', this)">Částečná shoda</button>
            <button class="btn-filter" onclick="setFilter('row-diff', this)">Odchylka</button>
        </div>
    </div>

    <!-- Data Table -->
    <div class="table-responsive">
        <table class="nejm-table">
            <thead>
                <tr>
                    <th class="col-id">Případ / ID</th>
                    <th class="col-is">Původně v IS</th>
                    <th class="col-human">Lidský Anotátor (Gold Standard)</th>
                    <th class="col-model">Vertex AI Model (SFT)</th>
                    <th class="col-status">Shoda & Detail</th>
                </tr>
            </thead>
            <tbody id="tableBody">
                {"".join(table_rows_html)}
            </tbody>
        </table>
    </div>

    <footer class="nejm-footer">
        © 2026 VFN Praha - Oddělení klinické auditu & výkaznictví. Generováno automatizovaným evaluačním skriptem Vertex AI.
    </footer>
</div>

<script>
    let currentFilter = 'all';

    function setFilter(filterType, btn) {{
        currentFilter = filterType;
        document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        filterTable();
    }}

    function filterTable() {{
        const searchVal = document.getElementById('searchInput').value.toLowerCase().strip();
        const mainRows = document.querySelectorAll('tbody tr[data-rep-id]');

        mainRows.forEach(row => {{
            const matchType = row.getAttribute('data-match');
            const repId = row.getAttribute('data-rep-id');
            const textRow = document.getElementById('text-row-' + repId);

            const rowText = row.innerText.toLowerCase();
            const textContent = textRow ? textRow.innerText.toLowerCase() : '';
            const combinedText = rowText + ' ' + textContent;

            const matchesSearch = combinedText.includes(searchVal);
            const matchesFilter = (currentFilter === 'all' || matchType === currentFilter);

            if (matchesSearch && matchesFilter) {{
                row.style.display = '';
            }} else {{
                row.style.display = 'none';
                if (textRow) textRow.style.display = 'none';
            }}
        }});
    }}

    function toggleText(repId) {{
        const textRow = document.getElementById('text-row-' + repId);
        if (textRow) {{
            if (textRow.style.display === 'none') {{
                textRow.style.display = '';
            }} else {{
                textRow.style.display = 'none';
            }}
        }}
    }}
</script>

</body>
</html>
"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"NEJM HTML Validation Report generated successfully at: {OUTPUT_HTML}")

if __name__ == "__main__":
    generate_html()
