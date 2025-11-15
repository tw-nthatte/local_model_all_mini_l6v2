"""
Web scraper module for RBI Master Directives
Fetches and parses the RBI Master Directives page using requests and BeautifulSoup
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging
from typing import List, Dict, Optional
from app.config import settings
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


class RBIScraper:
    """
    Scraper for RBI Master Directives page
    Handles HTTP requests, HTML parsing, and data extraction
    """

    def __init__(self):
        self.url = settings.RBI_MASTER_DIRECTIVES_URL
        self.timeout = settings.REQUEST_TIMEOUT
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        logger.info(f"RBIScraper initialized for URL: {self.url}")

    def fetch_page(self) -> Optional[str]:
        """
        Fetch the RBI Master Directives page

        Returns:
            HTML content of the page or None if fetch fails
        """
        try:
            logger.info(f"Fetching RBI page: {self.url}")
            response = self.session.get(self.url, timeout=self.timeout)
            response.raise_for_status()
            logger.info(f"Successfully fetched RBI page (Status: {response.status_code})")
            return response.text
        except requests.Timeout:
            logger.error(f"Request timeout after {self.timeout} seconds")
            return None
        except requests.RequestException as e:
            logger.error(f"Error fetching RBI page: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching page: {e}")
            return None

    def parse_directives(self, html: str) -> List[Dict]:
        """
        Parse master directives from HTML content

        Extracts directive information including:
        - Title
        - Publication date
        - Category
        - URLs (page and PDF)

        Args:
            html: HTML content of the page

        Returns:
            List of dictionaries containing directive information
        """
        directives = []

        try:
            soup = BeautifulSoup(html, 'lxml')

            # Find all table rows that contain directives
            # Adjust selectors based on RBI page structure
            rows = soup.find_all('tr')

            for row in rows:
                try:
                    cells = row.find_all('td')
                    if len(cells) < 2:
                        continue

                    # Extract directive link
                    link = row.find('a', href=True)
                    if not link:
                        continue

                    title_text = link.get_text(strip=True)
                    if not title_text or len(title_text) < 5:
                        continue

                    # Extract URL
                    href = link.get('href', '')
                    if not href:
                        continue

                    # Extract date information from the row
                    date_text = None
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        # Try to parse as date
                        try:
                            parsed_date = date_parser.parse(cell_text, fuzzy=True)
                            date_text = parsed_date
                            break
                        except:
                            continue

                    if not date_text:
                        date_text = datetime.utcnow()

                    # Extract category from row context
                    category = self._extract_category(row)

                    directive = {
                        'title': title_text,
                        'url': self._make_absolute_url(href),
                        'publication_date': date_text,
                        'category': category,
                        'pdf_url': self._make_absolute_url(href) if 'pdf' in href.lower() else None
                    }

                    directives.append(directive)

                except Exception as e:
                    logger.debug(f"Error parsing row: {e}")
                    continue

            logger.info(f"Parsed {len(directives)} directives from page")
            return directives

        except Exception as e:
            logger.error(f"Error parsing directives: {e}")
            return []

    def _extract_category(self, element) -> str:
        """
        Extract category information from HTML element

        Args:
            element: BeautifulSoup element

        Returns:
            Category name or 'General' if not found
        """
        try:
            # Look for category in preceding heading
            heading = element.find_previous(['h2', 'h3', 'h4', 'th'])
            if heading:
                heading_text = heading.get_text(strip=True)
                if heading_text and len(heading_text) > 2:
                    return heading_text

            # Look in parent section
            section = element.find_previous('section')
            if section:
                section_heading = section.find(['h1', 'h2', 'h3'])
                if section_heading:
                    return section_heading.get_text(strip=True)

        except Exception as e:
            logger.debug(f"Error extracting category: {e}")

        return "General"

    def _make_absolute_url(self, url: str) -> str:
        """
        Convert relative URL to absolute URL

        Args:
            url: Relative or absolute URL

        Returns:
            Absolute URL
        """
        if not url:
            return ""

        if url.startswith('http://') or url.startswith('https://'):
            return url

        base_url = "https://www.rbi.org.in"
        if url.startswith('/'):
            return f"{base_url}{url}"
        else:
            return f"{base_url}/{url}"

    def scrape(self) -> List[Dict]:
        """
        Main scraping method
        Fetches page and parses directives

        Returns:
            List of directive dictionaries
        """
        try:
            html = self.fetch_page()
            if not html:
                logger.warning("Failed to fetch page content")
                return []

            directives = self.parse_directives(html)
            logger.info(f"Scraping completed. Found {len(directives)} directives")
            return directives

        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            return []


def get_new_directives(all_directives: List[Dict], latest_date: Optional[datetime]) -> List[Dict]:
    """
    Filter directives to get only new ones after the latest stored date

    Args:
        all_directives: All scraped directives
        latest_date: Latest directive date in database

    Returns:
        List of new directives only
    """
    if not latest_date:
        logger.info("No previous directives found. Treating all as new.")
        return all_directives

    new_directives = [
        d for d in all_directives 
        if d['publication_date'] > latest_date
    ]

    logger.info(f"Filtered {len(all_directives)} directives to {len(new_directives)} new directives")
    return new_directives
