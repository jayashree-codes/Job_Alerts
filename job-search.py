"""
Edinburgh Job Alert - Sainsbury's & Tesco (within 5 miles of EH11 2EE)
=======================================================================
Polls both career sites and opens a sticky-note HTML page in your browser
whenever new jobs appear, with clickable apply links.

SETUP
-----
1. Install dependencies:
       pip install requests beautifulsoup4 playwright
       playwright install chromium

2. (Optional) Set your email credentials for email alerts too:
   - Create a Gmail App Password: https://myaccount.google.com/apppasswords
   - Fill in the CONFIG section below, and set NOTIFY_EMAIL = True

3. Run once manually to seed the known-jobs cache:
       python job_alert.py

4. Schedule it (runs every 30 min):
   - Mac:     crontab -e  →  */30 * * * * /usr/bin/python3 /Users/jayashreehariharan/Desktop/Part-Time/job-search.py
   - Windows: Task Scheduler → repeat every 30 minutes

Duplicate prevention
--------------------
Jobs are deduplicated by BOTH their URL and their normalised title+location,
so the same posting won't appear twice even if the URL changes slightly.
Seen jobs are stored in 'seen_jobs.json' next to this script.
"""

import json
import smtplib
import webbrowser
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG  ← edit these
# ─────────────────────────────────────────────────────────────────────────────
EMAIL_FROM   = "jayworks2043@gmail.com"
EMAIL_TO     = "jayworks2043@gmail.com"
SMTP_HOST    = "smtp.gmail.com"
SMTP_PORT    = 587
SMTP_USER    = "jayworks2043@gmail.com"
SMTP_PASS    = "eablnvnlnoizvmlz"

SEEN_FILE      = Path(__file__).parent / "seen_jobs.json"
USE_BROWSER    = True    # True = Playwright (handles JS); False = plain requests
NOTIFY_POPUP   = True    # Open a sticky HTML page in browser when new jobs found
NOTIFY_EMAIL   = True   # Also send an email (set True and fill creds above)
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

SAINSBURYS_URL = (
    "https://www.sainsburys.jobs/jobs"
    "?full_time=&part_time=&fixed_term=&filter_by=&location=edinburgh&keywords="
)

TESCO_URL = (
    "https://careers.tesco.com/en_GB/careers/SearchJobs/"
    "?748_location_place=EH11%202EE,%20Gorgie,%20Edinburgh,%20Scotland,%20United%20Kingdom"
    "&748_location_radius=5"
    "&748_location_coordinates=[55.94,-3.22]"
    "&listFilterMode=1&jobRecordsPerPage=10&"
)

