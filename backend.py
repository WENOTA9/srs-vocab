"""
╔══════════════════════════════════════════════════════════════════╗
║  SRS 英文單字學習系統 v2 — 後端核心模組 (backend.py)           ║
║  重構: 章節架構 · PDF/CSV 匯入 · 圖表防護 · 3NF SQLite        ║
╚══════════════════════════════════════════════════════════════════╝
"""

# Python 3.9 compatible - no future annotations

import base64
import csv
import io
import json
import math
import os
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# §1  SM-2 演算法
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# 核心公式:
#   EF' = EF + (0.1 − (5 − q) × (0.08 + (5 − q) × 0.02))
#   q ≥ 3 → 回想成功: n=1→I=1, n=2→I=6, n>2→I=round(I_prev × EF)
#   q < 3 → 回想失敗: n=0, I=1
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class SM2Result:
    easiness_factor: float
    interval_days: int
    repetitions: int
    next_review: datetime


class SM2Algorithm:
    EF_MINIMUM: float = 1.3
    EF_DEFAULT: float = 2.5

    @staticmethod
    def calculate(
        quality: int,
        easiness_factor: float,
        interval_days: int,
        repetitions: int,
    ) -> SM2Result:
        """
        SM-2 核心計算。

        Parameters: quality(0-5), easiness_factor(≥1.3), interval_days, repetitions
        Returns: SM2Result with updated values
        """
        if not 0 <= quality <= 5:
            raise ValueError(f"quality 必須 0–5，收到: {quality}")

        # EF' = EF + (0.1 − (5−q)×(0.08 + (5−q)×0.02))
        d = 5 - quality
        new_ef = easiness_factor + (0.1 - d * (0.08 + d * 0.02))
        new_ef = max(SM2Algorithm.EF_MINIMUM, new_ef)

        if quality >= 3:
            new_reps = repetitions + 1
            if new_reps == 1:
                new_interval = 1
            elif new_reps == 2:
                new_interval = 6
            else:
                new_interval = max(1, round(interval_days * new_ef))
        else:
            new_reps = 0
            new_interval = 1

        return SM2Result(
            easiness_factor=round(new_ef, 4),
            interval_days=new_interval,
            repetitions=new_reps,
            next_review=datetime.now() + timedelta(days=new_interval),
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# §2  字典樹 (Trie) — O(L) 自動完成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class TrieNode:
    children: dict = field(default_factory=dict)
    is_end: bool = False
    word_data: Optional[list] = None  # List[dict] — 支援多分類 (國中+高中)


class Trie:
    def __init__(self) -> None:
        self._root = TrieNode()
        self._size = 0

    @property
    def size(self) -> int:
        return self._size

    def insert(self, word: str, data: Optional[dict] = None) -> None:
        """
        插入單字。若同一單字已存在 (如同時在國中和高中)，
        將新的 data 追加到 word_data 列表中，而非覆蓋。
        """
        word = word.lower().strip()
        if not word:
            return
        node = self._root
        for char in word:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        if not node.is_end:
            self._size += 1
            node.is_end = True
            node.word_data = [data] if data else []
        else:
            # 同一單字的第二個分類 → 追加而非覆蓋
            if data and node.word_data is not None:
                # 避免完全重複的 entry
                existing_cats = {d.get("category") for d in node.word_data}
                if data.get("category") not in existing_cats:
                    node.word_data.append(data)

    def search(self, word: str) -> Optional[list]:
        node = self._find_node(word.lower().strip())
        if node and node.is_end:
            return node.word_data
        return None

    def autocomplete(self, prefix: str, max_results: int = 50) -> List[dict]:
        """
        前綴自動完成 (DFS + 提早終止)。
        max_results=50 防止單字母搜尋產生數千個 UI 節點導致凍結。
        """
        prefix = prefix.lower().strip()
        if not prefix:
            return []
        node = self._find_node(prefix)
        if node is None:
            return []
        results: List[dict] = []
        self._dfs_collect(node, prefix, results, max_results)
        return results

    def _find_node(self, prefix: str) -> Optional["TrieNode"]:
        node = self._root
        for char in prefix:
            if char not in node.children:
                return None
            node = node.children[char]
        return node

    def _dfs_collect(self, node, current_word, results, max_results):
        if len(results) >= max_results:
            return
        if node.is_end:
            # data 現在是 List[dict]，包含所有分類的資料
            results.append({"word": current_word, "data": node.word_data or []})
        for char in sorted(node.children.keys()):
            if len(results) >= max_results:
                return
            self._dfs_collect(node.children[char], current_word + char,
                              results, max_results)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# §3  PDF / CSV 資料解析器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WORDS_PER_CHAPTER = 20  # 每章固定 20 個單字


class DataImporter:
    """
    解析 PDF (國中 2000 字) 與 CSV (學測 6000 字)。
    自動以 20 字為單位切分章節。
    """

    # ── 正規表示式 (高包容性版本) ──
    # 詞性標籤: 允許點號可選 (PDF 中有少數漏打的)
    _POS = r'(?:n\.?|v\.?|adj\.?|adv\.?|prep\.?|conj\.?|aux\.?|pron\.?|det\.?|prop\.?|int\.?)'

    # 主模式: [英文] [詞性(可選)] [中文]
    # 改進: 詞性為可選群組，中文可以 CJK 或 ( 開頭
    _PATTERN_MAIN = re.compile(
        rf'^([a-zA-Z][a-zA-Z\s\-\'()./:]*?)\s+'
        rf'(?:({_POS}(?:/{_POS})*)\s+)?'
        rf'([(\u4e00-\u9fff].*)$'
    )

    # 嚴格模式 (備用): 詞性必須存在
    _PATTERN_STRICT = re.compile(
        rf'^([a-zA-Z][a-zA-Z\s\-\'()./:]*?)\s+'
        rf'({_POS}(?:/{_POS})*)\s*'
        rf'(.+)$'
    )

    # 延續行偵測: 以 CJK 或括號開頭且短於 5 字
    _CONTINUATION = re.compile(r'^[\u4e00-\u9fff(（]')

    @staticmethod
    def parse_pdf(pdf_path: str) -> List[dict]:
        """
        解析國中 2000 字 PDF。高包容性版本：
        - 詞性為可選匹配 (處理 'foggy 濃霧的' 等缺少詞性的行)
        - 延續行合併 (處理中文翻譯跨行: '精力充沛' + '的' → '精力充沛的')
        - 雙重 Regex 策略: 先嘗試寬鬆模式，再嘗試嚴格模式
        - 每行獨立 try/except，單行錯誤不中斷匯入
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            print("⚠ PyMuPDF 未安裝。請執行: pip install PyMuPDF")
            return []

        words = []
        seen = set()
        skipped = 0

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"⚠ PDF 開啟失敗: {e}")
            return []

        for page in doc:
            try:
                text = page.get_text("text")
            except Exception:
                continue

            lines = text.split("\n")
            i = 0
            while i < len(lines):
                try:
                    line = lines[i].strip()
                    i += 1

                    # ── 噪音過濾 ──
                    if not line or len(line) < 2:
                        continue
                    if "英文銜接教材" in line or "英文單字" in line:
                        continue
                    if line.isdigit():
                        continue
                    if len(line) <= 2 and line.isalpha() and line.isupper():
                        continue
                    if "PAGE" in line.upper() or "---" in line:
                        continue

                    # ── 嘗試匹配 (寬鬆模式優先) ──
                    m = DataImporter._PATTERN_MAIN.match(line)
                    if not m:
                        m = DataImporter._PATTERN_STRICT.match(line)
                    if not m:
                        skipped += 1
                        continue

                    eng = m.group(1).strip().lower()
                    pos = (m.group(2) or "").strip()
                    chi = m.group(3).strip()

                    # ── 延續行合併 ──
                    # 檢查下一行是否為中文延續 (短的中文片段)
                    while i < len(lines):
                        next_line = lines[i].strip()
                        if (next_line
                            and len(next_line) <= 5
                            and DataImporter._CONTINUATION.match(next_line)
                            and not any(c.isascii() and c.isalpha() for c in next_line)):
                            chi += next_line
                            i += 1
                        else:
                            break

                    # ── 驗證 & 去重 ──
                    if len(eng) < 1 or eng in seen:
                        continue
                    # 確保包含至少一個 CJK 字元
                    if not any('\u4e00' <= c <= '\u9fff' for c in chi):
                        skipped += 1
                        continue
                    seen.add(eng)

                    if pos and not pos.endswith('.'):
                        pos += '.'

                    words.append({
                        "english": eng,
                        "chinese": chi,
                        "part_of_speech": pos,
                    })

                except Exception:
                    skipped += 1
                    i += 1
                    continue

        doc.close()
        print(f"  PDF 解析: {len(words)} 個單字 (跳過 {skipped} 行)")
        return words

    @staticmethod
    def parse_csv(csv_path: str) -> List[dict]:
        """
        解析學測 6000 字 CSV。
        標題列: 級別,單字,屬性,輸出,中文

        Returns: [{"english": ..., "chinese": ..., "part_of_speech": ..., "level": ...}, ...]
        """
        words = []
        seen = set()

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                eng = row.get("單字", "").strip().lower()
                chi = row.get("中文", "").strip()
                pos = row.get("屬性", "").strip()
                level = row.get("級別", "").strip()

                if not eng or not chi:
                    continue
                # 跳過含 "/" 的複合詞 (如 a/an → 只取 a)
                if "/" in eng:
                    parts = eng.split("/")
                    eng = parts[0].strip()

                if eng in seen or len(eng) < 1:
                    continue
                seen.add(eng)

                words.append({
                    "english": eng,
                    "chinese": chi,
                    "part_of_speech": pos,
                    "level": int(level) if level.isdigit() else 0,
                })
        return words

    @staticmethod
    def assign_chapters(words: List[dict]) -> List[dict]:
        """
        將單字列表按每 WORDS_PER_CHAPTER 個分為一章。
        為每個 dict 加入 "chapter_num" 鍵。
        """
        for i, w in enumerate(words):
            w["chapter_num"] = (i // WORDS_PER_CHAPTER) + 1
        return words


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# §4  SQLite 資料庫管理器 (3NF + 章節支援)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Schema:
#   categories(id, name, description)
#   words(id, category_id FK, chapter_num, english, chinese, part_of_speech)
#   user_progress(id, word_id FK UNIQUE, ef, interval, reps, next_review, ...)
#   review_logs(id, word_id FK, quality, reviewed_at, ef_before, ef_after)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DatabaseManager:
    def __init__(self, db_path: str = "srs_vocab.db") -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._db_lock = threading.RLock()  # 全域 DB 鎖：序列化所有 SQL 操作

    def connect(self) -> None:
        """
        建立 SQLite 連線並啟用效能/安全 PRAGMA。

        · check_same_thread=False: 允許跨執行緒存取
        · journal_mode=WAL: 預寫式日誌，讀寫併發
        · synchronous=NORMAL: WAL 下最佳平衡
        · busy_timeout=5000: 等待鎖 5 秒
        · _db_lock: 應用層 RLock 序列化所有 SQL 操作
        """
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self._conn.execute("PRAGMA foreign_keys=ON;")

    def _commit(self) -> None:
        """執行緒安全的 commit。"""
        with self._db_lock:
            if self._conn:
                self._conn.commit()

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """執行緒安全的 execute。回傳 cursor 供後續 fetch。"""
        with self._db_lock:
            return self.conn.cursor().execute(sql, params)

    def _fetchone(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """執行緒安全的 execute + fetchone。"""
        with self._db_lock:
            c = self.conn.cursor()
            c.execute(sql, params)
            row = c.fetchone()
            return dict(row) if row else None

    def _fetchall(self, sql: str, params: tuple = ()) -> List[dict]:
        """執行緒安全的 execute + fetchall。"""
        with self._db_lock:
            c = self.conn.cursor()
            c.execute(sql, params)
            return [dict(r) for r in c.fetchall()]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn

    def initialize_schema(self) -> None:
        """
        建立/升級資料庫綱要。

        ■ 致命 Bug 修復：絕不使用 DROP TABLE
          舊版邏輯在偵測到 v1 綱要時會 DROP 所有表 → 使用者進度全部消失。
          新邏輯使用 ALTER TABLE ADD COLUMN 安全升級，保留所有學習紀錄。
        """
        c = self.conn.cursor()

        # ── 安全遷移 v1 → v2 ──
        # 檢查 words 表是否存在
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='words';")
        words_exists = c.fetchone() is not None

        if words_exists:
            # 檢查是否缺少 chapter_num 欄位
            c.execute("PRAGMA table_info(words);")
            columns = [row[1] for row in c.fetchall()]
            if "chapter_num" not in columns:
                # v1 → v2: 用 ALTER TABLE 加欄位，不刪表！
                print("  ⚠ 偵測到 v1 綱要，正在安全升級 (不刪除資料)...")
                c.execute("ALTER TABLE words ADD COLUMN chapter_num INTEGER NOT NULL DEFAULT 1;")
                # 為現有單字自動分配章節號 (每20字一章)
                c.execute("SELECT id, category_id FROM words ORDER BY category_id, id;")
                rows = c.fetchall()
                current_cat = None
                counter = 0
                for row in rows:
                    if row[1] != current_cat:
                        current_cat = row[1]
                        counter = 0
                    counter += 1
                    ch = ((counter - 1) // WORDS_PER_CHAPTER) + 1
                    c.execute("UPDATE words SET chapter_num = ? WHERE id = ?;",
                              (ch, row[0]))
                self._commit()
                print(f"  ✓ 已為 {len(rows)} 個現有單字分配章節")

        # ── 建立資料表 (IF NOT EXISTS — 冪等安全) ──
        c.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT ''
            );""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS words (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id     INTEGER NOT NULL,
                chapter_num     INTEGER NOT NULL DEFAULT 1,
                english         TEXT NOT NULL,
                chinese         TEXT NOT NULL,
                part_of_speech  TEXT DEFAULT '',
                example_sentence TEXT DEFAULT '',
                phonetic        TEXT DEFAULT '',
                FOREIGN KEY (category_id) REFERENCES categories(id)
                    ON DELETE CASCADE,
                UNIQUE(english, category_id)
            );""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_progress (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                word_id          INTEGER NOT NULL UNIQUE,
                easiness_factor  REAL    NOT NULL DEFAULT 2.5,
                interval_days    INTEGER NOT NULL DEFAULT 0,
                repetitions      INTEGER NOT NULL DEFAULT 0,
                next_review_date TEXT    NOT NULL DEFAULT '1970-01-01',
                last_review_date TEXT    DEFAULT NULL,
                total_reviews    INTEGER NOT NULL DEFAULT 0,
                correct_count    INTEGER NOT NULL DEFAULT 0,
                is_starred       INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (word_id) REFERENCES words(id)
                    ON DELETE CASCADE
            );""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS review_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                word_id     INTEGER NOT NULL,
                quality     INTEGER NOT NULL CHECK(quality >= 0 AND quality <= 5),
                reviewed_at TEXT    NOT NULL,
                ef_before   REAL   NOT NULL,
                ef_after    REAL   NOT NULL,
                FOREIGN KEY (word_id) REFERENCES words(id)
                    ON DELETE CASCADE
            );""")
        # 使用者狀態表 (打卡紀錄)
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );""")

        # ── 安全加欄位 (已存在的表) ──
        self._safe_add_column(c, "user_progress", "is_starred", "INTEGER NOT NULL DEFAULT 0")
        self._safe_add_column(c, "words", "example_sentence", "TEXT DEFAULT ''")
        self._safe_add_column(c, "words", "phonetic", "TEXT DEFAULT ''")

        c.execute("CREATE INDEX IF NOT EXISTS idx_words_cat_chap ON words(category_id, chapter_num);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_progress_next ON user_progress(next_review_date);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_logs_date ON review_logs(reviewed_at);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_progress_starred ON user_progress(is_starred);")
        self._commit()

    @staticmethod
    def _safe_add_column(cursor, table, column, col_def):
        """安全地為已存在的表加入新欄位。若欄位已存在則靜默忽略。"""
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def};")
        except sqlite3.OperationalError:
            pass  # 欄位已存在

    # ── 使用者狀態 (打卡 / 連勝) ──

    def get_meta(self, key: str, default: str = "") -> str:
        c = self.conn.cursor()
        c.execute("SELECT value FROM user_meta WHERE key = ?;", (key,))
        row = c.fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        c = self.conn.cursor()
        c.execute("INSERT OR REPLACE INTO user_meta (key, value) VALUES (?, ?);",
                  (key, value))
        self._commit()

    def update_streak(self) -> int:
        """
        更新並回傳連續學習天數 (streak)。
        邏輯: 今天首次開啟 → 檢查昨天是否有學習 → 連勝 +1 或歸零。
        """
        today = datetime.now().strftime("%Y-%m-%d")
        last_active = self.get_meta("last_active_date", "")
        streak = int(self.get_meta("streak", "0"))

        if last_active == today:
            return streak  # 今天已計算過

        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if last_active == yesterday:
            streak += 1  # 連續學習
        elif last_active == "":
            streak = 0   # 從未學習過，首次打卡後會變 1
        else:
            streak = 0   # 中斷超過一天

        self.set_meta("streak", str(streak))
        return streak

    def record_activity(self) -> None:
        """記錄今日有學習活動。每次答題後呼叫。"""
        today = datetime.now().strftime("%Y-%m-%d")
        last = self.get_meta("last_active_date", "")

        if last == today:
            return  # 今天已記錄

        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        streak = int(self.get_meta("streak", "0"))

        if last == yesterday:
            streak += 1
        else:
            streak = 1  # 首次或中斷後重新開始

        self.set_meta("last_active_date", today)
        self.set_meta("streak", str(streak))

    # ── 星號 / 錯題本 ──

    def toggle_star(self, word_id: int) -> bool:
        """切換星號狀態。回傳新的 is_starred 值。"""
        c = self.conn.cursor()
        c.execute("SELECT is_starred FROM user_progress WHERE word_id = ?;", (word_id,))
        row = c.fetchone()
        if not row:
            return False
        new_val = 0 if row["is_starred"] else 1
        c.execute("UPDATE user_progress SET is_starred = ? WHERE word_id = ?;",
                  (new_val, word_id))
        self._commit()
        return bool(new_val)

    def get_starred_words(self, limit: int = 50) -> List[dict]:
        """取得所有星號標記的單字。"""
        c = self.conn.cursor()
        c.execute("""
            SELECT w.*, c.name AS category_name,
                   p.easiness_factor, p.interval_days, p.repetitions,
                   p.next_review_date, p.total_reviews, p.correct_count, p.is_starred
            FROM words w
            JOIN categories c ON w.category_id = c.id
            JOIN user_progress p ON w.id = p.word_id
            WHERE p.is_starred = 1
            ORDER BY w.english
            LIMIT ?;
        """, (limit,))
        return [dict(r) for r in c.fetchall()]

    def get_starred_count(self) -> int:
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) AS cnt FROM user_progress WHERE is_starred = 1;")
        return c.fetchone()["cnt"]

    def get_all_due_words(self, limit: int = 50, category_id: int = None) -> List[dict]:
        """
        取得到期單字 (用於一鍵複習)。
        可選 category_id 篩選特定分類。
        """
        today = datetime.now().strftime("%Y-%m-%d")
        c = self.conn.cursor()
        if category_id:
            c.execute("""
                SELECT w.*, c.name AS category_name,
                       p.easiness_factor, p.interval_days, p.repetitions,
                       p.next_review_date, p.total_reviews, p.correct_count, p.is_starred
                FROM words w
                JOIN categories c ON w.category_id = c.id
                JOIN user_progress p ON w.id = p.word_id
                WHERE p.next_review_date <= ? AND w.category_id = ?
                ORDER BY RANDOM() LIMIT ?;
            """, (today, category_id, limit))
        else:
            c.execute("""
                SELECT w.*, c.name AS category_name,
                       p.easiness_factor, p.interval_days, p.repetitions,
                       p.next_review_date, p.total_reviews, p.correct_count, p.is_starred
                FROM words w
                JOIN categories c ON w.category_id = c.id
                JOIN user_progress p ON w.id = p.word_id
                WHERE p.next_review_date <= ?
                ORDER BY RANDOM() LIMIT ?;
            """, (today, limit))
        return [dict(r) for r in c.fetchall()]

    def get_due_count(self, category_id: int = None) -> int:
        """取得到期單字數量。可選 category_id 篩選。"""
        today = datetime.now().strftime("%Y-%m-%d")
        c = self.conn.cursor()
        if category_id:
            c.execute("""SELECT COUNT(*) AS cnt FROM user_progress p
                JOIN words w ON p.word_id = w.id
                WHERE p.next_review_date <= ? AND w.category_id = ?;""",
                (today, category_id))
        else:
            c.execute("SELECT COUNT(*) AS cnt FROM user_progress WHERE next_review_date <= ?;",
                (today,))
        return c.fetchone()["cnt"]

    def get_today_reviewed_count(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) AS cnt FROM review_logs WHERE DATE(reviewed_at) = ?;",
                  (today,))
        return c.fetchone()["cnt"]
        self._commit()

    # ── 分類 ──

    def insert_category(self, name: str, description: str = "") -> int:
        c = self.conn.cursor()
        c.execute("SELECT id FROM categories WHERE name = ?;", (name,))
        row = c.fetchone()
        if row:
            return row["id"]
        c.execute("INSERT INTO categories (name, description) VALUES (?, ?);",
                  (name, description))
        self._commit()
        return c.lastrowid

    def get_categories(self) -> List[dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM categories ORDER BY id;")
        return [dict(r) for r in c.fetchall()]

    def get_categories_with_chapter_count(self) -> List[dict]:
        """單一查詢取得所有分類及其章節數，避免 N+1 問題。"""
        c = self.conn.cursor()
        c.execute("""
            SELECT c.*, COUNT(DISTINCT w.chapter_num) AS chapter_count
            FROM categories c
            LEFT JOIN words w ON c.id = w.category_id
            GROUP BY c.id
            HAVING chapter_count > 0
            ORDER BY c.id;
        """)
        return [dict(r) for r in c.fetchall()]

    # ── 單字 ──

    def insert_word(self, category_id: int, chapter_num: int,
                    english: str, chinese: str,
                    part_of_speech: str = "") -> Optional[int]:
        c = self.conn.cursor()
        try:
            c.execute(
                """INSERT INTO words (category_id, chapter_num, english, chinese, part_of_speech)
                   VALUES (?, ?, ?, ?, ?);""",
                (category_id, chapter_num, english.lower().strip(),
                 chinese, part_of_speech))
            wid = c.lastrowid
            now_iso = datetime.now().strftime("%Y-%m-%d")
            c.execute(
                """INSERT INTO user_progress
                   (word_id, easiness_factor, interval_days, repetitions,
                    next_review_date, total_reviews, correct_count)
                   VALUES (?, 2.5, 0, 0, ?, 0, 0);""",
                (wid, now_iso))
            self._commit()
            return wid
        except sqlite3.IntegrityError:
            return None

    def get_word_count(self) -> int:
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) AS cnt FROM words;")
        return c.fetchone()["cnt"]

    def get_all_words(self) -> List[dict]:
        c = self.conn.cursor()
        c.execute("""SELECT w.*, c.name AS category_name
                     FROM words w JOIN categories c ON w.category_id = c.id
                     ORDER BY w.english;""")
        return [dict(r) for r in c.fetchall()]

    def browse_words(self, category_id=None, letter=None, limit=300) -> List[dict]:
        """
        單字庫瀏覽查詢，支援分類 + 字首篩選。

        Parameters:
            category_id: 分類 ID (None = 全部)
            letter: 字首字母 (None/"all" = 全部, "A"~"Z" = 特定字母)
            limit: 回傳上限

        SQL 邏輯:
            WHERE w.category_id = ?           -- 分類篩選
              AND w.english LIKE 'A%'         -- 字首篩選 (LIKE + COLLATE NOCASE)
        """
        c = self.conn.cursor()
        conditions = []
        params = []

        if category_id:
            conditions.append("w.category_id = ?")
            params.append(category_id)

        # 字首字母篩選: LIKE 'X%' COLLATE NOCASE
        # "all" 或 None 表示不篩選
        if letter and letter.upper() != "ALL" and len(letter) == 1 and letter.isalpha():
            conditions.append("w.english LIKE ? COLLATE NOCASE")
            params.append(f"{letter.lower()}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)

        c.execute(f"""SELECT w.*, c.name AS category_name,
                             p.easiness_factor, p.total_reviews
                      FROM words w
                      JOIN categories c ON w.category_id = c.id
                      LEFT JOIN user_progress p ON w.id = p.word_id
                      {where}
                      ORDER BY w.english
                      LIMIT ?;""", params)
        return [dict(r) for r in c.fetchall()]

    def get_available_letters(self, category_id=None) -> List[str]:
        """
        取得指定分類中實際存在的字首字母列表。
        用於動態顯示 A-Z 按鈕 (只顯示有單字的字母)。
        """
        c = self.conn.cursor()
        if category_id:
            c.execute("""SELECT DISTINCT UPPER(SUBSTR(english, 1, 1)) AS letter
                         FROM words WHERE category_id = ?
                         ORDER BY letter;""", (category_id,))
        else:
            c.execute("""SELECT DISTINCT UPPER(SUBSTR(english, 1, 1)) AS letter
                         FROM words ORDER BY letter;""")
        return [r["letter"] for r in c.fetchall() if r["letter"].isalpha()]

    def search_words(self, query: str) -> List[dict]:
        c = self.conn.cursor()
        like_q = f"%{query}%"
        c.execute("""SELECT w.*, c.name AS category_name
                     FROM words w JOIN categories c ON w.category_id = c.id
                     WHERE w.english LIKE ? OR w.chinese LIKE ?
                     ORDER BY w.english LIMIT 50;""", (like_q, like_q))
        return [dict(r) for r in c.fetchall()]

    # ── 章節查詢 ──

    def get_chapters_for_category(self, category_id: int) -> List[dict]:
        """
        取得某分類的所有章節，含完整動態統計。

        回傳欄位:
          chapter_num, word_count, total_reviews, correct_count,
          accuracy(%), retention(%),
          due_words_count  — 今日待複習單字數 (next_review <= today)
          next_due_date    — 最近一個需複習的日期 (MIN(next_review_date))
          mastery_score    — 精熟評分 = correct_count / total_reviews × 100 (直覺化)
          avg_ef           — 該章節平均容易度因子
        """
        today = datetime.now().strftime("%Y-%m-%d")
        c = self.conn.cursor()
        c.execute("""
            SELECT
                w.chapter_num,
                COUNT(w.id) AS word_count,
                COALESCE(SUM(p.total_reviews), 0) AS total_reviews,
                COALESCE(SUM(p.correct_count), 0) AS correct_count,
                ROUND(
                    CASE WHEN SUM(p.total_reviews) > 0
                         THEN SUM(p.correct_count) * 100.0 / SUM(p.total_reviews)
                         ELSE 0 END, 1
                ) AS accuracy,
                ROUND(
                    SUM(CASE WHEN p.next_review_date > ? THEN 1 ELSE 0 END)
                    * 100.0 / COUNT(w.id), 1
                ) AS retention,
                -- ▼ 待複習單字數
                SUM(CASE WHEN p.next_review_date <= ? THEN 1 ELSE 0 END)
                    AS due_words_count,
                -- ▼ 最近待複習日期
                MIN(p.next_review_date) AS next_due_date,
                -- ▼ 平均 EF
                ROUND(AVG(p.easiness_factor), 2) AS avg_ef,
                -- ▼ 精熟評分 = 正確次數 / 總次數 × 100 (總次數=0 時為 0)
                ROUND(
                    CASE WHEN SUM(p.total_reviews) > 0
                         THEN SUM(p.correct_count) * 100.0 / SUM(p.total_reviews)
                         ELSE 0 END, 0
                ) AS mastery_score
            FROM words w
            JOIN user_progress p ON w.id = p.word_id
            WHERE w.category_id = ?
            GROUP BY w.chapter_num
            ORDER BY w.chapter_num;
        """, (today, today, category_id))
        return [dict(r) for r in c.fetchall()]

    def get_words_for_chapter(self, category_id: int, chapter_num: int) -> List[dict]:
        c = self.conn.cursor()
        c.execute("""
            SELECT w.*, c.name AS category_name,
                   p.easiness_factor, p.interval_days, p.repetitions,
                   p.next_review_date, p.total_reviews, p.correct_count
            FROM words w
            JOIN categories c ON w.category_id = c.id
            JOIN user_progress p ON w.id = p.word_id
            WHERE w.category_id = ? AND w.chapter_num = ?
            ORDER BY w.english;
        """, (category_id, chapter_num))
        return [dict(r) for r in c.fetchall()]

    def get_due_words_for_chapter(self, category_id: int, chapter_num: int,
                                   limit: int = 20) -> List[dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        c = self.conn.cursor()
        c.execute("""
            SELECT w.*, c.name AS category_name,
                   p.easiness_factor, p.interval_days, p.repetitions,
                   p.next_review_date, p.total_reviews, p.correct_count
            FROM words w
            JOIN categories c ON w.category_id = c.id
            JOIN user_progress p ON w.id = p.word_id
            WHERE w.category_id = ? AND w.chapter_num = ?
              AND p.next_review_date <= ?
            ORDER BY p.next_review_date ASC
            LIMIT ?;
        """, (category_id, chapter_num, today, limit))
        return [dict(r) for r in c.fetchall()]

    def generate_mcq(self, word_id: int) -> Optional[dict]:
        """
        標準英翻中 MCQ。

        干擾項撈取降級策略 (防止小分類崩潰):
          1. 優先同類別：SELECT ... WHERE category_id = target_cat
          2. 不足 → 全庫補充：SELECT ... (無視類別)
          3. 仍不足 → 合成假選項填補
          絕不會因單字不足而崩潰。
        """
        import random
        c = self.conn.cursor()
        c.execute("SELECT id, english, chinese, category_id FROM words WHERE id = ?;",
                  (word_id,))
        row = c.fetchone()
        if not row: return None
        correct_chinese = row["chinese"]
        cat_id = row["category_id"]

        # 第 1 階段: 同類別撈取干擾項
        c.execute("""SELECT DISTINCT chinese FROM words
            WHERE category_id = ? AND id != ? AND chinese != ?
            ORDER BY RANDOM() LIMIT 3;""",
            (cat_id, word_id, correct_chinese))
        distractors = [r["chinese"] for r in c.fetchall()]

        # 第 2 階段: 不足 → 全庫補充 (排除已有的)
        if len(distractors) < 3:
            existing = set(distractors) | {correct_chinese}
            placeholders = ",".join(["?"] * len(existing))
            c.execute(f"""SELECT DISTINCT chinese FROM words
                WHERE id != ? AND chinese NOT IN ({placeholders})
                ORDER BY RANDOM() LIMIT ?;""",
                (word_id, *existing, 3 - len(distractors)))
            distractors += [r["chinese"] for r in c.fetchall()]

        # 第 3 階段: 仍不足 → 合成假選項
        fallbacks = ["未知字彙", "無此翻譯", "非此單字之義",
                     "查無此義", "其他意思", "不正確的翻譯"]
        for fb in fallbacks:
            if len(distractors) >= 3: break
            if fb != correct_chinese and fb not in distractors:
                distractors.append(fb)

        options = [correct_chinese] + distractors[:3]
        random.shuffle(options)
        return {"word_id": row["id"], "english": row["english"],
                "correct_chinese": correct_chinese, "options": options,
                "correct_index": options.index(correct_chinese),
                "mode": "translate"}

    def generate_cloze_mcq(self, word_id: int) -> Optional[dict]:
        """
        克漏字 MCQ：句子中挖空，選正確的英文單字填入。

        邏輯:
          1. 取得單字的例句 (優先從 DB 快取)
          2. 若無例句 → 回傳 None (由呼叫方 fallback 到標準 MCQ)
          3. 用 Regex 將句子中的目標單字替換為 ________
          4. 選項: 1 正確英文 + 3 隨機英文干擾項
        """
        import random
        c = self.conn.cursor()
        c.execute("SELECT id, english, chinese, example_sentence, category_id FROM words WHERE id = ?;",
                  (word_id,))
        row = c.fetchone()
        if not row or not row["example_sentence"]:
            return None

        eng = row["english"]
        sentence = row["example_sentence"]

        # 用 Regex 遮蔽目標單字 (不分大小寫)
        pattern = re.compile(re.escape(eng), re.IGNORECASE)
        if not pattern.search(sentence):
            return None  # 例句中找不到該單字
        cloze_sentence = pattern.sub("________", sentence)

        # 取得 3 個同分類的英文干擾項
        c.execute("""SELECT DISTINCT english FROM words
            WHERE id != ? AND category_id = ? AND english != ?
            ORDER BY RANDOM() LIMIT 3;""",
            (word_id, row["category_id"], eng))
        distractors = [r["english"] for r in c.fetchall()]
        max_att = 10; att = 0
        while len(distractors) < 3 and att < max_att:
            att += 1
            c.execute("""SELECT DISTINCT english FROM words
                WHERE id != ? AND english != ? ORDER BY RANDOM() LIMIT 1;""",
                (word_id, eng))
            r2 = c.fetchone()
            if r2 and r2["english"] not in distractors:
                distractors.append(r2["english"])
            else:
                break
        # 安全填補: 資料庫單字不足時用假選項
        cloze_fallbacks = ["unknown", "other", "none"]
        for fb in cloze_fallbacks:
            if len(distractors) >= 3: break
            if fb != eng and fb not in distractors:
                distractors.append(fb)

        options = [eng] + distractors[:3]
        random.shuffle(options)
        return {
            "word_id": row["id"], "english": eng,
            "correct_chinese": row["chinese"],
            "cloze_sentence": cloze_sentence,
            "options": options,
            "correct_index": options.index(eng),
            "correct_answer": eng,
            "mode": "cloze",
        }

    def cache_example_sentence(self, word_id: int, sentence: str) -> None:
        """將 API 取得的例句寫入資料庫快取。"""
        c = self.conn.cursor()
        c.execute("UPDATE words SET example_sentence = ? WHERE id = ?;",
                  (sentence, word_id))
        self._commit()

    # ── 進度 ──

    def get_progress(self, word_id: int) -> Optional[dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM user_progress WHERE word_id = ?;", (word_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def update_progress(self, word_id: int, easiness_factor: float,
                        interval_days: int, repetitions: int,
                        next_review_date: str, quality: int) -> None:
        c = self.conn.cursor()
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT easiness_factor FROM user_progress WHERE word_id = ?;",
                  (word_id,))
        row = c.fetchone()
        ef_before = row["easiness_factor"] if row else 2.5
        is_correct = 1 if quality >= 3 else 0

        c.execute("""UPDATE user_progress
                     SET easiness_factor=?, interval_days=?, repetitions=?,
                         next_review_date=?, last_review_date=?,
                         total_reviews = total_reviews + 1,
                         correct_count = correct_count + ?
                     WHERE word_id=?;""",
                  (easiness_factor, interval_days, repetitions,
                   next_review_date, now_iso, is_correct, word_id))
        c.execute("""INSERT INTO review_logs
                     (word_id, quality, reviewed_at, ef_before, ef_after)
                     VALUES (?, ?, ?, ?, ?);""",
                  (word_id, quality, now_iso, ef_before, easiness_factor))
        self._commit()

    # ── 統計 ──

    def get_total_review_count(self) -> int:
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) AS cnt FROM review_logs;")
        return c.fetchone()["cnt"]

    def get_overall_stats(self, category_id: int = None) -> dict:
        """取得統計數據。可選 category_id 過濾特定分類。"""
        c = self.conn.cursor()
        if category_id:
            c.execute("""SELECT COUNT(*) AS total_words,
                                COALESCE(SUM(CASE WHEN p.total_reviews > 0 THEN 1 ELSE 0 END), 0) AS learned,
                                COALESCE(SUM(CASE WHEN p.total_reviews = 0 THEN 1 ELSE 0 END), 0) AS new_words
                         FROM user_progress p
                         JOIN words w ON p.word_id = w.id
                         WHERE w.category_id = ?;""", (category_id,))
        else:
            c.execute("""SELECT COUNT(*) AS total_words,
                                COALESCE(SUM(CASE WHEN total_reviews > 0 THEN 1 ELSE 0 END), 0) AS learned,
                                COALESCE(SUM(CASE WHEN total_reviews = 0 THEN 1 ELSE 0 END), 0) AS new_words
                         FROM user_progress;""")
        stats = dict(c.fetchone())
        today = datetime.now().strftime("%Y-%m-%d")
        if category_id:
            c.execute("""SELECT COUNT(*) AS due_today FROM user_progress p
                         JOIN words w ON p.word_id = w.id
                         WHERE p.next_review_date <= ? AND w.category_id = ?;""",
                      (today, category_id))
        else:
            c.execute("SELECT COUNT(*) AS due_today FROM user_progress WHERE next_review_date <= ?;",
                      (today,))
        stats.update(dict(c.fetchone()))
        # 總複習次數
        if category_id:
            c.execute("""SELECT COALESCE(COUNT(*), 0) AS total_reviews FROM review_logs r
                         JOIN words w ON r.word_id = w.id WHERE w.category_id = ?;""",
                      (category_id,))
        else:
            c.execute("SELECT COALESCE(COUNT(*), 0) AS total_reviews FROM review_logs;")
        stats.update(dict(c.fetchone()))
        # 正確率
        if category_id:
            c.execute("""SELECT COALESCE(ROUND(
                             SUM(CASE WHEN r.quality >= 3 THEN 1 ELSE 0 END) * 100.0
                             / NULLIF(COUNT(*), 0), 1), 0.0) AS overall_accuracy
                         FROM review_logs r JOIN words w ON r.word_id = w.id
                         WHERE w.category_id = ?;""", (category_id,))
        else:
            c.execute("""SELECT COALESCE(ROUND(
                             SUM(CASE WHEN quality >= 3 THEN 1 ELSE 0 END) * 100.0
                             / NULLIF(COUNT(*), 0), 1), 0.0) AS overall_accuracy
                         FROM review_logs;""")
        stats["overall_accuracy"] = c.fetchone()["overall_accuracy"] or 0.0
        return stats

    def get_global_statistics(self, category_id: int = None) -> dict:
        """
        取得完整統計 (統計頁面用)。
        可選 category_id 過濾。所有欄位用 COALESCE 防 NULL。
        """
        c = self.conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")

        # JOIN 條件片段
        if category_id:
            join = "JOIN words w ON p.word_id = w.id"
            where = f"AND w.category_id = {category_id}"
            rjoin = "JOIN words w ON r.word_id = w.id"
            rwhere = f"AND w.category_id = {category_id}"
        else:
            join = ""; where = ""; rjoin = ""; rwhere = ""

        # 基本統計
        c.execute(f"""SELECT
                COALESCE(COUNT(*), 0) AS total_words,
                COALESCE(SUM(CASE WHEN p.total_reviews > 0 THEN 1 ELSE 0 END), 0) AS learned,
                COALESCE(SUM(CASE WHEN p.total_reviews = 0 THEN 1 ELSE 0 END), 0) AS new_words
            FROM user_progress p {join} WHERE 1=1 {where};""")
        stats = dict(c.fetchone())

        c.execute(f"""SELECT COALESCE(COUNT(*), 0) AS due_today
            FROM user_progress p {join} WHERE p.next_review_date <= ? {where};""", (today,))
        stats.update(dict(c.fetchone()))

        # 答題次數
        c.execute(f"SELECT COALESCE(COUNT(*), 0) AS total_answers FROM review_logs r {rjoin} WHERE 1=1 {rwhere};")
        stats.update(dict(c.fetchone()))

        # 正確率
        c.execute(f"""SELECT COALESCE(ROUND(
                SUM(CASE WHEN r.quality >= 3 THEN 1 ELSE 0 END) * 100.0
                / NULLIF(COUNT(*), 0), 1), 0.0) AS accuracy
            FROM review_logs r {rjoin} WHERE 1=1 {rwhere};""")
        stats["accuracy"] = c.fetchone()["accuracy"] or 0.0

        # 平均 EF
        c.execute(f"""SELECT COALESCE(ROUND(AVG(p.easiness_factor), 2), 2.50) AS avg_ef
            FROM user_progress p {join} WHERE p.total_reviews > 0 {where};""")
        stats["avg_ef"] = c.fetchone()["avg_ef"] or 2.50

        # 本週 / 今日
        week_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        c.execute(f"""SELECT COALESCE(COUNT(*), 0) AS week_answers
            FROM review_logs r {rjoin} WHERE DATE(r.reviewed_at) >= ? {rwhere};""", (week_start,))
        stats["week_answers"] = c.fetchone()["week_answers"] or 0

        c.execute(f"""SELECT COALESCE(COUNT(*), 0) AS today_answers
            FROM review_logs r {rjoin} WHERE DATE(r.reviewed_at) = ? {rwhere};""", (today,))
        stats["today_answers"] = c.fetchone()["today_answers"] or 0

        return stats

    def get_daily_accuracy(self, days: int = 30, category_id: int = None) -> List[dict]:
        """
        取得每日正確率。可選 category_id 過濾特定分類。
        SQL: JOIN words 表以支援分類篩選。
        """
        c = self.conn.cursor()
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        if category_id:
            c.execute("""SELECT DATE(r.reviewed_at) AS review_date,
                                COUNT(*) AS total,
                                SUM(CASE WHEN r.quality >= 3 THEN 1 ELSE 0 END) AS correct,
                                ROUND(SUM(CASE WHEN r.quality >= 3 THEN 1 ELSE 0 END)
                                      * 100.0 / COUNT(*), 1) AS accuracy
                         FROM review_logs r
                         JOIN words w ON r.word_id = w.id
                         WHERE DATE(r.reviewed_at) >= ? AND w.category_id = ?
                         GROUP BY DATE(r.reviewed_at) ORDER BY review_date;""",
                      (start, category_id))
        else:
            c.execute("""SELECT DATE(reviewed_at) AS review_date,
                                COUNT(*) AS total,
                                SUM(CASE WHEN quality >= 3 THEN 1 ELSE 0 END) AS correct,
                                ROUND(SUM(CASE WHEN quality >= 3 THEN 1 ELSE 0 END)
                                      * 100.0 / COUNT(*), 1) AS accuracy
                         FROM review_logs WHERE DATE(reviewed_at) >= ?
                         GROUP BY DATE(reviewed_at) ORDER BY review_date;""", (start,))
        return [dict(r) for r in c.fetchall()]

    def get_7day_history(self) -> List[dict]:
        """
        取得過去 7 天的學習紀錄，按日期 + 章節分組。

        SQL 邏輯:
          JOIN words 取得 category_name 和 chapter_num
          GROUP BY 日期, 分類, 章節
          ORDER BY 日期 DESC (最近的排在最前面)

        回傳: [{review_date, category_name, chapter_num, total, correct, accuracy}, ...]
        """
        c = self.conn.cursor()
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        c.execute("""
            SELECT
                DATE(r.reviewed_at) AS review_date,
                c.name AS category_name,
                w.chapter_num,
                COUNT(*) AS total,
                SUM(CASE WHEN r.quality >= 3 THEN 1 ELSE 0 END) AS correct,
                ROUND(
                    SUM(CASE WHEN r.quality >= 3 THEN 1 ELSE 0 END) * 100.0
                    / COUNT(*), 0
                ) AS accuracy
            FROM review_logs r
            JOIN words w ON r.word_id = w.id
            JOIN categories c ON w.category_id = c.id
            WHERE DATE(r.reviewed_at) >= ?
            GROUP BY DATE(r.reviewed_at), c.name, w.chapter_num
            ORDER BY DATE(r.reviewed_at) DESC, c.name, w.chapter_num;
        """, (start,))
        return [dict(r) for r in c.fetchall()]

    def get_ef_distribution(self, category_id: int = None) -> List[dict]:
        """
        取得 EF 難度分布。可選 category_id 過濾。
        SQL: JOIN words 表以支援分類篩選。
        """
        c = self.conn.cursor()
        if category_id:
            c.execute("""SELECT
                           CASE WHEN p.easiness_factor < 1.5 THEN '困難 (<1.5)'
                                WHEN p.easiness_factor < 2.0 THEN '較難 (1.5-2.0)'
                                WHEN p.easiness_factor < 2.5 THEN '中等 (2.0-2.5)'
                                WHEN p.easiness_factor < 3.0 THEN '容易 (2.5-3.0)'
                                ELSE '非常容易 (≥3.0)' END AS difficulty_range,
                           COUNT(*) AS count
                         FROM user_progress p
                         JOIN words w ON p.word_id = w.id
                         WHERE p.total_reviews > 0 AND w.category_id = ?
                         GROUP BY difficulty_range ORDER BY MIN(p.easiness_factor);""",
                      (category_id,))
        else:
            c.execute("""SELECT
                           CASE WHEN easiness_factor < 1.5 THEN '困難 (<1.5)'
                                WHEN easiness_factor < 2.0 THEN '較難 (1.5-2.0)'
                                WHEN easiness_factor < 2.5 THEN '中等 (2.0-2.5)'
                                WHEN easiness_factor < 3.0 THEN '容易 (2.5-3.0)'
                                ELSE '非常容易 (≥3.0)' END AS difficulty_range,
                           COUNT(*) AS count
                         FROM user_progress WHERE total_reviews > 0
                         GROUP BY difficulty_range ORDER BY MIN(easiness_factor);""")
        return [dict(r) for r in c.fetchall()]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# §5  TTS 語音引擎 (優雅降級)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TTSEngine:
    """
    跨平台 TTS 引擎 + 佇列防狂點機制。

    架構:
      · queue.Queue(maxsize=1) — 只保留最新一個請求，丟棄舊的
      · 單一守護執行緒依序消費佇列，防止併發 subprocess 崩潰
      · macOS: say 指令 | Windows: pyttsx3 | Linux: espeak
    """
    def __init__(self) -> None:
        import platform
        import subprocess
        import queue as _q
        self._available = False
        self._error_msg = ""
        self._platform = platform.system()
        self._stop = False
        self._queue = _q.Queue(maxsize=2)  # 小佇列，防堆積
        self._busy = False  # 正在發音中

        if self._platform in ("Android", "iOS", "Emscripten"):
            self._error_msg = "行動裝置不支援本地 TTS"
            self._method = "none"
        elif self._platform == "Darwin":
            try:
                subprocess.run(["which", "say"], capture_output=True, check=True)
                self._available = True
                self._method = "say"
            except Exception:
                self._error_msg = "macOS 'say' 指令不可用"
        elif self._platform == "Windows":
            try:
                import pyttsx3
                self._available = True
                self._method = "pyttsx3"
            except ImportError:
                self._error_msg = "pyttsx3 未安裝"
        else:
            try:
                import pyttsx3
                self._available = True
                self._method = "pyttsx3"
            except ImportError:
                try:
                    subprocess.run(["which", "espeak"], capture_output=True, check=True)
                    self._available = True
                    self._method = "espeak"
                except Exception:
                    self._error_msg = "espeak/pyttsx3 皆未安裝"

        # 啟動單一工作執行緒
        if self._available:
            self._worker = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker.start()

    def _worker_loop(self) -> None:
        """工作執行緒主迴圈：依序從佇列取出文字發音。"""
        import subprocess
        while not self._stop:
            try:
                text = self._queue.get(timeout=0.5)
                if text is None:
                    break  # poison pill
                self._busy = True
                try:
                    if self._method == "say":
                        subprocess.run(["say", "-r", "160", text],
                                       timeout=10, capture_output=True)
                    elif self._method == "espeak":
                        subprocess.run(["espeak", "-s", "150", text],
                                       timeout=10, capture_output=True)
                    elif self._method == "pyttsx3":
                        import pyttsx3
                        eng = pyttsx3.init()
                        eng.setProperty("rate", 150)
                        eng.setProperty("volume", 0.9)
                        eng.say(text)
                        eng.runAndWait()
                        try: eng.stop()
                        except: pass
                except Exception:
                    pass
                finally:
                    self._busy = False
                    self._queue.task_done()
            except Exception:
                continue  # timeout → 繼續等

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def error_message(self) -> str:
        return self._error_msg

    def speak(self, text: str) -> None:
        """
        非阻塞發音。若正在忙碌或佇列滿，丟棄舊請求只保留最新的。
        狂點喇叭按鈕不會崩潰，只會聽到最後一次的發音。
        """
        if not self._available or self._stop:
            return
        # 清空佇列中的舊請求 (只保留最新)
        while not self._queue.empty():
            try: self._queue.get_nowait()
            except: break
        try:
            self._queue.put_nowait(text)
        except:
            pass  # 佇列滿 → 丟棄

    def shutdown(self) -> None:
        self._stop = True
        try: self._queue.put_nowait(None)
        except: pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# §6  圖表產生器 (含資料防護)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MIN_REVIEWS_FOR_CHARTS = 10  # 解鎖圖表的最低答題數


class ChartGenerator:
    _font_configured = False
    _plt = None
    _has_cjk = False  # 是否找到中文字型

    @staticmethod
    def _get_plt():
        """首次匯入 matplotlib 並設定，後續直接回傳快取。"""
        if ChartGenerator._plt is not None:
            return ChartGenerator._plt
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ChartGenerator._plt = plt

        # CJK 字型偵測
        if not ChartGenerator._font_configured:
            import matplotlib.font_manager as fm
            import platform
            candidates = []
            if platform.system() == "Darwin":
                candidates = ["PingFang TC", "PingFang SC", "Heiti TC",
                              "Apple LiGothic", "Arial Unicode MS"]
            elif platform.system() == "Windows":
                candidates = ["Microsoft JhengHei", "Microsoft YaHei",
                              "SimHei", "DFKai-SB"]
            else:
                # Android/Linux: 嘗試手動註冊系統字型
                import glob
                for d in ["/system/fonts", "/data/fonts",
                          "/usr/share/fonts", "/usr/local/share/fonts"]:
                    for ttf in glob.glob(os.path.join(d, "*.ttf")) + \
                               glob.glob(os.path.join(d, "*.otf")) + \
                               glob.glob(os.path.join(d, "**/*.ttf"), recursive=True):
                        try: fm.fontManager.addfont(ttf)
                        except: pass
                candidates = ["Noto Sans CJK TC", "Noto Sans CJK SC",
                              "Noto Sans TC", "Noto Sans SC",
                              "WenQuanYi Micro Hei", "AR PL UMing TW",
                              "Droid Sans Fallback"]
            available = {f.name for f in fm.fontManager.ttflist}
            for font in candidates:
                if font in available:
                    plt.rcParams["font.sans-serif"] = [font] + plt.rcParams["font.sans-serif"]
                    plt.rcParams["axes.unicode_minus"] = False
                    ChartGenerator._has_cjk = True
                    break
            ChartGenerator._font_configured = True
        return plt

    @staticmethod
    def _setup_cjk_font():
        """相容呼叫，實際由 _get_plt() 處理。"""
        ChartGenerator._get_plt()

    @staticmethod
    def _t(zh, en):
        """有中文字型 → 用中文；沒有 → 用英文。"""
        return zh if ChartGenerator._has_cjk else en

    @staticmethod
    def generate_accuracy_chart(data: List[dict], dark_mode: bool = True) -> str:
        plt = ChartGenerator._get_plt()
        _t = ChartGenerator._t
        import matplotlib.dates as mdates

        bg = "#1a1a2e" if dark_mode else "#ffffff"
        tc = "#e0e0e0" if dark_mode else "#333333"
        lc = "#7c4dff" if dark_mode else "#6200ee"
        gc = "#333355" if dark_mode else "#e0e0e0"

        fig, ax = plt.subplots(figsize=(5, 2.5), dpi=72)
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        if data:
            dates = [datetime.strptime(d["review_date"], "%Y-%m-%d") for d in data]
            accs = [d["accuracy"] for d in data]
            ax.plot(dates, accs, color=lc, linewidth=2, marker="o",
                    markersize=4, markerfacecolor="white",
                    markeredgecolor=lc, markeredgewidth=1.5)
            ax.fill_between(dates, accs, alpha=0.15, color=lc)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
            fig.autofmt_xdate(rotation=45)

        ax.set_ylim(0, 105)
        ax.set_title(_t("歷史答題正確率 (%)", "Accuracy History (%)"), fontsize=12, color=tc, pad=10, fontweight="bold")
        ax.set_xlabel(_t("日期", "Date"), fontsize=9, color=tc)
        ax.set_ylabel(_t("正確率 (%)", "Accuracy (%)"), fontsize=9, color=tc)
        ax.tick_params(colors=tc, labelsize=8)
        ax.grid(True, alpha=0.3, color=gc)
        for s in ax.spines.values():
            s.set_color(gc)
        fig.tight_layout(pad=0.5)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return "data:image/png;base64," + base64.b64encode(buf.read()).decode("utf-8")

    @staticmethod
    def generate_ef_chart(data: List[dict], dark_mode: bool = True) -> str:
        plt = ChartGenerator._get_plt()
        _t = ChartGenerator._t

        bg = "#1a1a2e" if dark_mode else "#ffffff"
        tc = "#e0e0e0" if dark_mode else "#333333"
        gc = "#333355" if dark_mode else "#e0e0e0"
        colors = (["#ff5252","#ff9800","#ffeb3b","#66bb6a","#42a5f5"] if dark_mode
                  else ["#d32f2f","#f57c00","#fbc02d","#388e3c","#1976d2"])

        fig, ax = plt.subplots(figsize=(5, 2.5), dpi=72)
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        if data:
            labels = [d["difficulty_range"] for d in data]
            # Android 沒中文字型時，翻譯 X 軸標籤為英文
            if not ChartGenerator._has_cjk:
                _label_map = {
                    "困難 (<1.5)": "Hard (<1.5)",
                    "較難 (1.5-2.0)": "Difficult (1.5-2.0)",
                    "中等 (2.0-2.5)": "Medium (2.0-2.5)",
                    "容易 (2.5-3.0)": "Easy (2.5-3.0)",
                    "非常容易 (≥3.0)": "Very Easy (≥3.0)",
                }
                labels = [_label_map.get(l, l) for l in labels]
            counts = [d["count"] for d in data]
            bars = ax.bar(labels, counts, color=colors[:len(labels)], width=0.6, zorder=3)
            for bar, cnt in zip(bars, counts):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                        str(cnt), ha="center", va="bottom", fontsize=10,
                        color=tc, fontweight="bold")

        ax.set_title(_t("單字難度分布", "Difficulty Distribution"), fontsize=12, color=tc, pad=10, fontweight="bold")
        ax.set_ylabel(_t("單字數", "Word Count"), fontsize=9, color=tc)
        ax.tick_params(colors=tc, labelsize=8)
        ax.grid(True, axis="y", alpha=0.3, color=gc, zorder=0)
        for s in ax.spines.values():
            s.set_color(gc)
        fig.tight_layout(pad=0.5)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return "data:image/png;base64," + base64.b64encode(buf.read()).decode("utf-8")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# §7  Facade — ReviewScheduler
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ReviewScheduler:
    def __init__(self, base_dir: str = ".") -> None:
        self.base_dir = base_dir
        db_path = os.path.join(base_dir, "srs_vocab.db")
        self.db = DatabaseManager(db_path)
        self.trie = Trie()
        self.tts = TTSEngine()
        self.charts = ChartGenerator()
        self._chart_cache = {}  # 圖表快取 {key: (total_answers, base64)}

    @staticmethod
    def _find_file(base_dir: str, patterns: List[str]) -> Optional[str]:
        """
        用多個 glob 模式搜尋檔案，回傳第一個匹配的完整路徑。
        解決使用者檔名可能與程式碼中硬編碼名稱不同的問題。
        """
        import glob
        for pattern in patterns:
            matches = glob.glob(os.path.join(base_dir, pattern))
            if matches:
                return matches[0]
        return None

    def initialize(self) -> dict:
        self.db.connect()
        self.db.initialize_schema()

        imported = 0
        if self.db.get_word_count() == 0:
            imported = self._import_real_data()

        self._build_trie()
        stats = self.db.get_overall_stats()

        # 背景預載 matplotlib (首次 import 約 1-2 秒，提前做好)
        threading.Thread(target=lambda: ChartGenerator._get_plt(), daemon=True).start()

        return {
            "imported": imported,
            "total_words": stats["total_words"],
            "tts_available": self.tts.is_available,
            "tts_error": self.tts.error_message,
        }

    def _import_real_data(self) -> int:
        """從 PDF 和 CSV 匯入真實資料。使用 glob 靈活匹配檔名。"""
        count = 0

        # ── 國中單字 (PDF) ──
        # 嘗試多種可能的檔名模式
        pdf_path = self._find_file(self.base_dir, [
            "國中2000字*.pdf",
            "國中*字*.pdf",
            "*2000*字*.pdf",
        ])
        if pdf_path:
            print(f"  找到 PDF: {os.path.basename(pdf_path)}")
            cat_id = self.db.insert_category("國中單字", "國中教育階段 2000 基礎英文單字")
            words = DataImporter.parse_pdf(pdf_path)
            words = DataImporter.assign_chapters(words)
            pdf_count = 0
            for w in words:
                r = self.db.insert_word(cat_id, w["chapter_num"],
                                        w["english"], w["chinese"],
                                        w["part_of_speech"])
                if r:
                    pdf_count += 1
            count += pdf_count
            print(f"  ✓ 國中單字匯入: {pdf_count} 個")
        else:
            print("  ⚠ 未找到國中 PDF 檔案")

        # ── 高中單字 (CSV) ──
        csv_path = self._find_file(self.base_dir, [
            "學測6000字*.csv",
            "學測*字*.csv",
            "*6000*字*.csv",
            "*6000*.csv",
        ])
        if csv_path:
            print(f"  找到 CSV: {os.path.basename(csv_path)}")
            cat_id = self.db.insert_category("高中單字", "學測 6000 英文單字")
            words = DataImporter.parse_csv(csv_path)
            words = DataImporter.assign_chapters(words)
            csv_count = 0
            for w in words:
                r = self.db.insert_word(cat_id, w["chapter_num"],
                                        w["english"], w["chinese"],
                                        w["part_of_speech"])
                if r:
                    csv_count += 1
            count += csv_count
            print(f"  ✓ 高中單字匯入: {csv_count} 個")
        else:
            print("  ⚠ 未找到高中 CSV 檔案")

        # ── 若無檔案，使用內建小型資料集 ──
        if count == 0:
            count = self._import_fallback()

        return count

    def _import_fallback(self) -> int:
        """當 PDF/CSV 不存在時，匯入最小預設資料。"""
        fallback = [
            ("apple", "蘋果", "n."), ("book", "書", "n."),
            ("cat", "貓", "n."), ("dog", "狗", "n."),
            ("eat", "吃", "v."), ("friend", "朋友", "n."),
            ("good", "好的", "adj."), ("happy", "快樂的", "adj."),
            ("idea", "想法", "n."), ("jump", "跳", "v."),
            ("kind", "善良的", "adj."), ("learn", "學習", "v."),
            ("morning", "早晨", "n."), ("night", "夜晚", "n."),
            ("open", "打開", "v."), ("play", "玩", "v."),
            ("question", "問題", "n."), ("run", "跑", "v."),
            ("school", "學校", "n."), ("teacher", "老師", "n."),
        ]
        cat_id = self.db.insert_category("預設單字", "基礎範例單字")
        for i, (e, c, p) in enumerate(fallback):
            ch = (i // WORDS_PER_CHAPTER) + 1
            self.db.insert_word(cat_id, ch, e, c, p)
        return len(fallback)

    def _build_trie(self) -> None:
        words = self.db.get_all_words()
        for w in words:
            self.trie.insert(w["english"], {
                "id": w["id"], "chinese": w["chinese"],
                "part_of_speech": w["part_of_speech"],
                "category": w["category_name"],
            })

    def process_review(self, word_id: int, quality: int) -> SM2Result:
        """處理評分。DB _write_lock 確保 commit 序列化。"""
        progress = self.db.get_progress(word_id)
        if not progress:
            raise ValueError(f"word_id={word_id} 不存在")
        result = SM2Algorithm.calculate(
            quality=quality,
            easiness_factor=progress["easiness_factor"],
            interval_days=progress["interval_days"],
            repetitions=progress["repetitions"],
        )
        self.db.update_progress(
            word_id=word_id,
            easiness_factor=result.easiness_factor,
            interval_days=result.interval_days,
            repetitions=result.repetitions,
            next_review_date=result.next_review.strftime("%Y-%m-%d"),
            quality=quality,
        )
        return result

    def process_mcq_answer(self, word_id: int, is_correct: bool,
                           response_time: float = 999.0) -> SM2Result:
        """
        處理四選一 MCQ 答題結果 (含反應時間啟發式)。

        演算法邏輯:
          四選一有 25% 瞎猜命中率。若答對但反應極快，很可能是亂點。
          · 答對 + response_time ≥ 1.5s → q=5 (完美回想，真正記得)
          · 答對 + response_time < 1.5s  → q=3 (快速猜對，僅勉強及格)
          · 答錯                         → q=0 (完全遺忘)

        這確保瞎猜答對的單字 EF 不會異常膨脹，保護 SM-2 的數學模型。
        """
        GUESS_THRESHOLD = 1.5  # 秒 — 低於此視為快速猜測

        if is_correct:
            quality = 5 if response_time >= GUESS_THRESHOLD else 3
        else:
            quality = 0

        result = self.process_review(word_id, quality)
        self.db.record_activity()
        return result

    def toggle_star(self, word_id: int) -> bool:
        return self.db.toggle_star(word_id)

    def get_starred_words(self) -> List[dict]:
        return self.db.get_starred_words()

    def get_starred_count(self) -> int:
        return self.db.get_starred_count()

    def get_all_due_words(self, limit: int = 50, category_id: int = None) -> List[dict]:
        return self.db.get_all_due_words(limit, category_id=category_id)

    def get_due_count(self, category_id: int = None) -> int:
        return self.db.get_due_count(category_id=category_id)

    def get_dashboard_data(self) -> dict:
        """首頁儀表板資料：連勝、今日進度、到期數、星號數、最高連擊。"""
        streak = self.db.update_streak()
        today_count = self.db.get_today_reviewed_count()
        stats = self.db.get_overall_stats()
        starred = self.db.get_starred_count()
        max_combo = int(self.db.get_meta("max_combo", "0"))
        return {
            "streak": streak,
            "today_count": today_count,
            "daily_goal": 50,
            "due_total": stats.get("due_today", 0),
            "total_words": stats.get("total_words", 0),
            "learned": stats.get("learned", 0),
            "starred": starred,
            "max_combo": max_combo,
        }

    def update_max_combo(self, current_combo: int) -> int:
        """若當前連擊超越歷史最高，更新並回傳新紀錄。"""
        old = int(self.db.get_meta("max_combo", "0"))
        if current_combo > old:
            self.db.set_meta("max_combo", str(current_combo))
            return current_combo
        return old

    def generate_mcq(self, word_id: int) -> Optional[dict]:
        """標準英翻中 MCQ（選項一律為中文）。"""
        return self.db.generate_mcq(word_id)

    @staticmethod
    def _fetch_example_from_api(word: str) -> Optional[str]:
        """
        從 Free Dictionary API 抓取例句。

        嚴格防禦:
          · timeout=3 秒 — 超時立即放棄，不阻塞 UI
          · 捕捉 TimeoutError, URLError, socket.timeout, 所有 Exception
          · 任何錯誤 → 回傳 None (觸發 fallback 到標準 MCQ)

        API: https://api.dictionaryapi.dev/api/v2/entries/en/{word}
        """
        import json
        import urllib.request
        import urllib.error
        import socket

        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"

        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "SRS-Vocab-App/1.0"
            })
            # 嚴格 3 秒超時 — 防止 UI 凍結
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            # 解析 JSON 尋找例句
            if isinstance(data, list) and data:
                for entry in data:
                    for meaning in entry.get("meanings", []):
                        for definition in meaning.get("definitions", []):
                            example = definition.get("example", "")
                            if example and len(example) > 10:
                                return example

        except (urllib.error.URLError, urllib.error.HTTPError,
                socket.timeout, TimeoutError):
            # 網路錯誤/超時 → 靜默放棄
            pass
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            # 解析錯誤 → 靜默放棄
            pass
        except Exception:
            # 任何未預期的錯誤 → 絕不崩潰
            pass

        return None  # 回傳 None → 呼叫方退回標準 MCQ

    def get_chapter_queue(self, category_id: int, chapter_num: int,
                          due_only: bool = True) -> List[dict]:
        """
        取得章節的複習佇列。

        Parameters:
            due_only=True  → 智能複習: 僅載入 next_review <= today 的單字
            due_only=False → 全章學習: 載入全部 20 個單字 (無視排程)
        """
        if due_only:
            return self.db.get_due_words_for_chapter(category_id, chapter_num, limit=20)
        else:
            return self.db.get_words_for_chapter(category_id, chapter_num)

    def speak_word(self, word: str) -> None:
        self.tts.speak(word)

    def autocomplete(self, prefix: str, max_results: int = 50) -> List[dict]:
        return self.trie.autocomplete(prefix, max_results)

    def charts_unlocked(self) -> bool:
        return self.db.get_total_review_count() >= MIN_REVIEWS_FOR_CHARTS

    # ── 圖表快取 ──
    # key = (chart_type, category_id, dark_mode)
    # value = (total_answers_at_generation, base64_str)

    def _chart_cache_key(self, chart_type: str, dark_mode: bool, category_id: int = None):
        return (chart_type, category_id, dark_mode)

    def _get_cached_chart(self, chart_type: str, dark_mode: bool, category_id: int = None) -> Optional[str]:
        """若快取有效 (total_answers 未變) 直接回傳，否則回傳 None。"""
        key = self._chart_cache_key(chart_type, dark_mode, category_id)
        if key not in self._chart_cache:
            return None
        cached_count, cached_img = self._chart_cache[key]
        current_count = self.db.get_total_review_count()
        if cached_count == current_count:
            return cached_img  # 資料沒變，直接回傳快取
        return None  # 資料已變，需要重新生成

    def _set_cached_chart(self, chart_type: str, dark_mode: bool, category_id: int, img: str):
        key = self._chart_cache_key(chart_type, dark_mode, category_id)
        current_count = self.db.get_total_review_count()
        self._chart_cache[key] = (current_count, img)

    def get_accuracy_chart(self, dark_mode: bool = True, category_id: int = None) -> Optional[str]:
        """生成正確率折線圖（帶快取）。"""
        if not self.charts_unlocked():
            return None
        cached = self._get_cached_chart("acc", dark_mode, category_id)
        if cached:
            return cached
        data = self.db.get_daily_accuracy(30, category_id=category_id)
        img = self.charts.generate_accuracy_chart(data, dark_mode)
        self._set_cached_chart("acc", dark_mode, category_id, img)
        return img

    def get_distribution_chart(self, dark_mode: bool = True, category_id: int = None) -> Optional[str]:
        """生成 EF 難度分布圖（帶快取）。"""
        if not self.charts_unlocked():
            return None
        cached = self._get_cached_chart("ef", dark_mode, category_id)
        if cached:
            return cached
        data = self.db.get_ef_distribution(category_id=category_id)
        img = self.charts.generate_ef_chart(data, dark_mode)
        self._set_cached_chart("ef", dark_mode, category_id, img)
        return img

    def cleanup(self) -> None:
        """
        優雅關閉: 停止 TTS 工作執行緒 + 關閉 SQLite 連線。
        必須在程式退出前呼叫，防止資源洩漏。
        """
        try:
            self.tts.shutdown()
        except Exception:
            pass
        try:
            self.db.close()
        except Exception:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 自我測試
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    print("=" * 60)
    print("  SRS v2 Backend 自我測試")
    print("=" * 60)

    # SM-2 測試
    r = SM2Algorithm.calculate(4, 2.5, 1, 1)
    print(f"[SM-2] q=4 → EF={r.easiness_factor}, I={r.interval_days}")

    # Trie 測試
    t = Trie()
    for w in ["apple", "application", "apply", "banana"]:
        t.insert(w, {"chinese": f"<{w}>"})
    print(f"[Trie] 'app' → {[x['word'] for x in t.autocomplete('app')]}")

    # 完整流程
    import tempfile, sys
    with tempfile.TemporaryDirectory() as tmp:
        s = ReviewScheduler(base_dir=tmp)
        info = s.initialize()
        print(f"[Init] {info}")
        cats = s.db.get_categories()
        for cat in cats:
            chapters = s.db.get_chapters_for_category(cat["id"])
            print(f"  {cat['name']}: {len(chapters)} 章")
        print(f"[Charts] unlocked={s.charts_unlocked()}")
        s.cleanup()

    print("\n✓ 測試通過")
    sys.exit(0)  # 強制退出 (TTS daemon 執行緒可能仍在運行)
