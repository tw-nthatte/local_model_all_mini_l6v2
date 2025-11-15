"""
FastAPI main application for RBI Master Directives Monitor
Provides REST API and Jinja2 dashboard
"""
from fastapi import FastAPI, Request, Depends, HTTPException, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
from contextlib import asynccontextmanager
import logging
import os

from app.config import settings, setup_logging
from app.database import (
    init_db, 
    get_db, 
    MasterDirective, 
    ScrapeLog,
    get_latest_directive_date
)
from app.scheduler import start_scheduler, stop_scheduler, run_job_manually, get_scheduler_status
from app.routes.api import router as api_router

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Initialize templates and static directories
templates_dir = Path(__file__).parent.parent / "templates"
static_dir = Path(__file__).parent.parent / "static"

templates = Jinja2Templates(directory=str(templates_dir))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager
    Handles startup and shutdown events
    """
    # Startup
    logger.info("Application starting up...")
    init_db()
    start_scheduler()
    logger.info("✓ Application ready")

    yield

    # Shutdown
    logger.info("Application shutting down...")
    stop_scheduler()
    logger.info("✓ Application stopped")


# Create FastAPI application
app = FastAPI(
    title="RBI Master Directives Monitor",
    description="Monitor and download RBI Master Directives related to IT governance and digital banking",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include API routes
app.include_router(api_router)


# ============================================================================
# DASHBOARD ROUTES
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Main dashboard showing recent relevant directives"""
    try:
        # Get statistics
        total_directives = db.query(MasterDirective).count()
        relevant_directives = db.query(MasterDirective).filter(MasterDirective.is_relevant == True).count()

        # Get recent relevant directives
        directives = db.query(MasterDirective).filter(
            MasterDirective.is_relevant == True
        ).order_by(MasterDirective.publication_date.desc()).limit(20).all()

        # Get last scrape log
        last_log = db.query(ScrapeLog).order_by(ScrapeLog.scrape_timestamp.desc()).first()

        stats = {
            'total_monitored': total_directives,
            'relevant_found': relevant_directives,
            'last_check': last_log.scrape_timestamp if last_log else None,
            'last_check_status': 'success' if last_log and last_log.success else 'pending'
        }

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "directives": directives,
            "stats": stats,
            "app_name": settings.APP_NAME
        })
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/directives", response_class=HTMLResponse)
async def directives_page(
    request: Request,
    relevant_only: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Page showing all directives"""
    try:
        query = db.query(MasterDirective)
        if relevant_only:
            query = query.filter(MasterDirective.is_relevant == True)

        directives = query.order_by(MasterDirective.publication_date.desc()).limit(limit).all()

        return templates.TemplateResponse("directives.html", {
            "request": request,
            "directives": directives,
            "app_name": settings.APP_NAME
        })
    except Exception as e:
        logger.error(f"Directives page error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Page showing scraping logs"""
    try:
        logs = db.query(ScrapeLog).order_by(ScrapeLog.scrape_timestamp.desc()).limit(limit).all()

        return templates.TemplateResponse("logs.html", {
            "request": request,
            "logs": logs,
            "app_name": settings.APP_NAME
        })
    except Exception as e:
        logger.error(f"Logs page error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page"""
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "settings": {
            'scrape_interval': settings.SCRAPE_INTERVAL_HOURS,
            'similarity_threshold': settings.SIMILARITY_THRESHOLD,
            'email_alerts_enabled': settings.ENABLE_EMAIL_ALERTS,
            'database': settings.DATABASE_URL
        }
    })


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.post("/api/manual-scrape")
async def trigger_manual_scrape():
    """Manually trigger a scraping job"""
    try:
        result = run_job_manually()
        return JSONResponse({"status": "success", "message": result.get("status")})
    except Exception as e:
        logger.error(f"Manual scrape error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status")
async def get_status(db: Session = Depends(get_db)):
    """Get application status"""
    try:
        scheduler_status = get_scheduler_status()
        total_directives = db.query(MasterDirective).count()
        relevant_directives = db.query(MasterDirective).filter(MasterDirective.is_relevant == True).count()

        return JSONResponse({
            "status": "running",
            "app_name": settings.APP_NAME,
            "scheduler": scheduler_status,
            "statistics": {
                'total_directives': total_directives,
                'relevant_directives': relevant_directives,
                'scrape_interval_hours': settings.SCRAPE_INTERVAL_HOURS
            }
        })
    except Exception as e:
        logger.error(f"Status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/directives")
async def get_directives(
    relevant_only: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get directives as JSON"""
    try:
        query = db.query(MasterDirective)
        if relevant_only:
            query = query.filter(MasterDirective.is_relevant == True)

        directives = query.order_by(
            MasterDirective.publication_date.desc()
        ).limit(limit).all()

        return JSONResponse([d.to_dict() for d in directives])
    except Exception as e:
        logger.error(f"API directives error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs")
async def get_logs(limit: int = 20, db: Session = Depends(get_db)):
    """Get scrape logs as JSON"""
    try:
        logs = db.query(ScrapeLog).order_by(
            ScrapeLog.scrape_timestamp.desc()
        ).limit(limit).all()

        return JSONResponse([log.to_dict() for log in logs])
    except Exception as e:
        logger.error(f"API logs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get application statistics"""
    try:
        total = db.query(MasterDirective).count()
        relevant = db.query(MasterDirective).filter(MasterDirective.is_relevant == True).count()
        downloaded = db.query(MasterDirective).filter(MasterDirective.pdf_downloaded == True).count()

        last_log = db.query(ScrapeLog).order_by(ScrapeLog.scrape_timestamp.desc()).first()

        return JSONResponse({
            "total_directives": total,
            "relevant_directives": relevant,
            "pdfs_downloaded": downloaded,
            "last_check": last_log.scrape_timestamp.isoformat() if last_log else None,
            "last_check_success": last_log.success if last_log else None
        })
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse({"status": "healthy"})


@app.get("/download/{directive_id}")
async def download_pdf(directive_id: int, db: Session = Depends(get_db)):
    """Download PDF for a directive"""
    try:
        directive = db.query(MasterDirective).filter(MasterDirective.id == directive_id).first()
        if not directive:
            raise HTTPException(status_code=404, detail="Directive not found")

        if not directive.pdf_local_path:
            raise HTTPException(status_code=404, detail="PDF not available")

        file_path = Path(settings.PDF_STORAGE_PATH) / directive.pdf_local_path
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="PDF file not found")

        return FileResponse(
            path=file_path,
            media_type='application/pdf',
            filename=f"{directive.title[:50]}.pdf"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
