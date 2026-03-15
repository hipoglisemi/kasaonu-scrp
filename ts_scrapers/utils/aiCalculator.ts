import { supabase } from './supabase';
import { generateContent } from './genai';

const MODEL_NAME = 'gemini-3.1-flash-lite-preview';

interface MasterData {
    categories: string[];
    brands: string[];
}

let cachedMasterData: MasterData | null = null;

async function fetchMasterData(): Promise<MasterData> {
    if (cachedMasterData) return cachedMasterData;

    const [sectorsRes, brandsRes] = await Promise.all([
        supabase.from('master_sectors').select('name'),
        supabase.from('master_brands').select('name')
    ]);

    const categories = sectorsRes.data?.map(c => c.name) || [
        'Market & Gıda', 'Akaryakıt', 'Giyim & Aksesuar', 'Restoran & Kafe',
        'Elektronik', 'Mobilya & Dekorasyon', 'Kozmetik & Sağlık', 'E-Ticaret',
        'Ulaşım', 'Dijital Platform', 'Kültür & Sanat', 'Eğitim',
        'Sigorta', 'Otomotiv', 'Vergi & Kamu', 'Turizm & Konaklama', 'Diğer'
    ];

    const brands = brandsRes.data?.map(b => b.name) || [];

    cachedMasterData = { categories, brands };
    return cachedMasterData;
}

const DISABLE_AI_COMPLETELY = false; // Enabled for advanced calculation features

/**
 * Modern AI Calculation Engine
 * Uses Gemini 2.0 Flash with Python Code Execution for mathematical precision
 */
export async function calculateCampaignBonus(campaignText: string) {
    if (DISABLE_AI_COMPLETELY) return null;

    const prompt = `
    Aşağıdaki banka kampanya metnini analiz et ve matematiksel hesaplamaları Python kullanarak doğrula.
    
    KAMPANYA METNİ:
    "${campaignText}"
    
    GÖREV:
    1. Metindeki harcama alt limitlerini, bonus oranlarını ve maksimum kazanım limitlerini ayıkla.
    2. Python kodunu kullanarak farklı harcama senaryoları için kazanılacak bonusu hesapla.
    3. Eğer "n. harcamadan sonra" veya "farklı günlerde" gibi şartlar varsa bunları Python mantığına (if/else) dök.
    4. Kampanya toplam üst limitini (max_bonus) her zaman bir kısıt olarak uygula.
    
    ÇIKTI FORMATI (Sadece saf JSON döndür):
    {
      "min_spend": number,
      "bonus_ratio": number,
      "max_bonus": number,
      "is_cumulative": boolean,
      "calculated_scenarios": {
          "scenario_1000tl": number,
          "scenario_5000tl": number,
          "scenario_max_target": number
      },
      "explanation": "Hesaplama mantığının kısa özeti"
    }`;

    try {
        const resultText = await generateContent(prompt, MODEL_NAME, {
            generationConfig: {
                temperature: 0.1
            },
            tools: [{ code_execution: {} }]
        });

        // resultText already contains the string from candidates or code execution in our utility
        if (resultText && resultText.includes('{')) {
            const jsonMatch = resultText.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                return JSON.parse(jsonMatch[0]);
            }
        }

        throw new Error("Modelden geçerli bir JSON çıktısı alınamadı.");

    } catch (error) {
        console.error("   ❌ AI Hesaplama Hatası:", error);
        return null;
    }
}

/**
 * Legacy support for extracting brand and category (uses simpler parameters)
 */
export async function calculateMissingFields(
    rawHtml: string,
    extracted: any
): Promise<any> {
    if (DISABLE_AI_COMPLETELY) {
        return { brand: null, category: 'Diğer' };
    }

    const masterData = await fetchMasterData();

    const prompt = `Sen bir kampanya analiz asistanısın. Aşağıdaki HTML'den kampanyanın MARKA ve KATEGORİ bilgilerini çıkar.

KURALLAR:
1. MARKA: Kampanyada geçen mağaza/firma adı (örn: Teknosa, CarrefourSA, FG Europe, Türk Hava Yolları)
   - Banka adları (Akbank, Axess vb.) MARKA DEĞİLDİR
   - Kart adları (Axess, Bonus vb.) MARKA DEĞİLDİR
   - Eğer belirli bir marka yoksa null döndür
2. KATEGORİ: Aşağıdaki listeden EN UYGUN olanı seç:
   ${masterData.categories.join(', ')}

KAMPANYA BAŞLIĞI: ${extracted.title}

HTML İÇERİĞİ:
${rawHtml.substring(0, 2000)}

ÇIKTI FORMATI (sadece JSON döndür):
{
  "brand": "Marka Adı veya null",
  "category": "Kategori Adı"
}`;

    try {
        const text = await generateContent(prompt, MODEL_NAME, {
            generationConfig: {
                temperature: 0.1,
                response_mime_type: "application/json"
            }
        });

        if (!text) throw new Error('No response from Gemini');
        const result = JSON.parse(text.replace(/```json|```/g, '').trim());

        // Normalize brand name
        if (result.brand && typeof result.brand === 'string') {
            const brandLower = result.brand.toLowerCase();
            const forbiddenTerms = ['akbank', 'axess', 'bonus', 'world', 'maximum', 'paraf', 'bankkart', 'wings', 'free', 'adios', 'play', 'crystal'];
            if (forbiddenTerms.some(term => brandLower.includes(term))) {
                result.brand = null;
            }
        }

        // Validate category
        if (result.category && !masterData.categories.includes(result.category)) {
            result.category = 'Diğer';
        }

        return {
            brand: result.brand || null,
            category: result.category || 'Diğer'
        };
    } catch (error: any) {
        console.error('   ❌ AI calculation error:', error.message);
        return {
            brand: null,
            category: 'Diğer'
        };
    }
}