RETAILER_COLORS = {
    "sainsburys": {"bg": "#f5f0e8", "accent": "#e8520a", "label": "Sainsbury's"},
    "tesco":      {"bg": "#eef4ff", "accent": "#004499", "label": "Tesco"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Deduplication helpers
# ─────────────────────────────────────────────────────────────────────────────
def load_seen() -> dict:
    if SEEN_FILE.exists():
        data = json.loads(SEEN_FILE.read_text())
        # Migrate old format that stored {"urls": [...], "fingerprints": [...]}
        for retailer in ("sainsburys", "tesco"):
            if retailer not in data:
                data[retailer] = []
            elif isinstance(data[retailer], dict):
                data[retailer] = data[retailer].get("urls", [])
        return data
    return {"sainsburys": [], "tesco": []}


def save_seen(seen: dict) -> None:
    SEEN_FILE.write_text(json.dumps(seen, indent=2))


def is_duplicate(job: dict, seen_urls: list) -> bool:
    """Return True only if this exact job URL/ID has been seen before."""
    return job["id"] in seen_urls


def mark_seen(job: dict, seen_urls: list) -> None:
    seen_urls.append(job["id"])


# ─────────────────────────────────────────────────────────────────────────────
# Fetching
# ─────────────────────────────────────────────────────────────────────────────

def fetch_html_requests(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def fetch_html_browser(url: str, wait_selector: str = "body") -> str:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"], locale="en-GB")
        page.goto(url, wait_until="networkidle", timeout=30_000)
        try:
            page.wait_for_selector(wait_selector, timeout=10_000)
        except Exception:
            pass
        html = page.content()
        browser.close()
    return html


def fetch_html(url: str, wait_selector: str = "body") -> str:
    if USE_BROWSER:
        return fetch_html_browser(url, wait_selector)
    return fetch_html_requests(url)


# ─────────────────────────────────────────────────────────────────────────────
# Scrapers
# ─────────────────────────────────────────────────────────────────────────────

def scrape_sainsburys() -> list[dict]:
    print("[Sainsbury's] Fetching...")
    html = fetch_html(SAINSBURYS_URL, wait_selector="[class*='job']")
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    cards = []
    for sel in ["article", "[class*='job-card']", "[class*='jobCard']",
                "[class*='vacancy']", "li[class*='job']"]:
        cards = soup.select(sel)
        if cards:
            break

    seen_ids = set()
    for card in cards:
        link_tag     = card.find("a", href=True)
        title_tag    = card.find(["h2", "h3", "h4"]) or card.find("[class*='title']")
        location_tag = card.find("[class*='location']") or card.find("[class*='place']")
        if not link_tag or not title_tag:
            continue
        href = link_tag["href"]
        if not href.startswith("http"):
            href = "https://www.sainsburys.jobs" + href
        if href in seen_ids:
            continue
        seen_ids.add(href)
        jobs.append({
            "id":       href,
            "title":    title_tag.get_text(strip=True),
            "location": location_tag.get_text(strip=True) if location_tag else "Edinburgh",
            "url":      href,
        })

    print(f"[Sainsbury's] Found {len(jobs)} jobs")
    return jobs


def scrape_tesco() -> list[dict]:
    print("[Tesco] Fetching...")
    html = fetch_html(TESCO_URL, wait_selector="[class*='job']")
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    cards = []
    for sel in ["[class*='article']", "[class*='job-item']", "[class*='jobItem']",
                "[class*='search-result']", "li[class*='job']", "article"]:
        cards = soup.select(sel)
        if cards:
            break

    seen_ids = set()
    for card in cards:
        link_tag     = card.find("a", href=True)
        title_tag    = card.find(["h2", "h3", "h4"]) or card.find("[class*='title']")
        location_tag = card.find("[class*='location']") or card.find("[class*='place']")
        if not link_tag or not title_tag:
            continue
        href = link_tag["href"]
        if not href.startswith("http"):
            href = "https://careers.tesco.com" + href
        if href in seen_ids:
            continue
        seen_ids.add(href)
        jobs.append({
            "id":       href,
            "title":    title_tag.get_text(strip=True),
            "location": location_tag.get_text(strip=True) if location_tag else "Edinburgh",
            "url":      href,
        })

    print(f"[Tesco] Found {len(jobs)} jobs")
    return jobs


# ─────────────────────────────────────────────────────────────────────────────
# Native desktop window (tkinter — built into Python, no install needed)
# ─────────────────────────────────────────────────────────────────────────────

def open_sticky_popup(new_jobs: dict[str, list[dict]]) -> None:
    """Open a native always-on-top desktop window listing jobs with clickable links."""
    import tkinter as tk
    import webbrowser

    total = sum(len(v) for v in new_jobs.values())
    now   = datetime.now().strftime("%d %b %Y  %H:%M")

    root = tk.Tk()
    root.title("🛒 New Jobs Near You!")
    root.configure(bg="#fffde7")
    root.resizable(False, False)
    root.attributes("-topmost", True)   # always on top of other windows

    # ── Header ──────────────────────────────────────────────────────────────
    hdr = tk.Frame(root, bg="#f9d000", pady=10, padx=16)
    hdr.pack(fill="x")

    tk.Label(
        hdr,
        text=f"🛒  {total} new job opening{'s' if total != 1 else ''} near you!",
        font=("Helvetica", 15, "bold"),
        bg="#f9d000", fg="#222",
        anchor="w",
    ).pack(fill="x")

    tk.Label(
        hdr,
        text=f"Found at {now}  ·  within 5 miles of EH11 2EE",
        font=("Helvetica", 10),
        bg="#f9d000", fg="#555",
        anchor="w",
    ).pack(fill="x")

    # ── Scrollable body ──────────────────────────────────────────────────────
    container = tk.Frame(root, bg="#fffde7")
    container.pack(fill="both", expand=True)

    canvas    = tk.Canvas(container, bg="#fffde7", highlightthickness=0)
    scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)

    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner = tk.Frame(canvas, bg="#fffde7")
    canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

    def on_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfig(canvas_window, width=canvas.winfo_width())

    inner.bind("<Configure>", on_configure)
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))

    # Mouse-wheel scrolling
    def on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", on_mousewheel)

    # ── Job sections ─────────────────────────────────────────────────────────
    ACCENT = {"sainsburys": "#e8520a", "tesco": "#004499"}
    SECBG  = {"sainsburys": "#f5f0e8", "tesco": "#eef4ff"}

    for retailer, jobs in new_jobs.items():
        accent = ACCENT.get(retailer, "#555")
        secbg  = SECBG.get(retailer, "#f9f9f9")
        label  = RETAILER_COLORS.get(retailer, {}).get("label", retailer.title())

        # Section header bar
        sec_hdr = tk.Frame(inner, bg=accent)
        sec_hdr.pack(fill="x", padx=14, pady=(14, 0))
        tk.Label(
            sec_hdr,
            text=f"  {label.upper()}",
            font=("Helvetica", 10, "bold"),
            bg=accent, fg="white",
            pady=4, anchor="w",
        ).pack(fill="x")

        # Job cards
        for j in jobs:
            card = tk.Frame(inner, bg=secbg, pady=8, padx=12,
                            highlightbackground="#ddd", highlightthickness=1)
            card.pack(fill="x", padx=14, pady=(0, 1))

            tk.Label(
                card,
                text=j["title"],
                font=("Helvetica", 12, "bold"),
                bg=secbg, fg="#1a1a1a",
                anchor="w", wraplength=380, justify="left",
            ).pack(fill="x")

            tk.Label(
                card,
                text=f"📍 {j['location']}",
                font=("Helvetica", 10),
                bg=secbg, fg="#666",
                anchor="w",
            ).pack(fill="x")

            # Clickable "Apply →" link
            url = j["url"]
            link = tk.Label(
                card,
                text="Apply →",
                font=("Helvetica", 10, "underline"),
                bg=secbg, fg=accent,
                cursor="hand2",
                anchor="w",
            )
            link.pack(anchor="w", pady=(4, 0))
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

    # ── Footer / close button ────────────────────────────────────────────────
    foot = tk.Frame(root, bg="#fffde7", pady=10)
    foot.pack(fill="x")
    tk.Button(
        foot,
        text="  Close  ",
        font=("Helvetica", 11),
        bg="#f9d000", fg="#333",
        relief="flat",
        cursor="hand2",
        command=root.destroy,
    ).pack()

    # ── Size & centre on screen ──────────────────────────────────────────────
    root.update_idletasks()
    win_w, win_h = 460, min(600, root.winfo_reqheight())
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x  = sw - win_w - 40          # 40px from right edge
    y  = 60                        # near top of screen
    root.geometry(f"{win_w}x{win_h}+{x}+{y}")

    print("[Popup] Showing native desktop window.")
    root.mainloop()                # blocks until user closes the window


