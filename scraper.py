import argparse
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import quote_plus
import random
import time
import re

def parse_date_text(date_text):
    if not date_text:
        return None
    text = str(date_text).strip()
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except Exception:
            pass
    rel = re.match(r"(\d+)\s+(day|days|week|weeks|month|months|year|years)\s+ago", text, flags=re.I)
    if rel:
        n = int(rel.group(1))
        unit = rel.group(2).lower()
        if unit.startswith("day"): return (datetime.now() - timedelta(days=n)).date()
        if unit.startswith("week"): return (datetime.now() - timedelta(weeks=n)).date()
        if unit.startswith("month"): return (datetime.now() - timedelta(days=30*n)).date()
        if unit.startswith("year"): return (datetime.now() - timedelta(days=365*n)).date()
    if re.search(r"\blast\s+week\b", text, flags=re.I): return (datetime.now() - timedelta(weeks=1)).date()
    if re.search(r"\blast\s+month\b", text, flags=re.I): return (datetime.now() - timedelta(days=30)).date()
    if re.search(r"\blast\s+year\b", text, flags=re.I): return (datetime.now() - timedelta(days=365)).date()
    month_like = re.search(r"([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})", text)
    if month_like:
        try:
            return dateutil_parser.parse(month_like.group(1)).date()
        except Exception:
            pass
    try:
        dt = dateutil_parser.parse(text, fuzzy=True)
        return dt.date()
    except Exception:
        return None

def _safe_text(elem):
    return "" if elem is None else elem.get_text(" ", strip=True)

