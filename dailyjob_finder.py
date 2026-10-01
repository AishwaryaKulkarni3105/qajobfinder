import asyncio
import csv
from datetime import datetime
import html
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from playwright.async_api import async_playwright

# Target: ~7.8 years QA Automation / SDET experience.
QA_KEYWORDS = (
    "qa", "quality assurance", "sdet", "software tester", "software test",
    "software testing", "test engineer", "testing engineer", "test automation",
    "automation test", "automation testing", "automation qa", "qa automation",
    "quality engineer",
)
SENIOR_TITLE_PATTERN = re.compile(r"\b(?:senior|sr\.?|lead|principal|staff|sdet)\b", re.I)
EXCLUDED_TITLE_PATTERN = re.compile(
    r"\b(?:junior|jr\.?|intern|internship|entry[- ]level|trainee|graduate|vp|vice president|director|head of)\b", re.I
)
EXPERIENCE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:\+|plus)?\s*(?:(?:-|to)\s*(\d+(?:\.\d+)?)\s*)?(?:years?|yrs?)\b", re.I
)
US_COUNTRY_PATTERN = re.compile(r"\b(?:united states(?: of america)?|u\.s\.a?\.?|usa)\b", re.I)
US_REMOTE_PATTERN = re.compile(
    r"\b(?:remote|based|residents?|candidates?|authorized to work|work authorization)[^.\n]{0,60}\b(?:u\.s\.?|us)\b|\b(?:u\.s\.?|us)[- ](?:only|based|remote|residents?)\b", re.I
)
US_ELIGIBILITY_PATTERN = re.compile(
    r"\b(?:located|based|reside|residing|residents?|candidates?|authorized to work|eligible to work|must be located|work from)\b[^.\n]{0,80}\b(?:united states(?: of america)?|u\.s\.a?\.?|usa)\b|\b(?:united states(?: of america)?|u\.s\.a?\.?|usa)\b[^.\n]{0,80}\b(?:residents?|candidates?|only|remote|based|located)\b", re.I
)
PEORIA_AREA_CITIES = (
    "peoria", "east peoria", "peoria heights", "morton", "washington", "pekin",
    "bartonville", "dunlap", "chillicothe", "canton", "eureka", "elmwood",
    "bloomington", "normal",
)
NON_US_LOCATION_PATTERN = re.compile(
    r"\b(?:india|indian|united kingdom|uk|canada|australia|europe|european union|germany|france|ireland|singapore)\b", re.I
)


def normalize_text(value):
    if not value:
        return ""
    clean = re.sub(r"<[^>]+>", " ", str(value))
    clean = html.unescape(clean)
    return re.sub(r"\s+", " ", clean).strip().lower()


def format_posted_date(value):
    if not value:
        return datetime.today().strftime("%Y-%m-%d")
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(int(value)).strftime("%Y-%m-%d")
        except Exception:
            return datetime.today().strftime("%Y-%m-%d")
    text = str(value)
    return text[:10] if text else datetime.today().strftime("%Y-%m-%d")


def extract_experience_requirements(description):
    result = []
    for match in EXPERIENCE_PATTERN.finditer(description):
        minimum = float(match.group(1))
        maximum = float(match.group(2)) if match.group(2) else minimum
        result.append((minimum, maximum))
    return result


def is_senior_qa_match(title, description=""):
    title = normalize_text(title)
    description = normalize_text(description)
    if not title or EXCLUDED_TITLE_PATTERN.search(title):
        return False

    combined = f"{title} {description}"
    if not any(keyword in combined for keyword in QA_KEYWORDS):
        return False

    requirements = extract_experience_requirements(description)
    if requirements:
        # 7.8 years is the target. Accept postings in roughly the 6-10 year band.
        for minimum, maximum in requirements:
            if minimum <= 7.8 <= max(maximum, minimum):
                return True
            if minimum <= 10 and maximum >= 6:
                return True
        return False

    # If years are not stated, require a senior-level title.
    return bool(SENIOR_TITLE_PATTERN.search(title))


