"""
╔══════════════════════════════════════════════════════════════════╗
║  SRS Vocab — 效能量測腳本 (真實 backend 版)                     ║
║  使用真實的 backend.py + srs_vocab.db，驗證模擬結果             ║
║  使用方法：                                                      ║
║    把本檔案放到 backend.py 同一資料夾                           ║
║    $ python benchmark_real.py                                   ║
╚══════════════════════════════════════════════════════════════════╝

本腳本測試 5 項指標（對應 benchmark_standalone.py）：
  [1] Trie 建構時間 (真實資料)
  [2] Trie 前綴搜尋 vs 線性掃描
  [3] SM-2 單次更新耗時 (呼叫 SM2Algorithm.calculate)
  [4] MCQ 生成 (呼叫 db.generate_mcq)
  [5] Fitness — 從 review_logs 分析真實使用者 EF 收斂情形
"""

import os
import random
import time
import statistics
from datetime import datetime

random.seed(42)

# ═══════════════════════════════════════════════════════════════
# Import backend（若失敗會給清楚提示）
# ═══════════════════════════════════════════════════════════════
try:
    from backend import (
        SM2Algorithm, Trie, DatabaseManager, ReviewScheduler
    )
except ImportError as e:
    print("❌ 無法 import backend，請確認：")
    print("   1. 本腳本放在與 backend.py 同一資料夾")
    print("   2. 依賴套件已安裝 (flet 等)")
    print(f"   錯誤：{e}")
    raise SystemExit(1)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def fmt_us(seconds):
    us = seconds * 1e6
    if us < 1000:
        return f"{us:>8.2f} µs"
    ms = us / 1000
    if ms < 1000:
        return f"{ms:>8.3f} ms"
    return f"{ms/1000:>8.3f} s"


def box(title, width=70):
    print("\n" + "═" * width)
    print(f"  {title}")
    print("═" * width)


def row(*cols, widths=None):
    if widths is None:
        widths = [20] * len(cols)
    parts = []
    for c, w in zip(cols, widths):
        parts.append(f"{str(c):<{w}}")
    print(" │ ".join(parts))


# ═══════════════════════════════════════════════════════════════
# 設定：找出 DB 路徑
# ═══════════════════════════════════════════════════════════════

