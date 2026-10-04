import datetime

FIXED_CZECH_HOLIDAYS = {
    (1, 1): "Nový rok / Den obnovy samostatného českého státu",
    (5, 1): "Svátek práce",
    (5, 8): "Den vítězství",
    (7, 5): "Den slovanských věrozvěstů Cyrila a Metoděje",
    (7, 6): "Den upálení mistra Jana Husa",
    (9, 28): "Den české státnosti",
    (10, 28): "Den vzniku samostatného československého státu",
    (11, 17): "Den boje za svobodu a demokracii",
    (12, 24): "Štědrý den",
    (12, 25): "1. svátek vánoční",
    (12, 26): "2. svátek vánoční"
}

def get_easter_sunday(year: int) -> datetime.date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)

def is_czech_holiday(dt_date: datetime.date):
    key = (dt_date.month, dt_date.day)
    if key in FIXED_CZECH_HOLIDAYS:
        return True, FIXED_CZECH_HOLIDAYS[key]

    easter_sun = get_easter_sunday(dt_date.year)
    good_friday = easter_sun - datetime.timedelta(days=2)
    easter_mon = easter_sun + datetime.timedelta(days=1)
    
    if dt_date == good_friday:
        return True, "Velký pátek (státní svátek)"
    if dt_date == easter_mon:
        return True, "Velikonoční pondělí (státní svátek)"
        
    return False, ""

def get_temporal_code_suggestions(date_str: str, time_str: str, existing_codes: list) -> list:
    """
    Evaluates temporal/calendar codes (09580, 09581, 09545) based on date, time, working hours and holidays.
    Returns list of suggested codes if NOT already present in existing_codes.
    """
    suggestions = []
    if not date_str or not time_str or pd_isna(date_str) or pd_isna(time_str):
        return suggestions
        
    try:
        # Format date 'DD.MM.YYYY'
        d_parts = [int(x) for x in str(date_str).strip().split('.')]
        t_parts = [int(x) for x in str(time_str).strip().split(':')]
        
        dt_date = datetime.date(d_parts[2], d_parts[1], d_parts[0])
        dt_time = datetime.time(t_parts[0], t_parts[1], t_parts[2] if len(t_parts)>2 else 0)
        
        is_hol, hol_name = is_czech_holiday(dt_date)
        is_weekend = dt_date.weekday() >= 5  # Saturday or Sunday
        
        # Working hours defined as 07:00 to 16:00 on business days
        is_after_hours = dt_time.hour >= 16 or dt_time.hour < 7
        
        existing_set = set(str(c).strip().zfill(5) for c in existing_codes)
        
        reasons = []
        if is_hol: reasons.append(f"Státní svátek ({hol_name})")
        if is_weekend: reasons.append(f"Víkend ({'Sobota' if dt_date.weekday()==5 else 'Neděle'})")
        if is_after_hours: reasons.append(f"Čas vyšetření {time_str} (mimo běžnou prac. dobu 07:00-16:00)")
        
        reason_str = ", ".join(reasons)
        
        # 09580: Bonifikační výkon za práci o svátcích, víkendech a v noci
        if (is_hol or is_weekend or is_after_hours) and "09580" not in existing_set:
            suggestions.append({
                "code": "09580",
                "name": "Bonifikační výkon za práci o svátcích, víkendech a v noci",
                "source": "ČASOVÉ PRAVIDLO",
                "reasoning": reason_str,
                "verbatim_quote": f"Datum: {date_str}, Čas: {time_str} ({reason_str})",
                "confidence": 1.0
            })
            
        # 09581: Péče ambulantního specialisty mimo běžnou pracovní dobu
        if (is_after_hours or is_weekend or is_hol) and "09581" not in existing_set:
            suggestions.append({
                "code": "09581",
                "name": "Péče ambulantního specialisty mimo běžnou pracovní dobu",
                "source": "ČASOVÉ PRAVIDLO",
                "reasoning": reason_str,
                "verbatim_quote": f"Datum: {date_str}, Čas: {time_str} ({reason_str})",
                "confidence": 1.0
            })
            
        # 09545: Regulační poplatek za pohotovostní službu - poplatek uhrazen
        if (is_after_hours or is_weekend or is_hol) and "09545" not in existing_set:
            suggestions.append({
                "code": "09545",
                "name": "Regulační poplatek za pohotovostní službu - poplatek uhrazen",
                "source": "ČASOVÉ PRAVIDLO",
                "reasoning": reason_str,
                "verbatim_quote": f"Datum: {date_str}, Čas: {time_str} ({reason_str})",
                "confidence": 1.0
            })
            
    except Exception as e:
        pass
        
    return suggestions

def pd_isna(val):
    return val is None or str(val).lower() == 'nan' or str(val).strip() == ''
