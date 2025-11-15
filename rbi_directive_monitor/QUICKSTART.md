# Quick Setup Guide

## For First Time Users

### Step 1: Extract the Project
Unzip the `rbi_directive_monitor.zip` to your desired location.

### Step 2: Configure Environment

Edit `.env` file with your settings:

```bash
# Essential settings that need changes:
ALERT_EMAIL=your-email@company.com
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password
SCRAPE_INTERVAL_HOURS=24
```

### Step 3: Run the Application

**On Linux/Mac:**
```bash
bash start.sh
```

**On Windows:**
```bash
start.bat
```

This will:
- Create Python virtual environment
- Install all dependencies
- Initialize database
- Start the application

### Step 4: Access Dashboard

Open your browser and visit:
- http://localhost:8000/

## Folder Locations After Running

- **Downloaded PDFs**: `data/pdfs/` (organized by YYYY/MM)
- **Logs**: `logs/rbi_monitor.log`
- **Database**: `rbi_monitor.db` (SQLite) or configured PostgreSQL

## Common Tasks

### Manual Scrape
Click "Check Now" button on dashboard or:
```bash
curl -X POST http://localhost:8000/api/manual-scrape
```

### View API Documentation
Visit: http://localhost:8000/docs

### Change Keywords
Edit: `data/keywords.json`

### Increase Sensitivity
Edit `.env`:
```env
SIMILARITY_THRESHOLD=0.2  # Lower = more sensitive
```

### Stop Application
Press: `Ctrl + C`

## Need Help?

1. Check `logs/rbi_monitor.log` for errors
2. Verify `.env` configuration
3. Ensure port 8000 is available
4. Check internet connectivity

## Logs Location

Monitor the application in real-time:

**Linux/Mac:**
```bash
tail -f logs/rbi_monitor.log
```

**Windows (PowerShell):**
```powershell
Get-Content logs/rbi_monitor.log -Wait
```
