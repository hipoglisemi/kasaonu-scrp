import psycopg2
from psycopg2.extras import RealDictCursor
import os

DATABASE_URL = "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"

def generate_markdown_audit_report():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # 29 Mayıs 18:00'den beri güncellenen kampanyaları sorgula
    cur.execute("""
        SELECT DISTINCT ON (c.id)
            c.id, 
            c.title, 
            c.start_date, 
            c.end_date, 
            c.tracking_url, 
            c.is_active, 
            c.is_approved, 
            c.date_extended, 
            c.updated_at,
            c.clean_text,
            c.repair_count,
            b.name as bank_name
        FROM campaigns c
        JOIN cards card ON c.card_id = card.id
        JOIN banks b ON card.bank_id = b.id
        LEFT JOIN campaign_audit_log log ON log.campaign_id = c.id
        WHERE 
            (c.updated_at >= '2026-05-29 18:00:00') AND (
                c.date_extended = True 
                OR c.repair_count > 0
                OR (log.created_at >= '2026-05-29 18:00:00' AND log.field_name = 'end_date')
            )
        ORDER BY c.id, c.updated_at DESC
    """)
    campaigns = cur.fetchall()
    
    # Rapor dosya yolu
    report_path = "/Users/hipoglisemi/.gemini/antigravity/artifacts/audit_report.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 🕵️‍♂️ Kartavantaj Proaktif Tarih ve Güncellik Denetim Raporu\n\n")
        f.write(f"Bu rapor, **29 Mayıs 2026 18:00** tarihinden bugüne kadar sistemde cleanup betikleri veya scraper'lar aracılığıyla tarihi uzatılan, canlandırılan veya AI tarafından yeniden parse edilen **toplam {len(campaigns)} kampanyayı** listeler. Her bir kampanya verisinin güncelliği ve doğruluk analizi bu rapordan manuel olarak takip edilebilir.\n\n")
        
        f.write("## 🚨 KRİTİK VE ŞÜPHELİ KAMPANYALAR (İlk İncelenmesi Gerekenler)\n")
        f.write("Aşağıdaki kampanyalar, `date_extended=True` (otomatik uzatılmış) olan veya bitiş tarihleri bir anda yıl sonuna (`2026-12-31`) ötelenmiş olan yüksek öncelikli denetim adaylarıdır.\n\n")
        
        suspicious_count = 0
        all_campaign_details = []
        
        for idx, camp in enumerate(campaigns):
            # Değişim loglarını çek
            cur.execute("""
                SELECT old_value, new_value, created_at, auto_fixed 
                FROM campaign_audit_log 
                WHERE campaign_id = %s AND field_name = 'end_date' AND created_at >= '2026-05-29 18:00:00'
                ORDER BY created_at DESC
            """, (camp['id'],))
            logs = cur.fetchall()
            
            clean_text = camp['clean_text'] or ""
            date_hints = []
            for line in clean_text.split('\n'):
                line_lower = line.lower()
                if any(kw in line_lower for kw in ['tarihine kadar', 'kampanya dönemi', 'son gün', 'geçerlidir', 'aralık 2026', 'haziran 2026', 'temmuz 2026']):
                    date_hints.append(line.strip())
            
            # Şüphelilik analizi
            is_suspicious = False
            reasons = []
            
            if camp['date_extended']:
                is_suspicious = True
                reasons.append("Otomatik Tarihi Uzatılmış (`date_extended=True`)")
                
            if camp['end_date'] and str(camp['end_date']).endswith('12-31'):
                # Yıl sonuna uzatılanlar her zaman mercek altında olmalı
                is_suspicious = True
                reasons.append("Yıl Sonuna Ötelenmiş (`12-31`)")
                
            if not logs and camp['repair_count'] > 5:
                is_suspicious = True
                reasons.append("Tarih Logu Yok ve Repair Count Yüksek (>5)")
                
            camp_detail = {
                "id": camp['id'],
                "title": camp['title'],
                "bank_name": camp['bank_name'],
                "start_date": camp['start_date'],
                "end_date": camp['end_date'],
                "url": camp['tracking_url'],
                "is_active": camp['is_active'],
                "is_approved": camp['is_approved'],
                "extended": camp['date_extended'],
                "repairs": camp['repair_count'],
                "updated_at": camp['updated_at'],
                "logs": logs,
                "hints": date_hints[:3],
                "is_suspicious": is_suspicious,
                "reasons": reasons
            }
            all_campaign_details.append(camp_detail)
            
            if is_suspicious:
                suspicious_count += 1
                f.write(f"### 🛑 [{camp['bank_name']}] {camp['title']} (ID: #{camp['id']})\n")
                f.write(f"- **Canlı URL:** [{camp['tracking_url']}]({camp['tracking_url']})\n")
                f.write(f"- **Mevcut DB Tarihi:** `{camp['start_date']}` ➔ `{camp['end_date']}`\n")
                f.write(f"- **Durum:** `Active={camp['is_active']}` | `Approved={camp['is_approved']}` | `Repairs={camp['repair_count']}`\n")
                f.write(f"- **Şüphe Gerekçeleri:** {', '.join(reasons)}\n")
                
                if logs:
                    f.write("- **Tarih Değişim Tarihçesi:**\n")
                    for l in logs:
                        f.write(f"  - `{l['created_at']}`: `{l['old_value']}` ➔ `{l['new_value']}` (Auto-Fixed: {l['auto_fixed']})\n")
                else:
                    f.write("- **Tarih Değişim Tarihçesi:** Bulunamadı (Doğrudan scraper/override güncellemesi).\n")
                
                if date_hints:
                    f.write("- **Sayfa Metnindeki Tarih İpuçları:**\n")
                    for hint in date_hints[:3]:
                        f.write(f"  - *\"{hint[:150]}\"*\n")
                f.write("\n" + "-"*40 + "\n\n")
                
        f.write(f"## 📋 TÜM GÜNCELLENEN KAMPANYALARIN LİSTESİ (Toplam: {len(campaigns)})\n\n")
        f.write("| ID | Banka | Kampanya Başlığı | Başlangıç | Bitiş | Aktif mi | Onaylı mı | Uzatıldı mı | Şüpheli mi |\n")
        f.write("|---|---|---|---|---|---|---|---|---|\n")
        
        for c in all_campaign_details:
            susp_emoji = "🛑 EVET" if c['is_suspicious'] else "✅ Temiz"
            ext_emoji = "🔄 Evet" if c['extended'] else "Hayır"
            act_emoji = "🟢 Aktif" if c['is_active'] else "🔴 Pasif"
            app_emoji = "👍 Onaylı" if c['is_approved'] else "⏳ Onay Bekliyor"
            
            # Başlığı kısaltıp markdown linke dönüştür
            title_clean = c['title'].replace('|', '-').strip()
            title_link = f"[{title_clean[:40]}]({c['url']})"
            
            f.write(f"| #{c['id']} | {c['bank_name']} | {title_link} | {c['start_date']} | {c['end_date']} | {act_emoji} | {app_emoji} | {ext_emoji} | {susp_emoji} |\n")
            
    print(f"🎉 Rapor başarıyla oluşturuldu! {suspicious_count} adet şüpheli kampanya tespit edildi.")
    print(f"📁 Dosya Yolu: {report_path}")
    cur.close()
    conn.close()

if __name__ == "__main__":
    generate_markdown_audit_report()
