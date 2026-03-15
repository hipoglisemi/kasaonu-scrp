// AI Snippet Extractor
// Extracts minimal context (300-400 chars) for AI sector classification
// Reduces token usage by ~84% compared to full HTML

/**
 * Extract a concise snippet for AI classification
 * Includes title + first 300-350 chars of content
 */
export function extractSnippetForAI(title: string, content: string): string {
    // Clean content: remove extra whitespace
    const cleanContent = content
        .replace(/\s+/g, ' ')
        .replace(/\n+/g, ' ')
        .trim();

    // Title + snippet (max 400 chars total)
    const titlePart = title.trim();
    const maxContentLength = 350 - titlePart.length;
    const contentSnippet = cleanContent.substring(0, maxContentLength);

    const snippet = `${titlePart}\n\n${contentSnippet}`;

    // Ensure max 400 chars
    return snippet.substring(0, 400);
}

/**
 * Classify sector using minimal AI prompt (snippet-only)
 * Returns only sector_slug to minimize tokens
 */
import { generateContent } from './genai';

/**
 * Classify sector using minimal AI prompt (snippet-only)
 * Returns only sector_slug to minimize tokens
 */
export async function classifySectorWithAI(
    snippet: string
): Promise<{ sector_slug: string, confidence: number }> {

    const prompt = `Classify this Turkish credit card campaign into EXACTLY ONE sector slug.
    
Response MUST be only the slug string. No explanation, no JSON, no formatting.

Valid slugs:
market-gida, akaryakit, giyim-aksesuar, restoran-kafe, elektronik, mobilya-dekorasyon, kozmetik-saglik, e-ticaret, ulasim, dijital-platform, kultur-sanat, egitim, sigorta, otomotiv, vergi-kamu, turizm-konaklama, diger

Campaign:
${snippet}`;

    try {
        const text = await generateContent(prompt, 'gemini-3.1-flash-lite-preview', {
            generationConfig: {
                temperature: 0.1,
                maxOutputTokens: 15
            }
        });

        const sectorSlug = text?.trim().toLowerCase() || 'diger';

        const validSlugs = [
            'market-gida', 'akaryakit', 'giyim-aksesuar', 'restoran-kafe',
            'elektronik', 'mobilya-dekorasyon', 'kozmetik-saglik', 'e-ticaret',
            'ulasim', 'dijital-platform', 'kultur-sanat', 'egitim',
            'sigorta', 'otomotiv', 'vergi-kamu', 'turizm-konaklama', 'diger'
        ];

        if (!validSlugs.includes(sectorSlug)) {
            console.warn(`Invalid AI response: "${sectorSlug}"`);
            return { sector_slug: 'diger', confidence: 0 };
        }

        return {
            sector_slug: sectorSlug,
            confidence: sectorSlug === 'diger' ? 0.4 : 0.8
        };

    } catch (error) {
        console.error('AI classification error:', error);
        return { sector_slug: 'diger', confidence: 0 };
    }
}