def is_us_remote_or_peoria_area(job):
    location = normalize_text(job.get("Location", ""))
    if re.search(r"\b616\d{2}\b", location):
        return True
    if any(re.search(rf"\b{re.escape(city)}\b", location) for city in PEORIA_AREA_CITIES):
        if re.search(r"\b(?:il|illinois)\b", location) or location.strip() in PEORIA_AREA_CITIES:
            return True
    return is_us_remote_job(job)


def is_us_remote_job(job):
    location = normalize_text(job.get("Location", ""))
    description = normalize_text(job.get("Description", ""))
    source = normalize_text(job.get("Source", ""))
    if source not in {"remotive api", "remoteok", "jobicy", "weworkremotely"}:
        return False
    if NON_US_LOCATION_PATTERN.search(location):
        return False
    if US_COUNTRY_PATTERN.search(location) or US_REMOTE_PATTERN.search(location):
        return True
    if location.strip() in {"us", "u.s.", "u.s.a.", "usa", "united states", "remote (us)"}:
        return True
    if US_ELIGIBILITY_PATTERN.search(description):
        return True
    # Many remote boards simply say Remote/Anywhere. Keep those unless the location
    # explicitly restricts the role to a non-US country/region.
    if location in {"", "remote", "anywhere", "remote - anywhere", "remote - us", "remote (us)", "remote (eligibility unverified)", "worldwide"}:
        return True
    return False


def fetch_remotive_jobs():
    jobs = []
    try:
        response = requests.get("https://remotive.com/api/remote-jobs?category=software-dev", timeout=15)
        if response.status_code == 200:
            for job in response.json().get("jobs", []):
                title = (job.get("title") or "").strip()
                description = job.get("description") or job.get("job_description") or ""
                if is_senior_qa_match(title, description):
                    jobs.append({
                        "Source": "Remotive API", "Company": job.get("company_name") or "N/A",
                        "Title": title, "Location": job.get("candidate_required_location") or "Remote",
                        "Posted Date": format_posted_date(job.get("publication_date")),
                        "URL": job.get("url") or "", "Description": description,
                    })
    except Exception as e:
        print(f"Error fetching Remotive API: {e}")
    print(f"Remotive: {len(jobs)} relevant QA jobs")
    return jobs


def fetch_remoteok_jobs():
    jobs = []
    try:
        response = requests.get("https://remoteok.com/api", timeout=15)
        if response.status_code == 200:
            for job in response.json():
                title = (job.get("position") or job.get("title") or "").strip()
                description = job.get("description") or job.get("content") or ""
                if is_senior_qa_match(title, description):
                    url = job.get("url")
                    if url and not url.startswith("http"):
                        url = f"https://remoteok.com{url}"
                    jobs.append({
                        "Source": "RemoteOK", "Company": job.get("company") or "N/A", "Title": title,
                        "Location": job.get("location") or "Remote",
                        "Posted Date": format_posted_date(job.get("published_at")),
                        "URL": url or "https://remoteok.com", "Description": description,
                    })
    except Exception as e:
        print(f"Error fetching RemoteOK: {e}")
    print(f"RemoteOK: {len(jobs)} relevant QA jobs")
    return jobs


def fetch_jobicy_jobs():
    jobs = []
    try:
        response = requests.get("https://jobicy.com/api/v2/remote-jobs", timeout=15)
        if response.status_code == 200:
            for job in response.json().get("jobs", []):
                title = (job.get("jobTitle") or job.get("title") or "").strip()
                description = job.get("description") or job.get("jobExcerpt") or ""
                if is_senior_qa_match(title, description):
                    jobs.append({
                        "Source": "Jobicy", "Company": job.get("companyName") or job.get("company") or "N/A",
                        "Title": title, "Location": job.get("jobGeo") or "Remote",
                        "Posted Date": format_posted_date(job.get("date")), "URL": job.get("url") or "",
                        "Description": description,
                    })
    except Exception as e:
        print(f"Error fetching Jobicy: {e}")
    print(f"Jobicy: {len(jobs)} relevant QA jobs")
    return jobs


