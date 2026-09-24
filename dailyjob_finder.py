import asyncio
import csv
from datetime import datetime
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
from playwright.async_api import async_playwright

SENIORITY_KEYWORDS = ["senior", "sr", "lead", "sdet", "principal", "staff", "architect"]
TECH_KEYWORDS = ["qa", "quality assurance", "automation", "playwright", "selenium", "rest assured", "api", "test"]
EXCLUDE_KEYWORDS = ["junior", "jr", "intern", "entry", "trainee", "manual qa", "vp", "director"]


def normalize_text(value):
    if not value:
        return ""
    clean = re.sub(r"<[^>]+>", " ", value)
    clean = clean.replace("&nbsp;", " ")
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip().lower()


def format_posted_date(value):
    if not value:
        return datetime.today().strftime('%Y-%m-%d')
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(int(value)).strftime('%Y-%m-%d')
        except Exception:
            return datetime.today().strftime('%Y-%m-%d')
    text = str(value)
    if len(text) >= 10 and text[4] == '-' and text[7] == '-':
        return text[:10]
    return text[:10] if text else datetime.today().strftime('%Y-%m-%d')


def is_senior_qa_match(title: str, description: str = "") -> bool:
    combined = normalize_text(f"{title} {description}")
    if not combined:
        return False
    if any(ex in combined for ex in EXCLUDE_KEYWORDS):
        return False
    has_seniority = any(s in combined for s in SENIORITY_KEYWORDS)
    has_tech = any(t in combined for t in TECH_KEYWORDS)
    has_qa_focus = "qa" in combined or "quality assurance" in combined or "automation" in combined or "sdet" in combined
    return has_seniority and has_tech and has_qa_focus


def fetch_remotive_jobs():
    url = "https://remotive.com/api/remote-jobs?category=software-dev"
    jobs = []
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json().get("jobs", [])
            for job in data:
                title = (job.get("title") or "").strip()
                description = job.get("description") or job.get("job_description") or ""
                if is_senior_qa_match(title, description):
                    jobs.append({
                        "Source": "Remotive API",
                        "Company": job.get("company_name") or "N/A",
                        "Title": title,
                        "Location": job.get("candidate_required_location") or "Remote",
                        "Posted Date": format_posted_date(job.get("publication_date")),
                        "URL": job.get("url") or "",
                        "Description": description
                    })
    except Exception as e:
        print(f"Error fetching Remotive API: {e}")
    return jobs


def fetch_remoteok_jobs():
    jobs = []
    try:
        response = requests.get("https://remoteok.com/api", timeout=15)
        if response.status_code == 200:
            data = response.json()
            for job in data:
                title = (job.get("position") or job.get("title") or "").strip()
                description = job.get("description") or job.get("content") or ""
                if is_senior_qa_match(title, description):
                    company = job.get("company") or "N/A"
                    location = job.get("location") or "Remote"
                    url = job.get("url")
                    if url and not url.startswith("http"):
                        url = f"https://remoteok.com{url}"
                    jobs.append({
                        "Source": "RemoteOK",
                        "Company": company,
                        "Title": title,
                        "Location": location,
                        "Posted Date": format_posted_date(job.get("published_at")),
                        "URL": url or "https://remoteok.com",
                        "Description": description
                    })
    except Exception as e:
        print(f"Error fetching RemoteOK: {e}")
    return jobs


def fetch_jobicy_jobs():
    jobs = []
    try:
        response = requests.get("https://jobicy.com/api/v2/remote-jobs", timeout=15)
        if response.status_code == 200:
            data = response.json().get("jobs", [])
            for job in data:
                title = (job.get("jobTitle") or job.get("title") or "").strip()
                description = job.get("description") or job.get("jobExcerpt") or ""
                if is_senior_qa_match(title, description):
                    jobs.append({
                        "Source": "Jobicy",
                        "Company": job.get("companyName") or job.get("company") or "N/A",
                        "Title": title,
                        "Location": job.get("jobGeo") or "Remote",
                        "Posted Date": format_posted_date(job.get("date")),
                        "URL": job.get("url") or "",
                        "Description": description
                    })
    except Exception as e:
        print(f"Error fetching Jobicy: {e}")
    return jobs


def fetch_arbeitnow_jobs():
    jobs = []
    try:
        response = requests.get("https://www.arbeitnow.com/api/job-board-api", timeout=15)
        if response.status_code == 200:
            data = response.json().get("data", [])
            for job in data:
                title = (job.get("title") or "").strip()
                description = job.get("description") or ""
                if is_senior_qa_match(title, description):
                    jobs.append({
                        "Source": "Arbeitnow",
                        "Company": job.get("company_name") or "N/A",
                        "Title": title,
                        "Location": job.get("location") or "Remote",
                        "Posted Date": format_posted_date(job.get("created_at")),
                        "URL": job.get("url") or "",
                        "Description": description
                    })
    except Exception as e:
        print(f"Error fetching Arbeitnow: {e}")
    return jobs


