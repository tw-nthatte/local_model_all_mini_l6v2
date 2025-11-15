"""
Database models and session management for RBI Master Directives Monitor
Uses SQLAlchemy ORM for database operations
"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Float, Text, Index, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import logging
from app.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

class MasterDirective(Base):
    """
    SQLAlchemy model for storing master directive information
    Tracks all metadata including classification results and download status
    """
    __tablename__ = "master_directives"

    id = Column(Integer, primary_key=True, index=True)

    # Directive metadata
    title = Column(String(500), nullable=False, index=True)
    category = Column(String(200), nullable=True)
    publication_date = Column(DateTime, nullable=False, index=True)
    url = Column(String(1000), unique=True, nullable=False)
    pdf_url = Column(String(1000), nullable=True)

    # Classification results
    is_relevant = Column(Boolean, default=False, index=True)
    similarity_score = Column(Float, nullable=True)
    keywords_matched = Column(Text, nullable=True)  # JSON string of matched keywords

    # PDF download information
    pdf_downloaded = Column(Boolean, default=False)
    pdf_local_path = Column(String(500), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)

    # Timestamp tracking
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes for common queries
    __table_args__ = (
        Index('idx_is_relevant', 'is_relevant'),
        Index('idx_pub_date_relevant', 'publication_date', 'is_relevant'),
    )

    def __repr__(self):
        return f"<MasterDirective(title='{self.title[:50]}...', date={self.publication_date.date()})>"

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'category': self.category,
            'publication_date': self.publication_date.isoformat(),
            'url': self.url,
            'is_relevant': self.is_relevant,
            'similarity_score': self.similarity_score,
            'keywords_matched': self.keywords_matched,
            'pdf_downloaded': self.pdf_downloaded,
            'pdf_local_path': self.pdf_local_path,
        }


class ScrapeLog(Base):
    """
    Tracks each scraping run for monitoring and debugging
    Records statistics and errors for each execution
    """
    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Execution metadata
    scrape_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    duration_seconds = Column(Float, nullable=True)

    # Statistics
    total_directives_found = Column(Integer, default=0)
    new_directives_found = Column(Integer, default=0)
    relevant_directives = Column(Integer, default=0)
    pdfs_downloaded = Column(Integer, default=0)

    # Execution status
    success = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)

    def __repr__(self):
        status = "✓ SUCCESS" if self.success else "✗ FAILED"
        return f"<ScrapeLog(timestamp={self.scrape_timestamp}, {status})>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'scrape_timestamp': self.scrape_timestamp.isoformat(),
            'duration_seconds': self.duration_seconds,
            'total_directives_found': self.total_directives_found,
            'new_directives_found': self.new_directives_found,
            'relevant_directives': self.relevant_directives,
            'pdfs_downloaded': self.pdfs_downloaded,
            'success': self.success,
            'error_message': self.error_message,
        }


# Database engine and session factory
try:
    engine = create_engine(
        settings.DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info(f"Database engine created: {settings.DATABASE_URL}")
except Exception as e:
    logger.error(f"Failed to create database engine: {e}")
    raise


def init_db():
    """Initialize database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def get_db():
    """Dependency function for FastAPI to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_latest_directive_date():
    """Get the latest directive publication date from database"""
    db = SessionLocal()
    try:
        latest = db.query(func.max(MasterDirective.publication_date)).scalar()
        return latest
    finally:
        db.close()


def add_directive(directive_data: dict) -> MasterDirective:
    """Add a new directive to the database"""
    db = SessionLocal()
    try:
        directive = MasterDirective(**directive_data)
        db.add(directive)
        db.commit()
        db.refresh(directive)
        logger.info(f"Added directive: {directive.title[:50]}...")
        return directive
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to add directive: {e}")
        raise
    finally:
        db.close()


def add_scrape_log(log_data: dict) -> ScrapeLog:
    """Add a scrape execution log to the database"""
    db = SessionLocal()
    try:
        log = ScrapeLog(**log_data)
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to add scrape log: {e}")
        raise
    finally:
        db.close()
