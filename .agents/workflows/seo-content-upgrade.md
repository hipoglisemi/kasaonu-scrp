# SEO İçerik Kalitesi: Benzersiz AI Metin Güncelleme Operasyonu

Bu workflow, sitedeki tüm kampanyaların `ai_marketing_text` kolonunu, Google'ın "İnce İçerik" (Thin Content) hatalarını aşacak şekilde, benzersiz ve enerjik metinlerle günceller.

## Ne Zaman Kullanılmalı?
- Sitedeki metinlerin çok benzer (repetitive) olduğu fark edildiğinde.
- Google Search Console'da içerik kalitesiyle ilgili uyarılar alındığında.
- Yeni bir banka veya büyük bir kampanya grubu eklendikten sonra toplu kalite artışı istendiğinde.

## Operasyon Adımları

### 1. Hazırlık ve Kontrol
Önce Gemini API keylerinizin durumunu ve `bulk_ai_marketing_energetic.py` scriptinin güncelliğini kontrol edin.

### 2. Güncellemeyi Başlat
Aşağıdaki komutu terminallinizde çalıştırarak operasyonu başlatın:

// turbo
```bash
export PYTHONPATH=$PYTHONPATH:. && python3 bulk_ai_marketing_energetic.py
```

### 3. Takip ve Doğrulama
Script çalışırken ekrana basılan örnekleri inceleyin:
- Başlık tekrarı var mı?
- Emojiler doğru yerde mi?
- Dil yeterince enerjik mi?

### 4. Checkpoint Sistemi
Eğer bağlantı koparsa veya Google 503 hatası verirse scripti durdurup tekrar başlattığınızda, `marketing_update_checkpoint.json` dosyası sayesinde kaldığı yerden devam edecektir.

## Dikkat Edilmesi Gerekenler
> [!WARNING]
> Google "High Demand" (503) hatası verirse script otomatik olarak beklemeye geçer. Bu durumda işlemi iptal etmeyin, script kendiliğinden devam edecektir.

> [!TIP]
> İşlem bittikten sonra Prisma Studio üzerinden rastgele bir kaç kampanya kimliğini (ID) kontrol ederek içeriğin özgünlüğünü teyit edin.