async def scrape_weworkremotely():
    jobs = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("https://weworkremotely.com/categories/remote-full-stack-programming-jobs", wait_until="domcontentloaded")
            postings = await page.locator("section.jobs article li:not(.view-all)").all()
            for post in postings[:40]:
                title_elem = post.locator("span.title")
                company_elem = post.locator("span.company")
                link_elem = post.locator("a").nth(0)
                if await title_elem.count() > 0 and await link_elem.count() > 0:
                    title = (await title_elem.text_content()) or ""
                    company = (await company_elem.text_content()) if await company_elem.count() > 0 else "N/A"
                    href = await link_elem.get_attribute("href")
                    content = normalize_text(await post.text_content())
                    if is_senior_qa_match(title, content):
                        jobs.append({
                            "Source": "WeWorkRemotely",
                            "Company": company.strip(),
                            "Title": title.strip(),
                            "Location": "Remote (US/Global)",
                            "Posted Date": datetime.today().strftime('%Y-%m-%d'),
                            "URL": f"https://weworkremotely.com{href}" if href and not href.startswith("http") else (href or ""),
                            "Description": content
                        })
        except Exception as e:
            print(f"Error scraping WeWorkRemotely: {e}")
        finally:
            await browser.close()
    return jobs


def job_relevance_score(job_title: str, description: str = "") -> int:
    combined = normalize_text(f"{job_title} {description}")
    score = 0
    for term in ["senior", "lead", "principal", "staff", "architect", "sdet"]:
        if term in combined:
            score += 6
    for term in ["qa", "quality assurance", "automation", "playwright", "selenium", "rest assured", "api", "test"]:
        if term in combined:
            score += 4
    if "remote" in combined:
        score += 2
    return score


def deduplicate_jobs(jobs):
    seen = set()
    unique_jobs = []
    for job in jobs:
        key = (job.get("Title", "").strip().lower(), job.get("Company", "").strip().lower(), job.get("URL", "").strip())
        if key in seen:
            continue
        seen.add(key)
        unique_jobs.append(job)
    return unique_jobs


def shortlist_jobs(jobs, max_jobs=10):
    scored = []
    for job in jobs:
        score = job_relevance_score(job.get("Title", ""), job.get("Description", ""))
        scored.append({**job, "Score": score})
    scored.sort(key=lambda item: (item["Score"], item["Posted Date"]), reverse=True)
    return scored[:max_jobs]


def send_email_alert(jobs):
    default_email = "aishwaryak3105@gmail.com"
    sender_email = os.environ.get("SENDER_EMAIL", default_email)
    sender_password = os.environ.get("SENDER_PASSWORD")
    receiver_email = os.environ.get("RECEIVER_EMAIL", default_email)

    if not sender_password:
        print("⚠️ Gmail app password missing. Set SENDER_PASSWORD to send email alerts.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 Shortlisted Senior Remote QA Jobs - {datetime.today().strftime('%Y-%m-%d')}"
    msg["From"] = sender_email
    msg["To"] = receiver_email

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2 style="color: #2c3e50;">Shortlisted Senior Remote QA / SDET Roles</h2>
        <p>Best-fit roles for you ({len(jobs)} total):</p>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
          <tr style="background-color: #f2f2f2;">
            <th>Title</th>
            <th>Company</th>
            <th>Source</th>
            <th>Apply</th>
          </tr>
    """
    for job in jobs:
        html_content += f"""
          <tr>
            <td><b>{job['Title']}</b></td>
            <td>{job['Company']}</td>
            <td>{job['Source']}</td>
            <td><a href="{job['URL']}" style="background-color: #27ae60; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px;">Apply</a></td>
          </tr>
        """
    html_content += """
        </table>
      </body>
    </html>
    """

    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("📧 Shortlist email sent successfully!")
    except Exception as e:
        print(f"❌ Email delivery failed: {e}")


async def main():
    print("🔍 Searching all available public sources for Senior Remote QA / SDET roles...")
    remotive_results = fetch_remotive_jobs()
    remoteok_results = fetch_remoteok_jobs()
    jobicy_results = fetch_jobicy_jobs()
    arbeitnow_results = fetch_arbeitnow_jobs()
    wwr_results = await scrape_weworkremotely()

    all_jobs = deduplicate_jobs(remotive_results + remoteok_results + jobicy_results + arbeitnow_results + wwr_results)

    output_filename = "latest_remote_qa_jobs.csv"
    fieldnames = ["Source", "Company", "Title", "Location", "Posted Date", "URL", "Description"]
    with open(output_filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_jobs)

    print(f"✅ Extracted {len(all_jobs)} unique jobs to CSV.")

    shortlisted = shortlist_jobs(all_jobs)
    if shortlisted:
        print("📌 Top shortlisted opportunities:")
        for job in shortlisted:
            print(f"- {job['Title']} @ {job['Company']} [{job['Source']}]")
        send_email_alert(shortlisted)
    else:
        print("No matching jobs found today. Skipping email.")


if __name__ == "__main__":
    asyncio.run(main())