def find_db():
    candidates = [
        "srs_vocab.db",
        os.path.expanduser("~/Library/Application Support/srs_vocab/srs_vocab.db"),
        os.path.expanduser("~/.srs_vocab/srs_vocab.db"),
        os.path.expanduser("~/AppData/Roaming/srs_vocab/srs_vocab.db"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


# ═══════════════════════════════════════════════════════════════
# 測試 1: Trie 建構時間 (真實 backend.Trie + 真實單字)
# ═══════════════════════════════════════════════════════════════

def test1_trie_build(all_words):
    box(f"測試 1：Trie 建構時間 (真實資料 {len(all_words):,} 字)")
    trials = []
    for _ in range(5):
        t0 = time.perf_counter()
        trie = Trie()
        for w in all_words:
            trie.insert(w["english"], {
                "id": w["id"],
                "chinese": w.get("chinese", ""),
                "category": w.get("category_name", ""),
            })
        trials.append(time.perf_counter() - t0)

    avg = statistics.mean(trials)
    avg_len = sum(len(w["english"]) for w in all_words) / len(all_words)
    print(f"  試驗次數     : 5")
    print(f"  平均建構時間 : {fmt_us(avg)}")
    print(f"  Trie 大小    : {trie.size:,} (unique 單字)")
    print(f"  總插入次數   : {len(all_words):,} (含跨類別重複)")
    print(f"  平均字長     : {avg_len:.2f}")
    return trie


# ═══════════════════════════════════════════════════════════════
# 測試 2: Trie vs 線性掃描 (真實單字)
# ═══════════════════════════════════════════════════════════════

def test2_prefix_search(all_words, trie, trials=1000):
    box(f"測試 2：前綴搜尋 — Trie vs 線性掃描 (各 {trials} 次取平均)")
    word_list = [w["english"].lower() for w in all_words]

    def linear_search(prefix, max_r=50):
        p = prefix.lower().strip()
        results = []
        for w in word_list:
            if w.startswith(p):
                results.append(w)
                if len(results) >= max_r:
                    break
        return results

    prefixes_by_len = {
        1: ['a', 'b', 'c', 's', 't', 'p', 'e', 'r'],
        2: ['ab', 'ca', 're', 'st', 'pr', 'in', 'co', 'de'],
        3: ['abs', 'con', 'pre', 'str', 'tra', 'com'],
        4: ['inte', 'prot', 'trap', 'cons'],
        5: ['inter', 'trans', 'prote'],
    }

    print()
    row("前綴長度 L", "Trie 平均", "線性 平均", "加速比",
        widths=[12, 15, 15, 12])
    print("─" * 65)

    for L, prefixes in prefixes_by_len.items():
        trie_times = []
        lin_times = []
        for _ in range(trials // len(prefixes)):
            for p in prefixes:
                t0 = time.perf_counter()
                trie.autocomplete(p, 50)
                trie_times.append(time.perf_counter() - t0)

                t0 = time.perf_counter()
                linear_search(p, 50)
                lin_times.append(time.perf_counter() - t0)

        avg_t = statistics.mean(trie_times)
        avg_l = statistics.mean(lin_times)
        speedup = avg_l / avg_t if avg_t > 0 else float('inf')
        row(f"L={L}", fmt_us(avg_t), fmt_us(avg_l),
            f"{speedup:>6.1f}×", widths=[12, 15, 15, 12])


# ═══════════════════════════════════════════════════════════════
# 測試 3: SM-2 呼叫 backend.SM2Algorithm.calculate
# ═══════════════════════════════════════════════════════════════

def test3_sm2_update(trials=100000):
    box(f"測試 3：SM-2 單次更新耗時 (backend.SM2Algorithm.calculate × {trials:,})")

    # 預先產生 100k 組參數
    params = [(random.randint(0, 5),
               2.5 + random.uniform(-0.5, 0.5),
               random.randint(1, 30),
               random.randint(0, 10)) for _ in range(trials)]

    t0 = time.perf_counter()
    for q, ef, iv, rep in params:
        SM2Algorithm.calculate(q, ef, iv, rep)
    elapsed = time.perf_counter() - t0

    avg = elapsed / trials
    print(f"  總耗時       : {fmt_us(elapsed)}")
    print(f"  單次平均     : {fmt_us(avg)}")
    print(f"  時間複雜度   : O(1)")
    print(f"  每秒可處理   : {int(1/avg):,} 次更新")


# ═══════════════════════════════════════════════════════════════
# 測試 4: MCQ 生成 (呼叫 db.generate_mcq)
# ═══════════════════════════════════════════════════════════════

def test4_mcq(db, trials=500):
    box(f"測試 4：MCQ 生成 — db.generate_mcq({trials} 次)")

    # 隨機抽 trials 個 word_id
    c = db.conn.cursor()
    c.execute("SELECT id FROM words ORDER BY RANDOM() LIMIT ?", (trials,))
    ids = [r["id"] for r in c.fetchall()]

    t0 = time.perf_counter()
    successes = 0
    for wid in ids:
        mcq = db.generate_mcq(wid)
        if mcq:
            successes += 1
    elapsed = time.perf_counter() - t0

    avg = elapsed / trials
    print(f"  成功生成     : {successes} / {trials}")
    print(f"  平均耗時     : {fmt_us(avg)}  / 次")
    print(f"  包含：SQL 查詢 + 分類池抽樣 + shuffle")


# ═══════════════════════════════════════════════════════════════
# 測試 5: Fitness — 從 review_logs 分析真實 EF 收斂
# ═══════════════════════════════════════════════════════════════

def test5_fitness(db):
    box("測試 5：Fitness — 真實使用者 EF 收斂分析")

    c = db.conn.cursor()
    # 取出至少被複習 3 次的單字
    c.execute("""SELECT word_id, COUNT(*) AS cnt
                 FROM review_logs GROUP BY word_id HAVING cnt >= 3""")
    word_ids = [r["word_id"] for r in c.fetchall()]

    if not word_ids:
        print("  ⚠ review_logs 中沒有足夠資料 (需有單字被複習過 ≥3 次)")
        print("  建議：先用 App 進行幾輪測驗累積資料後再跑此測試")
        return

    print(f"  分析單字數量 : {len(word_ids):,} 個 (複習次數 ≥3 次)")

    converged_rounds = []
    never_converged = 0
    final_efs = []

    for wid in word_ids:
        c.execute("""SELECT ef_after FROM review_logs
                     WHERE word_id = ? ORDER BY reviewed_at ASC""", (wid,))
        efs = [r["ef_after"] for r in c.fetchall()]

        conv_at = None
        for i in range(3, len(efs) + 1):
            window = efs[i-3:i]
            if max(window) - min(window) < 0.01:
                conv_at = i
                break

        if conv_at is None:
            never_converged += 1
        else:
            converged_rounds.append(conv_at)
        final_efs.append(efs[-1])

    if converged_rounds:
        avg_rounds = statistics.mean(converged_rounds)
        print(f"  已收斂單字數 : {len(converged_rounds):,}")
        print(f"  未收斂單字數 : {never_converged:,} (仍在學習中)")
        print(f"  平均收斂輪數 : {avg_rounds:.2f} 輪")
        print(f"  最快收斂     : {min(converged_rounds)} 輪")
        print(f"  最慢收斂     : {max(converged_rounds)} 輪")
    else:
        print(f"  尚無單字達到收斂 (全部 {never_converged} 個仍在學習中)")

    if final_efs:
        print(f"\n  目前 EF 統計：")
        print(f"    平均 EF    : {statistics.mean(final_efs):.3f}")
        print(f"    中位數 EF  : {statistics.median(final_efs):.3f}")
        print(f"    EF 範圍    : {min(final_efs):.3f} ~ {max(final_efs):.3f}")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  SRS Vocab — 效能量測腳本 (真實 backend 版)                     ║
║  請將以下全部輸出結果貼給 Claude 以整合到期末報告               ║
╚══════════════════════════════════════════════════════════════════╝
""")
    import platform, sys
    print(f"  Python 版本  : {sys.version.split()[0]}")
    print(f"  作業系統     : {platform.system()} {platform.release()}")
    print(f"  處理器架構   : {platform.machine()}")

    # 找 DB
    db_path = find_db()
    if not db_path:
        print("\n❌ 找不到 srs_vocab.db")
        print("   請確認 App 至少執行過一次以建立 DB，或把 DB 放在腳本同資料夾")
        raise SystemExit(1)
    print(f"  資料庫路徑   : {db_path}")
    print(f"  資料庫大小   : {os.path.getsize(db_path)/1024:.1f} KB")

    # 連線
    db = DatabaseManager(db_path)
    db.connect()

    all_words = db.get_all_words()
    print(f"  單字總數     : {len(all_words):,}")

    if len(all_words) == 0:
        print("\n❌ 資料庫中沒有單字，請先執行 App 匯入資料")
        raise SystemExit(1)

    # 跑測試
    trie = test1_trie_build(all_words)
    test2_prefix_search(all_words, trie, trials=1000)
    test3_sm2_update(trials=100000)
    test4_mcq(db, trials=500)
    test5_fitness(db)

    db.close()
    print("\n" + "═" * 70)
    print("  ✅ 全部測試完成。請複製以上輸出結果貼給 Claude。")
    print("═" * 70 + "\n")


if __name__ == "__main__":
    main()
