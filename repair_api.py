"""
Repair API — Lightweight FastAPI service for campaign repair.
This wraps data_quality_autofix.py and exposes it as an HTTP endpoint
so the Next.js frontend can trigger repairs from Coolify.
"""

import os
import sys
import json
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from contextlib import redirect_stdout
import io

app = FastAPI(title="KartAvantaj Repair API", version="1.0.0")

# Simple token-based auth
REPAIR_API_SECRET = os.getenv("REPAIR_API_SECRET", "")

def verify_token(authorization: Optional[str] = Header(None)):
    """Verify the API token to prevent unauthorized access."""
    if not REPAIR_API_SECRET:
        return  # No secret configured = open (dev mode)
    
    if not authorization or authorization != f"Bearer {REPAIR_API_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
async def health():
    """Health check endpoint for Coolify."""
    return {"status": "ok", "service": "repair-api"}


@app.post("/repair/{campaign_id}")
async def repair_campaign(campaign_id: int, force: bool = True, authorization: Optional[str] = Header(None)):
    """
    Repair a single campaign using data_quality_autofix.py
    This is the same logic that runs in GitHub Actions.
    """
    verify_token(authorization)
    
    try:
        from data_quality_autofix import run_autofix
        
        # Capture stdout to extract the JSON sentinel output
        captured = io.StringIO()
        
        with redirect_stdout(captured):
            run_autofix(
                limit=1,
                campaign_id=campaign_id,
                force_all=force,
                ui_mode=True
            )
        
        output = captured.getvalue()
        
        # Extract JSON between sentinels
        import re
        match = re.search(r'---AIPARSER_JSON_START---\n([\s\S]*?)\n---AIPARSER_JSON_END---', output)
        
        if match:
            result = json.loads(match.group(1))
            return JSONResponse(content={
                "success": True,
                "data": result,
                "logs": output[:2000]  # First 2K chars of logs for debugging
            })
        else:
            # No JSON sentinel found — campaign might have been healthy or AI failed
            return JSONResponse(content={
                "success": False,
                "message": "AI onarımı başarısız oldu veya kampanyada sorun bulunamadı.",
                "logs": output[:2000]
            }, status_code=422)
            
    except Exception as e:
        logging.exception(f"Repair failed for campaign {campaign_id}")
        return JSONResponse(content={
            "success": False,
            "message": f"Sunucu hatası: {str(e)}"
        }, status_code=500)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
