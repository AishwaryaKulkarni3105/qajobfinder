import asyncio
import csv
from datetime import datetime
import requests
from playwright.async_api import async_playwright

# Filtering rules for 7+ Yrs Senior QA / SDET roles
SENIORITY_KEYWORDS = ["senior", "sr", "lead", "sdet", "principal", "staff", "architect"]
TECH_KEYWORDS = ["qa", "quality assurance", "automation", "playwright", "selenium", "rest assured", "api", "test"]
EXCLUDE_KEYWORDS = ["junior", "jr", "intern", "entry", "trainee", "manual qa", "vp", "director"]

def is_senior_qa_match(title: str) -> bool:
    title_lower = title.lower()
    
    # Instant rejection for non-senior or purely manual roles
    if any(ex in title_lower for ex in EXCLUDE_KEYWORDS):
        return False
        
    has_seniority = any(s in title_lower for s in SENIORITY_KEYWORDS)
    has_tech = any(t in title_lower for t in TECH_KEYWORDS)
    
    return has_seniority and has_tech

def fetch_remotive_jobs():
    """Fetch remote engineering jobs from Remotive API"""
    url = "https://remotive.com/api/remote-jobs?category=software-dev"
    jobs = []
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json().get("jobs", [])
            for job in data:
                title = job.get("title", "")
                if is_senior_qa_match(title):
                    jobs.append({
                        "Source": "Remotive API",
                        "Company": job.get("company_name"),
                        "Title": title,
                        "Location": job.get("candidate_required_location", "Remote"),
                        "Posted Date": job.get("publication_date", "")[:10],
                        "URL": job.get("url")
                    })
    except Exception as e:
        print(f"Error fetching Remotive API: {e}")
    return jobs

async def scrape_weworkremotely():
    """Scrape fresh QA / Automation roles from We Work Remotely"""
    jobs = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto("https://weworkremotely.com/categories/remote-full-stack-programming-jobs", wait_until="domcontentloaded")
            postings = await page.locator("section.jobs article li:not(.view-all)").all()
            
            for post in postings[:25]:
                title_elem = post.locator("span.title")
                company_elem = post.locator("span.company")
                link_elem = post.locator("a").nth(0)
                
                if await title_elem.count() > 0 and await link_elem.count() > 0:
                    title = await title_elem.text_content()
                    company = await company_elem.text_content() if await company_elem.count() > 0 else "N/A"
                    href = await link_elem.get_attribute("href")
                    
                    if is_senior_qa_match(title):
                        jobs.append({
                            "Source": "WeWorkRemotely",
                            "Company": company.strip(),
                            "Title": title.strip(),
                            "Location": "Remote (US/Global)",
                            "Posted Date": datetime.today().strftime('%Y-%m-%d'),
                            "URL": f"https://weworkremotely.com{href}"
                        })
        except Exception as e:
            print(f"Error scraping WeWorkRemotely: {e}")
        finally:
            await browser.close()
            
    return jobs

async def main():
    print("🔍 Fetching senior-level remote QA / SDET postings...")
    
    remotive_results = fetch_remotive_jobs()
    wwr_results = await scrape_weworkremotely()
    
    all_jobs = remotive_results + wwr_results
    
    # Always save output to a clean, updated CSV file
    output_filename = "latest_remote_qa_jobs.csv"
    fieldnames = ["Source", "Company", "Title", "Location", "Posted Date", "URL"]
    
    with open(output_filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_jobs)
        
    print(f"✅ Extracted {len(all_jobs)} senior QA/SDET positions to '{output_filename}'.")

if __name__ == "__main__":
    asyncio.run(main())