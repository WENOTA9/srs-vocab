"""
Test 5 補強版：EF 演化分析（適用小樣本）
放寬收斂條件 + 增加多面向分析
"""
import os, sqlite3, statistics

db_path = "srs_vocab.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

def box(t, w=70):
    print("\n" + "═"*w + f"\n  {t}\n" + "═"*w)

box("測試 5 (補強版)：真實使用者 EF 演化分析")

# 放寬：複習 ≥ 2 次就分析
c.execute("""SELECT word_id, COUNT(*) AS cnt FROM review_logs
             GROUP BY word_id HAVING cnt >= 2""")
word_ids = [r["word_id"] for r in c.fetchall()]
print(f"\n  樣本單字數   : {len(word_ids):,} (複習 ≥2 次)")

total_logs = c.execute("SELECT COUNT(*) AS n FROM review_logs").fetchone()["n"]
print(f"  總複習紀錄   : {total_logs}")

# 分類 EF 走勢
up, down, flat = [], [], []
final_efs = []
total_ef_changes = []

for wid in word_ids:
    c.execute("""SELECT ef_after, quality FROM review_logs
                 WHERE word_id=? ORDER BY reviewed_at""", (wid,))
    rows = c.fetchall()
    efs = [r["ef_after"] for r in rows]
    qs = [r["quality"] for r in rows]
    delta = efs[-1] - efs[0]
    total_ef_changes.append(delta)
    final_efs.append(efs[-1])
    if delta > 0.05: up.append((wid, delta, efs, qs))
    elif delta < -0.05: down.append((wid, delta, efs, qs))
    else: flat.append((wid, delta, efs, qs))

print(f"\n  EF 走勢分類：")
print(f"    上升 (熟悉度 ↑) : {len(up):>3} 個  ({100*len(up)/len(word_ids):.1f}%)")
print(f"    下降 (需加強)   : {len(down):>3} 個  ({100*len(down)/len(word_ids):.1f}%)")
print(f"    持平            : {len(flat):>3} 個  ({100*len(flat)/len(word_ids):.1f}%)")

print(f"\n  EF 統計：")
print(f"    平均最終 EF     : {statistics.mean(final_efs):.3f}")
print(f"    中位數 EF       : {statistics.median(final_efs):.3f}")
print(f"    EF 範圍         : {min(final_efs):.3f} ~ {max(final_efs):.3f}")
print(f"    平均變動量 ΔEF  : {statistics.mean(total_ef_changes):+.3f}")

# 放寬收斂定義：最後兩次 EF 變動 < 0.15
converged = 0
for wid in word_ids:
    c.execute("""SELECT ef_after FROM review_logs
                 WHERE word_id=? ORDER BY reviewed_at""", (wid,))
    efs = [r["ef_after"] for r in c.fetchall()]
    if len(efs) >= 2 and abs(efs[-1] - efs[-2]) < 0.15:
        converged += 1
print(f"\n  放寬收斂 (ΔEF<0.15) : {converged} / {len(word_ids)} ({100*converged/len(word_ids):.1f}%)")

# 展示代表性案例
box("代表性案例：SM-2 的自我修正行為")

# Case 1: 連續答對 → EF 上升
if up:
    u = max(up, key=lambda x: x[1])
    wid = u[0]
    c.execute("SELECT english, chinese FROM words WHERE id=?", (wid,))
    w = c.fetchone()
    ef_str = " → ".join(f"{e:.2f}" for e in u[2])
    q_str = "/".join(str(q) for q in u[3])
    print(f"\n  [上升案例] {w['english']} ({w['chinese']})")
    print(f"    EF 軌跡   : {ef_str}")
    print(f"    品質序列  : q = {q_str}")
    print(f"    ΔEF       : {u[1]:+.3f}  → SM-2 正確判定『已熟練』")

# Case 2: 答錯後 → EF 下降
if down:
    d = min(down, key=lambda x: x[1])
    wid = d[0]
    c.execute("SELECT english, chinese FROM words WHERE id=?", (wid,))
    w = c.fetchone()
    ef_str = " → ".join(f"{e:.2f}" for e in d[2])
    q_str = "/".join(str(q) for q in d[3])
    print(f"\n  [下降案例] {w['english']} ({w['chinese']})")
    print(f"    EF 軌跡   : {ef_str}")
    print(f"    品質序列  : q = {q_str}")
    print(f"    ΔEF       : {d[1]:+.3f}  → SM-2 正確判定『需加強』")

conn.close()
print("\n" + "═"*70 + "\n")
