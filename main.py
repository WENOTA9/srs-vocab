"""
SRS 英文單字學習系統 — Flet 前端
首頁儀表板 · 大考倒數 · 範圍/上限控制 · 四選一MCQ · 星號錯題本 · 雙層說明對話框
"""
import os, sys, threading, time
from datetime import datetime, timedelta
from typing import Optional
import flet as ft

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend import ReviewScheduler, MIN_REVIEWS_FOR_CHARTS

def oc(o, c): return f"{c},{o}"
DARK = {"bg":"#0f0f1a","surface":"#1a1a2e","sv":"#232340","card":"#1e1e35",
    "primary":"#b388ff","secondary":"#80cbc4","tertiary":"#ffab91",
    "on":"#e8e8f0","dim":"#9e9eb8","outline":"#3a3a5c",
    "error":"#ff5252","success":"#69f0ae","warning":"#ffd740",
    "star":"#ffd740","fire":"#ff6d00"}
LIGHT = {"bg":"#f5f5fa","surface":"#ffffff","sv":"#ede7f6","card":"#ffffff",
    "primary":"#6200ee","secondary":"#00897b","tertiary":"#e64a19",
    "on":"#1c1b1f","dim":"#79747e","outline":"#d6d6e6",
    "error":"#b00020","success":"#2e7d32","warning":"#f57f17",
    "star":"#f57f17","fire":"#e64a19"}

