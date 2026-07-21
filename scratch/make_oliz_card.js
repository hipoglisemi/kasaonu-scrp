const fs = require('fs');
const sharp = require('sharp');
const path = require('path');

const svgLogo = fs.readFileSync('/Users/hipoglisemi/Desktop/kartavantaj-scraper/scratch/oliz_logo.svg', 'utf8');

// Extract paths from oliz_logo.svg or wrap it
// The SVG contains paths with fill-rule="evenodd". Let's convert them to white (#FFFFFF)
const whiteLogo = svgLogo
  .replace(/fill="none"/g, 'fill="none"')
  .replace(/fill="[^"]*"/g, 'fill="#FFFFFF"')
  .replace(/<path /g, '<path fill="#FFFFFF" ');

const cardSvg = `
<svg width="1000" height="630" viewBox="0 0 1000 630" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <!-- Rich Oliz Crimson Gradient -->
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#E2182B" />
      <stop offset="50%" stop-color="#B30F1F" />
      <stop offset="100%" stop-color="#67050E" />
    </linearGradient>

    <!-- Metallic Gold EMV Chip -->
    <linearGradient id="chipGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FFE082" />
      <stop offset="50%" stop-color="#FFB300" />
      <stop offset="100%" stop-color="#FF6F00" />
    </linearGradient>

    <!-- Gloss Wave Overlay -->
    <linearGradient id="glossGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.15" />
      <stop offset="40%" stop-color="#FFFFFF" stop-opacity="0.05" />
      <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0" />
    </linearGradient>

    <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="#000000" flood-opacity="0.3" />
    </filter>
  </defs>

  <!-- Base Card Rectangle -->
  <rect x="20" y="20" width="960" height="590" rx="36" fill="url(#bgGrad)" filter="url(#shadow)" />

  <!-- Decorative Abstract Wave Lines -->
  <path d="M 20 200 Q 400 400 980 150 L 980 20 L 20 20 Z" fill="url(#glossGrad)" />
  <circle cx="850" cy="500" r="280" fill="#FFFFFF" fill-opacity="0.03" />
  <circle cx="900" cy="120" r="180" fill="#FFFFFF" fill-opacity="0.04" />

  <!-- EMV Chip -->
  <g transform="translate(100, 160)">
    <rect width="110" height="84" rx="14" fill="url(#chipGrad)" stroke="#FFD54F" stroke-width="2" />
    <path d="M 0 42 H 110 M 36 0 V 84 M 74 0 V 84" stroke="#B36B00" stroke-width="2" fill="none" opacity="0.6" />
    <rect x="36" y="24" width="38" height="36" rx="6" fill="none" stroke="#B36B00" stroke-width="2" opacity="0.6" />
  </g>

  <!-- Contactless Wave Icon -->
  <g transform="translate(240, 180)" fill="none" stroke="#FFFFFF" stroke-opacity="0.7" stroke-width="4" stroke-linecap="round">
    <path d="M 0 10 A 15 15 0 0 1 0 34" />
    <path d="M 10 2 A 25 25 0 0 1 10 42" />
    <path d="M 20 -6 A 35 35 0 0 1 20 50" />
  </g>

  <!-- Main Oliz Logo (Centered & Scaled) -->
  <g transform="translate(350, 260) scale(4.2)">
    ${whiteLogo}
  </g>

  <!-- Card Details / Tagline -->
  <text x="100" y="520" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-weight="700" font-size="28" fill="#FFFFFF" letter-spacing="4" opacity="0.9">OLİZ DIJITAL KART</text>
  <text x="100" y="555" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-weight="500" font-size="18" fill="#FFFFFF" letter-spacing="2" opacity="0.6">KOÇ TOPLULUĞU AYRICALIKLARI</text>
</svg>
`;

const outputPath = '/Users/hipoglisemi/Desktop/kartavantaj/public/logos/creditcard/oliz.webp';

sharp(Buffer.from(cardSvg))
  .webp({ quality: 95 })
  .toFile(outputPath)
  .then(() => console.log('Successfully created Oliz credit card visual:', outputPath))
  .catch(err => console.error('Error creating Oliz credit card:', err));
