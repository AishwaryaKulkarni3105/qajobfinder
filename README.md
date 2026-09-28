# QA Job Finder

A Python script that searches multiple public remote job sources for senior QA / SDET roles and saves matching opportunities to a CSV file.

## What it does

- Queries several remote job APIs and job boards
- Filters results for likely senior QA / SDET roles using both job title and description text
- Removes duplicate jobs
- Ranks the best-fit matches
- Saves the results to `latest_remote_qa_jobs.csv`
- Optionally emails the top shortlisted jobs via Gmail SMTP

## Search scope

- Prioritizes remote roles explicitly open to candidates in the United States.
- Includes Peoria-area roles as a secondary option, using ZIP codes beginning with `616` and nearby Illinois cities (approximately a 50-mile area).
- Matches QA/SDET, senior or lead QA, automation testing, software tester, and software test engineering titles. When a posting states required experience, it keeps roles asking for 5–9 years; senior/lead titles with no stated years can still match.
- Currently queries Remotive, RemoteOK, Jobicy, Arbeitnow, and We Work Remotely.

LinkedIn, Indeed, and Dice are not currently queried. This script uses public APIs and accessible public listings; it does not sign in to or scrape account-protected job-board pages.

## Project structure

- `dailyjob_finder.py` — main script
- `latest_remote_qa_jobs.csv` — generated job results
- `requirements.txt` — Python dependencies

## Setup

1. Clone the repository:

```bash
git clone https://github.com/AishwaryaKulkarni3105/qajobfinder.git
cd qajobfinder
```

2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Run the script

```bash
python3 dailyjob_finder.py
```

This will:
- search job sources
- generate a fresh CSV file
- print the shortlisted jobs
- send an email if Gmail credentials are configured

## Gmail email setup

Set these environment variables before running the script:

```bash
export SENDER_EMAIL="aishwaryak3105@gmail.com"
export SENDER_PASSWORD="your-16-character-gmail-app-password"
export RECEIVER_EMAIL="aishwaryak3105@gmail.com"
```

> Use a Gmail app password, not your normal Google account password.

## Notes

- The script is designed to prioritize senior QA / SDET opportunities.
- Some public job APIs may change structure over time.
- The filter is intentionally conservative to reduce false positives, but it may still need tuning for your exact preferences.

## License

This project is for personal use and job-search automation.
