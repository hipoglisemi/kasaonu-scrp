---
description: Kasaonu SEO Performans Raporu Oluşturma (Google Search Console)
---

Bu workflow, Google Search Console verilerini kullanarak Kasaonu'ın güncel SEO performans raporunu manuel olarak oluşturmanızı sağlar.

### Ön Hazırlık
1. `.env` dosyasında `SEARCH_CONSOLE_KEY` değişkeninin tanımlı olduğundan emin olun.
2. `sc-domain:@@KASAONU_DOMAIN@@` mülküne ilgili service account e-postasının (@@KASAONU_INDEXING@@@...) erişimi olduğunu kontrol edin.

### Adımlar

1. **Terminali açın ve scraper klasörüne gidin:**
   ```bash
   cd /Users/hipoglisemi/Desktop/kasaonu-scraper
   ```

2. **Python sanal ortamını aktif edin:**
   ```bash
   source venv/bin/activate
   ```

3. **Raporscriptini çalıştırın:**
   ```bash
   python3 seo_performance_check.py
   ```

### Rapor İçeriği
Sorgu bittiğinde ekranda şu bilgiler listelenecektir:
- **Genel Performans**: Tıklama, Gösterim, CTR ve Pozisyon değişimleri.
- **Top Sorgular**: En çok trafik getiren kelimeler.
- **Pozisyon Dağılımı**: İlk 3, ilk 10 ve diğer sıralamalar.
- **Fırsatlar**: Gösterimi yüksek ama tıklaması düşük olan sayfalar (SEO/Meta optimizasyonu için).
- **Trendler**: Son 7 günün en popüler sorguları.

### Sorun Giderme
- **403 Hatası**: Service account'un Search Console yetkisini kontrol edin veya API'nin aktif olduğunu doğrulayın.
- **Empty Result**: Belirtilen tarih aralığında henüz veri çekilmemiş olabilir (GSC verileri 2-3 gün gecikmeli gelir).
