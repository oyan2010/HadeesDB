-- Sahih al-Bukhari Database Schema (sunnah.com)
-- Books 1-97, ~7563 hadith. Two DBs: bukhari_english.db + bukhari_urdu.db
-- Join key between the two: english.hadith.container_id == urdu.hadith.matching_arabic_urn

-- ============================================================
-- ENGLISH DB (bukhari_english.db)
-- ============================================================

CREATE TABLE IF NOT EXISTS books (
    book_number   INTEGER PRIMARY KEY,          -- 1..97
    english_name  TEXT NOT NULL,                -- e.g. "Revelation"
    arabic_name   TEXT NOT NULL,                -- e.g. "كتاب بدء الوحى"
    url           TEXT NOT NULL                 -- https://sunnah.com/bukhari/N
);

CREATE TABLE IF NOT EXISTS chapters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    book_number     INTEGER NOT NULL REFERENCES books(book_number),
    chapter_number  INTEGER NOT NULL,           -- bab number within book
    english_title   TEXT,                       -- e.g. "Chapter: How the Divine Revelation..."
    arabic_title    TEXT,                       -- e.g. "باب كَيْفَ كَانَ بَدْءُ الْوَحْىِ..."
    intro_english   TEXT,                       -- chapter intro (english)
    intro_arabic    TEXT,                       -- chapter intro (arabic)
    UNIQUE(book_number, chapter_number)
);

CREATE TABLE IF NOT EXISTS hadith (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    container_id        TEXT UNIQUE NOT NULL,   -- sunnah.com DOM id e.g. "h100010" (also join key with urdu)
    hadith_number       INTEGER NOT NULL,       -- Sahih al-Bukhari N (standard numbering)
    book_number         INTEGER NOT NULL REFERENCES books(book_number),
    chapter_number      INTEGER,                -- nullable, bab within book
    narrator            TEXT,                   -- "Narrated 'Umar bin Al-Khattab:"
    english_text        TEXT NOT NULL,          -- full English translation
    arabic_sanad        TEXT,                   -- Arabic chain of narration
    arabic_text         TEXT NOT NULL,          -- Arabic matn (body)
    reference           TEXT,                   -- "Sahih al-Bukhari 1"
    in_book_reference   TEXT,                   -- "Book 1, Hadith 1"
    usc_msa_reference   TEXT,                   -- "Vol. 1, Book 1, Hadith 1" (deprecated numbering)
    source_url          TEXT NOT NULL           -- https://sunnah.com/bukhari:N
);

CREATE INDEX IF NOT EXISTS idx_hadith_book     ON hadith(book_number);
CREATE INDEX IF NOT EXISTS idx_hadith_number   ON hadith(hadith_number);
CREATE INDEX IF NOT EXISTS idx_hadith_chapter  ON hadith(book_number, chapter_number);

-- ============================================================
-- URDU DB (bukhari_urdu.db)
-- ============================================================

CREATE TABLE IF NOT EXISTS books (
    book_number   INTEGER PRIMARY KEY,          -- 1..97
    english_name  TEXT,                         -- from ajax (may be empty)
    arabic_name   TEXT,                         -- bookName in urdu e.g. "کتاب وحی کے بیان میں"
    ajax_url      TEXT NOT NULL                 -- https://sunnah.com/ajax/urdu/bukhari/N
);

CREATE TABLE IF NOT EXISTS hadith (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    urdu_urn             TEXT UNIQUE NOT NULL,  -- e.g. "4000010"
    matching_arabic_urn  TEXT NOT NULL,         -- join key == english.container_id ("h100010" strip prefix h -> "100010")
    hadith_number        INTEGER,               -- from ajax hadithNumber
    our_hadith_number    INTEGER,               -- from ajax ourHadithNumber
    book_number          INTEGER NOT NULL REFERENCES books(book_number),
    bab_number           INTEGER,               -- chapter/bab number
    bab_name             TEXT,                  -- bab title (urdu)
    urdu_sanad           TEXT,                  -- Urdu chain of narration
    urdu_text            TEXT NOT NULL,         -- Urdu translation body
    grade                TEXT,                  -- grade if provided (usually empty)
    comments             TEXT,
    source_url           TEXT NOT NULL          -- https://sunnah.com/bukhari:N
);

CREATE INDEX IF NOT EXISTS idx_urdu_book    ON hadith(book_number);
CREATE INDEX IF NOT EXISTS idx_urdu_match   ON hadith(matching_arabic_urn);
CREATE INDEX IF NOT EXISTS idx_urdu_number  ON hadith(hadith_number);

-- ============================================================
-- HOW TO QUERY (examples for app building)
-- ============================================================

-- Get hadith #1 English + Arabic:
--   SELECT * FROM hadith WHERE hadith_number = 1;

-- Get full book list:
--   SELECT * FROM books ORDER BY book_number;

-- Get all hadith of a book with chapter titles:
--   SELECT h.*, c.english_title, c.arabic_title
--   FROM hadith h LEFT JOIN chapters c
--     ON h.book_number = c.book_number AND h.chapter_number = c.chapter_number
--   WHERE h.book_number = 1
--   ORDER BY h.hadith_number;

-- Join English + Urdu (from both DBs, use sqlite ATTACH):
--   ATTACH 'bukhari_urdu.db' AS u;
--   SELECT e.hadith_number, e.english_text, e.arabic_text, u.urdu_text
--   FROM hadith e
--   JOIN u.hadith u ON e.container_id = 'h' || u.matching_arabic_urn
--   ORDER BY e.hadith_number;
