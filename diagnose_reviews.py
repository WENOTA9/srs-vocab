"""
診斷腳本：檢查 review_logs 的實際分佈
找出為什麼 Test 5 沒有資料
"""
import os
import sqlite3

db_path = "srs_vocab.db"
if not os.path.exists(db_path):
    print("❌ 找不到 srs_vocab.db")
    raise SystemExit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("═" * 60)
print("  review_logs 診斷報告")
print("═" * 60)

# 總日誌數
c.execute("SELECT COUNT(*) AS n FROM review_logs")
total_logs = c.fetchone()["n"]
print(f"\n總複習紀錄數         : {total_logs}")

# 有被複習過的 unique 單字數
c.execute("SELECT COUNT(DISTINCT word_id) AS n FROM review_logs")
unique_words = c.fetchone()["n"]
print(f"有被複習過的單字數   : {unique_words}")

# 每字平均被複習次數
if unique_words > 0:
    print(f"每字平均複習次數     : {total_logs/unique_words:.2f}")

# 複習次數分佈
print(f"\n複習次數分佈：")
c.execute("""SELECT cnt, COUNT(*) AS num_words FROM (
    SELECT word_id, COUNT(*) AS cnt FROM review_logs GROUP BY word_id
) GROUP BY cnt ORDER BY cnt""")
for r in c.fetchall():
    print(f"  被複習 {r['cnt']} 次的單字數 : {r['num_words']}")

# 時間範圍
c.execute("SELECT MIN(reviewed_at) AS mn, MAX(reviewed_at) AS mx FROM review_logs")
r = c.fetchone()
print(f"\n紀錄時間範圍         : {r['mn']} ~ {r['mx']}")

# 複習次數 ≥ 2 的單字（放寬條件）
c.execute("SELECT COUNT(*) AS n FROM (SELECT word_id FROM review_logs GROUP BY word_id HAVING COUNT(*) >= 2)")
print(f"\n複習 ≥2 次的單字數   : {c.fetchone()['n']}")
c.execute("SELECT COUNT(*) AS n FROM (SELECT word_id FROM review_logs GROUP BY word_id HAVING COUNT(*) >= 3)")
print(f"複習 ≥3 次的單字數   : {c.fetchone()['n']}")
c.execute("SELECT COUNT(*) AS n FROM (SELECT word_id FROM review_logs GROUP BY word_id HAVING COUNT(*) >= 5)")
print(f"複習 ≥5 次的單字數   : {c.fetchone()['n']}")

# 取一個樣本：被複習最多次的那個單字，看它的 EF 變化
c.execute("""SELECT word_id, COUNT(*) AS cnt FROM review_logs
             GROUP BY word_id ORDER BY cnt DESC LIMIT 5""")
top = c.fetchall()
if top:
    print(f"\n被複習最多次的前 5 個單字：")
    for r in top:
        c.execute("SELECT english FROM words WHERE id=?", (r["word_id"],))
        w = c.fetchone()
        word = w["english"] if w else "?"
        c.execute("""SELECT ef_after FROM review_logs
                     WHERE word_id=? ORDER BY reviewed_at""", (r["word_id"],))
        efs = [row["ef_after"] for row in c.fetchall()]
        ef_str = " → ".join(f"{ef:.2f}" for ef in efs)
        print(f"  {word:<15} ({r['cnt']} 次) : EF = {ef_str}")

conn.close()
print("\n" + "═" * 60)
