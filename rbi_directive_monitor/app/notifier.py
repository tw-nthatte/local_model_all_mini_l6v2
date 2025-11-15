"""
Notification module for RBI Master Directives Monitor
Handles email alerts and logging
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class EmailNotifier:
    """
    Sends email notifications for new directives
    """

    def __init__(self):
        """Initialize email notifier"""
        self.enabled = settings.ENABLE_EMAIL_ALERTS
        self.server = settings.SMTP_SERVER
        self.port = settings.SMTP_PORT
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_USERNAME
        self.to_email = settings.ALERT_EMAIL

        if self.enabled:
            logger.info(f"Email notifications enabled. Recipient: {self.to_email}")
        else:
            logger.info("Email notifications disabled (credentials not configured)")

    def send_alert(self, directives: List[Dict], subject: Optional[str] = None) -> bool:
        """
        Send email alert with directive details

        Args:
            directives: List of directive dictionaries
            subject: Email subject (optional)

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.debug("Email notifications disabled. Skipping send.")
            return False

        if not directives:
            logger.warning("No directives provided for email alert")
            return False

        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject or f"New RBI Directives: {len(directives)} found"
            msg['From'] = self.from_email
            msg['To'] = self.to_email

            # Create HTML body
            html_body = self._format_email_body(directives)

            # Attach body
            msg.attach(MIMEText(html_body, 'html'))

            # Send email
            logger.info(f"Sending email alert to {self.to_email}")

            with smtplib.SMTP(self.server, self.port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info("Email sent successfully")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def _format_email_body(self, directives: List[Dict]) -> str:
        """
        Format email body with directive information

        Args:
            directives: List of directive dictionaries

        Returns:
            HTML formatted email body
        """
        rows = ""
        for directive in directives:
            if directive.get('is_relevant'):
                rows += f"""
                <tr>
                    <td style="border: 1px solid #ddd; padding: 8px;">{directive.get('publication_date', 'N/A')}</td>
                    <td style="border: 1px solid #ddd; padding: 8px;">{directive.get('title', 'N/A')[:80]}</td>
                    <td style="border: 1px solid #ddd; padding: 8px;">{directive.get('category', 'N/A')}</td>
                    <td style="border: 1px solid #ddd; padding: 8px;">{directive.get('similarity_score', 0):.2f}</td>
                </tr>
                """

        html = f"""
        <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    h2 {{ color: #1f4788; }}
                    table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                    th {{ background-color: #1f4788; color: white; padding: 12px; text-align: left; }}
                    td {{ border: 1px solid #ddd; padding: 8px; }}
                    tr:nth-child(even) {{ background-color: #f9f9f9; }}
                    .footer {{ margin-top: 20px; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <h2>RBI Master Directives Alert</h2>
                <p>New IT Governance and Digital Banking directives have been found:</p>

                <table>
                    <thead>
                        <tr>
                            <th>Publication Date</th>
                            <th>Title</th>
                            <th>Category</th>
                            <th>Relevance Score</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>

                <p>Log in to the dashboard for more details and to download PDFs.</p>

                <div class="footer">
                    <p>RBI Master Directives Monitor</p>
                    <p>This is an automated notification. Please do not reply to this email.</p>
                </div>
            </body>
        </html>
        """

        return html

    def send_error_alert(self, error_message: str) -> bool:
        """
        Send error notification

        Args:
            error_message: Error message to send

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        try:
            msg = MIMEMultipart()
            msg['Subject'] = "RBI Monitor - Error Alert"
            msg['From'] = self.from_email
            msg['To'] = self.to_email

            html_body = f"""
            <html>
                <body>
                    <h2 style="color: red;">RBI Directives Monitor - Error</h2>
                    <p>{error_message}</p>
                    <p style="color: #666; font-size: 12px;">
                        Please check the application logs for more information.
                    </p>
                </body>
            </html>
            """

            msg.attach(MIMEText(html_body, 'html'))

            with smtplib.SMTP(self.server, self.port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info("Error alert sent successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to send error alert: {e}")
            return False


def send_alert(directives: List[Dict]) -> bool:
    """
    Convenience function to send email alert

    Args:
        directives: List of directive dictionaries

    Returns:
        True if sent successfully
    """
    notifier = EmailNotifier()
    return notifier.send_alert(directives)


def send_error_notification(error_msg: str) -> bool:
    """
    Convenience function to send error notification

    Args:
        error_msg: Error message

    Returns:
        True if sent successfully
    """
    notifier = EmailNotifier()
    return notifier.send_error_alert(error_msg)
