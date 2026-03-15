import { generateContent } from '../utils/genai';

/**
 * Enhances a campaign description using AI to make it more marketing-oriented.
 * Uses minimal tokens (~275) for cost efficiency.
 * 
 * @param rawDescription - The original description (usually just title)
 * @returns Enhanced marketing-style description with emojis (2 sentences max)
 */
export async function enhanceDescription(rawDescription: string, retryCount = 0): Promise<string> {
    const MAX_RETRIES = 3;
    const BASE_DELAY_MS = 2000;

    if (!rawDescription || rawDescription.length < 10) {
        return rawDescription;
    }

    if (/[\u{1F300}-\u{1F9FF}]/u.test(rawDescription)) {
        return rawDescription;
    }

    const prompt = `
You are a creative banking marketing expert.
Convert this raw campaign into a 1-sentence catchy summary.
Language: TURKISH.
- Use 1 emoji. 
- Focus on the PRIMARY benefit.
- NO extra words, NO prefix.

Input: "${rawDescription}"
    `.trim();

    try {
        const enhanced = await generateContent(prompt, 'gemini-3.1-flash-lite-preview', {
            generationConfig: {
                temperature: 0.1
            }
        });

        if (enhanced && enhanced.length > 0) {
            console.log(`   ✨ Enhanced: ${enhanced.substring(0, 80)}...`);
            return enhanced;
        }

        if (enhanced && enhanced.length > 0) {
            console.log(`   ✨ Enhanced: ${enhanced.substring(0, 80)}...`);
            return enhanced;
        }

        return rawDescription;

    } catch (error: any) {
        if (retryCount < MAX_RETRIES) {
            const delay = BASE_DELAY_MS * Math.pow(2, retryCount);
            await new Promise(r => setTimeout(r, delay));
            return enhanceDescription(rawDescription, retryCount + 1);
        }
        console.error('   ❌ Description enhancement error:', error.message);
        return rawDescription;
    }
}

/**
 * Batch enhance descriptions (for future optimization)
 */
export async function enhanceDescriptionsBatch(descriptions: string[]): Promise<string[]> {
    const enhanced: string[] = [];

    for (const desc of descriptions) {
        const result = await enhanceDescription(desc);
        enhanced.push(result);
        // Small delay to avoid rate limits
        await new Promise(resolve => setTimeout(resolve, 100));
    }

    return enhanced;
}
