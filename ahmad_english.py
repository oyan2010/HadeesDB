"""
Musnad Ahmad - English + Arabic scraper
Source: https://sunnah.com/ahmad/N  (books 1-7 and 31)
Output: db\ahmad_english.db (SQLite); logs\ahmad_english.log
Run:    python ahmad_english.py
"""

import re
import sys
import time
import sqlite3
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------- config ----------------
COLLECTION = "ahmad"            # sunnah.com slug + filename prefix
COLLECTION_TITLE = "Musnad Ahmad"
BOOKS = list(range(1, 8)) + [31]             # book numbers for this collection

BASE = Path(__file__).resolve().parent
DB_DIR = BASE / "db"
LOG_DIR = BASE / "logs"
DB_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / f"{COLLECTION}_english.db"
LOG_PATH = LOG_DIR / f"{COLLECTION}_english.log"
DELAY = 1.2                        # seconds between requests
TIMEOUT = 30
MAX_RETRIES = 3
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
# ---------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
log = logging.getLogger(COLLECTION + "-en")


SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    book_number   INTEGER PRIMARY KEY,
    english_name  TEXT NOT NULL,
    arabic_name   TEXT NOT NULL,
    url           TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chapters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    book_number     INTEGER NOT NULL,
    chapter_number  INTEGER NOT NULL,
    english_title   TEXT,
    arabic_title    TEXT,
    intro_english   TEXT,
    intro_arabic    TEXT,
    UNIQUE(book_number, chapter_number)
);
CREATE TABLE IF NOT EXISTS hadith (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    container_id        TEXT UNIQUE NOT NULL,
    hadith_number       INTEGER NOT NULL,
    book_number         INTEGER NOT NULL,
    chapter_number      INTEGER,
    narrator            TEXT,
    english_text        TEXT NOT NULL,
    arabic_sanad        TEXT,
    arabic_text         TEXT NOT NULL,
    reference           TEXT,
    in_book_reference   TEXT,
    usc_msa_reference   TEXT,
    source_url          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hadith_book    ON hadith(book_number);
CREATE INDEX IF NOT EXISTS idx_hadith_number  ON hadith(hadith_number);
"""


def clean(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def fetch(url):
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log.info(f"GET {url}  (attempt {attempt}/{MAX_RETRIES})")
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
            r.raise_for_status()
            log.info(f"  -> HTTP {r.status_code}, {len(r.text):,} bytes")
            return r.text
        except Exception as e:
            last_err = e
            log.warning(f"  -> failed: {e}")
            if attempt < MAX_RETRIES:
                wait = DELAY * (2 ** attempt)
                log.info(f"  -> retrying in {wait:.1f}s ...")
                time.sleep(wait)
    raise RuntimeError(f"fetch failed after {MAX_RETRIES} retries: {url} ({last_err})")


def parse_book(html, book_number):
    soup = BeautifulSoup(html, "html.parser")

    book_en_el = soup.select_one(".book_page_english_name")
    book_ar_el = soup.select_one(".book_page_arabic_name")
    book_en = clean(book_en_el.get_text()) if book_en_el else f"Book {book_number}"
    book_ar = clean(book_ar_el.get_text()) if book_ar_el else ""

    chapters = []
    hadith_list = []
    current_chapter = None

    root = soup.select_one(".AllHadith") or soup
    for el in root.children:
        if not getattr(el, "name", None):
            continue

        if "chapter" in (el.get("class") or []):
            ch_no_el = el.select_one(".echapno")
            ch_en_el = el.select_one(".englishchapter")
            ch_ar_el = el.select_one(".arabicchapter")
            ch_no = None
            if ch_no_el:
                m = re.search(r"\d+", ch_no_el.get_text())
                if m:
                    ch_no = int(m.group())
            current_chapter = ch_no
            chapters.append({
                "chapter_number": ch_no,
                "english_title": clean(ch_en_el.get_text()) if ch_en_el else "",
                "arabic_title": clean(ch_ar_el.get_text()) if ch_ar_el else "",
            })
            intro_en = el.find_next_sibling(class_="echapintro")
            intro_ar = el.find_next_sibling(class_=lambda c: c and "achapintro" in c)
            if chapters:
                chapters[-1]["intro_english"] = clean(intro_en.get_text()) if intro_en else ""
                chapters[-1]["intro_arabic"] = clean(intro_ar.get_text()) if intro_ar else ""
            continue

        classes = el.get("class") or []
        if "actualHadithContainer" in classes or el.get("id", "").startswith("h"):
            container_id = el.get("id") or ""
            sticky = el.select_one(".hadith_reference_sticky")
            ref = clean(sticky.get_text()) if sticky else ""
            m = re.search(r"(\d+)", ref)
            hadith_number = int(m.group(1)) if m else None

            narr_el = el.select_one(".hadith_narrated")
            narrator = clean(narr_el.get_text()) if narr_el else ""

            eng_el = el.select_one(".text_details")
            english_text = clean(eng_el.get_text(" ")) if eng_el else ""

            ar_full = el.select_one(".arabic_hadith_full")
            sanad_el = el.select_one(".arabic_sanad")
            matn_el = el.select_one(".arabic_text_details")
            arabic_sanad = clean(sanad_el.get_text(" ")) if sanad_el else ""
            arabic_text = clean(matn_el.get_text(" ")) if matn_el else ""
            if not arabic_text and ar_full:
                arabic_text = clean(ar_full.get_text(" "))

            in_book = ""
            usc = ""
            for tr in el.select("table.hadith_reference tr"):
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                key = clean(tds[0].get_text()).rstrip(":")
                val = clean(tds[1].get_text())
                if key.lower().startswith("in-book"):
                    in_book = val
                elif "Vol" in val:
                    usc = val

            if not english_text and not arabic_text:
                continue

            hadith_list.append({
                "container_id": container_id,
                "hadith_number": hadith_number,
                "chapter_number": current_chapter,
                "narrator": narrator,
                "english_text": english_text,
                "arabic_sanad": arabic_sanad,
                "arabic_text": arabic_text,
                "reference": ref,
                "in_book_reference": in_book,
                "usc_msa_reference": usc,
            })

    return book_en, book_ar, chapters, hadith_list


def main():
    log.info("=" * 70)
    log.info(f"{COLLECTION_TITLE} ENGLISH+ARABIC scraper START")
    log.info(f"DB  : {DB_PATH}")
    log.info(f"Log : {LOG_PATH}")
    log.info(f"Books: {len(BOOKS)} pages {BOOKS[0]}..{BOOKS[-1]} | delay={DELAY}s | retries={MAX_RETRIES}")
    log.info("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()

    total_hadith = 0
    total_chapters = 0
    failed_books = []
    started = time.time()

    for idx, book_no in enumerate(BOOKS):
        url = f"https://sunnah.com/{COLLECTION}/{book_no}"
        log.info("-" * 60)
        log.info(f"BOOK {book_no} ({idx + 1}/{len(BOOKS)}) -> {url}")
        try:
            html = fetch(url)
            book_en, book_ar, chapters, hadith_list = parse_book(html, book_no)

            conn.execute(
                "INSERT OR REPLACE INTO books(book_number, english_name, arabic_name, url) "
                "VALUES (?,?,?,?)",
                (book_no, book_en, book_ar, url),
            )
            conn.execute("DELETE FROM chapters WHERE book_number=?", (book_no,))
            conn.execute("DELETE FROM hadith WHERE book_number=?", (book_no,))

            for ch in chapters:
                if ch.get("chapter_number") is None:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO chapters"
                    "(book_number, chapter_number, english_title, arabic_title, intro_english, intro_arabic) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        book_no,
                        ch["chapter_number"],
                        ch.get("english_title", ""),
                        ch.get("arabic_title", ""),
                        ch.get("intro_english", ""),
                        ch.get("intro_arabic", ""),
                    ),
                )

            for h in hadith_list:
                conn.execute(
                    "INSERT OR REPLACE INTO hadith"
                    "(container_id, hadith_number, book_number, chapter_number, narrator,"
                    " english_text, arabic_sanad, arabic_text, reference,"
                    " in_book_reference, usc_msa_reference, source_url) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        h["container_id"],
                        h["hadith_number"],
                        book_no,
                        h["chapter_number"],
                        h["narrator"],
                        h["english_text"],
                        h["arabic_sanad"],
                        h["arabic_text"],
                        h["reference"],
                        h["in_book_reference"],
                        h["usc_msa_reference"],
                        url,
                    ),
                )
            conn.commit()

            total_hadith += len(hadith_list)
            total_chapters += len(chapters)
            log.info(
                f"BOOK {book_no} OK | '{book_en}' | "
                f"{len(chapters)} chapters, {len(hadith_list)} hadith | "
                f"running total: {total_hadith} hadith"
            )

        except Exception as e:
            log.error(f"BOOK {book_no} FAILED: {e}")
            failed_books.append(book_no)
            conn.rollback()

        if idx < len(BOOKS) - 1:
            time.sleep(DELAY)

    elapsed = time.time() - started
    log.info("=" * 70)
    log.info("DONE")
    log.info(f"  books scraped : {len(BOOKS) - len(failed_books)}/{len(BOOKS)}")
    log.info(f"  chapters      : {total_chapters}")
    log.info(f"  hadith total  : {total_hadith}")
    log.info(f"  failed books  : {failed_books if failed_books else 'none'}")
    log.info(f"  time          : {elapsed / 60:.1f} min")
    log.info(f"  database      : {DB_PATH}")
    log.info("=" * 70)

    cur = conn.execute("SELECT COUNT(*), MIN(hadith_number), MAX(hadith_number) FROM hadith")
    cnt, mn, mx = cur.fetchone()
    log.info(f"DB verify: rows={cnt}, hadith_number range={mn}..{mx}")
    cur = conn.execute(
        "SELECT book_number, COUNT(*) c FROM hadith GROUP BY book_number ORDER BY book_number"
    )
    for bn, c in cur.fetchall():
        log.info(f"  book {bn:>3}: {c:>5} hadith")
    conn.close()

    if failed_books:
        log.warning("Some books failed. Re-run the script - existing books will be replaced.")
        sys.exit(1)


if __name__ == "__main__":
    main()