def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# ---------------- Selenium driver ----------------
def make_driver(headless=False, proxy=None, window_size=(1366,768)):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(f"--window-size={window_size[0]},{window_size[1]}")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "disable-infobars"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    if proxy:
        chrome_options.add_argument(f'--proxy-server={proxy}')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_window_size(window_size[0], window_size[1])
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.navigator.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            """
        })
    except Exception:
        pass
    return driver

def load_cookies_file(driver, cookies_path, base_url=None):
    if not cookies_path: return
    p = Path(cookies_path)
    if not p.exists(): raise FileNotFoundError("Cookies file not found: " + str(cookies_path))
    with open(p, "r", encoding="utf-8") as f: cookies = json.load(f)
    if base_url:
        driver.get(base_url)
        time.sleep(1)
    for c in cookies:
        cpop = {k:v for k,v in c.items() if k!='sameSite'}
        try:
            driver.add_cookie(cpop)
        except Exception:
            trimmed = {k:v for k,v in cpop.items() if k in ("name","value","domain","path","expiry","httpOnly","secure")}
            try: driver.add_cookie(trimmed)
            except Exception: pass

# ---------------- Trustpilot: JSON-first approach ----------------
def fetch_trustpilot(driver, company_url_path, start_date, end_date, use_json_first=False,debug=False):
  
    reviews = []
    base_url = f"https://www.trustpilot.com/review/www.{company_url_path}"

    if debug:
        print(f"[DEBUG] Navigating to {base_url}")

    driver.get(base_url)
    time.sleep(2.0)  # Allow page to load
    soup = BeautifulSoup(driver.page_source, "html.parser")
    # --- Try JSON API method (much faster) ---
    script_tag = soup.find("script", string=re.compile("businessUnitId"))
    if not script_tag:
        if debug:
            print("[DEBUG] Could not find businessUnitId on page.")
        return reviews

    match = re.search(r'"businessUnitId":"(.*?)"', script_tag.text)
    if not match:
        if debug:
            print("[DEBUG] Could not extract businessUnitId value.")
        return reviews

    business_unit_id = match.group(1)
    if debug:
        print(f"[DEBUG] Found businessUnitId: {business_unit_id}")

    # Trustpilot API URL
    api_url = f"https://www.trustpilot.com/api/reviews/business-unit/{business_unit_id}"
    page = 1
    per_page = 20

    while True:
        params = {
            "page": page,
            "perPage": per_page,
            "sortBy": "createdAt",
            "order": "desc"
        }
        resp = requests.get(api_url, params=params, headers={
            "User-Agent": "Mozilla/5.0"
        })

        if resp.status_code != 200:
            if debug:
                print(f"[DEBUG] API request failed with status {resp.status_code}")
            break

        data = resp.json()
        page_reviews = data.get("reviews", [])
        if not page_reviews:
            break

        for r in page_reviews:
            review_date = r.get("dates", {}).get("publishedDate", "")[:10]
            if start_date <= review_date <= end_date:
                reviews.append({
                    "author": r.get("consumer", {}).get("displayName", ""),
                    "rating": r.get("rating", {}).get("value", ""),
                    "date": review_date,
                    "content": r.get("text", "")
                })

        page += 1
        time.sleep(0.5)  # be nice to the server

    if debug:
        print(f"[DEBUG] Total reviews scraped: {len(reviews)}")

    return reviews
# ---------------- G2 ----------------
def fetch_g2(driver, company_slug, start_date, end_date, debug=False):
    url = f"https://www.g2.com/products/{company_slug}/reviews"
    driver.get(url)
    wait = WebDriverWait(driver, 18)
    try:
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    except TimeoutException:
        if debug:
            with open("g2_snapshot_initial.html","w",encoding="utf-8") as f: f.write(driver.page_source)
        return []
    time.sleep(1.2)
    page = 0
    reviews = []
    while page < 40:
        page += 1
        time.sleep(1.0 + (page % 2))
        soup = BeautifulSoup(driver.page_source, "html.parser")
        containers = []
        for sel in ["div[itemprop='review']", "div[data-test='review-card']", "article", "div.review-card", "div[class*='reviewCard']"]:
            found = soup.select(sel)
            if found:
                containers = found
                break
        if not containers:
            if debug:
                with open(f"g2_snapshot_page_{page}.html","w",encoding="utf-8") as f: f.write(driver.page_source)
            break
        matched = False
        for rc in containers:
            date_text = None
            dm = rc.find(attrs={"itemprop":"datePublished"})
            if dm and dm.get("content"): date_text = dm["content"]
            else:
                t = rc.find("time")
                if t and t.get("datetime"): date_text = t["datetime"].split("T")[0]
                else:
                    txt = rc.get_text(" ",strip=True)
                    mm = re.search(r"([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})", txt)
                    if mm: date_text = mm.group(1)
                    else:
                        mm2 = re.search(r"(\d{4}-\d{2}-\d{2})", txt)
                        if mm2: date_text = mm2.group(1)
            parsed = parse_date_text(date_text) if date_text else None
            if parsed is None: continue
            if parsed < start_date.date() or parsed > end_date.date(): continue
            matched = True
            title = _safe_text(rc.find(itemprop="name") or rc.find(["h3","h2","strong"])) or "No Title"
            desc = _safe_text(rc.find(itemprop="reviewBody") or rc.find("p") or rc.find("div", class_=lambda v: v and "body" in v)) or "No Description"
            reviewer = _safe_text(rc.find(itemprop="author") or rc.find(class_=lambda v: v and ("user" in v or "reviewer" in v))) or "Anonymous"
            rating = None
            rv = rc.find(attrs={"itemprop":"ratingValue"})
            if rv and rv.get("content"): rating = rv["content"]
            else:
                img = rc.find("img", alt=re.compile(r"\d out of \d")) if rc else None
                if img and img.get("alt"):
                    m = re.search(r"(\d(?:\.\d)?)", img["alt"])
                    if m: rating = m.group(1)
            reviews.append({"title": title,"description": desc,"date": parsed.strftime("%Y-%m-%d"),"reviewer_name": reviewer,"rating": rating or "No Rating","source":"g2"})
        if not matched: break
        try:
            next_btn = driver.find_element(By.CSS_SELECTOR, "button[data-test='load-more'], button.load-more, a[rel='next'], a.pagination-next")
            href = next_btn.get_attribute("href")
            if href:
                driver.get(href)
                continue
            else:
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(1.0)
                continue
        except Exception:
            prev = len(driver.page_source)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.2)
            new = len(driver.page_source)
            if new == prev:
                break
    return reviews

# ---------------- Capterra ----------------
def fetch_capterra(driver, company_name, start_date, end_date, debug=False):
    # Randomized query to slightly change search pattern (avoid bot detection)
    search_url = f"https://www.capterra.com/search/?query={quote_plus(company_name)}"
    driver.get(search_url)

    # Wait for search results to load
    WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    soup = BeautifulSoup(driver.page_source, "html.parser")
    product_link = None

    # Multiple selectors for product link
    for sel in ["a[href*='/p/']", "a.product-title", "h3 a"]:
        el = soup.select_one(sel)
        if el and "/p/" in el.get("href", ""):
            product_link = el.get("href")
            break

    if not product_link:
        if debug:
            with open("capterra_no_results.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
        return []
   
    if not product_link.startswith("http"):
        product_link = "https://www.capterra.com" + product_link

    if not product_link.endswith("reviews"):
        product_link += "reviews"

    driver.get(product_link)

    time.sleep(random.uniform(2, 4))

    reviews = []
    visited_pages = set()

    while True:
        current_url = driver.current_url
        if current_url in visited_pages:
            break
        visited_pages.add(current_url)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        cards = soup.select("div.review-card, li.review, article, div[class*='review']")

        if not cards:
            # Possibly blocked → break early
            if "Access Denied" in soup.get_text() or "captcha" in soup.get_text().lower():
                print("⚠ Blocked by Capterra. Try changing IP/User-Agent.")
            break

        for r in cards:
            # Extract date
            t = r.find("time")
            date_text = None
            if t and t.get("datetime"):
                date_text = t["datetime"].split("T")[0]
            else:
                txt = r.get_text(" ", strip=True)
                m = re.search(r"([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})", txt)
                if m:
                    date_text = m.group(1)

            parsed = parse_date_text(date_text) if date_text else None
            if not parsed:
                continue
            if parsed < start_date.date() or parsed > end_date.date():
                continue

            title = _safe_text(r.find(["h3", "h4"])) or "No Title"
            desc = _safe_text(r.find("p", class_=lambda v: v and "review-text" in v)) or _safe_text(r.find("p")) or "No Description"
            reviewer = _safe_text(r.find(class_=lambda v: v and ("reviewer" in v or "user" in v))) or "Anonymous"

            rating = None
            star = r.find(attrs={"aria-label": re.compile(r"\d out of \d")})
            if star and star.get("aria-label"):
                mm = re.search(r"(\d(?:\.\d)?)", star["aria-label"])
                if mm:
                    rating = mm.group(1)

            reviews.append({
                "title": title,
                "description": desc,
                "date": parsed.strftime("%Y-%m-%d"),
                "reviewer_name": reviewer,
                "rating": rating or "No Rating",
                "source": "capterra"
            })

        try:
            next_btn = driver.find_element(By.CSS_SELECTOR, "a.pagination-next, a.next")
            if next_btn and next_btn.get_attribute("href"):
                time.sleep(random.uniform(1, 2.5))  # Random pause before next request
                driver.get(next_btn.get_attribute("href"))
                continue
        except:
            pass

        break

    return reviews

# ---------------- main runner ----------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["g2","capterra","trustpilot"], help="Source")
    p.add_argument("--company", help="Company/product name (e.g., zoom)")
    p.add_argument("--start", help="Start YYYY-MM-DD")
    p.add_argument("--end", help="End YYYY-MM-DD")
    p.add_argument("--headless", action="store_true", help="Run headless")
    p.add_argument("--cookies-file", help="cookies.json exported from Selenium or browser")
    p.add_argument("--proxy", help="proxy like http://user:pass@host:port")
    p.add_argument("--debug", action="store_true", help="save snapshots")
    args = p.parse_args()

    if not args.source:
        args.source = input("Enter source (g2/capterra/trustpilot): ").strip().lower()
    if not args.company:
        args.company = input("Enter company (e.g., zoom): ").strip()
    if not args.start:
        args.start = input("Enter start date (YYYY-MM-DD): ").strip()
    if not args.end:
        args.end = input("Enter end date (YYYY-MM-DD): ").strip()
    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
        end_date = datetime.strptime(args.end, "%Y-%m-%d")
        if end_date < start_date:
            print("end must be >= start"); return
    except Exception:
        print("Date format YYYY-MM-DD required"); return

    driver = make_driver(headless=args.headless, proxy=args.proxy)
    try:
        if args.cookies_file:
            base_map = {"g2": "https://www.g2.com", "capterra":"https://www.capterra.com", "trustpilot":"https://www.trustpilot.com"}
            load_cookies_file(driver, args.cookies_file, base_url=base_map.get(args.source))
        reviews = []
        if args.source == "trustpilot":
            reviews = fetch_trustpilot(driver, args.company, start_date, end_date, use_json_first=True, debug=args.debug)
        elif args.source == "g2":
            slug = args.company.strip().replace(" ", "-").lower()
            reviews = fetch_g2(driver, slug, start_date, end_date, debug=args.debug)
        elif args.source == "capterra":
            reviews = fetch_capterra(driver, args.company, start_date, end_date, debug=args.debug)
        fname = f"{args.source}_reviews_{args.company.strip().replace(' ','_')}_{args.start}_to_{args.end}.json"
        save_json(fname, reviews)
        print(f"Saved {len(reviews)} reviews to {fname}")
        if args.debug and len(reviews)==0:
            print("0 reviews — debug snapshots saved where applicable. Try running without --headless and/or provide --cookies-file.")
    finally:
        try: driver.quit()
        except Exception: pass

if __name__ == "__main__":
    main()
