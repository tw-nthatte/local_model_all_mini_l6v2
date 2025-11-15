# RBI Master Directives Monitor

A production-ready FastAPI-based system for automated monitoring, classification, and management of RBI Master Directives related to IT governance and digital banking.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-blue)

## Features

✅ **Automated Scraping** - Periodic monitoring of RBI website (no webhooks needed)
✅ **NLP Classification** - Intelligent filtering using TF-IDF and cosine similarity
✅ **PDF Download** - Automatic download of relevant directives
✅ **Email Alerts** - Notifications for new IT/Digital directives
✅ **Dashboard** - Web-based monitoring interface
✅ **REST API** - Full REST API for integration
✅ **Database Logging** - Complete audit trail of all operations
✅ **Production-Ready** - Error handling, logging, monitoring

## Quick Start

### 1. Prerequisites

- Python 3.10+
- pip or poetry
- SQLite (included) or PostgreSQL (optional)

### 2. Installation

```bash
# Clone or extract the project
cd rbi_directive_monitor

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

```bash
# Copy example .env to .env
cp .env.example .env

# Edit .env with your configuration
# - Set SCRAPE_INTERVAL_HOURS (default: 24)
# - Configure email alerts (optional)
# - Set DATABASE_URL if using PostgreSQL
```

### 4. Run Application

```bash
# Using uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or using Python module
python -m uvicorn app.main:app --reload
```

Access the application:
- Dashboard: http://localhost:8000
- API Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Configuration

All settings are managed through the `.env` file:

### Essential Settings

```env
# Scraping
SCRAPE_INTERVAL_HOURS=24          # Check RBI website daily
ENABLE_SCHEDULER=true             # Enable background scheduler

# Classification
SIMILARITY_THRESHOLD=0.3          # Classification sensitivity (0-1)
MIN_KEYWORD_MATCHES=2             # Minimum keywords to match

# Database
DATABASE_URL=sqlite:///./rbi_monitor.db  # SQLite or PostgreSQL
```

### Email Alerts Configuration

For Gmail:
1. Enable 2-factor authentication in your Google Account
2. Generate app-specific password: https://myaccount.google.com/apppasswords
3. Add to .env:
```env
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password
ALERT_EMAIL=compliance@company.com
```

## Project Structure

```
rbi_directive_monitor/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application
│   ├── config.py                  # Configuration management
│   ├── database.py                # Database models
│   ├── scraper.py                 # Web scraping logic
│   ├── classifier.py              # NLP classification
│   ├── downloader.py              # PDF download handler
│   ├── notifier.py                # Email notifications
│   ├── scheduler.py               # Background job scheduler
│   └── routes/
│       └── api.py                 # Additional API routes
├── templates/
│   ├── base.html                  # Base template
│   ├── dashboard.html             # Main dashboard
│   ├── directives.html            # Directives list
│   ├── logs.html                  # Scraping logs
│   └── settings.html              # Settings page
├── static/
│   ├── css/
│   │   └── style.css              # Main stylesheet
│   └── js/
│       └── main.js                # Main JavaScript
├── data/
│   ├── keywords.json              # Classification keywords
│   └── pdfs/                      # Downloaded PDFs
├── logs/
│   └── rbi_monitor.log            # Application logs
├── requirements.txt               # Python dependencies
├── .env                           # Configuration (copy from .env.example)
└── README.md                      # This file
```

## How It Works

### Workflow

1. **Scheduled Job** (APScheduler)
   - Triggered at specified interval (default: 24 hours)
   - Can also be manually triggered via API

2. **Scraping** (RBIScraper)
   - Fetches RBI Master Directives page
   - Parses HTML to extract directive metadata
   - Compares with latest stored date to find new directives

3. **Classification** (DirectiveClassifier)
   - Uses TF-IDF vectorization and cosine similarity
   - Matches directive text against IT governance/digital banking keywords
   - Assigns relevance score and matched keywords

4. **PDF Download** (PDFDownloader)
   - Downloads PDF files for relevant directives
   - Organizes by year/month folder structure
   - Stores metadata in database

5. **Notification** (EmailNotifier)
   - Sends email alert if new relevant directives found
   - Logs all operations for audit trail

6. **Storage** (Database)
   - Stores directives with classification results
   - Maintains scraping logs
   - Provides data for dashboard and API

## Dashboard

The web dashboard provides:

- **Dashboard** - Overview with statistics and recent directives
- **Directives** - Full list with search and filtering
- **Logs** - Scraping execution history
- **Settings** - Configuration reference and API documentation

## REST API

### Endpoints

**Directives:**
- `GET /api/directives` - All directives
- `GET /api/directives/relevant` - Only relevant directives
- `GET /api/directives/{id}` - Get specific directive
- `GET /api/directives/search?q=query` - Search directives
- `GET /api/directives/category/{category}` - By category

**Statistics:**
- `GET /api/stats` - Overall statistics
- `GET /api/statistics/summary` - Summary stats by category

**Management:**
- `GET /api/status` - Application status
- `GET /api/logs` - Scraping logs
- `POST /api/manual-scrape` - Trigger manual scrape

**Utility:**
- `GET /health` - Health check
- `GET /download/{id}` - Download PDF

### Example API Usage

```bash
# Get relevant directives
curl http://localhost:8000/api/directives/relevant