def fetch_arbeitnow_jobs():
    jobs = []
    try:
        response = requests.get("https://www.arbeitnow.com/api/job-board-api", timeout=15)
        if response.status_code == 200:
            for job in response.json().get("data", []):
                title = (job.get("title") or "").strip()
                description = job.get("description") or ""
                if is_senior_qa_match(title, description):
                    jobs.append({
                        "Source": "Arbeitnow", "Company": job.get("company_name") or "N/A", "Title": title,
                        "Location": job.get("location") or "Remote",
                        "Posted Date": format_posted_date(job.get("created_at")), "URL": job.get("url") or "",
                        "Description": description,
                    })
    except Exception as e:
        print(f"Error fetching Arbeitnow: {e}")
    print(f"Arbeitnow: {len(jobs)} relevant QA jobs")
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
                            "Source": "WeWorkRemotely", "Company": company.strip(), "Title": title.strip(),
                            "Location": "Remote (eligibility unverified)",
                            "Posted Date": datetime.today().strftime("%Y-%m-%d"),
                            "URL": f"https://weworkremotely.com{href}" if href and not href.startswith("http") else (href or ""),
                            "Description": content,
                        })
        except Exception as e:
            print(f"Error scraping WeWorkRemotely: {e}")
        finally:
            await browser.close()
    print(f"WeWorkRemotely: {len(jobs)} relevant QA jobs")
    return jobs


def job_relevance_score(job_title, description=""):
    title = normalize_text(job_title)
    description = normalize_text(description)
    combined = f"{title} {description}"
    score = 0

    if re.search(r"\b(?:senior|sr\.?)\b", title):
        score += 12
    if re.search(r"\b(?:lead|principal|staff)\b", title):
        score += 10
    if "sdet" in title:
        score += 12

    role_weights = {
        "qa": 8, "quality assurance": 10, "sdet": 12, "test automation": 12,
        "automation test": 10, "automation testing": 10, "qa automation": 12,
        "automation qa": 12, "software test engineer": 10, "test engineer": 8,
        "quality engineer": 7,
    }
    for term, weight in role_weights.items():
        if term in title:
            score += weight

    skill_weights = {
        "selenium": 8, "playwright": 8, "java": 7, "rest assured": 8,
        "api automation": 8, "rest api": 6, "api testing": 6, "jmeter": 6,
        "performance testing": 5, "testng": 4, "maven": 3, "jenkins": 3,
        "gitlab": 3, "ci/cd": 3, "docker": 3, "kubernetes": 3,
    }
    for skill, weight in skill_weights.items():
        if skill in combined:
            score += weight

    if "remote" in combined:
        score += 3
    if US_COUNTRY_PATTERN.search(combined):
        score += 3

    for minimum, maximum in extract_experience_requirements(description):
        if minimum <= 7.8 <= max(maximum, minimum):
            score += 8
            break

    return score


def deduplicate_jobs(jobs):
    seen = set()
    unique_jobs = []
    for job in jobs:
        key = (job.get("Title", "").strip().lower(), job.get("Company", "").strip().lower(), job.get("URL", "").strip())
        if key not in seen:
            seen.add(key)
            unique_jobs.append(job)
    return unique_jobs


