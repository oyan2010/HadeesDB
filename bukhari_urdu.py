"""
Sahih al-Bukhari - URDU translation scraper
Source AJAX: https://sunnah.com/ajax/urdu/bukhari/1 .. /97
Output: db\bukhari_urdu.db (SQLite); logs\bukhari_urdu.log
Run:    python bukhari_urdu.py

Join key with english DB: matching_arabic_urn ("100010") == english.container_id ("h100010")
"""

import re
import sys
import time
import json
import sqlite3
import logging
from pathlib import Path

import requests

# ---------------- config ----------------
BASE = Path(__file__).resolve().parent
DB_DIR = BASE / "db"
LOG_DIR = BASE / "logs"
DB_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "bukhari_urdu.db"
LOG_PATH = LOG_DIR / "bukhari_urdu.log"
BOOKS = range(1, 98)          # 1..97
DELAY = 1.2
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
log = logging.getLogger("bukhari-ur")


SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    book_number   INTEGER PRIMARY KEY,
    english_name  TEXT,
    arabic_name   TEXT,
    ajax_url      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hadith (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    urdu_urn             TEXT UNIQUE NOT NULL,
    matching_arabic_urn  TEXT NOT NULL,
    hadith_number        INTEGER,
    our_hadith_number    INTEGER,
    book_number          INTEGER NOT NULL,
    bab_number           INTEGER,
    bab_name             TEXT,
    urdu_sanad           TEXT,
    urdu_text            TEXT NOT NULL,
    grade                TEXT,
    comments             TEXT,
    source_url           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_urdu_book   ON hadith(book_number);
CREATE INDEX IF NOT EXISTS idx_urdu_match  ON hadith(matching_arabic_urn);
CREATE INDEX IF NOT EXISTS idx_urdu_number ON hadith(hadith_number);
"""


def clean(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def to_int(v):
    if v is None:
        return None
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


def fetch_json(url: str):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://sunnah.com/bukhari",
    }
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log.info(f"GET {url}  (attempt {attempt}/{MAX_RETRIES})")
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            log.info(f"  -> HTTP {r.status_code}, {len(r.text):,} bytes, {len(data)} items")
            return data
        except Exception as e:
            last_err = e
            log.warning(f"  -> failed: {e}")
            if attempt < MAX_RETRIES:
                wait = DELAY * (2 ** attempt)
                log.info(f"  -> retrying in {wait:.1f}s ...")
                time.sleep(wait)
    raise RuntimeError(f"fetch failed after {MAX_RETRIES} retries: {url} ({last_err})")


def main():
    log.info("=" * 70)
    log.info("Sahih al-Bukhari URDU scraper START")
    log.info(f"DB  : {DB_PATH}")
    log.info(f"Log : {LOG_PATH}")
    log.info(f"Books: 1..97 | delay={DELAY}s | retries={MAX_RETRIES}")
    log.info("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()

    total = 0
    failed_books = []
    started = time.time()

    for book_no in BOOKS:
        url = f"https://sunnah.com/ajax/urdu/bukhari/{book_no}"
        log.info("-" * 60)
        log.info(f"BOOK {book_no}/97 -> {url}")
        try:
            items = fetch_json(url)
            if not isinstance(items, list):
                log.warning(f"  unexpected payload type: {type(items)}")
                items = []

            conn.execute("DELETE FROM hadith WHERE book_number=?", (book_no,))
            book_name = ""
            for it in items:
                bn = clean(it.get("bookName"))
                if bn:
                    book_name = bn
                urdu_urn = clean(it.get("urduURN"))
                match_urn = clean(it.get("matchingArabicURN"))
                if not urdu_urn:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO hadith"
                    "(urdu_urn, matching_arabic_urn, hadith_number, our_hadith_number,"
                    " book_number, bab_number, bab_name, urdu_sanad, urdu_text,"
                    " grade, comments, source_url) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        urdu_urn,
                        match_urn,
                        to_int(it.get("hadithNumber")),
                        to_int(it.get("ourHadithNumber")),
                        book_no,
                        to_int(it.get("babNumber")),
                        clean(it.get("babName")),
                        clean(it.get("hadithSanad")),
                        clean(it.get("hadithText")),
                        clean(it.get("grade")),
                        clean(it.get("comments")),
                        f"https://sunnah.com/bukhari/{book_no}",
                    ),
                )

            conn.execute(
                "INSERT OR REPLACE INTO books(book_number, english_name, arabic_name, ajax_url) "
                "VALUES (?,?,?,?)",
                (book_no, "", book_name, url),
            )
            conn.commit()

            total += len(items)
            log.info(
                f"BOOK {book_no} OK | '{book_name or '?'}' | "
                f"{len(items)} hadith | running total: {total}"
            )

        except Exception as e:
            log.error(f"BOOK {book_no} FAILED: {e}")
            failed_books.append(book_no)
            conn.rollback()

        if book_no < 97:
            time.sleep(DELAY)

    elapsed = time.time() - started
    log.info("=" * 70)
    log.info("DONE")
    log.info(f"  books scraped : {97 - len(failed_books)}/97")
    log.info(f"  hadith total  : {total}  (expected ~7563)")
    log.info(f"  failed books  : {failed_books if failed_books else 'none'}")
    log.info(f"  time          : {elapsed/60:.1f} min")
    log.info(f"  database      : {DB_PATH}")
    log.info("=" * 70)

    cur = conn.execute("SELECT COUNT(*) FROM hadith")
    cnt = cur.fetchone()[0]
    log.info(f"DB verify: rows={cnt}")
    cur = conn.execute(
        "SELECT book_number, COUNT(*) c FROM hadith GROUP BY book_number ORDER BY book_number"
    )
    for bn, c in cur.fetchall():
        log.info(f"  book {bn:>2}: {c:>4} hadith")
    conn.close()

    if failed_books:
        log.warning("Some books failed. Re-run the script — existing books will be replaced.")
        sys.exit(1)


if __name__ == "__main__":
    main()