# Search directives
curl "http://localhost:8000/api/directives/search?q=cyber%20security"

# Get statistics
curl http://localhost:8000/api/stats

# Trigger manual scrape
curl -X POST http://localhost:8000/api/manual-scrape

# Check health
curl http://localhost:8000/health
```

## Customization

### Adding More Keywords

Edit `data/keywords.json`:

```json
{
    "it_governance": ["your-keyword-1", "your-keyword-2"],
    "digital_banking": ["your-keyword-3"],
    "compliance": ["your-keyword-4"]
}
```

### Adjusting Classification Threshold

Edit `.env`:

```env
SIMILARITY_THRESHOLD=0.4  # Higher = stricter, Lower = more inclusive
```

### Changing Scrape Interval

Edit `.env`:

```env
SCRAPE_INTERVAL_HOURS=12  # Check every 12 hours instead of daily
```

## Production Deployment

### Using Gunicorn

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Using Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t rbi-monitor .
docker run -p 8000:8000 -v $(pwd)/data:/app/data rbi-monitor
```

### Environment Setup

For production, ensure:

1. ✅ Use PostgreSQL instead of SQLite
2. ✅ Set DEBUG=false in .env
3. ✅ Configure email credentials
4. ✅ Set up proper logging (sentry recommended)
5. ✅ Use reverse proxy (Nginx)
6. ✅ Enable HTTPS/SSL
7. ✅ Set up database backups
8. ✅ Configure monitoring and alerting

## Logging

Logs are written to `logs/rbi_monitor.log` with configurable levels:

```env
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

Logs capture:
- Scraping runs (success/failure)
- Classification results
- PDF downloads
- Email sends
- Database operations
- Errors and exceptions

## Troubleshooting

### Scheduler Not Starting

Check logs:
```bash
tail -f logs/rbi_monitor.log
```

Ensure `ENABLE_SCHEDULER=true` in .env

### PDF Download Failures

- Check PDF URL is valid
- Verify file size < MAX_PDF_SIZE_MB
- Check storage directory permissions

### Email Not Sending

- Verify SMTP credentials in .env
- For Gmail: Use app-specific password, not account password
- Check firewall/network connectivity to SMTP server

### Database Errors

- For SQLite: Ensure write permissions in app directory
- For PostgreSQL: Verify connection string and database exists

## Performance Tips

1. **Increase Check Interval** - Reduce database load with larger SCRAPE_INTERVAL_HOURS
2. **Archive Old Records** - Implement record archival for directives older than N months
3. **Use PostgreSQL** - Better for production than SQLite
4. **Enable Indexing** - Database indexes are created on publication_date and is_relevant
5. **Monitor Disk Space** - PDFs storage can grow; implement cleanup policies

## Contributing & Enhancements

Potential improvements:

- [ ] OCR support for image-based PDFs
- [ ] Webhook notifications (Slack, Teams)
- [ ] Advanced search with filters
- [ ] Batch operations (mark multiple as relevant/irrelevant)
- [ ] Category suggestions using ML
- [ ] PDF content analysis and extraction
- [ ] User authentication and multi-user support
- [ ] Audit log with user tracking

## Support

For issues or questions:

1. Check logs in `logs/rbi_monitor.log`
2. Review `.env` configuration
3. Test API endpoints at `http://localhost:8000/docs`

## License

This project is provided as-is for compliance monitoring purposes.

## References

- RBI Master Directives: https://www.rbi.org.in/scripts/BS_ViewMasterDirections.aspx
- FastAPI Documentation: https://fastapi.tiangolo.com
- APScheduler Documentation: https://apscheduler.readthedocs.io
- scikit-learn (TF-IDF): https://scikit-learn.org

---

**Version:** 1.0.0  
**Last Updated:** November 2024
