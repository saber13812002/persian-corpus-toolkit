"""
Khamenei.ir Speech Scraper - Standalone Python Script
Can run independently or be called by the extension backend.
Discovers and extracts all speeches from farsi.khamenei.ir/speech.
"""
import requests, re, sys, io, time, json, os, urllib3
urllib3.disable_warnings()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = "https://farsi.khamenei.ir"
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'backend', 'thesaurus.db')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "fa,en-US;q=0.9,en;q=0.8",
}

def extract_speech(speech_id):
    """Extract all data from a speech content page."""
    url = f"{BASE}/speech-content?id={speech_id}"
    try:
        r = requests.get(url, headers=headers, verify=False, timeout=30)
    except Exception as e:
        return {"error": str(e), "speech_id": speech_id}
    
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}", "speech_id": speech_id}
    
    text = r.text
    
    # Title
    title_match = re.search(r'<title>([^<]+)</title>', text)
    title = title_match.group(1).strip() if title_match else ""
    title = re.sub(r'\s*[-–|]\s*KHAMENEI\.IR.*$', '', title, flags=re.I).strip()
    title = re.sub(r'\s*[-–|]\s*پایگاه.*$', '', title).strip()
    
    def to_ascii_digits(s):
        table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        return (s or "").translate(table)

    # Date: prefer span.oliveDate (Jalali Persian digits)
    date = ""
    olive = re.search(
        r'<span[^>]*class="[^"]*oliveDate[^"]*"[^>]*>([^<]+)</span>',
        text, re.I,
    )
    if olive:
        m = re.search(r'(\d{4}/\d{2}/\d{2})', to_ascii_digits(olive.group(1)))
        if m:
            date = m.group(1)
    if not date:
        m = re.search(r'(\d{4}/\d{2}/\d{2})', to_ascii_digits(text))
        date = m.group(1) if m else ""
    year = date[:4] if date else ""

    # Main content
    content = ""
    content_div = re.search(r'<div[^>]*class="Content"[^>]*>(.*?)</div>', text, re.DOTALL)
    if content_div:
        content = re.sub(r'<[^>]+>', ' ', content_div.group(1))
        content = re.sub(r'\s+', ' ', content).strip()
    else:
        news_match = re.search(r'id="newsContentInnerSide"[^>]*>(.*?)</div>\s*</td>', text, re.DOTALL)
        if news_match:
            content = re.sub(r'<[^>]+>', ' ', news_match.group(1))
            content = re.sub(r'\s+', ' ', content).strip()

    # Clean date prefix (ASCII or Persian digits)
    if date and to_ascii_digits(content).startswith(date):
        content = content[len(date):].strip()
    
    # Audio
    audio_url = ""
    audio_match = re.search(r'(?:src|href)=["\']([^"\']*audio-content\?id=\d+[^"\']*)["\']', text)
    if audio_match:
        audio_url = f"{BASE}{audio_match.group(1)}" if audio_match.group(1).startswith('/') else audio_match.group(1)
    
    # Tags
    tags = list(set(re.findall(r'class="topmenu-tag"[^>]*title="([^"]+)"', text)))
    
    return {
        "speech_id": speech_id,
        "title": title,
        "date": date,
        "year": year,
        "content": content,
        "audio_url": audio_url,
        "tags": tags,
        "char_count": len(content),
    }


def discover_ids(year=None, max_pages=50):
    """Discover speech IDs by scanning list pages."""
    all_ids = set()
    
    for page in range(1, max_pages + 1):
        url = f"{BASE}/speech?page={page}"
        if year:
            url += f"&year={year}"
        
        try:
            r = requests.get(url, headers=headers, verify=False, timeout=30)
        except:
            print(f"  Failed to load page {page}")
            break
        
        ids = re.findall(r'speech-content\?id=(\d+)', r.text)
        ids = set(ids)
        new = ids - all_ids
        all_ids.update(ids)
        
        print(f"  Page {page}: {len(ids)} IDs ({len(new)} new, total {len(all_ids)})")
        
        if len(new) == 0:
            print(f"  No new IDs, stopping")
            break
        
        time.sleep(1 + 0.5 * (page % 5))  # Rate limiting
    
    return sorted(all_ids, key=int, reverse=True)


