import subprocess
import time
import sys

# Define sequential list of workflows ordered by cron schedule (TSİ)
workflows = [
    {"repo": "hipoglisemi/kartavantaj-scrp", "name": "Cleanup Expired Campaigns", "file": "cleanup-campaigns.yml", "time": "TSİ 00:15"},
    {"repo": "hipoglisemi/kartavantaj-scrp", "name": "🅰️ Scrapers – Grup A", "file": "scrapers-group-a.yml", "time": "TSİ 00:30"},
    {"repo": "hipoglisemi/kartavantaj-scrp", "name": "🅱️ Scrapers – Grup B", "file": "scrapers-group-b.yml", "time": "TSİ 01:00"},
    {"repo": "hipoglisemi/kartavantaj-scrp", "name": "🆑 Scrapers – Grup C", "file": "scrapers-group-c.yml", "time": "TSİ 01:30"},
    {"repo": "hipoglisemi/kartavantaj-scrp", "name": "🆗 Scrapers – Grup D", "file": "scrapers-group-d.yml", "time": "TSİ 02:00"},
    {"repo": "hipoglisemi/kartavantaj-scrp", "name": "🍬 Scrapers – Grup E", "file": "scrapers-group-e.yml", "time": "TSİ 02:30"},
    {"repo": "hipoglisemi/kartavantaj-scrp", "name": "⛽ Scrapers – Grup F", "file": "scrapers-group-f.yml", "time": "TSİ 03:00"},
    {"repo": "hipoglisemi/kartavantaj-scrp", "name": "Data Quality Auto-Fixer", "file": "data-quality-autofix.yml", "time": "TSİ 03:30"},
    {"repo": "hipoglisemi/kartavantaj", "name": "Automated Daily Database Backup", "file": "kartavantaj-db-backup.yml", "time": "TSİ 06:00"},
    {"repo": "hipoglisemi/kartavantaj", "name": "Daily Z Report Generator", "file": "z-report.yml", "time": "TSİ 06:00"},
    {"repo": "hipoglisemi/kartavantaj", "name": "Google Indexing Otomasyonu", "file": "google-indexing.yml", "time": "TSİ 08:00"},
    {"repo": "hipoglisemi/kartavantaj-scrp", "name": "SEO Blog Auto-Generator", "file": "seo_blog_generator.yml", "time": "TSİ 09:00 / 15:00"},
    {"repo": "hipoglisemi/kartavantaj-scrp", "name": "SEO Pillar Page Auto-Generator", "file": "auto_pillar_generator.yml", "time": "TSİ 10:00"},
    {"repo": "hipoglisemi/kartavantaj", "name": "Push Bildirim Gönderici", "file": "push-notifications.yml", "time": "TSİ 10:00 / 20:00"},
    {"repo": "hipoglisemi/kartavantaj", "name": "Weekly Sector AI Summaries", "file": "weekly-sector-summaries.yml", "time": "TSİ 10:00 (Pazar)"},
    {"repo": "hipoglisemi/kartavantaj-scrp", "name": "Weekly Auto-SEO Worker", "file": "auto-seo.yml", "time": "TSİ 13:00 (Çarşamba)"},
    {"repo": "hipoglisemi/kartavantaj", "name": "Haftalık SEO Raporu", "file": "weekly-seo-report.yml", "time": "TSİ 09:00 (Pazartesi)"}
]

print("==================================================================")
print("🚀 Kartavantaj Sıralı Workflow Başlatma Otomasyonu 🚀")
print("==================================================================\n")

for idx, wf in enumerate(workflows):
    print(f"[{idx+1}/{len(workflows)}] 🕒 {wf['time']} | Repo: {wf['repo'].split('/')[-1]} | {wf['name']} ({wf['file']})")
    
    # Construct gh workflow run command
    cmd = ["gh", "workflow", "run", wf["file"], "-R", wf["repo"]]
    
    try:
        # Run using subprocess
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"   ✅ Başarıyla tetiklendi!")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ HATA! Tetiklenemedi. Detay: {e.stderr.strip()}")
    except Exception as e:
        print(f"   ❌ Beklenmeyen Hata: {str(e)}")
        
    # Sleep 3 seconds between triggers to avoid GitHub API abuse / rate limits
    time.sleep(3)

print("\n==================================================================")
print("🎉 Tüm workflow'lar sıralı bir şekilde başarıyla tetiklendi!")
print("==================================================================")