def shortlist_jobs(jobs, max_jobs=10):
    scored = []
    for job in jobs:
        scored.append({**job, "Score": job_relevance_score(job.get("Title", ""), job.get("Description", ""))})
    scored.sort(key=lambda item: (item["Score"], item.get("Posted Date", "")), reverse=True)
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
    today = datetime.today().strftime("%Y-%m-%d")
    msg["Subject"] = f"🎯 Senior QA Jobs - {len(jobs)} Matches - {today}" if jobs else f"📭 QA Job Finder - No Matches Today - {today}"
    msg["From"] = sender_email
    msg["To"] = receiver_email

    if jobs:
        rows = ""
        for i, job in enumerate(jobs, 1):
            title = html.escape(job.get("Title", "N/A"))
            company = html.escape(job.get("Company", "N/A"))
            location = html.escape(job.get("Location", "Remote"))
            source = html.escape(job.get("Source", "N/A"))
            score = job.get("Score", 0)
            url = html.escape(job.get("URL", ""), quote=True)
            rows += f'''<tr><td>{i}</td><td><b>{title}</b></td><td>{company}</td><td>{location}</td><td>{source}</td><td>{score}</td><td><a href="{url}">Apply</a></td></tr>'''

        html_content = f'''
        <html><body style="font-family:Arial,sans-serif;line-height:1.5;">
        <h2>🎯 Senior QA / SDET Job Matches</h2>
        <p>Best matches for a <b>~7.8 year QA Automation / SDET profile</b>.</p>
        <p><b>Target:</b> Senior QA, QA Automation, SDET, Test Automation, Software Test Engineering</p>
        <p><b>Skills prioritized:</b> Selenium, Playwright, Java, REST Assured, API Automation, JMeter, CI/CD</p>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;">
        <tr><th>#</th><th>Title</th><th>Company</th><th>Location</th><th>Source</th><th>Score</th><th>Apply</th></tr>
        {rows}</table>
        <p style="color:#666;">Filtered for QA/testing relevance, approximately 6-10 years experience, and US-remote or Peoria-area eligibility.</p>
        </body></html>'''
    else:
        html_content = '''<html><body style="font-family:Arial,sans-serif;line-height:1.6;">
        <h2>📭 No Matching QA Jobs Today</h2>
        <p>The daily job finder ran successfully, but no jobs met the current filters.</p>
        <ul><li>Senior QA / QA Automation / SDET / Test Automation</li><li>Approximately 6-10 years experience</li><li>US remote or Peoria-area</li><li>Relevant automation/testing skills</li></ul>
        <p>This email confirms that the daily automation ran successfully.</p>
        </body></html>'''

    msg.attach(MIMEText(html_content, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("📧 Email sent successfully!")
    except Exception as e:
        print(f"❌ Email delivery failed: {e}")


async def main():
    print("🔍 Searching for relevant Senior QA / SDET / Test Automation jobs...")
    results = []
    results.extend(fetch_remotive_jobs())
    results.extend(fetch_remoteok_jobs())
    results.extend(fetch_jobicy_jobs())
    results.extend(fetch_arbeitnow_jobs())
    results.extend(await scrape_weworkremotely())

    print(f"📥 Collected {len(results)} QA/testing candidates before location filtering.")
    eligible_jobs = [job for job in results if is_us_remote_or_peoria_area(job)]
    all_jobs = deduplicate_jobs(eligible_jobs)

    remote_count = sum(is_us_remote_job(job) for job in all_jobs)
    peoria_count = len(all_jobs) - remote_count

    with open("latest_remote_qa_jobs.csv", "w", newline="", encoding="utf-8") as file:
        fieldnames = ["Source", "Company", "Title", "Location", "Posted Date", "URL", "Description"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_jobs)

    print(f"✅ Extracted {len(all_jobs)} eligible jobs to CSV ({remote_count} U.S. remote, {peoria_count} Peoria-area).")

    shortlisted = shortlist_jobs(all_jobs, max_jobs=10)
    if shortlisted:
        print("📌 Top shortlisted opportunities:")
        for job in shortlisted:
            print(f"- {job['Title']} @ {job['Company']} [{job['Source']}] Score={job['Score']}")
    else:
        print("📭 No matching jobs found today.")

    # Always send an email, including a "no matches" email, so a successful run is visible.
    send_email_alert(shortlisted)


if __name__ == "__main__":
    asyncio.run(main())
