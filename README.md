# Web Scraping Showcase

> **High-precision data extraction engines built to operate against real-world anti-bot infrastructure** — Cloudflare, eBay's SRP detection layer, and AJAX-driven dynamic content — without triggering blocks or captchas.

This repository contains three production-grade scrapers developed during training for a high-level Data Extraction role. Each engine targets a distinct class of anti-bot defense, demonstrates a different extraction pattern, and delivers clean, normalized output data.

---

## The Engines

### 1. Global Stealth Scraper — eBay GPU Listings

| Property | Detail |
|---|---|
| **Target** | `ebay.com` — RTX 4060 search results |
| **Script** | `ebay_scraper.py` |
| **Output** | `ebay_gpus.json` |
| **Pages** | 3 (pagination via `a[type='next']`) |

**What it does:**

eBay's Search Results Page runs a full browser fingerprinting stack. This scraper bypasses it using a hard stealth requirement — `playwright_stealth` is a non-negotiable dependency (`sys.exit(1)` if absent), supplemented by a belt-and-suspenders `navigator.languages` init script patch that pins the language array to `['en-US', 'en']` independently of the stealth library version.

Human simulation is not cosmetic — it is structural. The scroll engine uses **randomized step sizes (250–650px) with micro-pauses (80–350ms)** to produce a scroll velocity profile that matches real user behavior. Inter-page delays are drawn from a `[2.5s–5.0s]` uniform distribution.

**Data normalization:**

- Price strings like `"$249.99 to $399.99"` are resolved to their lower bound (`249.99`) via regex — no fragile string splits.
- Shipping is parsed to `0.0` on any "free" variant; otherwise the numeric value is extracted.
- A **`total_cost`** field (price + shipping) is computed and stored alongside the raw strings for auditability.
- eBay injects ghost listings (`"SHOP ON EBAY"`) at list position 0 — these are filtered by exact title match.

```json
{
    "title": "ZOTAC Gaming GeForce RTX 4060 Twin Edge OC",
    "price": 279.99,
    "shipping": 0.0,
    "total_cost": 279.99,
    "price_raw": "$279.99",
    "shipping_raw": "Free shipping"
}
```

---

### 2. Regional Commercial Scraper — PakWheels Used Cars

| Property | Detail |
|---|---|
| **Target** | `pakwheels.com` — Honda Civic listings |
| **Script** | `pakwheels_scraper.py` |
| **Output** | `pakwheels_civics.json` |
| **Results** | First 20 listings |

**What it does:**

PakWheels is served behind Cloudflare's Bot Management layer. The standard `wait_for_load_state("networkidle")` approach **always times out** on Cloudflare — the CDN's bot-management JS sends continuous background XHR heartbeats that permanently prevent the network from going idle. This scraper implements a **Heuristic Anti-Bot Bypass**:

1. `page.goto(url, wait_until="load")` — waits for the HTML document, not network silence.
2. Fixed 3-second settle delay — allows Cloudflare's challenge script to execute.
3. `page.wait_for_selector(SEL_CONTAINER)` — confirms real listing content reached the DOM before extraction begins.

If a Cloudflare CAPTCHA interstitial is detected (via title/body phrase matching), the scraper pauses and polls every 5 seconds for up to 120 seconds, allowing manual resolution in the open browser window before resuming automatically.

**Regional data normalization:**

PakWheels prices use South Asian shorthand that no generic parser handles correctly. This scraper applies explicit multipliers:

| Raw String | Parsed Value (PKR) |
|---|---|
| `PKR 21 lacs` | `2,100,000` |
| `PKR 2.1 crore` | `21,000,000` |
| `PKR 23,50,000` | `2,350,000` |

```json
{
    "title": "Honda Civic 2021 1.5 Turbo Oriel",
    "price_pkr": 7800000,
    "price_raw": "PKR 78 lacs",
    "year": "2021",
    "mileage": "45,000 km",
    "fuel_type": "Petrol"
}
```

---

### 3. Dynamic Content Scraper — Quotes (Infinite Scroll)

| Property | Detail |
|---|---|
| **Target** | `quotes.toscrape.com/scroll` |
| **Script** | `playwright_scraper.py` |
| **Output** | `quotes.json` |
| **Mechanism** | AJAX infinite scroll |

**What it does:**

Infinite-scroll pages load content lazily — a naive scraper that reads the DOM immediately will capture only the first batch. This engine uses **DOM Plateau Detection** to determine programmatically when all content has loaded:

```
while scroll_count < MAX_SCROLLS:
    height_before = document.body.scrollHeight
    scroll to bottom → wait [1.5s–3.5s]
    height_after = document.body.scrollHeight
    if height_after == height_before: STOP  ← plateau detected
```

The scroll loop terminates on the **first height plateau** — no arbitrary page count, no guessing. `MAX_SCROLLS = 10` acts as a safety ceiling only. Data extraction runs once on the fully-loaded DOM, not per scroll, which eliminates duplicates entirely.

A pool of six User-Agents (Chrome 124, Firefox 125, Safari 17, Edge 124 — across Windows and macOS) is rotated per session.

```json
{
    "text": "\u201cThe world as we have created it is a process of our thinking.\u201d",
    "author": "Albert Einstein"
}
```

---

## Tech Stack

| Technology | Role |
|---|---|
| **Python 3.10+** | Runtime |
| **Playwright (Sync API)** | Browser automation, DOM interaction, pagination |
| **playwright-stealth 1.0.6** | Fingerprint masking — patches 20+ browser properties |
| **Regex (`re`)** | Price extraction, currency normalization, range parsing |
| **JSON** | Structured output for all three engines |

---

## Key Features

**Fingerprint Masking**
`playwright_stealth` patches the full automation fingerprint surface: `navigator.webdriver`, Chrome runtime object, plugin arrays, permissions API, language headers, and more. The eBay engine adds an explicit `navigator.languages` init script as an additional safeguard.

**User-Agent Rotation**
The PakWheels and Quotes scrapers rotate across a curated pool of Chrome, Firefox, Safari, and Edge UAs per session. The eBay engine uses a single, consistent Chrome 124 UA — rotating on a session-cookie-dependent site breaks the session.

**Data Integrity**
Every scraper stores both the **raw string** and the **normalized value** side-by-side. If a regex or multiplier produces an unexpected result, the source string is always available for debugging without re-scraping.

**Resilient Navigation**
All three scrapers include HTML debug dumps (`*_debug.html`) that are written automatically when selectors fail — making selector updates a 30-second offline exercise instead of a full re-investigation.

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/web-scraping-showcase.git
cd web-scraping-showcase

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Playwright's Chromium browser
playwright install chromium
```

**Dependencies (`requirements.txt`)**

```
requests==2.31.0
beautifulsoup4==4.12.3
selenium==4.18.1
undetected-chromedriver==3.5.5
playwright==1.44.0
playwright-stealth==1.0.6
```

---

## Usage

```bash
# eBay GPU scraper (3 pages → ebay_gpus.json)
python ebay_scraper.py

# PakWheels Honda Civic scraper (20 listings → pakwheels_civics.json)
python pakwheels_scraper.py

# Quotes infinite scroll scraper (all quotes → quotes.json)
python playwright_scraper.py
```

> All three scripts launch a **visible browser window** (`headless=False`) — required for stealth-dependent sites where headless mode exposes additional automation signals.
