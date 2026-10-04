import json
import os
import re
import sqlite3
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd

from temporal_rules import get_temporal_code_suggestions, is_czech_holiday

DB_FILE = "validator_data.db"
AMBU_FILE = "ambu_anonymized.xlsx"
KODY_FILE = "kody.xlsx"

TEMPORAL_CODES = {"09545", "09580", "09581"}
EXCLUDED_CODES = {"09557"}  # Věkově vymezené kódy (v anonymizovaných zprávách schází věk pacientky)

app = FastAPI(title="VFN Validator - Návrhy doplnění a odebrání kódů", version="3.1.0")

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY,
        row_idx INTEGER UNIQUE,
        codes_raw TEXT,
        date_str TEXT,
        time_str TEXT,
        text TEXT,
        status TEXT DEFAULT 'PENDING'
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER,
        type TEXT, -- 'ADDITION' or 'REMOVAL'
        code TEXT,
        code_name TEXT,
        source TEXT, -- 'ČASOVÉ PRAVIDLO', 'GEMINI BATCH', 'TEXTOVÁ EXTRAKCE'
        exact_text_snippet TEXT,
        reason TEXT,
        confidence REAL,
        FOREIGN KEY(report_id) REFERENCES reports(id)
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER,
        review_id INTEGER,
        code TEXT,
        type TEXT,
        action TEXT, -- 'ACCEPT', 'REJECT'
        validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(report_id) REFERENCES reports(id)
    )
    """)
    
    conn.commit()
    conn.close()


init_db()


def is_out_of_hours_or_holiday(date_str, time_str):
    if not date_str or not time_str:
        return False, ""
    try:
        import datetime
        d_parts = [int(x) for x in str(date_str).strip().split('.')]
        t_parts = [int(x) for x in str(time_str).strip().split(':')]
        dt_date = datetime.date(d_parts[2], d_parts[1], d_parts[0])
        dt_time = datetime.time(t_parts[0], t_parts[1], t_parts[2] if len(t_parts)>2 else 0)
        
        is_hol, hol_name = is_czech_holiday(dt_date)
        is_wkn = dt_date.weekday() >= 5
        is_after_h = dt_time.hour >= 16 or dt_time.hour < 7
        
        if is_hol or is_wkn or is_after_h:
            reasons = []
            if is_hol: reasons.append(hol_name)
            if is_wkn: reasons.append(f"Víkend ({'Sobota' if dt_date.weekday()==5 else 'Neděle'})")
            if is_after_h: reasons.append(f"Čas {time_str} (mimo 07:00-16:00)")
            return True, ", ".join(reasons)
        return False, ""
    except Exception:
        return False, ""


def is_past_history_or_plan(snippet_phrase: str) -> bool:
    if not snippet_phrase:
        return False
    lower_phrase = snippet_phrase.lower()
    
    # 1. Past years check (e.g. 1990-2025)
    if re.search(r'\b(19\d\d|20[0-2][0-5])\b', lower_phrase):
        return True
        
    # 2. History, past state, recommendations, negations keywords
    past_keywords = [
        "anamn", "doporuč", "doporuc", "plán", "plan", "za rok", "za 6", "za 12",
        "před", "pred", "minule", "neodebr", "odmít", "dříve", "st.p.", "st p", 
        "rezidua", "dřívější", "předchozí", "anamnestick", "v minulosti", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025"
    ]
    return any(kw in lower_phrase for kw in past_keywords)


def seed_database(force: bool = False):
    conn = get_db()
    cursor = conn.cursor()
    
    if force:
        cursor.execute("DELETE FROM decisions")
        cursor.execute("DELETE FROM reviews")
        cursor.execute("DELETE FROM reports")
        conn.commit()
    else:
        cursor.execute("SELECT COUNT(*) FROM reports")
        if cursor.fetchone()[0] > 0:
            conn.close()
            return

    print("Initializing DB with reports, Gemini batch predictions, temporal rules, and text extractions...")
    
    kody_catalog = {}
    if os.path.exists(KODY_FILE):
        df_kody = pd.read_excel(KODY_FILE)
        for _, r in df_kody.iterrows():
            c = str(r["Kód"]).strip().zfill(5)
            kody_catalog[c] = {
                "nazev": str(r["Název výkonu"]) if pd.notna(r["Název výkonu"]) else "",
                "obsah_rozsah": str(r["Obsah a rozsah výkonu"]) if pd.notna(r["Obsah a rozsah výkonu"]) else ""
            }
            
    responses_map = {}
    import glob
    resp_files = glob.glob("batch_chunk_*_resp.jsonl") + glob.glob("batch_responses.jsonl")
    for rfile in resp_files:
        if not os.path.exists(rfile):
            continue
        with open(rfile, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                cid = d.get("custom_id") # "row_0"
                try:
                    raw_txt = d["response"]["candidates"][0]["content"]["parts"][0]["text"]
                    evals = json.loads(raw_txt).get("evaluations", [])
                    responses_map[cid] = evals
                except Exception:
                    pass
                    
    df_ambu = pd.read_excel(AMBU_FILE)
    vykony_col = df_ambu.columns[0]
    text_col = df_ambu.columns[1]
    datum_col = df_ambu.columns[2]
    cas_col = df_ambu.columns[3]
    
    inserted_count = 0
    
    for idx, row in df_ambu.iterrows():
        codes_raw = str(row[vykony_col]) if pd.notna(row[vykony_col]) else ""
        text_str = str(row[text_col]) if pd.notna(row[text_col]) else ""
        date_str = str(row[datum_col]) if pd.notna(row[datum_col]) else ""
        time_str = str(row[cas_col]) if pd.notna(row[cas_col]) else ""
        
        if not text_str.strip():
            continue
            
        cursor.execute("""
        INSERT INTO reports (row_idx, codes_raw, date_str, time_str, text, status)
        VALUES (?, ?, ?, ?, ?, 'PENDING')
        """, (idx, codes_raw, date_str, time_str, text_str))
        report_id = cursor.lastrowid
        inserted_count += 1
        
        raw_parts = re.split(r'[, \t]+', codes_raw.replace(';', ','))
        existing_codes = []
        for p in raw_parts:
            p = p.strip()
            if p:
                c = re.sub(r'^\d+x', '', p, flags=re.IGNORECASE).strip().zfill(5)
                if c not in existing_codes:
                    existing_codes.append(c)
                    
        custom_id = f"row_{idx}"
        evals = responses_map.get(custom_id, [])
        
        is_out_hours, out_reason = is_out_of_hours_or_holiday(date_str, time_str)
        
        # 1. REMOVALS (Nadbytečný kód)
        for ev in evals:
            code = str(ev.get("code", "")).strip().zfill(5)
            if code in EXCLUDED_CODES:
                continue
            status = bool(ev.get("status"))
            reason = ev.get("unsupported_reason", "")
            quote = ev.get("verbatim_quote", "")
            conf = float(ev.get("confidence", 0.9))
            
            # CRITICAL RULE: Ignore LLM text-based removal for temporal codes (09545, 09580, 09581)!
            if code in TEMPORAL_CODES:
                # Only remove temporal code if it was reported DURING regular working hours on a non-holiday!
                if not is_out_hours:
                    k_info = kody_catalog.get(code, {"nazev": "Výkon", "obsah_rozsah": ""})
                    cursor.execute("""
                    INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
                    VALUES (?, 'REMOVAL', ?, ?, 'ČASOVÉ PRAVIDLO', ?, 'Kód vykázán v běžné pracovní době (nepohotovost)', 1.0)
                    """, (report_id, code, k_info["nazev"], f"Vyšetření v běžné pracovní době ({date_str} {time_str})"))
            else:
                if not status:
                    k_info = kody_catalog.get(code, {"nazev": "Výkon", "obsah_rozsah": ""})
                    exact_snippet = quote if quote else f"V textu chybí zmínka nebo podklad (důvod: {reason or 'nedoloženo'})"
                    
                    cursor.execute("""
                    INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
                    VALUES (?, 'REMOVAL', ?, ?, 'GEMINI BATCH', ?, ?, ?)
                    """, (report_id, code, k_info["nazev"], exact_snippet, reason or "Kód vykázán nadbytečně", conf))
                
        # 2. ADDITIONS via Temporal Rules (09580, 09581, 09545)
        temp_suggs = get_temporal_code_suggestions(date_str, time_str, existing_codes)
        for ts in temp_suggs:
            cursor.execute("""
            INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
            VALUES (?, 'ADDITION', ?, ?, 'ČASOVÉ PRAVIDLO', ?, ?, ?)
            """, (report_id, ts["code"], ts["name"], ts["verbatim_quote"], ts["reasoning"], ts["confidence"]))
        # 3. ADDITIONS via Textual Evidence
        lower_txt = text_str.lower()
        
        if "uz:" in lower_txt or "ultrazvuk" in lower_txt:
            if "63417" not in existing_codes:
                match = re.search(r'(uz:[^\.\n]+|ultrazvuk[^\.\n]+)', text_str, re.IGNORECASE)
                if match:
                    exact_snippet = match.group(0).strip()
                    if not is_past_history_or_plan(exact_snippet):
                        cursor.execute("""
                        INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
                        VALUES (?, 'ADDITION', '63417', 'Ultrasonografické vyšetření pánve', 'TEXTOVÁ EXTRAKCE', ?, 'V textu popsáno UZ vyšetření pánve', 0.95)
                        """, (report_id, exact_snippet))

        if "kolposkop" in lower_txt or "kys. octov" in lower_txt:
            if "63063" not in existing_codes:
                match = re.search(r'([^\.\n]*kolposkop[^\.\n]*|[^\.\n]*kys\. octov[^\.\n]*)', text_str, re.IGNORECASE)
                if match:
                    exact_snippet = match.group(0).strip()
                    if not is_past_history_or_plan(exact_snippet):
                        cursor.execute("""
                        INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
                        VALUES (?, 'ADDITION', '63063', 'Kolposkopická expertíza', 'TEXTOVÁ EXTRAKCE', ?, 'V textu popsaný kolposkopický zákrok', 0.92)
                        """, (report_id, exact_snippet))

        # Biopsie z čípku / PB / punch biopsie (Kód 63531)
        biopsy_pat = r'(\bpunch\s*biops[a-ž]*\b|\bpunch\b|provedena\s*pb|odebrána\s*pb|odběr\s*pb|biops[a-ž]*\s*(z\s*)?(čípku|hrdla|cervixu)|exciz[a-ž]*\s*(z\s*)?(čípku|hrdla)|probatorní\s*biops[a-ž]*)'
        if re.search(biopsy_pat, lower_txt, re.IGNORECASE):
            match = re.search(r'([^\.\n]*' + biopsy_pat + r'[^\.\n]*)', text_str, re.IGNORECASE)
            if match:
                snippet_phrase = match.group(0).strip()
                if not is_past_history_or_plan(snippet_phrase) and "63531" not in existing_codes:
                    cursor.execute("""
                    INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
                    VALUES (?, 'ADDITION', '63531', 'Biopsie z čípku děložního', 'TEXTOVÁ EXTRAKCE', ?, 'V textu popsána dnešní biopsie z děložního hrdla / PB (punch biopsie)', 0.96)
                    """, (report_id, snippet_phrase))

        # Odběr cytologie / MOP / stěr z čípku (Kód 63532)
        cyto_pat = r'(\bcytolog[a-ž]*\b|\boncogyn[a-ž]*\b|\bmop\b|stěr\s*z\s*čípku)'
        if re.search(cyto_pat, lower_txt, re.IGNORECASE):
            match = re.search(r'([^\.\n]*' + cyto_pat + r'[^\.\n]*)', text_str, re.IGNORECASE)
            if match:
                snippet_phrase = match.group(0).strip()
                if not is_past_history_or_plan(snippet_phrase) and "63532" not in existing_codes:
                    cursor.execute("""
                    INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
                    VALUES (?, 'ADDITION', '63532', 'Odběr materiálu z pochvy, čípku a hrdla děložního (Cytologie/MOP)', 'TEXTOVÁ EXTRAKCE', ?, 'V textu popsán dnešní odběr cytologie / MOP / stěr z čípku', 0.92)
                    """, (report_id, snippet_phrase))

        # Odběr kultivace / biologického materiálu / HPV (Kód 09115)
        cult_pat = r'(\bkultiva[a-ž]*\b|\bchlamydi[a-ž]*\b|\bhpv\s*typizac[a-ž]*\b|\bhpv\s*odběr\b)'
        if re.search(cult_pat, lower_txt, re.IGNORECASE):
            match = re.search(r'([^\.\n]*' + cult_pat + r'[^\.\n]*)', text_str, re.IGNORECASE)
            if match:
                snippet_phrase = match.group(0).strip()
                if not is_past_history_or_plan(snippet_phrase) and "09115" not in existing_codes:
                    cursor.execute("""
                    INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
                    VALUES (?, 'ADDITION', '09115', 'Odběr biologického materiálu na kvantitativní vyšetření (Kultivace/HPV)', 'TEXTOVÁ EXTRAKCE', ?, 'V textu popsán dnešní odběr na kultivaci / HPV / Chlamydie', 0.91)
                    """, (report_id, snippet_phrase))

        # Extrakce IUD / tělíska (Kód 63555)
        iud_pat = r'(\bextrakce\s*iud\b|\bvytažení\s*tělíska\b|\bextrakce\s*tělíska\b|\bvytažení\s*iud\b)'
        if re.search(iud_pat, lower_txt, re.IGNORECASE):
            match = re.search(r'([^\.\n]*' + iud_pat + r'[^\.\n]*)', text_str, re.IGNORECASE)
            if match:
                snippet_phrase = match.group(0).strip()
                if not is_past_history_or_plan(snippet_phrase) and "63555" not in existing_codes:
                    cursor.execute("""
                    INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
                    VALUES (?, 'ADDITION', '63555', 'Extrakce IUD hákem', 'TEXTOVÁ EXTRAKCE', ?, 'V textu popsána dnešní extrakce IUD / vytažení tělíska', 0.95)
                    """, (report_id, snippet_phrase))

    conn.commit()
    conn.close()
    print(f"Database seeded with {inserted_count} reports and clean review suggestions!")


seed_database()


CONFIG_FILE = "vertex_config.json"

def get_vertex_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "vertex_model_id": "",
        "project_id": "ibis-510508",
        "location": "us-central1",
        "is_active": False,
        "status_message": "Model Vertex AI ibis_amb se aktuálně trénuje nebo není připojen k aplikaci."
    }

def save_vertex_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


class ConnectModelPayload(BaseModel):
    vertex_model_id: str


class SingleReviewDecision(BaseModel):
    review_id: int
    action: str


class DecisionItem(BaseModel):
    review_id: int
    code: str
    type: str  # 'ADDITION' or 'REMOVAL'
    action: str  # 'ACCEPT', 'REJECT'


class ValidationPayload(BaseModel):
    decisions: List[DecisionItem]


# API Routes
@app.get("/api/vertex_status")
def get_vertex_status():
    return get_vertex_config()


@app.post("/api/connect_vertex_model")
def connect_vertex_model(payload: ConnectModelPayload):
    model_id = payload.vertex_model_id.strip()
    if not model_id:
        raise HTTPException(status_code=400, detail="Model ID/Endpoint nesmí být prázdné.")
        
    cfg = get_vertex_config()
    cfg["vertex_model_id"] = model_id
    cfg["is_active"] = True
    cfg["status_message"] = f"Aplikace úspěšně připojena k modelu Vertex AI ({model_id})."
    save_vertex_config(cfg)
    
    return {"status": "success", "config": cfg}


@app.get("/api/stats")
def get_stats():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM reports")
    total_reports = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM reports WHERE status = 'VALIDATED'")
    validated_reports = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM reviews WHERE type = 'ADDITION'")
    total_additions = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM reviews WHERE type = 'REMOVAL'")
    total_removals = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM decisions WHERE action = 'ACCEPT'")
    accepted_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM decisions WHERE action = 'REJECT'")
    rejected_count = cursor.fetchone()[0]
    
    conn.close()
    
    # Batch baseline & counters
    cfg = get_vertex_config()
    batch_start_val = cfg.get("batch_start_validated_count", 1441)
    batch_size = cfg.get("batch_size", 200)
    
    validated_in_batch = max(0, validated_reports - batch_start_val)
    batch_remaining = max(0, batch_size - validated_in_batch)
    
    return {
        "total_reports": total_reports,
        "validated_reports": validated_reports,
        "pending_reports": total_reports - validated_reports,
        "total_additions": total_additions,
        "total_removals": total_removals,
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "validated_since_tuning": validated_in_batch,
        "batch_remaining": batch_remaining,
        "batch_total": batch_size
    }


@app.get("/api/reports")
def get_reports(filter_status: str = "ALL", limit: int = 50, offset: int = 0):
    conn = get_db()
    cursor = conn.cursor()
    
    query = """
    SELECT r.id, r.row_idx, r.codes_raw, r.date_str, r.time_str, substr(r.text, 1, 140) as text_snippet, r.status,
           SUM(CASE WHEN rev.type = 'ADDITION' THEN 1 ELSE 0 END) as addition_count,
           SUM(CASE WHEN rev.type = 'REMOVAL' THEN 1 ELSE 0 END) as removal_count
    FROM reports r
    LEFT JOIN reviews rev ON r.id = rev.report_id
    """
    params = []
    
    if filter_status == "PENDING":
        query += " WHERE r.status = 'PENDING'"
        query += " GROUP BY r.id ORDER BY (CASE WHEN lower(r.text) LIKE '%kolpo%' AND lower(r.text) LIKE '%pb%' THEN 0 ELSE 1 END), r.id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    elif filter_status == "VALIDATED":
        query += " WHERE r.status = 'VALIDATED'"
        query += " GROUP BY r.id ORDER BY r.id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    else:
        query += " GROUP BY r.id ORDER BY r.id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


@app.get("/api/reports/{report_id}")
def get_report_detail(report_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
    report = cursor.fetchone()
    
    if not report:
        conn.close()
        raise HTTPException(status_code=404, detail="Report not found")
        
    cursor.execute("SELECT * FROM reviews WHERE report_id = ?", (report_id,))
    reviews = [dict(r) for r in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM decisions WHERE report_id = ?", (report_id,))
    decisions = [dict(d) for d in cursor.fetchall()]
    
    conn.close()
    
    return {
        "report": dict(report),
        "reviews": reviews,
        "decisions": decisions
    }


class ManualReviewPayload(BaseModel):
    report_id: int
    code: str
    type: str = "ADDITION"
    reason: Optional[str] = "Ručně doplněno auditorem"

@app.post("/api/add_manual_review")
def add_manual_review(payload: ManualReviewPayload):
    code_clean = str(payload.code).strip().zfill(5)
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM reports WHERE id = ?", (payload.report_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Report not found")
        
    k_name = "Zdravotní výkon"
    if os.path.exists(KODY_FILE):
        try:
            df_kody = pd.read_excel(KODY_FILE)
            for _, r in df_kody.iterrows():
                if str(r["Kód"]).strip().zfill(5) == code_clean:
                    k_name = str(r["Název výkonu"]) if pd.notna(r["Název výkonu"]) else "Zdravotní výkon"
                    break
        except Exception:
            pass

    cursor.execute("""
    INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
    VALUES (?, ?, ?, ?, 'MANUÁLNÍ DOPLNĚNÍ', '', ?, 1.0)
    """, (payload.report_id, payload.type, code_clean, k_name, payload.reason or "Ručně doplněno auditorem"))
    
    review_id = cursor.lastrowid
    
    cursor.execute("DELETE FROM decisions WHERE review_id = ?", (review_id,))
    cursor.execute("""
    INSERT INTO decisions (report_id, review_id, code, type, action)
    VALUES (?, ?, ?, ?, 'ACCEPT')
    """, (payload.report_id, review_id, code_clean, payload.type))
    
    cursor.execute("UPDATE reports SET status = 'VALIDATED' WHERE id = ?", (payload.report_id,))
    conn.commit()
    conn.close()
    
    return {"status": "success", "review_id": review_id, "code": code_clean, "code_name": k_name}


@app.post("/api/save_review_decision")
def save_review_decision(payload: SingleReviewDecision):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT report_id, code, type FROM reviews WHERE id = ?", (payload.review_id,))
    rev = cursor.fetchone()
    if not rev:
        conn.close()
        raise HTTPException(status_code=404, detail="Review not found")
        
    cursor.execute("DELETE FROM decisions WHERE review_id = ?", (payload.review_id,))
    cursor.execute("""
    INSERT INTO decisions (report_id, review_id, code, type, action)
    VALUES (?, ?, ?, ?, ?)
    """, (rev["report_id"], payload.review_id, rev["code"], rev["type"], payload.action))
    
    cursor.execute("UPDATE reports SET status = 'VALIDATED' WHERE id = ?", (rev["report_id"],))
    conn.commit()
    conn.close()
    return {"status": "success", "review_id": payload.review_id, "action": payload.action}


@app.post("/api/reports/{report_id}/validate")
@app.post("/api/validate_report/{report_id}")
def validate_report(report_id: int, payload: ValidationPayload):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM reports WHERE id = ?", (report_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Report not found")
        
    cursor.execute("DELETE FROM decisions WHERE report_id = ?", (report_id,))
    
    for item in payload.decisions:
        cursor.execute("""
        INSERT INTO decisions (report_id, review_id, code, type, action)
        VALUES (?, ?, ?, ?, ?)
        """, (report_id, item.review_id, item.code, item.type, item.action))
        
    cursor.execute("UPDATE reports SET status = 'VALIDATED' WHERE id = ?", (report_id,))
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": f"Report {report_id} validated successfully!"}


@app.get("/api/export_gold_dataset")
def export_gold_dataset():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT r.id, r.row_idx, r.text, r.date_str, r.time_str, rev.type, rev.code, rev.code_name, rev.exact_text_snippet, d.action
    FROM decisions d
    JOIN reviews rev ON d.review_id = rev.id
    JOIN reports r ON d.report_id = r.id
    WHERE r.status = 'VALIDATED'
    """)
    rows = cursor.fetchall()
    conn.close()
    
    output_lines = []
    for r in rows:
        act = r["action"]
        status_bool = True if act == 'ACCEPT' else False
        reason_str = None
        if act == 'REJECT_PAST':
            reason_str = "anamnesticky_udaj_z_minulosti_st_p"
        elif act == 'REJECT':
            reason_str = "zcela_chybi_zminka_nebo_jiny_duvod"
            
        item = {
            "report_id": r["id"],
            "row_idx": r["row_idx"],
            "text": r["text"],
            "date": r["date_str"],
            "time": r["time_str"],
            "review_type": r["type"],
            "code": r["code"],
            "code_name": r["code_name"],
            "exact_snippet": r["exact_text_snippet"],
            "doctor_action": act,
            "status": status_bool,
            "unsupported_reason": reason_str
        }
        output_lines.append(json.dumps(item, ensure_ascii=False))
        
    gold_file = "gold_dataset_vertex.jsonl"
    with open(gold_file, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
        
    return {
        "status": "success",
        "file": gold_file,
        "count": len(output_lines),
        "message": f"Gold standard dataset exported to '{gold_file}' with {len(output_lines)} validated decisions."
    }


@app.get("/", response_class=HTMLResponse)
def index_html():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/nejm_table", response_class=HTMLResponse)
def nejm_table_html():
    if os.path.exists("summary_table_nejm.html"):
        with open("summary_table_nejm.html", "r", encoding="utf-8") as f:
            return f.read()
    return "HTML tabulka nebyla nalezena."


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
