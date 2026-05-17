"""
Fact Checker Service - PEER-REVIEW NLI AGENT 🔬
Independent NLI (Natural Language Inference) engine to verify campaign grounding
against the original scraped web source text.
"""
import os
import json
import logging
from typing import Dict, Any, List
from google.genai import types  # type: ignore
from src.utils.gemini_client import generate_with_rotation  # type: ignore

logger = logging.getLogger(__name__)

class FactCheckerAgent:
    def __init__(self, model: str = "models/gemini-3.1-flash-lite"):
        self.model = model

    def verify_campaign(self, source_text: str, candidate_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verifies if the extracted candidate_data is 100% grounded in the source_text.
        Returns a detailed JSON showing the grounding status of each field.
        """
        if not source_text or len(source_text.strip()) < 50:
            logger.warning("[FactChecker] Empty source text provided. Rejecting grounding.")
            return {"is_grounded": False, "reason": "Kaynak metin boş veya çok kısa."}

        system_instruction = (
            "Sen KartAvantaj projesinde çalışan kıdemli bir 'Veri Doğrulama ve Gerçeklik Analizi (NLI - Natural Language Inference)' uzmanısın.\n"
            "Görevin, birinci yapay zekanın taranan web sayfasından çıkardığı bilgilerin (aday veriler), "
            "sayfanın orijinal ham metninde (kaynak metin) açıkça desteklenip desteklenmediğini nesnel bir şekilde doğrulamaktır.\n\n"
            "Kurallar:\n"
            "1. Asla onay sapmasına (confirmation bias) düşme. Birinci yapay zekanın çıkardığı her iddiayı şüpheyle incele.\n"
            "2. Çıktıyı her zaman belirtilen JSON formatında ver.\n"
            "3. Sektör doğruluğunu teyit et: Kampanya başlığı ve detayları, atanan sektör (kategori) ile mantıksal olarak 100% örtüşmelidir.\n"
            "4. Marka doğruluğunu teyit et: Kampanyaya atanan tüm markaların kampanya başlığında ya da açıklamasında açıkça geçtiğini ve kampanya ile doğrudan ilişkili olduğunu doğrula. Geçmeyen markaları 'unsupported_brands' içine yaz.\n"
            "5. Katılım yöntemini teyit et: Metinde katılım için mobil uygulama, SMS, web vb. belirtilen yöntem ile adayın katılım yöntemi uyuşmalıdır.\n"
            "6. Her alan için şu statülerden birini seç:\n"
            "   - 'YES': Kaynak metin bu bilgiyi açıkça destekliyor, mantıksal olarak teyit ediyor ve çelişmiyor.\n"
            "   - 'NO': Kaynak metinde bu bilgiyi destekleyecek hiçbir kanıt yok (uydurma/halüsinasyon).\n"
            "   - 'CONTRADICTION': Kaynak metinde bu bilgiyle doğrudan çelişen bir ifade var (örn. kart dahil yazılmış ama metin hariç diyor, veya katılım SMS diyor ama adaya Mobil girilmiş).\n"
        )

        prompt = f"""
KAYNAK METİN (BANKA WEB SİTESİ):
---
{source_text}
---

BİRİNCİ YAPAY ZEKA TARAFINDAN ÇIKARILAN ADAY BİLGİLER:
```json
{json.dumps(candidate_data, ensure_ascii=False, indent=2)}
```

GÖREV:
Aday bilgileri kaynak metin ile karşılaştır. Çıktıyı kesinlikle aşağıdaki JSON şemasına göre üret:

```json
{{
  "is_grounded": true, // Tüm kritik alanlar (reward, eligible_cards, participation, sector, brands) YES ise true, aksi halde false.
  "verifications": {{
    "reward": {{
      "status": "YES", // YES | NO | CONTRADICTION
      "reason": "Bu karara varma nedenini açıklayan kısa Türkçe gerekçe."
    }},
    "eligible_cards": {{
      "status": "YES", // YES | NO | CONTRADICTION
      "unsupported_cards": [], // Kaynak metinde desteklenmeyen kartların listesi (örn: ["Maximiles", "Paraf Ticari"])
      "reason": "Açıklama."
    }},
    "participation": {{
      "status": "YES", // YES | NO | CONTRADICTION
      "reason": "Açıklama."
    }},
    "sector": {{
      "status": "YES", // YES | NO | CONTRADICTION
      "reason": "Açıklama."
    }},
    "brands": {{
      "status": "YES", // YES | NO | CONTRADICTION
      "unsupported_brands": [], // Kaynak metinde adı/markası veya kampanyayla ilgisi kesinlikle geçmeyen veya uydurulan markaların listesi. (Örn: bankanın kendi adı veya ilgisiz bir marka)
      "reason": "Açıklama."
    }}
  }}
}}
```
"""
        config = types.GenerateContentConfig(
            temperature=0.0,
            top_p=0.1,
            top_k=1,
            response_mime_type="application/json",
            system_instruction=system_instruction
        )

        try:
            result_str = generate_with_rotation(
                prompt=prompt,
                model=self.model,
                config=config
            )
            
            if not result_str:
                logger.error("[FactChecker] Gemini returned empty response.")
                return {"is_grounded": False, "reason": "Boş API yanıtı."}

            # Handle potential markdown code fences in response
            cleaned_result = result_str.strip()
            if cleaned_result.startswith("```"):
                # strip code block prefix/suffix
                lines = cleaned_result.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned_result = "\n".join(lines).strip()

            data = json.loads(cleaned_result)
            logger.info(f"[FactChecker] Grounding Result: is_grounded={data.get('is_grounded')}")
            return data

        except Exception as e:
            logger.error(f"[FactChecker] Verification failed: {e}", exc_info=True)
            return {"is_grounded": False, "error": str(e)}
