---
description: Kartavantaj SEO - Otomatik Banka/Kart Özeti Üretici (Haftalık)
---

Bu workflow, sistemdeki SEO özeti eksik olan tüm banka ve kartları tespit eder ve Gemini 3.1 Flash-Lite kullanarak 4 bölümlü zengin SEO içerikleri üretir.

// turbo-all
1. Bağımlılıkları ve ortam değişkenlerini kontrol et.
2. Otomatik SEO işçisini çalıştır:
   ```bash
   export PYTHONPATH=$PYTHONPATH:. && python3 scripts/autoseo_worker.py
   ```
3. Güncellenen kayıt sayısını ve başarı durumunu raporla.

> [!TIP]
> Bu işlemi haftada bir kez veya büyük bir veri çekme (scrape) operasyonundan sonra çalıştırmanız önerilir.
