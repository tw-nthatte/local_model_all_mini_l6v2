"""
Scheduler module for RBI Master Directives Monitor
Orchestrates scraping, classification, downloading, and notifications
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
from datetime import datetime
import traceback
from typing import Optional

from app.scraper import RBIScraper, get_new_directives
from app.classifier import DirectiveClassifier
from app.downloader import download_pdf
from app.notifier import send_alert, send_error_notification
from app.database import (
    MasterDirective, 
    ScrapeLog,
    SessionLocal, 
    get_latest_directive_date,
    add_directive,
    add_scrape_log
)
from app.config import settings

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def monitor_rbi_directives() -> None:
    """
    Main monitoring job that orchestrates the entire workflow

    Workflow:
    1. Scrape RBI website
    2. Filter for new directives
    3. Classify directives
    4. Download PDFs for relevant ones
    5. Store in database
    6. Send notifications
    """
    job_start_time = datetime.utcnow()
    logger.info("=" * 80)
    logger.info("STARTING RBI DIRECTIVES MONITORING JOB")
    logger.info("=" * 80)

    # Initialize counters
    stats = {
        'total_found': 0,
        'new_found': 0,
        'relevant_found': 0,
        'pdfs_downloaded': 0,
        'errors': 0,
        'success': False
    }

    error_messages = []
    relevant_directives_to_notify = []

    try:
        # Step 1: Scrape RBI website
        logger.info("[STEP 1/5] Scraping RBI Master Directives page...")
        scraper = RBIScraper()
        all_directives = scraper.scrape()
        stats['total_found'] = len(all_directives)
        logger.info(f"✓ Found {stats['total_found']} total directives")

        if not all_directives:
            logger.warning("No directives found. Exiting job.")
            raise Exception("No directives found from RBI website")

        # Step 2: Filter for new directives
        logger.info("[STEP 2/5] Filtering for new directives...")
        latest_date = get_latest_directive_date()
        new_directives = get_new_directives(all_directives, latest_date)
        stats['new_found'] = len(new_directives)
        logger.info(f"✓ Found {stats['new_found']} new directives")

        if not new_directives:
            logger.info("No new directives found. Job complete.")
            stats['success'] = True
        else:
            # Step 3: Classify directives
            logger.info("[STEP 3/5] Classifying directives using NLP...")
            classifier = DirectiveClassifier()
            classified_directives = classifier.classify_batch(new_directives)

            relevant_directives = [d for d in classified_directives if d['is_relevant']]
            stats['relevant_found'] = len(relevant_directives)
            logger.info(f"✓ Classified {stats['relevant_found']} as relevant")

            # Step 4: Download PDFs and store in database
            logger.info("[STEP 4/5] Downloading PDFs and storing in database...")

            for directive in classified_directives:
                try:
                    # Store directive in database
                    db_directive_data = {
                        'title': directive['title'],
                        'category': directive.get('category', 'General'),
                        'publication_date': directive['publication_date'],
                        'url': directive['url'],
                        'pdf_url': directive.get('pdf_url'),
                        'is_relevant': directive['is_relevant'],
                        'similarity_score': directive.get('similarity_score', 0),
                        'keywords_matched': directive.get('keywords_matched', '[]'),
                        'pdf_downloaded': False,
                        'pdf_local_path': None,
                        'file_size_bytes': None
                    }

                    # Try to download PDF if relevant and URL exists
                    if directive['is_relevant'] and directive.get('pdf_url'):
                        try:
                            logger.info(f"Downloading PDF for: {directive['title'][:50]}...")
                            result = download_pdf(
                                directive['pdf_url'],
                                directive['title'],
                                directive['publication_date']
                            )

                            if result:
                                pdf_path, file_size = result
                                db_directive_data['pdf_downloaded'] = True
                                db_directive_data['pdf_local_path'] = pdf_path
                                db_directive_data['file_size_bytes'] = file_size
                                stats['pdfs_downloaded'] += 1
                                logger.info(f"✓ PDF downloaded: {pdf_path}")
                            else:
                                logger.warning(f"Failed to download PDF for: {directive['title'][:50]}")
                        except Exception as e:
                            logger.warning(f"PDF download error: {e}")
                            stats['errors'] += 1

                    # Add to database
                    add_directive(db_directive_data)

                    # Add to notification list if relevant
                    if directive['is_relevant']:
                        relevant_directives_to_notify.append(directive)

                except Exception as e:
                    error_msg = f"Error processing directive: {e}"
                    logger.error(error_msg)
                    error_messages.append(error_msg)
                    stats['errors'] += 1
                    continue

            logger.info(f"✓ Downloaded {stats['pdfs_downloaded']} PDFs")

            # Step 5: Send notifications
            logger.info("[STEP 5/5] Sending notifications...")
            if relevant_directives_to_notify:
                try:
                    send_alert(relevant_directives_to_notify)
                    logger.info(f"✓ Notification sent for {len(relevant_directives_to_notify)} directives")
                except Exception as e:
                    logger.warning(f"Failed to send notification: {e}")

            stats['success'] = True

    except Exception as e:
        error_msg = f"Job execution error: {str(e)}"
        logger.error(error_msg)
        error_messages.append(error_msg)
        logger.error(traceback.format_exc())

        # Try to send error notification
        try:
            send_error_notification(error_msg)
        except:
            pass

    finally:
        # Calculate job duration
        job_duration = (datetime.utcnow() - job_start_time).total_seconds()

        # Log statistics
        logger.info("=" * 80)
        logger.info("JOB STATISTICS:")
        logger.info(f"  Total directives found: {stats['total_found']}")
        logger.info(f"  New directives: {stats['new_found']}")
        logger.info(f"  Relevant directives: {stats['relevant_found']}")
        logger.info(f"  PDFs downloaded: {stats['pdfs_downloaded']}")
        logger.info(f"  Errors encountered: {stats['errors']}")
        logger.info(f"  Job duration: {job_duration:.2f} seconds")
        logger.info(f"  Status: {'SUCCESS' if stats['success'] else 'FAILED'}")
        logger.info("=" * 80)

        # Store log in database
        try:
            log_data = {
                'scrape_timestamp': job_start_time,
                'duration_seconds': job_duration,
                'total_directives_found': stats['total_found'],
                'new_directives_found': stats['new_found'],
                'relevant_directives': stats['relevant_found'],
                'pdfs_downloaded': stats['pdfs_downloaded'],
                'success': stats['success'],
                'error_message': '\n'.join(error_messages) if error_messages else None
            }
            add_scrape_log(log_data)
        except Exception as e:
            logger.error(f"Failed to log statistics: {e}")


def start_scheduler() -> None:
    """
    Start the background scheduler
    Configures and starts periodic monitoring jobs
    """
    if not settings.ENABLE_SCHEDULER:
        logger.warning("Scheduler is disabled in configuration")
        return

    try:
        # Add job to run at specified interval
        interval_hours = settings.SCRAPE_INTERVAL_HOURS

        scheduler.add_job(
            monitor_rbi_directives,
            trigger=IntervalTrigger(hours=interval_hours),
            id='rbi_monitor_job',
            name='RBI Master Directives Monitor',
            replace_existing=True,
            misfire_grace_time=60,
            coalesce=True
        )

        logger.info(f"Scheduler configured: Job will run every {interval_hours} hour(s)")

        # Start scheduler
        if not scheduler.running:
            scheduler.start()
            logger.info("✓ Background scheduler started successfully")
        else:
            logger.info("Scheduler already running")

    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise


def stop_scheduler() -> None:
    """Stop the background scheduler"""
    try:
        if scheduler.running:
            scheduler.shutdown()
            logger.info("✓ Scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")


def run_job_manually() -> dict:
    """
    Manually trigger the monitoring job
    Useful for testing and on-demand execution

    Returns:
        Dictionary with job statistics
    """
    logger.info("Manual job execution triggered")
    monitor_rbi_directives()
    return {"status": "Job executed. Check logs for details."}


def get_scheduler_status() -> dict:
    """
    Get current scheduler status

    Returns:
        Dictionary with scheduler information
    """
    return {
        'running': scheduler.running,
        'jobs': len(scheduler.get_jobs()),
        'interval_hours': settings.SCRAPE_INTERVAL_HOURS,
        'next_run': str(scheduler.get_jobs()[0].next_run_time) if scheduler.get_jobs() else None
    }
