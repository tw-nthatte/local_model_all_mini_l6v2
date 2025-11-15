"""
Configuration module for RBI Master Directives Monitor
Loads settings from environment variables and .env file
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
import logging

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """Application configuration settings"""

    # Application
    APP_NAME: str = "RBI Master Directives Monitor"
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = APP_ENV == "development"

    # Database Configuration
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "sqlite:///./rbi_monitor.db"
    )

    # RBI Scraper Configuration
    RBI_MASTER_DIRECTIVES_URL: str = "https://www.rbi.org.in/scripts/BS_ViewMasterDirections.aspx"
    REQUEST_TIMEOUT: int = 30

    # Scheduler Configuration
    SCRAPE_INTERVAL_HOURS: int = int(os.getenv("SCRAPE_INTERVAL_HOURS", "24"))
    ENABLE_SCHEDULER: bool = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"

    # Classification Configuration
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.3"))
    MIN_KEYWORD_MATCHES: int = 2
    KEYWORDS_FILE: str = os.getenv("KEYWORDS_FILE", "data/keywords.json")

    # PDF Storage Configuration
    PDF_STORAGE_PATH: str = os.getenv("PDF_STORAGE_PATH", "data/pdfs")
    MAX_PDF_SIZE_MB: int = 50

    # Email/Notification Configuration
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    ALERT_EMAIL: str = os.getenv("ALERT_EMAIL", "")
    ENABLE_EMAIL_ALERTS: bool = bool(SMTP_USERNAME and SMTP_PASSWORD and ALERT_EMAIL)

    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = "logs/rbi_monitor.log"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Create settings instance
settings = Settings()

# Setup logging
def setup_logging():
    """Configure logging for the application"""
    log_dir = Path(settings.LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(settings.LOG_FILE),
            logging.StreamHandler()
        ]
    )

    logger.info(f"Logging initialized. Level: {settings.LOG_LEVEL}")

# Ensure PDF directory exists
Path(settings.PDF_STORAGE_PATH).mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print(f"RBI Monitor Configuration:")
    print(f"  Database: {settings.DATABASE_URL}")
    print(f"  Scrape Interval: {settings.SCRAPE_INTERVAL_HOURS} hours")
    print(f"  Classification Threshold: {settings.SIMILARITY_THRESHOLD}")
    print(f"  Email Alerts Enabled: {settings.ENABLE_EMAIL_ALERTS}")
