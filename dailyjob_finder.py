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

QA_ROLE_PATTERN = re.compile(
    r"\b(?:sdet|qa|quality assurance|software tester|software test(?:ing)? engineer|"
    r"test automation|automation test(?:ing)?|automation qa|qa automation)\b",
    re.IGNORECASE,
)
SENIOR_TITLE_PATTERN = re.compile(r"\b(?:senior|sr\.?|lead|principal|staff|sdet)\b", re.IGNORECASE)
EXCLUDED_TITLE_PATTERN = re.compile(r"\b(?:junior|jr\.?|intern|entry[- ]level|trainee|vp|director)\b", re.IGNORECASE)
EXPERIENCE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:\+|plus)?\s*(?:(?:-|to)\s*\d+(?:\.\d+)?\s*)?(?:years?|yrs?)\b",
    re.IGNORECASE,
)
US_COUNTRY_PATTERN = re.compile(r"\b(?:united states(?: of america)?|u\.s\.a?\.?|usa)\b", re.IGNORECASE)
US_REMOTE_PATTERN = re.compile(
    r"\b(?:remote|based|residents?|candidates?|authorized to work|work authorization)"
    r"[^.\n]{0,40}\b(?:u\.s\.?|us)\b|\b(?:u\.s\.?|us)[- ](?:only|based|remote|residents?)\b",
    re.IGNORECASE,
)
US_ELIGIBILITY_PATTERN = re.compile(
    r"\b(?:located|based|reside|residing|residents?|candidates?|authorized to work|"
    r"eligible to work|must be located|work from)\b[^.\n]{0,60}\b"
    r"(?:united states(?: of america)?|u\.s\.a?\.?|usa)\b|\b"
    r"(?:united states(?: of america)?|u\.s\.a?\.?|usa)\b[^.\n]{0,60}\b"
    r"(?:residents?|candidates?|only|remote|based|located)\b",
    re.IGNORECASE,
)
PEORIA_AREA_CITIES = (
    "peoria", "east peoria", "peoria heights", "morton", "washington", "pekin",
    "bartonville", "dunlap", "chillicothe", "canton", "eureka", "elmwood",
    "bloomington", "normal",
)


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
    clean_title = normalize_text(title)
    clean_description = normalize_text(description)
    if not clean_title or EXCLUDED_TITLE_PATTERN.search(clean_title):
        return False
    if not QA_ROLE_PATTERN.search(clean_title):
        return False
    required_years = [float(match.group(1)) for match in EXPERIENCE_PATTERN.finditer(clean_description)]
    if required_years:
        return 5 <= max(required_years) <= 9
    return bool(SENIOR_TITLE_PATTERN.search(clean_title))


def is_us_remote_or_peoria_area(job):
    location = normalize_text(job.get("Location", ""))
    postal_code_match = re.search(r"\b616\d{2}\b", location)
    city_match = any(re.search(rf"\b{re.escape(city)}\b", location) for city in PEORIA_AREA_CITIES)
    illinois_match = bool(re.search(r"\b(?:il|illinois)\b", location))
    if postal_code_match or (city_match and (illinois_match or location.strip() in PEORIA_AREA_CITIES)):
        return True

    return is_us_remote_job(job)


def is_us_remote_job(job):
    location = normalize_text(job.get("Location", ""))
    description = normalize_text(job.get("Description", ""))
    source = normalize_text(job.get("Source", ""))
    remote_source = source in {"remotive api", "remoteok", "jobicy", "weworkremotely"}
    us_location = bool(
        US_COUNTRY_PATTERN.search(location)
        or US_REMOTE_PATTERN.search(location)
        or location.strip() in {"us", "u.s.", "u.s.a.", "usa", "united states"}
    )
    us_eligibility = bool(US_ELIGIBILITY_PATTERN.search(description) or US_REMOTE_PATTERN.search(description))
    return remote_source and (us_location or us_eligibility)


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
                            "Location": "Remote (eligibility unverified)",
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
    scored.sort(
        key=lambda item: (is_us_remote_job(item), item["Score"], item["Posted Date"]),
        reverse=True,
    )
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

    collected_jobs = remotive_results + remoteok_results + jobicy_results + arbeitnow_results + wwr_results
    eligible_jobs = [job for job in collected_jobs if is_us_remote_or_peoria_area(job)]
    all_jobs = deduplicate_jobs(eligible_jobs)
    remote_count = sum(is_us_remote_job(job) for job in all_jobs)
    peoria_count = len(all_jobs) - remote_count

    output_filename = "latest_remote_qa_jobs.csv"
    fieldnames = ["Source", "Company", "Title", "Location", "Posted Date", "URL", "Description"]
    with open(output_filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_jobs)

    print(f"✅ Extracted {len(all_jobs)} eligible jobs to CSV ({remote_count} U.S. remote, {peoria_count} Peoria-area).")

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