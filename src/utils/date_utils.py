import re

_TR_MONTHS = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan",
    5: "Mayıs", 6: "Haziran", 7: "Temmuz", 8: "Ağustos",
    9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
}

def update_dates_in_text(text: str, old_end_date, new_end_date) -> str:
    if not text or not old_end_date or not new_end_date:
        return text

    old_day   = old_end_date.day
    old_month = old_end_date.month
    old_year  = old_end_date.year
    new_day   = new_end_date.day
    new_month = new_end_date.month
    new_year  = new_end_date.year

    old_month_tr = _TR_MONTHS[old_month]
    new_month_tr = _TR_MONTHS[new_month]

    result = text

    # 1. ISO format: 2026-06-08 -> 2026-07-09
    result = result.replace(
        f"{old_year}-{old_month:02d}-{old_day:02d}",
        f"{new_year}-{new_month:02d}-{new_day:02d}"
    )

    # 2. Noktalı format: 08.06.2026 -> 09.07.2026
    result = result.replace(
        f"{old_day:02d}.{old_month:02d}.{old_year}",
        f"{new_day:02d}.{new_month:02d}.{new_year}"
    )
    result = result.replace(
        f"{old_day}.{old_month}.{old_year}",
        f"{new_day}.{new_month}.{new_year}"
    )

    # 3. Türkçe format: "8 Haziran 2026" veya "8 Haziran" -> "9 Temmuz 2026" / "9 Temmuz"
    if old_month_tr != new_month_tr or old_day != new_day or old_year != new_year:
        result = re.sub(
            rf'\b{old_day}\s+{old_month_tr}\s+{old_year}\b',
            f"{new_day} {new_month_tr} {new_year}",
            result, flags=re.IGNORECASE
        )
        result = re.sub(
            rf'\b{old_day}\s+{old_month_tr}\b(?!\s+\d{{4}})',
            f"{new_day} {new_month_tr}",
            result, flags=re.IGNORECASE
        )
        if old_month != new_month:
            result = re.sub(
                rf'\b{old_month_tr}\b',
                new_month_tr,
                result, flags=re.IGNORECASE
            )

    return result