def submit_to_backend(speech, backend_url="http://127.0.0.1:5055"):
    """Submit extracted speech to the Flask backend."""
    try:
        r = requests.post(f"{backend_url}/api/khamenei/submit", json=speech, timeout=30)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def scrape_all(years=None, start_from=None, max_per_run=100, delay=2, backend="http://127.0.0.1:5055"):
    """
    Main scraping orchestrator.
    - Discover IDs from list pages
    - Scrape each speech
    - Submit to backend (which handles dedup via hash)
    """
    if years:
        all_ids = []
        for year in years:
            print(f"\n📅 Scanning year {year}...")
            ids = discover_ids(year=year)
            all_ids.extend(ids)
            all_ids = list(set(all_ids))
    else:
        print(f"\n🔍 Discovering all speech IDs...")
        all_ids = discover_ids()
    
    print(f"\n🎯 Total unique speech IDs: {len(all_ids)}")
    
    # Filter already-done from backend (true resume)
    done_ids = set()
    try:
        r = requests.get(f"{backend}/api/khamenei/stats")
        done_count = r.json().get('total', 0)
        print(f"  Already crawled: {done_count}")
        # Prefer pending queue if available
        pr = requests.get(f"{backend}/api/khamenei/pending?limit=5000", timeout=30)
        pending = pr.json().get('ids') or []
        if pending:
            all_ids = [str(x) for x in pending]
            print(f"  Resuming {len(all_ids)} pending from queue")
    except Exception:
        done_count = 0

    # Sort and limit
    all_ids = [str(i) for i in all_ids]
    all_ids.sort(key=int, reverse=True)
    if start_from:
        all_ids = [i for i in all_ids if int(i) <= int(start_from)]

    to_crawl = all_ids[:max_per_run]
    print(f"\n🚀 Scraping {len(to_crawl)} speeches (rate limit: {delay}s between requests)...")
    
    results = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
    
    for i, sid in enumerate(to_crawl):
        print(f"  [{i+1}/{len(to_crawl)}] Speech #{sid}...", end=" ", flush=True)
        
        speech = extract_speech(sid)
        if "error" in speech:
            print(f"❌ {speech['error']}")
            results["errors"] += 1
            time.sleep(delay * 2)  # Longer wait on error
            continue
        
        result = submit_to_backend(speech, backend)
        status = result.get("status", "error")
        print(f"{status} - {speech['title'][:60]} ({speech['char_count']} chars)")
        
        if status in results:
            results[status] += 1
        
        time.sleep(delay)
    
    print(f"\n✅ Done! Results: {json.dumps(results)}")
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Khamenei.ir Speech Scraper")
    parser.add_argument("--discover", action="store_true", help="Only discover IDs, don't scrape")
    parser.add_argument("--scrape", type=str, help="Scrape specific speech IDs (comma-separated)")
    parser.add_argument("--year", type=int, help="Filter by year (e.g. 1404)")
    parser.add_argument("--max", type=int, default=100, help="Max speeches to scrape (default: 100)")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests in seconds")
    parser.add_argument("--backend", default="http://127.0.0.1:5055", help="Backend URL")
    args = parser.parse_args()
    
    if args.discover:
        ids = discover_ids(year=args.year)
        print(f"\nFound {len(ids)} IDs")
        print(f"First 10: {ids[:10]}")
        print(f"Last 10: {ids[-10:]}")
    elif args.scrape:
        ids = args.scrape.split(",")
        for sid in ids:
            speech = extract_speech(sid.strip())
            print(json.dumps(speech, ensure_ascii=False, indent=2))
            result = submit_to_backend(speech, args.backend)
            print(f"Submit: {result}")
            time.sleep(args.delay)
    else:
        # Full scrape
        years = [args.year] if args.year else None
        scrape_all(years=years, max_per_run=args.max, delay=args.delay, backend=args.backend)
