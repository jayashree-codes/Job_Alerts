# Edinburgh Job Alert - Sainsbury's & Tesco 

Polls both career sites and opens a sticky-note HTML page in your browser
whenever new jobs appear, with clickable apply links.

## SETUP
-----
1. Install dependencies:
       pip install requests beautifulsoup4 playwright
       playwright install chromium

2. (Optional) Set your email credentials for email alerts too:
   - Create a Gmail App Password: https://myaccount.google.com/apppasswords
   - Fill in the CONFIG section below, and set NOTIFY_EMAIL = True

3. Run once manually to seed the known-jobs cache:
       python job-search.py

4. Schedule it (runs every 30 min):
   - Mac:     crontab -e  →  */30 * * * * /usr/bin/python3 /path-to-file/job-search.py
   - Windows: Task Scheduler → repeat every 30 minutes

## Duplicate prevention
--------------------
Jobs are deduplicated by BOTH their URL and their normalised title+location,
so the same posting won't appear twice even if the URL changes slightly.
Seen jobs are stored in 'seen_jobs.json' next to this script.

### NOTE: Update the job page URLS for Sainsbury's and Tesco in the python file
