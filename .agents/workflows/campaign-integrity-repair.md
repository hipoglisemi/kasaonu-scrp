---
description: Kartavantaj Kampanya Veri Bütünlüğü - Onarım (Repair) ve Kurtarma (Rescue) Operasyonu
---

Bu workflow, banka kampanyalarındaki veri kesintilerini (truncation), eksik koşulları ve hatalı AI çıkarımlarını düzeltmek için kullanılır.

### 🔍 1. Problemli Kampanyaların Tespiti

Veritabanında koşulları eksik veya metni kesik olan aktif kampanyaları belirleyin.

// turbo
```bash
python3 check_short_text.py
# VEYA
python3 find_empty_conditions.py
```

### 🆘 2. Metin Kurtarma (Rescue) Operasyonu

Eğer kampanyalar scraper hatası nedeniyle kısa çekilmişse (Örn: Yapı Kredi/Garanti eski hali), tam metinleri banka sitesinden tekrar çekmek için:

// turbo
```bash
python3 rescue_short_campaigns.py
```

### 🔧 3. Toplu AI Onarımı (Bulk Repair)

Kampanya metni (clean_text) tam olmasına rağmen AI parser'ın navigasyon gürültüsü veya eski prompt nedeniyle koşulları (conditions) eksik bıraktığı durumlarda (Threshold: 200 karakter):

// turbo
```bash
python3 repair_empty_fields.py
```

### 🛡️ 4. Veri Doğrulama ve Koruma Standartları

Herhangi bir onarım sonrasında aşağıdaki noktaları kontrol edin:
- **Header Sniper:** Navigasyon linklerinin ("Nedir?", "Kurallar") budandığından emin olun.
- **Hoarder Prompt:** Anadolu Bank, Vakıfbank gibi partner bankaların koşullarda korunduğunu doğrulayın.
- **Selector Integrity:** Yapı Kredi için `.campaign-detail-content`, Garanti için `.container-wide` gibi detay selector'larının kullanıldığını script çıktılarından teyit edin.
