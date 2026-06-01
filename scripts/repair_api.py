"""
Repair API — Lightweight FastAPI service for campaign repair.
This wraps data_quality_autofix.py and exposes it as an HTTP endpoint
so the Next.js frontend can trigger repairs from Coolify.
"""

import os
import sys
import json
import logging
import re
import io
from contextlib import redirect_stdout
from typing import Optional

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add project root and scripts directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
for p in [current_dir, project_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from fastapi import FastAPI, HTTPException, Header, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
except ImportError as e:
    logger.error(f"Critical Import Error: {e}")
    # We can't even start FastAPI if this fails
    raise

app = FastAPI(title="KartAvantaj Repair API", version="1.0.1")

# Simple token-based auth
REPAIR_API_SECRET = os.getenv("REPAIR_API_SECRET", "")

def verify_token(authorization: Optional[str]):
    """Verify the API token to prevent unauthorized access."""
    if not REPAIR_API_SECRET:
        return  # No secret configured = open (dev mode)
    
    if not authorization or authorization != f"Bearer {REPAIR_API_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized Access")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return them as JSON."""
    logger.exception(f"Unhandled exception during request to {request.url}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False, 
            "message": f"Python Global Hatası: {str(exc)}",
            "type": type(exc).__name__,
            "detail": "Sunucu tarafında beklenmedik bir hata oluştu."
        }
    )

@app.get("/health")
async def health():
    """Health check endpoint for Coolify."""
    return {"status": "ok", "service": "repair-api", "version": "1.0.1"}

@app.post("/repair/{campaign_id}")
def repair_campaign(campaign_id: int, force: bool = True, model: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """
    Repair a single campaign using data_quality_autofix.py
    """
    verify_token(authorization)
    
    logger.info(f"Starting repair for campaign ID: {campaign_id}")
    
    try:
        # Import inside handler to catch specific import errors
        try:
            from data_quality_autofix import run_autofix
        except ImportError as ie:
            logger.error(f"Failed to import run_autofix: {ie}")
            return JSONResponse(status_code=500, content={
                "success": False,
                "message": f"Modül yükleme hatası: {str(ie)}. Bağımlılıklar eksik olabilir."
            })
        
        # Capture stdout to extract the JSON sentinel output
        captured = io.StringIO()
        
        with redirect_stdout(captured):
            try:
                run_autofix(
                    limit=1,
                    campaign_id=campaign_id,
                    force_all=force,
                    ui_mode=True,
                    model=model,
                    force_rescue=force
                )
            except Exception as run_err:
                logger.error(f"run_autofix crashed: {run_err}")
                raise run_err
        
        output = captured.getvalue()
        
        # Extract JSON between sentinels
        match = re.search(r'---AIPARSER_JSON_START---\n([\s\S]*?)\n---AIPARSER_JSON_END---', output)
        
        if match:
            try:
                result = json.loads(match.group(1))
                return JSONResponse(content={
                    "success": True,
                    "data": result,
                    "logs": output[:3000] # Increased log size for debugging
                })
            except json.JSONDecodeError as jde:
                logger.error(f"JSON Decode Error: {jde}")
                return JSONResponse(status_code=422, content={
                    "success": False,
                    "message": "AI çıktısı geçerli bir JSON formatında değil.",
                    "logs": output[:3000]
                })
        else:
            logger.warning(f"No JSON sentinel found for campaign {campaign_id}")
            # Check if it was skipped by data_quality_autofix due to cooldown/filters
            if "Total campaigns to process in this run: 0" in output or "All active campaigns look healthy" in output:
                return JSONResponse(status_code=422, content={
                    "success": False,
                    "message": "Bu kampanya kalite kontrol filtreleri veya cooldown süresi nedeniyle atlandı. Lütfen en son yaptığımız hızlandırma/atlama düzeltmelerinin canlıya geçmesi için Coolify üzerinden redeploy işlemi yapın veya Zorla (Force) butonlarını kullanın.",
                    "logs": output[:3000]
                })
            return JSONResponse(status_code=422, content={
                "success": False,
                "message": "AI onarımı başarısız oldu (JSON çıktısı üretilemedi).",
                "logs": output[:3000]
            })
            
    except Exception as e:
        logger.exception(f"Repair failed for campaign {campaign_id}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": f"Onarım sırasında teknik hata: {str(e)}"
        })

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    logger.info(f"Starting Repair API on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
