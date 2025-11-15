"""
API routes for RBI Master Directives Monitor
Additional API endpoints for advanced operations
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.database import MasterDirective, get_db
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["directives"])


@router.get("/directives/relevant")
async def get_relevant_directives(
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get only relevant directives with pagination"""
    try:
        directives = db.query(MasterDirective).filter(
            MasterDirective.is_relevant == True
        ).order_by(
            MasterDirective.publication_date.desc()
        ).offset(offset).limit(limit).all()

        total = db.query(MasterDirective).filter(
            MasterDirective.is_relevant == True
        ).count()

        return JSONResponse({
            "total": total,
            "offset": offset,
            "limit": limit,
            "data": [d.to_dict() for d in directives]
        })
    except Exception as e:
        logger.error(f"Error fetching relevant directives: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/directives/search")
async def search_directives(
    q: str = Query(..., min_length=3),
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db)
):
    """Search directives by title or category"""
    try:
        search_term = f"%{q}%"
        directives = db.query(MasterDirective).filter(
            or_(
                MasterDirective.title.ilike(search_term),
                MasterDirective.category.ilike(search_term)
            )
        ).order_by(MasterDirective.publication_date.desc()).limit(limit).all()

        return JSONResponse([d.to_dict() for d in directives])
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/directives/{directive_id}")
async def get_directive(directive_id: int, db: Session = Depends(get_db)):
    """Get detailed information about a specific directive"""
    try:
        directive = db.query(MasterDirective).filter(
            MasterDirective.id == directive_id
        ).first()

        if not directive:
            raise HTTPException(status_code=404, detail="Directive not found")

        return JSONResponse(directive.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching directive: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/directives/category/{category}")
async def get_directives_by_category(
    category: str,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db)
):
    """Get directives by category"""
    try:
        directives = db.query(MasterDirective).filter(
            MasterDirective.category.ilike(f"%{category}%")
        ).order_by(
            MasterDirective.publication_date.desc()
        ).limit(limit).all()

        return JSONResponse([d.to_dict() for d in directives])
    except Exception as e:
        logger.error(f"Error fetching by category: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics/summary")
async def get_summary_statistics(db: Session = Depends(get_db)):
    """Get summary statistics"""
    try:
        from sqlalchemy import func

        total = db.query(MasterDirective).count()
        relevant = db.query(MasterDirective).filter(
            MasterDirective.is_relevant == True
        ).count()
        downloaded = db.query(MasterDirective).filter(
            MasterDirective.pdf_downloaded == True
        ).count()

        # Average similarity score
        avg_score = db.query(func.avg(MasterDirective.similarity_score)).scalar() or 0

        # Count by category
        by_category = db.query(
            MasterDirective.category,
            func.count(MasterDirective.id).label('count')
        ).group_by(MasterDirective.category).all()

        return JSONResponse({
            "total_directives": total,
            "relevant_directives": relevant,
            "pdfs_downloaded": downloaded,
            "average_similarity_score": float(avg_score),
            "by_category": {cat: count for cat, count in by_category}
        })
    except Exception as e:
        logger.error(f"Statistics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
