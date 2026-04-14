import json

def generate_table():
    try:
        with open("brand_scan_report.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return f"Hata: {str(e)}"

    lines = []
    lines.append("# 📊 Gelişmiş Marka Tarama Analiz Raporu")
    lines.append("\nHatalı etiketlendiği tespit edilen **66** kampanya ve detaylı analizleri aşağıdadır:")
    lines.append("\n| Kampanya ID | Başlık | Tespit Edilen Hatalı Markalar | Neden |")
    lines.append("| :--- | :--- | :--- | :--- |")

    for item in data:
        brands = []
        reasons = []
        
        if item.get("removals_negation"):
            brands.extend(item["removals_negation"])
            reasons.append("Dahil Değildir / Kısıtlı Metin")
        
        if item.get("removals_noise"):
            brands.extend(item["removals_noise"])
            reasons.append("Gürültü (Marka Değil)")
            
        brands_str = ", ".join(brands)
        reason_str = " / ".join(reasons)
        
        # Clean title for markdown table
        title = item["title"].replace("|", "\\|")
        # Truncate title if too long for readability
        if len(title) > 60:
            title = title[:57] + "..."
            
        lines.append(f"| **{item['id']}** | {title} | {brands_str} | {reason_str} |")

    return "\n".join(lines)

if __name__ == "__main__":
    report_content = generate_table()
    with open("brand_tag_report.md", "w", encoding="utf-8") as f:
        f.write(report_content)
    print("Rapor başarıyla oluşturuldu: brand_tag_report.md")
