import { generateContent } from '../utils/genai';

// Minimal sleep utility
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

export interface BrandValidationResult {
    brand: string;
    decision: 'AUTO_ADD' | 'PENDING_REVIEW' | 'REJECT';
    confidence: number;
    reason: string;
}

/**
 * Validates whether a detected name is a real commercial brand using minimal AI tokens.
 * This is a focused, single-purpose validator to prevent garbage in master_brands.
 */
export async function validateBrand(
    brandName: string,
    contextSnippet: string,
    retryCount = 0
): Promise<BrandValidationResult> {
    const MAX_RETRIES = 2;
    const BASE_DELAY_MS = 1000;

    // STRICT ENFORCEMENT: Max 400 chars snippet
    const MAX_SNIPPET_LENGTH = 400;
    if (contextSnippet.length > MAX_SNIPPET_LENGTH) {
        contextSnippet = contextSnippet.substring(0, MAX_SNIPPET_LENGTH);
        console.log(`   ⚠️ Snippet truncated to ${MAX_SNIPPET_LENGTH} chars for brand "${brandName}"`);
    }

    const prompt = `
You are assisting a master brand governance system.

Your task:
Evaluate whether a detected name should be treated as a REAL COMMERCIAL BRAND.

------------------------
DECISION TYPES
------------------------

AUTO_ADD:
- A real commercial brand or merchant
- Clearly identifiable as a company or retailer
- Appears as a proper noun
- Not generic, not a campaign phrase

PENDING_REVIEW:
- Might be a brand, but context is weak
- Could be a sub-brand, temporary campaign name, or unclear entity
- Needs human confirmation

REJECT:
- Generic word or phrase
- Bank, card, payment system
- Reward, discount, or campaign terminology
- Sector name (e.g. "market", "restaurant")
- Campaign slogans or benefit names

------------------------
STRICT RULES
------------------------

- NEVER auto-add banks, cards, or payment systems
- NEVER auto-add reward-related terms (puan, taksit, indirim, chip-para)
- If unsure, choose PENDING_REVIEW
- Be conservative

------------------------
RETURN ONLY JSON
------------------------

{
  "brand": "${brandName}",
  "decision": "AUTO_ADD | PENDING_REVIEW | REJECT",
  "confidence": 0.0,
  "reason": "short technical explanation"
}

------------------------
CONTEXT
------------------------
Campaign text excerpt:
"""
${contextSnippet.substring(0, 500)}
"""
`;

    try {
        const responseText = await generateContent(prompt, 'gemini-3.1-flash-lite-preview', {
            generationConfig: {
                temperature: 0.1
            }
        });

        if (!responseText) {
            throw new Error('No response from Gemini');
        }

        // Extract JSON
        const jsonMatch = responseText.match(/\{[\s\S]*\}/);
        if (!jsonMatch) {
            console.warn(`   ⚠️ AI returned non-JSON for brand "${brandName}". Defaulting to PENDING_REVIEW.`);
            return {
                brand: brandName,
                decision: 'PENDING_REVIEW',
                confidence: 0.0,
                reason: 'AI returned invalid format'
            };
        }

        const result: BrandValidationResult = JSON.parse(jsonMatch[0]);
        return result;

    } catch (error: any) {
        console.error(`   ❌ Brand validation failed for "${brandName}":`, error.message);

        // Safe fallback: PENDING_REVIEW (don't auto-add on error)
        return {
            brand: brandName,
            decision: 'PENDING_REVIEW',
            confidence: 0.0,
            reason: `Error: ${error.message}`
        };
    }
}

/**
 * Batch validate multiple brands (with rate limiting between calls)
 */
export async function validateBrandsBatch(
    brands: Array<{ name: string, context: string }>
): Promise<BrandValidationResult[]> {
    const results: BrandValidationResult[] = [];

    for (const brand of brands) {
        const result = await validateBrand(brand.name, brand.context);
        results.push(result);

        // Rate limit: 1 second between requests
        if (brands.indexOf(brand) < brands.length - 1) {
            await sleep(1000);
        }
    }

    return results;
}