# ─────────────────────────────────────────────────────────────────────────────
# Email (optional)
# ─────────────────────────────────────────────────────────────────────────────

def send_email(new_jobs: dict[str, list[dict]]) -> None:
    total   = sum(len(v) for v in new_jobs.values())
    subject = f"New Edinburgh job opening{'s' if total != 1 else ''} - Sainsbury's / Tesco"

    rows = ""
    for retailer, jobs in new_jobs.items():
        for j in jobs:
            label = RETAILER_COLORS.get(retailer, {}).get("label", retailer.title())
            rows += f"""
            <tr>
              <td style="padding:8px;border:1px solid #ddd;font-weight:bold">{label}</td>
              <td style="padding:8px;border:1px solid #ddd">{j['title']}</td>
              <td style="padding:8px;border:1px solid #ddd">{j['location']}</td>
              <td style="padding:8px;border:1px solid #ddd"><a href="{j['url']}">Apply</a></td>
            </tr>"""

    html_body = f"""
    <html><body style="font-family:sans-serif;color:#222">
    <h2>New Edinburgh job openings near EH11 2EE</h2>
    <p>Found at {datetime.now().strftime('%d %b %Y %H:%M')}</p>
    <table style="border-collapse:collapse;width:100%">
      <thead style="background:#f4f4f4">
        <tr>
          <th style="padding:8px;border:1px solid #ddd;text-align:left">Retailer</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left">Role</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left">Location</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left">Link</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    print(f"[Email] Sent: {subject}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print(f"  Edinburgh Job Alert  -  {datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"{'='*55}")

    seen     = load_seen()
    new_jobs: dict[str, list[dict]] = {}

    # Sainsbury's
    try:
        sains_jobs = scrape_sainsburys()
        new_sains  = [j for j in sains_jobs if not is_duplicate(j, seen["sainsburys"])]
        if new_sains:
            new_jobs["sainsburys"] = new_sains
            for j in new_sains:
                mark_seen(j, seen["sainsburys"])
            print(f"[Sainsbury's] {len(new_sains)} NEW job(s)!")
        else:
            print("[Sainsbury's] No new jobs.")
    except Exception as e:
        print(f"[Sainsbury's] ERROR: {e}")

    # Tesco
    try:
        tesco_jobs = scrape_tesco()
        new_tesco  = [j for j in tesco_jobs if not is_duplicate(j, seen["tesco"])]
        if new_tesco:
            new_jobs["tesco"] = new_tesco
            for j in new_tesco:
                mark_seen(j, seen["tesco"])
            print(f"[Tesco] {len(new_tesco)} NEW job(s)!")
        else:
            print("[Tesco] No new jobs.")
    except Exception as e:
        print(f"[Tesco] ERROR: {e}")

    # Notify
    if new_jobs:
        if NOTIFY_POPUP:
            open_sticky_popup(new_jobs)
        if NOTIFY_EMAIL:
            try:
                send_email(new_jobs)
            except Exception as e:
                print(f"[Email] ERROR: {e}")
    else:
        print("\nNo new openings since last check.")

    save_seen(seen)
    print("Done.\n")


if __name__ == "__main__":
    main()