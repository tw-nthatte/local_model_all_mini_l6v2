"""
PDF Download module for RBI Master Directives
Handles downloading and storing PDF files
"""
import requests
from pathlib import Path
import logging
from typing import Optional, Tuple
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)


class PDFDownloader:
    """
    Handles PDF downloading and file organization
    """

    def __init__(self):
        """Initialize downloader"""
        self.storage_path = Path(settings.PDF_STORAGE_PATH)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.max_size_mb = settings.MAX_PDF_SIZE_MB
        logger.info(f"PDFDownloader initialized. Storage: {self.storage_path}")

    def download_pdf(self, url: str, directive_title: str, pub_date: datetime) -> Optional[Tuple[str, int]]:
        """
        Download PDF from URL

        Args:
            url: URL to download from
            directive_title: Title of directive (for naming)
            pub_date: Publication date

        Returns:
            Tuple of (file_path, file_size) or None if download fails
        """
        if not url:
            logger.warning("Empty URL provided for download")
            return None

        try:
            logger.info(f"Downloading PDF from: {url}")

            # Set timeout and headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.get(url, timeout=settings.REQUEST_TIMEOUT, headers=headers, stream=True)
            response.raise_for_status()

            # Check file size
            content_length = response.headers.get('content-length')
            if content_length:
                file_size_mb = int(content_length) / (1024 * 1024)
                if file_size_mb > self.max_size_mb:
                    logger.warning(f"PDF too large: {file_size_mb:.2f} MB (max: {self.max_size_mb} MB)")
                    return None

            # Generate filename
            filename = self._generate_filename(directive_title, pub_date)

            # Organize by year/month
            year_month = pub_date.strftime("%Y/%m")
            file_dir = self.storage_path / year_month
            file_dir.mkdir(parents=True, exist_ok=True)

            filepath = file_dir / filename

            # Download and write file
            file_size = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        file_size += len(chunk)

            logger.info(f"PDF downloaded successfully: {filepath} ({file_size / 1024:.2f} KB)")

            # Return relative path for database storage
            relative_path = str(filepath.relative_to(self.storage_path))
            return relative_path, file_size

        except requests.Timeout:
            logger.error(f"Download timeout for: {url}")
            return None
        except requests.RequestException as e:
            logger.error(f"Download failed for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading PDF: {e}")
            return None

    def _generate_filename(self, title: str, pub_date: datetime) -> str:
        """
        Generate a safe filename from title and date

        Args:
            title: Directive title
            pub_date: Publication date

        Returns:
            Safe filename
        """
        try:
            # Sanitize title - remove special characters
            safe_title = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in title)
            safe_title = safe_title.strip().replace(' ', '_')[:50]

            # Prepend date
            date_str = pub_date.strftime("%Y%m%d")
            filename = f"{date_str}_{safe_title}.pdf"

            return filename
        except Exception as e:
            logger.warning(f"Error generating filename: {e}")
            return f"{datetime.utcnow().strftime('%Y%m%d')}_directive.pdf"

    def file_exists(self, filepath: str) -> bool:
        """
        Check if file already exists

        Args:
            filepath: Relative path from storage root

        Returns:
            True if file exists
        """
        full_path = self.storage_path / filepath
        return full_path.exists()

    def get_file_path(self, relative_path: str) -> Optional[Path]:
        """
        Get full file path from relative path

        Args:
            relative_path: Relative path

        Returns:
            Full Path object or None
        """
        full_path = self.storage_path / relative_path
        if full_path.exists():
            return full_path
        return None


def download_pdf(url: str, directive_title: str, pub_date: datetime) -> Optional[Tuple[str, int]]:
    """
    Convenience function to download PDF

    Args:
        url: PDF URL
        directive_title: Directive title
        pub_date: Publication date

    Returns:
        Tuple of (relative_path, file_size) or None
    """
    downloader = PDFDownloader()
    return downloader.download_pdf(url, directive_title, pub_date)