def main(page: ft.Page):
    bd = os.path.dirname(os.path.abspath(__file__))
    S = ReviewScheduler(base_dir=bd)
    dm = True
    state = "idle"; queue = []; qi = 0; rv = 0; co = 0
    cur_cat = None; cur_ch = None; cur_mcq = None; mcq_done = False
    review_mode = "chapter"
    combo = 0          # 連擊計數器 — 連續答對 +1, 答錯歸零
    mcq_start_time = 0  # 題目載入時間戳 (用於反應時間計算)

    page.title = "SRS 英文單字學習系統"; page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0; page.bgcolor = DARK["bg"]
    try: page.window.width=500; page.window.height=860; page.window.min_width=380
    except: pass
    try: S.initialize()
    except Exception as e: page.add(ft.Text(f"初始化失敗: {e}",color="red",size=18)); return

    def C(): return DARK if dm else LIGHT
    def crd(ct, p=24):
        return ft.Container(content=ct, bgcolor=C()["card"], border_radius=20, padding=p,
            shadow=ft.BoxShadow(spread_radius=0,blur_radius=12,color=oc(0.15,"black"),offset=ft.Offset(0,4)))
    def snk(m):
        sb=ft.SnackBar(ft.Text(m),bgcolor=C()["sv"]); page.overlay.append(sb); sb.open=True; page.update()
    def close_dlg(d): d.open=False; page.update()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 雙層說明對話框 (白話文 → 數學)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def show_info_dialog(e):
        """章節分頁專屬：白話文說明"""
        dlg = ft.AlertDialog(modal=True,
            title=ft.Text("章節指標說明", weight=ft.FontWeight.W_700, size=18),
            content=ft.Container(content=ft.Column([
                ft.Text("📊 答對率", weight=ft.FontWeight.W_700, size=16, color=C()["primary"]),
                ft.Text("反映你在這個章節的真實作答表現。\n"
                         "80% 代表每 10 題你能憑直覺答對 8 題。\n"
                         "四選一選對就算答對，選錯就算答錯。", size=13, color=C()["on"]),
                ft.Divider(height=20, color=C()["outline"]),
                ft.Text("🧠 記住率", weight=ft.FontWeight.W_700, size=16, color=C()["secondary"]),
                ft.Text("代表這個章節中「已記牢」的單字比例。\n"
                         "系統根據你的答題紀錄判斷每個單字\n"
                         "是否已進入長期記憶。100% = 全部記牢。\n"
                         "答對越多→複習間隔越長→記住率越高。", size=13, color=C()["on"]),
                ft.Divider(height=20, color=C()["outline"]),
                ft.Text("🔴 待複習 / ✅ 下次複習", weight=ft.FontWeight.W_700, size=16, color=C()["tertiary"]),
                ft.Text("紅色數字 = 今天到期需要複習的單字數。\n"
                         "綠色日期 = 最近需要複習的時間。\n"
                         "答對越多，下次複習日期就會越遠。", size=13, color=C()["on"]),
            ], spacing=4, scroll=ft.ScrollMode.AUTO), width=360, height=400),
            actions=[
                ft.TextButton("深入了解演算法",
                    on_click=lambda e: (close_dlg(dlg), show_math_dialog(e))),
                ft.TextButton("了解了！", on_click=lambda e: close_dlg(dlg)),
            ])
        page.overlay.append(dlg); dlg.open=True; page.update()

    def show_math_dialog(e):
        """第二層：SM-2 數學公式"""
        dlg = ft.AlertDialog(modal=True,
            title=ft.Text("SM-2 演算法技術規格", weight=ft.FontWeight.W_700, size=18),
            content=ft.Container(content=ft.Column([
                ft.Text("EF 更新公式", weight=ft.FontWeight.W_700, size=15, color=C()["primary"]),
                ft.Text("EF' = EF + (0.1 − (5−q) × (0.08 + (5−q) × 0.02))\n\n"
                         "MCQ 映射: 答對→q=5 (+0.10), 答錯→q=0 (−0.80)\n"
                         "下限: EF ≥ 1.3", size=12, color=C()["on"]),
                ft.Divider(height=16, color=C()["outline"]),
                ft.Text("間隔計算", weight=ft.FontWeight.W_700, size=15, color=C()["secondary"]),
                ft.Text("答對 (q≥3):\n  n=1→I=1天, n=2→I=6天, n>2→I=round(I×EF)\n"
                         "答錯 (q<3):\n  n歸零, I=1天 (重新學習)", size=12, color=C()["on"]),
                ft.Divider(height=16, color=C()["outline"]),
                ft.Text("答對率 SQL", weight=ft.FontWeight.W_700, size=15, color=C()["tertiary"]),
                ft.Text("SUM(quality≥3) / COUNT(*) × 100%\n\n"
                         "記憶率 SQL:\n  SUM(next_review > today) / COUNT(*) × 100%\n\n"
                         "精熟評分:\n  correct_count / total_reviews × 100", size=12, color=C()["on"]),
            ], spacing=4, scroll=ft.ScrollMode.AUTO), width=360, height=400),
            actions=[ft.TextButton("關閉", on_click=lambda e: close_dlg(dlg))])
        page.overlay.append(dlg); dlg.open=True; page.update()

    def show_stats_info_dialog(e):
        """統計分頁專屬：白話文說明 (對應統計頁的 4 個指標)"""
        dlg = ft.AlertDialog(modal=True,
            title=ft.Text("統計指標說明", weight=ft.FontWeight.W_700, size=18),
            content=ft.Container(content=ft.Column([
                ft.Text("📝 總答題數", weight=ft.FontWeight.W_700, size=16, color=C()["primary"]),
                ft.Text("你使用這個 APP 以來，進行單字測驗的總次數。\n"
                         "每答一題（無論對錯）都會 +1。\n"
                         "累積越多，統計數據越準確。", size=13, color=C()["on"]),
                ft.Divider(height=20, color=C()["outline"]),
                ft.Text("✅ 正確率", weight=ft.FontWeight.W_700, size=16, color=C()["secondary"]),
                ft.Text("歷史總結的答對比例，反映你的整體英文單字實力。\n"
                         "計算方式：全部答對次數 ÷ 全部答題次數 × 100%\n"
                         "這個數字越高，代表你的單字基礎越紮實。", size=13, color=C()["on"]),
                ft.Divider(height=20, color=C()["outline"]),
                ft.Text("🔥 熟練度", weight=ft.FontWeight.W_700, size=16, color=C()["tertiary"]),
                ft.Text("系統計算出的整體單字熟悉程度。\n"
                         "數字越高，代表你覺得這些單字越簡單。\n"
                         "初始值 2.50，持續答對會上升，答錯會下降。\n"
                         "高於 2.5 = 大部分單字對你來說很容易。", size=13, color=C()["on"]),
                ft.Divider(height=20, color=C()["outline"]),
                ft.Text("📅 今日答題", weight=ft.FontWeight.W_700, size=16, color=C()["success"]),
                ft.Text("你今天已經完成的單字測驗題數。\n"
                         "包含所有分類、所有章節的答題總和。\n"
                         "建議每天至少完成 30~50 題維持記憶。", size=13, color=C()["on"]),
            ], spacing=4, scroll=ft.ScrollMode.AUTO), width=360, height=440),
            actions=[
                ft.TextButton("深入了解演算法",
                    on_click=lambda e: (close_dlg(dlg), show_math_dialog(e))),
                ft.TextButton("了解了！", on_click=lambda e: close_dlg(dlg)),
            ])
        page.overlay.append(dlg); dlg.open=True; page.update()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TAB 0: 首頁 (大考倒數 + 範圍控制 + 一鍵複習)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    home_section = ft.Container(expand=True)
    h_streak = ft.Text("0", size=36, weight=ft.FontWeight.W_700)
    h_max_combo = ft.Text("", size=14, weight=ft.FontWeight.W_600)  # 最高連擊紀錄
    h_remaining = ft.Text("0", size=22, weight=ft.FontWeight.W_700)  # 今日剩餘量
    h_remaining_label = ft.Text("", size=13)
    h_starred = ft.Text("0", size=28, weight=ft.FontWeight.W_700)
    # 大考倒數元件
    h_exam_card = ft.Container(visible=False)
    h_exam_name = ft.Text("", size=14, weight=ft.FontWeight.W_600)
    h_exam_days = ft.Text("", size=40, weight=ft.FontWeight.W_700)

    # 範圍控制元件
    home_cat_dd = ft.Dropdown(label="複習範圍", hint_text="全部", width=200,
        border_color=DARK["outline"], focused_border_color=DARK["primary"],
        label_style=ft.TextStyle(color=DARK["dim"], size=12),
        text_style=ft.TextStyle(color=DARK["on"], size=13),
        bgcolor=DARK["surface"], border_radius=12,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8))
    home_limit_dd = ft.Dropdown(label="每日上限", width=120,
        border_color=DARK["outline"], focused_border_color=DARK["primary"],
        label_style=ft.TextStyle(color=DARK["dim"], size=12),
        text_style=ft.TextStyle(color=DARK["on"], size=13),
        bgcolor=DARK["surface"], border_radius=12,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        options=[ft.dropdown.Option(str(n), str(n)) for n in [20,30,50,80,100]],
        value="50")

    def pop_home_dd():
        cats = S.db.get_categories()
        home_cat_dd.options = [ft.dropdown.Option("all","全部")] + \
            [ft.dropdown.Option(str(c["id"]), c["name"]) for c in cats]
        home_cat_dd.value = "all"
        home_cat_dd.on_change = lambda e: (refresh_home(), page.update())
        home_limit_dd.on_change = lambda e: (refresh_home(), page.update())
        

    def get_home_cat_id():
        v = home_cat_dd.value
        return None if v == "all" else int(v)

    def get_home_limit():
        try: return int(home_limit_dd.value)
        except: return 50

    # 首頁動態元件 — 開始按鈕 + 慶祝文字
    start_btn = ft.Container(border_radius=18, padding=ft.Padding.symmetric(horizontal=20, vertical=18), ink=True)
    celebrate_text = ft.Text("", size=16, weight=ft.FontWeight.W_700, text_align=ft.TextAlign.CENTER)

    def refresh_home():
        cid = get_home_cat_id()
        d = S.get_dashboard_data()
        due_c = S.get_due_count(category_id=cid)
        limit = get_home_limit()
        today_done = d["today_count"]
        # 剩餘量 = min(每日上限, 到期數) - 今日已答
        remaining = max(0, min(limit, due_c) - today_done)

        h_streak.value = str(d["streak"]); h_streak.color = C()["fire"]
        h_remaining.value = str(remaining)
        h_starred.value = str(d["starred"]); h_starred.color = C()["star"]
        # Fix 5: 最高連擊紀錄
        mc = d.get("max_combo", 0)
        h_max_combo.value = f"🔥 最高連擊: {mc}" if mc >= 2 else ""
        h_max_combo.color = C()["fire"]

        # 動態按鈕狀態: 有剩餘 → 啟用(紫色); 無剩餘 → 禁用(灰色) + 慶祝
        if remaining > 0:
            h_remaining.color = oc(0.8, "#f9f900")
            h_remaining_label.value = "個單字待複習"
            h_remaining_label.color = oc(0.8, "#ffffff")
            start_btn.bgcolor = C()["primary"]
            start_btn.on_click = on_global_review
            start_btn.opacity = 1.0
            celebrate_text.value = ""
            celebrate_text.visible = False
        else:
            h_remaining.color = oc(0.8, "#f9f900")
            h_remaining_label.value = "今日目標已完成！"
            h_remaining_label.color = oc(0.8, "#ffffff")
            start_btn.bgcolor = C()["outline"]
            start_btn.on_click = None  # 禁用點擊
            start_btn.opacity = 0.5
            celebrate_text.value = "🎉 太棒了！你已清空今日的複習任務！"
            celebrate_text.color = C()["success"]
            celebrate_text.visible = True

        start_btn.content = ft.Row([ft.Text("⚡",size=22),
            ft.Column([ft.Text("開始今日複習",size=18,weight=ft.FontWeight.W_700,color="#ffffff"),
                ft.Row([h_remaining, h_remaining_label],
                    spacing=4,vertical_alignment=ft.CrossAxisAlignment.CENTER)],
                spacing=2, expand=True),
            ft.Icon(ft.Icons.ARROW_FORWARD_ROUNDED,color="#ffffff",size=24)],
            spacing=12,vertical_alignment=ft.CrossAxisAlignment.CENTER)
        # 大考倒數
        exam_name = S.db.get_meta("exam_name", "")
        exam_date = S.db.get_meta("exam_date", "")
        if exam_name and exam_date:
            try:
                target = datetime.strptime(exam_date, "%Y-%m-%d")
                delta = (target - datetime.now()).days
                h_exam_name.value = exam_name; h_exam_name.color = C()["on"]
                h_exam_days.value = str(max(delta, 0)); h_exam_days.color = C()["error"]
                h_exam_card.visible = True
            except: h_exam_card.visible = False
        else:
            h_exam_card.visible = False

    def show_exam_dialog(e):
        """設定大考倒數的對話框"""
        name_f = ft.TextField(label="考試名稱", hint_text="例: 114年學測",
            value=S.db.get_meta("exam_name",""),
            border_color=C()["outline"], focused_border_color=C()["primary"],
            label_style=ft.TextStyle(color=C()["dim"]),
            text_style=ft.TextStyle(color=C()["on"]),
            bgcolor=C()["surface"], border_radius=12)
        date_f = ft.TextField(label="考試日期 (YYYY-MM-DD)", hint_text="2026-01-18",
            value=S.db.get_meta("exam_date",""),
            border_color=C()["outline"], focused_border_color=C()["primary"],
            label_style=ft.TextStyle(color=C()["dim"]),
            text_style=ft.TextStyle(color=C()["on"]),
            bgcolor=C()["surface"], border_radius=12)
        def save(ev):
            n = name_f.value.strip(); d = date_f.value.strip()
            if n: S.db.set_meta("exam_name", n)
            if d:
                try:
                    datetime.strptime(d, "%Y-%m-%d")
                    S.db.set_meta("exam_date", d)
                except: snk("日期格式錯誤！請用 YYYY-MM-DD"); return
            close_dlg(dlg); refresh_home(); page.update()
        def clear(ev):
            S.db.set_meta("exam_name",""); S.db.set_meta("exam_date","")
            close_dlg(dlg); refresh_home(); page.update()
        dlg = ft.AlertDialog(modal=True,
            title=ft.Text("設定大考倒數", weight=ft.FontWeight.W_700, size=18),
            content=ft.Container(content=ft.Column([name_f, ft.Container(height=8), date_f],
                spacing=0), width=340, height=160),
            actions=[ft.TextButton("清除",on_click=clear),
                     ft.TextButton("儲存",on_click=save)])
        page.overlay.append(dlg); dlg.open=True; page.update()

    def on_global_review(e):
        nonlocal queue, qi, rv, co, state, review_mode, combo
        review_mode = "global"; combo = 0
        cid = get_home_cat_id(); limit = get_home_limit()
        today_done = S.db.get_today_reviewed_count()
        actual_limit = max(1, limit - today_done)
        queue = S.get_all_due_words(limit=actual_limit, category_id=cid)
        if not queue: snk("今日目標已完成！休息一下 🎉"); return
        qi=0; rv=0; co=0; state="q"; load_mcq()
        # 切換到 chap_tab 顯示測驗 UI
        home_tab_wrap.visible=False; chap_tab.visible=True
        search_tab.visible=False; stats_tab.visible=False
        mcq_wrapper.visible=True; chap_section.visible=False
        switch_to_review(); page.update()

    def on_starred_review(e):
        nonlocal queue, qi, rv, co, state, review_mode, combo
        review_mode = "starred"; combo = 0
        queue = S.get_starred_words()
        if not queue: snk("錯題本是空的！📚"); return
        qi=0; rv=0; co=0; state="q"; load_mcq()
        # 切換到 chap_tab 顯示測驗 UI
        home_tab_wrap.visible=False; chap_tab.visible=True
        search_tab.visible=False; stats_tab.visible=False
        mcq_wrapper.visible=True; chap_section.visible=False
        switch_to_review(); page.update()

    def build_home():
        refresh_home()
        today_s = datetime.now().strftime("%Y年%m月%d日")
        # 大考倒數卡片
        h_exam_card.content = crd(ft.Row([
            ft.Column([
                ft.Row([ft.Text("🎯", size=20), h_exam_name], spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Text("距離考試還有", size=12, color=C()["dim"]),
            ], expand=True),
            ft.Column([h_exam_days, ft.Text("天", size=14, color=C()["dim"])],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
            ft.IconButton(icon=ft.Icons.EDIT_ROUNDED, icon_color=C()["dim"], icon_size=18,
                on_click=show_exam_dialog),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER), p=16)

        home_section.content = ft.Column([
            ft.Container(height=8),
            ft.Row([ft.Text(today_s, size=13, color=C()["dim"]), ft.Container(expand=True),
                ft.TextButton("設定大考倒數", on_click=show_exam_dialog)],
                vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(height=4),
            # 大考倒數
            h_exam_card,
            ft.Container(height=8),
            # 連勝卡片
            crd(ft.Row([
                ft.Row([ft.Text("🔥",size=28), h_streak],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                ft.Column([
                    ft.Text("連續學習天數", size=13, color=C()["dim"]),
                    h_max_combo,  # Fix 5: 最高連擊紀錄
                ], horizontal_alignment=ft.CrossAxisAlignment.END, spacing=2),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
               vertical_alignment=ft.CrossAxisAlignment.CENTER), p=20),
            ft.Container(height=12),
            # 範圍設定
            ft.Text("複習設定", size=14, weight=ft.FontWeight.W_600, color=C()["dim"]),
            ft.Container(height=6),
            ft.Row([home_cat_dd, home_limit_dd], spacing=10),
            ft.Container(height=12),
            # 一鍵複習 (動態: 有剩餘→紫色啟用, 無剩餘→灰色禁用)
            start_btn,
            # 慶祝文字 (待辦=0 時顯示)
            celebrate_text,
            ft.Container(height=10),
            # 錯題本
            ft.Container(
                content=ft.Row([ft.Text("⭐",size=20),
                    ft.Column([ft.Text("複習錯題本",size=16,weight=ft.FontWeight.W_600,color=C()["on"]),
                        ft.Row([h_starred,ft.Text("個收藏",size=12,color=C()["dim"])],
                            spacing=4,vertical_alignment=ft.CrossAxisAlignment.CENTER)],
                        spacing=2,expand=True),
                    ft.Icon(ft.Icons.ARROW_FORWARD_ROUNDED,color=C()["dim"],size=22)],
                    spacing=12,vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=C()["card"], border_radius=18, padding=ft.Padding.symmetric(horizontal=20, vertical=16),
                border=ft.Border.all(width=1, color=C()["outline"]), on_click=on_starred_review, ink=True),
            ft.Container(height=20),
        ], scroll=ft.ScrollMode.AUTO, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MCQ 四選一測驗
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    review_container = ft.Container(visible=False, expand=True)
    done_container = ft.Container(visible=False, expand=True)
    pbar = ft.ProgressBar(value=0,height=6,border_radius=3)
    ptxt = ft.Text("",size=12)
    t_eng = ft.Text("",size=36,weight=ft.FontWeight.W_700,text_align=ft.TextAlign.CENTER)
    t_pos = ft.Text("",size=13,text_align=ft.TextAlign.CENTER,italic=True)
    t_chip = ft.Container(content=ft.Text("",size=11),border_radius=12,padding=ft.Padding.symmetric(horizontal=8, vertical=4))
    mcq_col = ft.Column(spacing=10,horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    mcq_fb = ft.Text("",size=15,text_align=ft.TextAlign.CENTER)
    fb_extra = ft.Column(opacity=0,animate_opacity=300,horizontal_alignment=ft.CrossAxisAlignment.CENTER,spacing=2)

    star_btn = ft.IconButton(icon=ft.Icons.STAR_BORDER_ROUNDED,icon_size=26,tooltip="錯題本")
    def on_star(e):
        if not queue or qi>=len(queue): return
        nv = S.toggle_star(queue[qi]["id"])
        star_btn.icon = ft.Icons.STAR_ROUNDED if nv else ft.Icons.STAR_BORDER_ROUNDED
        star_btn.icon_color = C()["star"] if nv else C()["dim"]; page.update()
    star_btn.on_click = on_star

    # ── TTS: 桌面用原生 (say/pyttsx3)，行動裝置用 flet-audio + Google TTS ──
    _mobile_audio = None  # flet-audio 控件 (Android 用)
    if not S.tts.is_available:
        try:
            from flet_audio import Audio
            _mobile_audio = Audio(src="", autoplay=False, volume=1.0)
            page.overlay.append(_mobile_audio)
        except Exception:
            _mobile_audio = None  # flet-audio 未安裝，靜默降級

    def on_speak(e):
        word = None
        if cur_mcq:
            word = cur_mcq["english"]
        elif queue and qi < len(queue):
            word = queue[qi]["english"]
        if not word:
            return
        if _mobile_audio:
            # Android: 用 Google Translate TTS
            import urllib.parse
            url = f"https://translate.googleapis.com/translate_tts?ie=UTF-8&tl=en&client=gtx&q={urllib.parse.quote(word)}"
            _mobile_audio.src = url
            _mobile_audio.play()
            page.update()
        else:
            # Mac/Windows/Linux: 用原生 TTS
            S.speak_word(word)
    speak_btn = ft.IconButton(icon=ft.Icons.VOLUME_UP_ROUNDED,icon_size=28,tooltip="發音",
        on_click=on_speak,visible=False)

    # 連擊顯示
    combo_text = ft.Text("", size=14, weight=ft.FontWeight.W_700, text_align=ft.TextAlign.CENTER)

    # 答錯後「繼續」按鈕 (手動跳轉，給大腦時間處理錯誤)
    continue_btn = ft.Button("繼續 →", bgcolor=C()["primary"], color="#ffffff",
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=14),
                             padding=ft.Padding.symmetric(horizontal=32, vertical=12)),
        visible=False)

    # 學習卡容器 (全新單字: 直接顯示答案，不考試)
    learn_card_col = ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8, visible=False)
    learn_chi = ft.Text("", size=32, weight=ft.FontWeight.W_700, text_align=ft.TextAlign.CENTER)
    learn_ph = ft.Text("", size=14, italic=True, text_align=ft.TextAlign.CENTER)
    learn_ex = ft.Text("", size=13, text_align=ft.TextAlign.CENTER, max_lines=3)

    def _advance_to_next():
        """
        共用: 推進到下一題或結算。
        包含非同步卸載保護：若使用者在延遲期間切換了分頁，
        review_container 已不在畫面上，跳過 UI 更新防止崩潰。
        """
        nonlocal qi, state
        # Fix 2: 非同步卸載保護 — 若元件已脫離頁面則靜默返回
        try:
            if not review_container.page:
                return
        except Exception:
            return
        qi += 1
        if qi >= len(queue):
            state = "done"; show_done()
        else:
            state = "q"; load_mcq()
        try:
            page.update()
        except Exception:
            pass  # 元件已卸載，靜默忽略

    def on_continue(e):
        """答錯後手動點擊「繼續」。"""
        continue_btn.visible = False
        _advance_to_next()

    continue_btn.on_click = on_continue

    def on_learn_confirm(e):
        """
        學習卡「我記住了」按鈕。
        SM-2 初始學習: q=3 (初次接觸，尚非完美回想)。
        """
        nonlocal qi, rv, state
        w = queue[qi]; rv += 1
        S.process_review(w["id"], 3)  # q=3: 初次學習
        S.db.record_activity()
        _advance_to_next()

    def on_mcq_select(e):
        nonlocal mcq_done, qi, rv, co, state, combo
        if mcq_done or cur_mcq is None: return
        mcq_done = True; sel = e.control.data; ans = cur_mcq["correct_chinese"]
        ok = (sel == ans); rv += 1
        response_time = time.time() - mcq_start_time

        if ok:
            co += 1; combo += 1
            S.update_max_combo(combo)  # Fix 5: 持久化最高連擊
        else:
            combo = 0

        # 連擊顯示
        if combo >= 2:
            combo_text.value = f"🔥 {combo} 連擊！"
            combo_text.color = C()["fire"] if combo < 5 else C()["star"]
        else:
            combo_text.value = ""

        # 視覺回饋: 正確→綠, 錯誤→紅, 其他→淡化
        for ctrl in mcq_col.controls:
            if not isinstance(ctrl, ft.Container): continue
            ot = ctrl.data
            if ot == ans:
                ctrl.bgcolor = C()["success"]; ctrl.border = ft.Border.all(width=2, color=C()["success"])
                for ch in ctrl.content.controls:
                    if isinstance(ch, ft.Text): ch.color = "#ffffff"
            elif ot == sel and not ok:
                ctrl.bgcolor = C()["error"]; ctrl.border = ft.Border.all(width=2, color=C()["error"])
                for ch in ctrl.content.controls:
                    if isinstance(ch, ft.Text): ch.color = "#ffffff"
            else:
                ctrl.opacity = 0.35

        if ok and response_time < 1.5:
            mcq_fb.value = "⚡ 正確！(快速作答)"
            mcq_fb.color = C()["warning"]
        elif ok:
            mcq_fb.value = "✅ 正確！"
            mcq_fb.color = C()["success"]
        else:
            mcq_fb.value = f"❌ 正確答案: {ans}"
            mcq_fb.color = C()["error"]

        w = queue[qi]; ph = w.get("phonetic","") or ""; ex = w.get("example_sentence","") or ""
        fb_extra.controls.clear()
        if ph: fb_extra.controls.append(ft.Text(ph,size=13,color=C()["dim"],italic=True))
        if ex: fb_extra.controls.append(ft.Text(ex,size=12,color=C()["dim"],max_lines=2))
        fb_extra.opacity = 1.0
        page.update()

        if ok:
            # 答對: 0.8 秒後自動跳轉
            def _auto():
                nonlocal qi, state
                time.sleep(0.8)
                # Fix 2: 非同步卸載保護
                try:
                    if not review_container.page: return
                except: return
                S.process_mcq_answer(queue[qi]["id"], True, response_time=response_time)
                _advance_to_next()
            threading.Thread(target=_auto, daemon=True).start()
        else:
            # 答錯: 顯示「繼續」按鈕，等使用者手動點擊
            S.process_mcq_answer(queue[qi]["id"], False, response_time=response_time)
            continue_btn.visible = True
            page.update()

    def build_opt(text, idx):
        lb = chr(65+idx)
        return ft.Container(content=ft.Row([
            ft.Container(content=ft.Text(lb,size=16,weight=ft.FontWeight.W_700,color=C()["primary"]),
                width=36,height=36,border_radius=18,bgcolor=oc(0.12,C()["primary"]),
                alignment=ft.Alignment(0,0)),
            ft.Container(width=12),
            ft.Text(text,size=17,color=C()["on"],expand=True)]),
            bgcolor=C()["card"],border_radius=14,padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            border=ft.Border.all(width=1, color=C()["outline"]),data=text,
            on_click=on_mcq_select,ink=True,animate=ft.Animation(300,ft.AnimationCurve.EASE_OUT))

    def load_mcq():
        """
        載入下一題。路由邏輯:
          · repetitions == 0 (全新單字) → 學習卡 (直接展示答案)
          · repetitions > 0 (已學過)    → 四選一 MCQ 測驗
        """
        nonlocal cur_mcq, mcq_done, mcq_start_time
        if qi>=len(queue): return
        w=queue[qi]; mcq_done=False
        continue_btn.visible = False  # 重置繼續按鈕

        reps = w.get("repetitions", 0) or 0

        if reps == 0:
            # ── 學習卡模式: 全新單字，直接展示答案 ──
            cur_mcq = None
            t_eng.value = w["english"]; t_eng.color = C()["on"]
            t_pos.value = w.get("part_of_speech",""); t_pos.color = C()["secondary"]
            t_chip.content.value = w.get("category_name","")
            t_chip.content.color = C()["primary"]; t_chip.bgcolor = oc(0.12,C()["primary"])

            # 學習卡內容: 中文翻譯 + 音標 + 例句
            learn_chi.value = w["chinese"]; learn_chi.color = C()["secondary"]
            ph = w.get("phonetic","") or ""
            learn_ph.value = ph; learn_ph.color = C()["dim"]
            ex = w.get("example_sentence","") or ""
            learn_ex.value = ex; learn_ex.color = C()["dim"]

            # 顯示學習卡，隱藏 MCQ 選項
            mcq_col.controls.clear()
            learn_card_col.visible = True
            mcq_fb.value = "📖 第一次見面！先記住它"
            mcq_fb.color = C()["primary"]
            fb_extra.opacity = 0
            speak_btn.visible = True; speak_btn.icon_color = C()["primary"]
            is_s = w.get("is_starred", 0)
            star_btn.icon = ft.Icons.STAR_ROUNDED if is_s else ft.Icons.STAR_BORDER_ROUNDED
            star_btn.icon_color = C()["star"] if is_s else C()["dim"]
        else:
            # ── MCQ 模式: 已學過的單字，進行測驗 ──
            learn_card_col.visible = False
            mcq = S.generate_mcq(w["id"])
            if not mcq: return
            cur_mcq = mcq
            mcq_start_time = time.time()
            t_eng.value = mcq["english"]; t_eng.color = C()["on"]
            t_pos.value = w.get("part_of_speech",""); t_pos.color = C()["secondary"]
            t_chip.content.value = w.get("category_name","")
            t_chip.content.color = C()["primary"]; t_chip.bgcolor = oc(0.12,C()["primary"])
            mcq_fb.value = ""; fb_extra.opacity = 0; fb_extra.controls.clear()
            speak_btn.visible = True; speak_btn.icon_color = C()["primary"]
            is_s = w.get("is_starred", 0)
            star_btn.icon = ft.Icons.STAR_ROUNDED if is_s else ft.Icons.STAR_BORDER_ROUNDED
            star_btn.icon_color = C()["star"] if is_s else C()["dim"]
            mcq_col.controls.clear()
            for i, opt in enumerate(mcq["options"]): mcq_col.controls.append(build_opt(opt, i))

        total = len(queue)
        prog = qi/total if total>0 else 0
        pbar.value = prog; pbar.bgcolor = C()["sv"]
        # Fix 4: 多巴胺進度條 — 顏色隨進度變化
        if prog >= 0.8: pbar.color = C()["success"]     # 即將完成 → 綠色
        elif prog >= 0.5: pbar.color = C()["secondary"]  # 一半 → 青色
        else: pbar.color = C()["primary"]                 # 開始 → 紫色
        ptxt.value = f"{qi+1}/{total}"; ptxt.color = C()["dim"]

    def show_done():
        acc=(co/rv*100) if rv>0 else 0
        em="🏆" if acc>=80 else ("👍" if acc>=60 else "💪")
        ms="太棒了！" if acc>=80 else ("不錯！" if acc>=60 else "加油！")
        # Fix 5: 顯示本次連擊 + 歷史最高連擊
        hist_max = S.update_max_combo(combo)
        combo_line = f"🔥 本次連擊: {combo}" if combo >= 2 else ""
        record_line = f"🏅 歷史最高: {hist_max}" if hist_max >= 3 else ""
        review_container.visible=False; done_container.visible=True
        done_items = [
            ft.Text(em,size=64),ft.Container(height=8),
            ft.Text(ms,size=22,weight=ft.FontWeight.W_700,color=C()["on"]),
            ft.Text(f"測驗 {rv} 題 | 正確率 {acc:.0f}%",size=14,color=C()["dim"]),
        ]
        if combo_line:
            done_items.append(ft.Text(combo_line, size=15, weight=ft.FontWeight.W_600,
                color=C()["fire"]))
        if record_line:
            done_items.append(ft.Text(record_line, size=13, color=C()["star"]))
        done_items += [
            ft.Container(height=20),
            ft.Button("再來一輪",icon=ft.Icons.REFRESH_ROUNDED,bgcolor=C()["primary"],
                color="#ffffff",style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=14)),
                on_click=lambda e:retry_review()),
            ft.Container(height=8),
            ft.TextButton("返回",on_click=lambda e:go_back()),
        ]
        done_container.content=ft.Container(content=crd(ft.Column(done_items,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,spacing=2),p=32),
            padding=ft.Padding.symmetric(horizontal=20, vertical=40))

    def retry_review():
        nonlocal queue,qi,rv,co,state,combo
        combo=0
        cid=get_home_cat_id(); lim=get_home_limit()
        td=S.db.get_today_reviewed_count()
        al=max(1, lim - td)
        if review_mode=="global": queue=S.get_all_due_words(al,cid)
        elif review_mode=="starred": queue=S.get_starred_words()
        elif cur_cat and cur_ch: queue=S.get_chapter_queue(cur_cat,cur_ch,due_only=False)
        if not queue: snk("今日目標已完成！"); go_back(); return
        qi=0;rv=0;co=0;state="q";load_mcq()
        done_container.visible=False;review_container.visible=True;page.update()

    def go_back():
        """
        測驗結束/中斷返回。
        確保首頁、章節、統計的資料全部刷新後再切換。
        """
        nonlocal state, _chap_data_cache, _chap_dirty
        state="idle"
        _chap_data_cache = {}; _chap_dirty = True  # 答題後資料已變→清快取
        review_container.visible=False; done_container.visible=False
        nav.selected_index=0; switch_tab(0); page.update()
        # 背景預生成圖表 (資料已變，提前重建快取)
        def _bg():
            try:
                if S.charts_unlocked():
                    S.get_accuracy_chart(dark_mode=dm, category_id=None)
                    S.get_distribution_chart(dark_mode=dm, category_id=None)
            except: pass
        threading.Thread(target=_bg, daemon=True).start()

    def switch_to_review():
        review_container.visible=True; done_container.visible=False

    bk_row = ft.Container(content=ft.Row([
        ft.IconButton(icon=ft.Icons.ARROW_BACK_ROUNDED,icon_color=C()["on"],icon_size=24,
            on_click=lambda e:go_back()),
        ft.Text("四選一測驗",size=16,weight=ft.FontWeight.W_600,color=C()["on"]),
        ft.Container(expand=True),star_btn,speak_btn],
        vertical_alignment=ft.CrossAxisAlignment.CENTER),padding=ft.Padding.symmetric(horizontal=4, vertical=0))

    # 學習卡 UI 組裝
    learn_confirm_btn = ft.Button("我記住了 ✓", bgcolor=C()["success"], color="#ffffff",
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=14),
                             padding=ft.Padding.symmetric(horizontal=32, vertical=14)),
        on_click=on_learn_confirm)
    learn_card_col.controls = [
        ft.Divider(height=1, color=C()["outline"]),
        ft.Container(height=8),
        learn_chi,
        learn_ph,
        ft.Container(height=4),
        learn_ex,
        ft.Container(height=16),
        learn_confirm_btn,
    ]

    review_container.content = ft.Column([bk_row,ft.Row([pbar],expand=False),
        ft.Row([ptxt, ft.Container(expand=True), combo_text],
            vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Container(height=12),
        crd(ft.Column([t_chip,ft.Container(height=10),t_eng,ft.Container(height=4),t_pos,
            learn_card_col],  # 學習卡嵌入英文卡片內
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,spacing=2),p=24),
        ft.Container(height=16),
        ft.Container(content=mcq_col,padding=ft.Padding.symmetric(horizontal=20, vertical=0)),
        ft.Container(height=8),mcq_fb,fb_extra,
        ft.Container(height=8),
        ft.Container(content=continue_btn, alignment=ft.Alignment(0,0))],  # 繼續按鈕
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,spacing=0,scroll=ft.ScrollMode.AUTO)

    mcq_wrapper = ft.Container(content=ft.Column([review_container,done_container],expand=True),
        expand=True,visible=False)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TAB 1: 章節列表 (含 info 圖示)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    chap_section = ft.Container(visible=True,expand=True)
    st_t=ft.Text("0",size=24,weight=ft.FontWeight.W_700)
    st_l=ft.Text("0",size=24,weight=ft.FontWeight.W_700)
    st_d=ft.Text("0",size=24,weight=ft.FontWeight.W_700)
    def sm(lb,ct,ic,cl):
        ct.color=cl
        return ft.Container(content=ft.Column([ft.Icon(ic,size=20,color=cl),ct,
            ft.Text(lb,size=10,color=C()["dim"])],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,spacing=2),
            expand=True,alignment=ft.Alignment(0,0))
    def ref_st(cid=None):
        s=S.db.get_overall_stats(category_id=cid)
        st_t.value=str(s.get("total_words",0));st_t.color=C()["primary"]
        st_l.value=str(s.get("learned",0));st_l.color=C()["secondary"]
        st_d.value=str(s.get("due_today",0));st_d.color=C()["tertiary"]

    CHAP_PAGE = 30  # 每次載入章節數量

    def _mk_chap_card(cid, ch):
        """建立單一章節卡片（精簡版：減少巢狀控件）。"""
        cn,wc,ac,rt,tr = ch["chapter_num"],ch["word_count"],ch["accuracy"],ch["retention"],ch["total_reviews"]
        du = ch["due_words_count"]
        nxt = ch["next_due_date"] or ""
        td = datetime.now().strftime("%Y-%m-%d")
        if tr==0: dc,l1 = C()["dim"],"尚未學習"
        elif ac>=80: dc,l1 = C()["success"],f"答對{ac:.0f}% | 🧠{rt:.0f}%"
        elif ac>=50: dc,l1 = C()["warning"],f"答對{ac:.0f}% | 🧠{rt:.0f}%"
        else: dc,l1 = C()["error"],f"答對{ac:.0f}% | 🧠{rt:.0f}%"
        if du>0: l2,lc = f"🔴 {du}個待複習",C()["error"]
        elif nxt>td:
            try: nf=datetime.strptime(nxt,"%Y-%m-%d").strftime("%m/%d")
            except: nf=nxt
            l2,lc = f"✅ 下次:{nf}",C()["success"]
        else: l2,lc = "尚無排程",C()["dim"]
        pv = rt/100.0 if tr>0 else 0
        def mk(ci,cn_,d): return lambda e:sco(ci,cn_,d)
        # 精簡卡片：用 Text spans 取代多層 Row 巢狀 (16→8 控件)
        return ft.Container(content=ft.Column([
            ft.Row([ft.Container(width=10,height=10,border_radius=5,bgcolor=dc),
                ft.Text(f"第{cn}章",size=15,weight=ft.FontWeight.W_600,color=C()["on"],expand=True),
                ft.Text(f"{wc}字",size=12,color=C()["dim"]),
                ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED,color=C()["dim"],size=20)],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,spacing=8),
            ft.Text(f"  {l1}",size=11,color=C()["dim"]),
            ft.Text(f"  {l2}",size=11,color=lc),
            ft.ProgressBar(value=pv,height=4,border_radius=2,color=dc,bgcolor=C()["outline"])],spacing=3),
            bgcolor=C()["card"],border_radius=14,padding=ft.Padding.symmetric(horizontal=14, vertical=12),
            border=ft.Border.all(width=1, color=C()["outline"]),on_click=mk(cid,cn,du),ink=True)

    cbr=ft.Row(spacing=6,scroll=ft.ScrollMode.AUTO)
    cla=ft.Column(spacing=6,scroll=ft.ScrollMode.AUTO,expand=True)
    aci=0
    _cats_cache = []
    _chap_data_cache = {}     # 快取章節 SQL 資料 {category_id: [dict]}
    _chap_loaded = {}         # 已載入筆數 {category_id: int}
    _chap_dirty = True
    _load_more_btn = ft.Container(
        content=ft.Text("載入更多 ▼",size=14,weight=ft.FontWeight.W_600,
            color=C()["primary"],text_align=ft.TextAlign.CENTER),
        bgcolor=C()["card"],border_radius=14,
        padding=ft.Padding.symmetric(horizontal=20, vertical=14),
        border=ft.Border.all(width=1, color=C()["outline"]),
        ink=True,alignment=ft.Alignment(0,0),visible=False)

    def _load_more_chaps(e):
        """滾動載入：追加下一批章節卡片。"""
        cs = _cats_cache
        if not cs or aci>=len(cs): return
        cid = cs[aci]["id"]
        data = _chap_data_cache.get(cid, [])
        loaded = _chap_loaded.get(cid, 0)
        end = min(loaded + CHAP_PAGE, len(data))
        for ch in data[loaded:end]:
            cla.controls.insert(len(cla.controls)-1, _mk_chap_card(cid, ch))  # 插在按鈕前
        _chap_loaded[cid] = end
        _load_more_btn.visible = (end < len(data))
        page.update()

    _load_more_btn.on_click = _load_more_chaps

    def _get_cats():
        nonlocal _cats_cache
        _cats_cache = S.db.get_categories_with_chapter_count()
        return _cats_cache

    def ocs(e):
        nonlocal aci, _chap_dirty;aci=int(e.control.data);_chap_dirty=True;rcv()
        cs = _cats_cache or _get_cats()
        if cs and aci<len(cs): ref_st(cs[aci]["id"])
        page.update()

    def rcv():
        nonlocal aci, _chap_dirty
        cs = _get_cats()
        if not cs: cla.controls.clear(); return
        if aci>=len(cs): aci=0
        cbr.controls.clear()
        for i,c in enumerate(cs):
            ia=(i==aci);nc=c.get("chapter_count",0)
            cbr.controls.append(ft.Container(content=ft.Text(f"{c['name']}({nc}章)",size=13,
                weight=ft.FontWeight.W_600,color="#ffffff" if ia else C()["dim"]),
                bgcolor=C()["primary"] if ia else C()["card"],border_radius=20,
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),border=ft.Border.all(width=1, color=C()["primary"] if ia else C()["outline"]),
                data=str(i),on_click=ocs,ink=True,animate=ft.Animation(200,ft.AnimationCurve.EASE_OUT)))
        ct=cs[aci]; cid=ct["id"]
        # 只在需要時重新查詢 SQL
        if _chap_dirty or cid not in _chap_data_cache:
            _chap_data_cache[cid] = S.db.get_chapters_for_category(cid)
            _chap_dirty = False
        data = _chap_data_cache[cid]
        # 分頁：只渲染前 CHAP_PAGE 個
        end = min(CHAP_PAGE, len(data))
        _chap_loaded[cid] = end
        cla.controls.clear()
        for ch in data[:end]:
            cla.controls.append(_mk_chap_card(cid, ch))
        _load_more_btn.visible = (end < len(data))
        cla.controls.append(_load_more_btn)
        ref_st(cid)

    def sco(ci,cn,du):
        sd=(du==0)
        dlg=ft.AlertDialog(modal=True,title=ft.Text(f"第{cn}章",weight=ft.FontWeight.W_700,size=18),
            content=ft.Container(content=ft.Column([
                ft.Container(content=ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED,
                    color="#ffffff" if not sd else C()["dim"],size=24),
                    ft.Column([ft.Text("智能測驗",size=15,weight=ft.FontWeight.W_700,
                        color="#ffffff" if not sd else C()["dim"]),
                        ft.Text(f"僅{du}個到期" if du>0 else "沒有到期單字",size=11,
                            color=oc(0.7,"#ffffff") if not sd else C()["dim"])],spacing=2,expand=True)],spacing=12),
                    bgcolor=C()["primary"] if not sd else C()["sv"],border_radius=14,
                    padding=ft.Padding.symmetric(horizontal=16, vertical=14),
                    on_click=(lambda e:(close_dlg(dlg),start_ch(ci,cn,True))) if not sd else None,
                    ink=not sd,opacity=1.0 if not sd else 0.5),
                ft.Container(height=8),
                ft.Container(content=ft.Row([ft.Icon(ft.Icons.MENU_BOOK_ROUNDED,color=C()["on"],size=24),
                    ft.Column([ft.Text("全章學習",size=15,weight=ft.FontWeight.W_700,color=C()["on"]),
                        ft.Text("載入全部單字",size=11,color=C()["dim"])],spacing=2,expand=True)],spacing=12),
                    bgcolor=C()["card"],border_radius=14,padding=ft.Padding.symmetric(horizontal=16, vertical=14),
                    border=ft.Border.all(width=1, color=C()["outline"]),
                    on_click=lambda e:(close_dlg(dlg),start_ch(ci,cn,False)),ink=True)],spacing=0),width=340),
            actions=[ft.TextButton("取消",on_click=lambda e:close_dlg(dlg))])
        page.overlay.append(dlg);dlg.open=True;page.update()

    def start_ch(ci,cn,do=True):
        nonlocal queue,qi,rv,co,state,cur_cat,cur_ch,review_mode,combo
        review_mode="chapter";cur_cat=ci;cur_ch=cn;rv=0;co=0;combo=0
        queue=S.get_chapter_queue(ci,cn,due_only=do)
        if not queue: snk("沒有單字！"); return
        qi=0;state="q";load_mcq();switch_to_review()
        mcq_wrapper.visible=True;chap_section.visible=False;page.update()

    # 章節頁標頭 (含 ⓘ info 按鈕)
    fh=ft.Container(content=ft.Column([
        ft.Row([ft.Text("選擇章節",size=18,weight=ft.FontWeight.W_700,color=C()["on"]),
            ft.IconButton(icon=ft.Icons.INFO_OUTLINE,icon_color=C()["dim"],icon_size=20,
                tooltip="指標說明",on_click=show_info_dialog)],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Container(height=6),
        crd(ft.Row([sm("總單字",st_t,ft.Icons.MENU_BOOK_ROUNDED,C()["primary"]),
            ft.VerticalDivider(width=1,color=C()["outline"]),
            sm("已學習",st_l,ft.Icons.SCHOOL_ROUNDED,C()["secondary"]),
            ft.VerticalDivider(width=1,color=C()["outline"]),
            sm("待複習",st_d,ft.Icons.SCHEDULE_ROUNDED,C()["tertiary"])],
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,height=76),p=12),
        ft.Container(height=6),cbr,ft.Container(height=6)],spacing=0),
        padding=ft.Padding.only(left=20,right=20,top=8))

    chap_section.content=ft.Column([fh,
        ft.Container(content=cla,padding=ft.Padding.symmetric(horizontal=20, vertical=0),expand=True)],spacing=0,expand=True)
    chap_tab=ft.Container(content=ft.Column([chap_section,mcq_wrapper],expand=True),expand=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TAB 2: 搜尋
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    sr=ft.Column(spacing=8,scroll=ft.ScrollMode.AUTO,expand=True);ss=ft.Text("",size=12)
    def ons(e):
        q=e.control.value.strip();sr.controls.clear()
        if not q: ss.value=f"字典樹: {S.trie.size} 字";ss.color=C()["dim"];page.update();return
        res=S.autocomplete(q,max_results=50);ss.value=f"找到 {len(res)} 個";ss.color=C()["dim"]
        for r in res:
            dl=r.get("data",[]);first=dl[0] if isinstance(dl,list) and dl else {}
            chi=first.get("chinese","") if isinstance(first,dict) else ""
            pos=first.get("part_of_speech","") if isinstance(first,dict) else ""
            tags=[]
            if isinstance(dl,list):
                for d in dl:
                    cn_=d.get("category","") if isinstance(d,dict) else ""
                    if cn_: tags.append(ft.Container(content=ft.Text(cn_,size=9,color=C()["primary"]),
                        bgcolor=oc(0.1,C()["primary"]),border_radius=8,padding=ft.Padding.symmetric(horizontal=6, vertical=2)))
            sr.controls.append(ft.Container(content=ft.Column([
                ft.Row([ft.Text(r["word"],size=17,weight=ft.FontWeight.W_600,color=C()["on"],expand=True),
                    ft.Text(chi,size=15,weight=ft.FontWeight.W_600,color=C()["secondary"])],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([ft.Text(pos,size=11,color=C()["dim"]),ft.Container(expand=True)]+tags,spacing=4)],
                spacing=4),bgcolor=C()["card"],border_radius=14,
                padding=ft.Padding.symmetric(horizontal=16, vertical=10),border=ft.Border.all(width=1, color=C()["outline"])))
        page.update()
    search_tab=ft.Container(content=ft.Column([ft.Container(height=10),
        ft.Text("字典搜尋",size=20,weight=ft.FontWeight.W_700,color=C()["on"]),
        ft.Container(height=12),
        ft.TextField(hint_text="輸入英文前綴...",prefix_icon=ft.Icons.SEARCH_ROUNDED,
            border_radius=16,border_color=C()["outline"],focused_border_color=C()["primary"],
            hint_style=ft.TextStyle(color=C()["dim"]),text_style=ft.TextStyle(color=C()["on"]),
            cursor_color=C()["primary"],bgcolor=C()["surface"],on_change=ons),
        ft.Container(height=8),ss,ft.Container(height=4),sr],spacing=0,expand=True),
        padding=ft.Padding.symmetric(horizontal=20, vertical=12),expand=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TAB 3: 統計 (含 ⓘ info 按鈕)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ca_img=ft.Image(src="",fit="contain",border_radius=16)
    ce_img=ft.Image(src="",fit="contain",border_radius=16)
    sa_t=ft.Text("0",size=24,weight=ft.FontWeight.W_700)
    sa_a=ft.Text("0%",size=24,weight=ft.FontWeight.W_700)
    sa_e=ft.Text("2.50",size=24,weight=ft.FontWeight.W_700)
    sa_d=ft.Text("0",size=24,weight=ft.FontWeight.W_700)
    sa_dt=ft.Text("",size=12);cc=ft.Column(spacing=0);scid=None
    scr=ft.Row(spacing=6,scroll=ft.ScrollMode.AUTO)
    _rc_gen = 0  # 競態防護：圖表生成世代計數器
    _stat_cats = []  # 統計頁分類快取 (不重複查 DB)

    def _build_stat_chips():
        """建構統計頁的分類篩選按鈕 (只在初始化/主題切換時呼叫)。"""
        nonlocal _stat_cats
        _stat_cats = S.db.get_categories()
        scr.controls.clear()
        scr.controls.append(ft.Container(content=ft.Text("全部",size=12,weight=ft.FontWeight.W_600,
            color="#ffffff",key="stat_all"),bgcolor=C()["primary"],
            border_radius=16,padding=ft.Padding.symmetric(horizontal=14, vertical=6),
            border=ft.Border.all(width=1, color=C()["primary"]),data="all",on_click=osc,ink=True))
        for c in _stat_cats:
            scr.controls.append(ft.Container(content=ft.Text(c["name"],size=12,
                weight=ft.FontWeight.W_600,color=C()["dim"],key=f"stat_{c['id']}"),
                bgcolor=C()["card"],border_radius=16,
                padding=ft.Padding.symmetric(horizontal=14, vertical=6),
                border=ft.Border.all(width=1, color=C()["outline"]),
                data=str(c["id"]),on_click=osc,ink=True))

    def _update_stat_chip_styles():
        """只更新篩選按鈕的顏色狀態，不重建元件。"""
        for ctrl in scr.controls:
            if not isinstance(ctrl, ft.Container): continue
            v = ctrl.data
            active = (v == "all" and scid is None) or (v != "all" and scid is not None and int(v) == scid)
            ctrl.bgcolor = C()["primary"] if active else C()["card"]
            ctrl.border = ft.Border.all(width=1, color=C()["primary"] if active else C()["outline"])
            if ctrl.content and isinstance(ctrl.content, ft.Text):
                ctrl.content.color = "#ffffff" if active else C()["dim"]

    def osc(e):
        nonlocal scid
        v = e.control.data
        scid = None if v == "all" else int(v)
        # 全部同步更新：按鈕外觀 + 數值 + 鎖定/loading → 一次 page.update()
        _update_stat_chip_styles()
        _update_stat_numbers()
        _update_stat_charts()   # 同步部分 (鎖定/loading) + 啟動背景圖表
        page.update()

    def rscr():
        """初始化/主題切換時重建按鈕。"""
        _build_stat_chips()
        _update_stat_chip_styles()

    def bsc2(lb,ct,cl,ic):
        ct.color=cl
        return ft.Container(content=ft.Column([ft.Icon(ic,size=20,color=cl),ct,
            ft.Text(lb,size=10,color=C()["dim"])],horizontal_alignment=ft.CrossAxisAlignment.CENTER,spacing=2),
            expand=True,alignment=ft.Alignment(0,0))

    def _update_stat_numbers():
        """同步更新統計數值 (不含圖表，極快)。"""
        try:
            gs = S.db.get_global_statistics(category_id=scid)
            sa_t.value = str(gs["total_answers"]); sa_t.color = C()["primary"]
            sa_a.value = f"{gs['accuracy']:.0f}%"; sa_a.color = C()["secondary"]
            sa_e.value = f"{gs['avg_ef']:.2f}"; sa_e.color = C()["tertiary"]
            sa_d.value = str(gs["today_answers"]); sa_d.color = C()["success"]
            sa_dt.value = f"本週:{gs['week_answers']}題 | 已學:{gs['learned']}/{gs['total_words']} | 待複習:{gs['due_today']}"
            sa_dt.color = C()["dim"]
            return gs
        except Exception as ex:
            print(f"Stats err: {ex}")
            return None

    def _show_chart_results(ab, eb):
        """同步把圖表 base64 放入 UI (不呼叫 page.update)。"""
        cc.controls.clear()
        if ab:
            ca_img.src = ab
            cc.controls += [
                ft.Text("歷史正確率",size=13,weight=ft.FontWeight.W_600,color=C()["dim"]),
                ft.Container(height=8),
                crd(ft.Container(content=ca_img,alignment=ft.Alignment(0,0)),p=12),
                ft.Container(height=16)]
        if eb:
            ce_img.src = eb
            cc.controls += [
                ft.Text("難度分布",size=13,weight=ft.FontWeight.W_600,color=C()["dim"]),
                ft.Container(height=8),
                crd(ft.Container(content=ce_img,alignment=ft.Alignment(0,0)),p=12)]

    def _update_stat_charts():
        """快取命中 → 同步顯示；快取未命中 → 背景生成。"""
        nonlocal _rc_gen
        cc.controls.clear()

        if not S.charts_unlocked():
            gs = S.db.get_global_statistics(category_id=scid)
            rem = MIN_REVIEWS_FOR_CHARTS - gs["total_answers"]
            cc.controls.append(crd(ft.Column([ft.Icon(ft.Icons.LOCK_OUTLINED,size=48,color=C()["dim"]),
                ft.Container(height=8),ft.Text(f"累積{MIN_REVIEWS_FOR_CHARTS}次答題解鎖圖表(還需{max(0,rem)}次)",
                    size=14,color=C()["dim"],text_align=ft.TextAlign.CENTER)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER),p=40))
            return

        # 嘗試快取命中 (同步，<1ms)
        ab = S._get_cached_chart("acc", dm, scid)
        eb = S._get_cached_chart("ef", dm, scid)
        if ab is not None or eb is not None:
            _show_chart_results(ab, eb)
            return  # 快取命中，不需要背景執行緒

        # 快取未命中 → loading + 背景生成
        cc.controls.append(ft.Container(
            content=ft.Column([ft.ProgressRing(width=28,height=28,stroke_width=3,color=C()["primary"]),
                ft.Container(height=8),
                ft.Text("正在生成圖表...",size=13,color=C()["dim"])],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,spacing=0),
            padding=ft.Padding.symmetric(horizontal=20, vertical=40),
            alignment=ft.Alignment(0,0)))

        _rc_gen += 1
        gen = _rc_gen

        def _g():
            try:
                if gen != _rc_gen: return
                ab = S.get_accuracy_chart(dark_mode=dm, category_id=scid)
                if gen != _rc_gen: return
                eb = S.get_distribution_chart(dark_mode=dm, category_id=scid)
                if gen != _rc_gen: return
                _show_chart_results(ab, eb)
                if gen != _rc_gen: return
                page.update()
            except Exception as ex:
                print(f"Chart err: {ex}")
        threading.Thread(target=_g, daemon=True).start()

    def rc():
        """完整刷新統計頁。"""
        _update_stat_numbers()
        _update_stat_charts()
        page.update()

    stats_tab=ft.Container(content=ft.Column([ft.Container(height=10),
        ft.Row([ft.Text("學習統計",size=20,weight=ft.FontWeight.W_700,color=C()["on"]),
            ft.Row([
                ft.IconButton(icon=ft.Icons.INFO_OUTLINE,icon_color=C()["dim"],icon_size=20,
                    tooltip="指標說明",on_click=show_stats_info_dialog),
                ft.IconButton(icon=ft.Icons.REFRESH_ROUNDED,icon_color=C()["primary"],icon_size=22,
                    on_click=lambda e:rc())],spacing=0)],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Container(height=8),scr,ft.Container(height=8),
        crd(ft.Column([ft.Row([bsc2("總答題",sa_t,C()["primary"],ft.Icons.QUIZ_ROUNDED),
            ft.VerticalDivider(width=1,color=C()["outline"]),
            bsc2("正確率",sa_a,C()["secondary"],ft.Icons.CHECK_CIRCLE_ROUNDED),
            ft.VerticalDivider(width=1,color=C()["outline"]),
            bsc2("熟練度",sa_e,C()["tertiary"],ft.Icons.SPEED_ROUNDED),
            ft.VerticalDivider(width=1,color=C()["outline"]),
            bsc2("今日",sa_d,C()["success"],ft.Icons.TODAY_ROUNDED)],
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,height=80),ft.Container(height=4),sa_dt],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,spacing=0),p=14),
        ft.Container(height=16),cc,ft.Container(height=30)],
        scroll=ft.ScrollMode.AUTO,spacing=0,expand=True),
        padding=ft.Padding.symmetric(horizontal=20, vertical=12),expand=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 導航 + 主題
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 預建 4 個 tab 容器，用 visible 切換 (0ms vs 重建 300ms+)
    home_tab_wrap = ft.Container(content=ft.Container(content=home_section,
        padding=ft.Padding.symmetric(horizontal=20, vertical=12),expand=True),expand=True,visible=True)
    _tabs_built = False  # 首次建立旗標

    ca=ft.Container(expand=True)
    def switch_tab(idx):
        nonlocal _chap_dirty, _tabs_built
        mcq_wrapper.visible=False;chap_section.visible=True
        review_container.visible=False;done_container.visible=False
        # 首次建立：把 4 個 tab 都放入 ca
        if not _tabs_built:
            ca.content = ft.Stack([home_tab_wrap, chap_tab, search_tab, stats_tab], expand=True)
            _tabs_built = True
        # 切換 visible
        home_tab_wrap.visible = (idx == 0)
        chap_tab.visible = (idx == 1)
        search_tab.visible = (idx == 2)
        stats_tab.visible = (idx == 3)
        # 只刷新資料，不重建 UI
        if idx==0: refresh_home()
        elif idx==1: _chap_dirty=True;ref_st();rcv()
        elif idx==2: ss.value=f"字典樹: {S.trie.size} 字";ss.color=C()["dim"]
        elif idx==3: rscr();rc()
        ca.bgcolor=C()["bg"];page.update()

    nav=ft.NavigationBar(selected_index=0,on_change=lambda e:switch_tab(e.control.selected_index),
        bgcolor=C()["surface"],indicator_color=oc(0.15,C()["primary"]),
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.HOME_OUTLINED,selected_icon=ft.Icons.HOME_ROUNDED,label="首頁"),
            ft.NavigationBarDestination(icon=ft.Icons.SCHOOL_OUTLINED,selected_icon=ft.Icons.SCHOOL_ROUNDED,label="章節"),
            ft.NavigationBarDestination(icon=ft.Icons.SEARCH_OUTLINED,selected_icon=ft.Icons.SEARCH_ROUNDED,label="搜尋"),
            ft.NavigationBarDestination(icon=ft.Icons.BAR_CHART_OUTLINED,selected_icon=ft.Icons.BAR_CHART_ROUNDED,label="統計")])

    tb=ft.IconButton(icon=ft.Icons.LIGHT_MODE_ROUNDED,icon_color=C()["dim"],icon_size=22)
    def tt(e):
        nonlocal dm, _chap_data_cache
        dm=not dm; _chap_data_cache = {}  # 主題變更→清空章節卡片快取
        page.theme_mode=ft.ThemeMode.DARK if dm else ft.ThemeMode.LIGHT
        tb.icon=ft.Icons.LIGHT_MODE_ROUNDED if dm else ft.Icons.DARK_MODE_ROUNDED
        page.bgcolor=C()["bg"];tb.icon_color=C()["dim"]
        tp.bgcolor=C()["surface"];tl.color=C()["on"]
        nav.bgcolor=C()["surface"];nav.indicator_color=oc(0.15,C()["primary"])
        build_home()  # 主題變更需要重建首頁 UI (顏色)
        switch_tab(nav.selected_index)
    tb.on_click=tt
    tl=ft.Text("SRS 單字學習",size=18,weight=ft.FontWeight.W_700,color=C()["on"])
    tp=ft.Container(content=ft.Row([ft.Icon(ft.Icons.AUTO_STORIES_ROUNDED,color=C()["primary"],size=26),
        ft.Container(width=8),tl,ft.Container(expand=True),tb],
        vertical_alignment=ft.CrossAxisAlignment.CENTER),bgcolor=C()["surface"],
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),shadow=ft.BoxShadow(spread_radius=0,blur_radius=6,
            color=oc(0.08,"black"),offset=ft.Offset(0,2)))

    pop_home_dd();ref_st();rcv();rscr();build_home()
    # 預設顯示首頁，隱藏其他 tab
    chap_tab.visible = False; search_tab.visible = False; stats_tab.visible = False
    ca.content = ft.Stack([home_tab_wrap, chap_tab, search_tab, stats_tab], expand=True)
    _tabs_built = True
    ca.bgcolor=C()["bg"]
    page.add(ft.Column([tp,ca,nav],expand=True,spacing=0))

    # 背景預生成圖表 (使用者進統計頁時直接從快取讀取，零延遲)
    def _prewarm_charts():
        try:
            if S.charts_unlocked():
                S.get_accuracy_chart(dark_mode=dm, category_id=None)
                S.get_distribution_chart(dark_mode=dm, category_id=None)
        except Exception:
            pass
    threading.Thread(target=_prewarm_charts, daemon=True).start()

    # ── 優雅關閉 (Graceful Shutdown) ──
    # 攔截視窗關閉事件 → 清理 TTS + SQLite → 再銷毀視窗
    def on_window_event(e):
        if e.data == "close":
            S.cleanup()  # 停止 TTS 工作執行緒 + 關閉 DB 連線
            page.window.destroy()

    try:
        # Flet >= 0.21: window.prevent_close + window.on_event
        page.window.prevent_close = True
        page.window.on_event = on_window_event
    except Exception:
        # 舊版 Flet 或不支援 → 退而求其次用 on_disconnect
        page.on_disconnect = lambda e: S.cleanup()


def safe_main(page):
    try:
        main(page)
    except Exception as e:
        import traceback
        page.add(ft.Text(f"啟動錯誤:\n{traceback.format_exc()}", color="red", size=12, selectable=True))

ft.run(safe_main)
