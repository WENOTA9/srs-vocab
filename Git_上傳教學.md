# Git 上傳教學 — SRS Vocab 專案

## 🎯 目標

將三個平台的 source code 上傳到同一個 GitHub repo，用 3 個 branch 分離，再透過 Releases 上傳打包好的 APK / EXE / .app。

---

## 📋 事前準備

### 1. 安裝 Git

macOS 已內建。如沒有，執行：
```bash
brew install git
```

### 2. 設定 Git 身分（一次性）

```bash
git config --global user.name "張哲維"
git config --global user.email "你的email@example.com"
```

### 3. 建立 GitHub 帳號

前往 https://github.com/signup 註冊（若已有帳號跳過）。

### 4. 建立 SSH 金鑰（推薦，免每次輸入密碼）

```bash
# 產生金鑰（三次 Enter 用預設值即可）
ssh-keygen -t ed25519 -C "你的email@example.com"

# 複製公鑰
cat ~/.ssh/id_ed25519.pub
```

將複製的內容貼到 GitHub → Settings → SSH and GPG keys → New SSH key。

測試連線：
```bash
ssh -T git@github.com
# 應看到：Hi xxx! You've successfully authenticated...
```

---

## 🚀 Step-by-Step 上傳流程

### Step 1：於 GitHub 建立空 repo

1. 前往 https://github.com/new
2. Repository name：`srs-vocab`
3. 選 **Public**
4. ❌ 不要勾 "Initialize with README"（我們本地已有）
5. 點 "Create repository"

GitHub 會給你一個 SSH URL，類似：
```
git@github.com:你的帳號/srs-vocab.git
```
**複製起來，下一步要用**。

### Step 2：準備本地專案資料夾

建立 3 個獨立資料夾，分別放三平台的 source code：

```
~/srs-vocab-all/
├── mac/          ← 你的 macOS 版 main.py + backend.py + assets
├── windows/      ← 你的 Windows 版 main.py + backend.py + assets
└── android/      ← 你的 Android 版 main.py + backend.py + assets
```

### Step 3：建立 main branch（共用說明）

```bash
# 先建一個空資料夾當 main branch 根目錄
mkdir ~/srs-vocab-main
cd ~/srs-vocab-main

# 把 README.md 和 .gitignore 放進去（我產的那兩個）
# 也可以把 benchmarks/ 資料夾一起放

# 初始化 git
git init
git branch -M main

# 加入檔案
git add .
git commit -m "Initial commit: README + benchmarks"

# 連接到 GitHub（把 URL 換成你的）
git remote add origin git@github.com:你的帳號/srs-vocab.git

# 推上去
git push -u origin main
```

### Step 4：建立 macos branch

```bash
# 切到 mac 版 source code 資料夾
cd ~/srs-vocab-all/mac

# 初始化 git
git init
git branch -M macos

# 加入 .gitignore（重要！避免傳上 __pycache__、.db 等）
cp ~/srs-vocab-main/.gitignore .

# 加入所有檔案
git add .
git commit -m "macOS version"

# 連接到同一個遠端 repo
git remote add origin git@github.com:你的帳號/srs-vocab.git

# 推上 macos branch
git push -u origin macos
```

### Step 5：建立 windows branch

```bash
cd ~/srs-vocab-all/windows
git init
git branch -M windows
cp ~/srs-vocab-main/.gitignore .
git add .
git commit -m "Windows version"
git remote add origin git@github.com:你的帳號/srs-vocab.git
git push -u origin windows
```

### Step 6：建立 android branch

```bash
cd ~/srs-vocab-all/android
git init
git branch -M android
cp ~/srs-vocab-main/.gitignore .
git add .
git commit -m "Android version"
git remote add origin git@github.com:你的帳號/srs-vocab.git
git push -u origin android
```

### Step 7：驗證

前往 `https://github.com/你的帳號/srs-vocab`，點左上角「branches」切換查看四個 branch：`main`、`macos`、`windows`、`android`。

---

## 📦 上傳編譯後的 APK / EXE / .app (Releases)

程式碼已在 branch 內，但 **編譯後的大檔案**（如 `.app`、`.exe`、`.apk`）不該用 git 追蹤，應該用 **Releases** 功能上傳：

### Step 8：建立 Release

1. 前往你的 repo → 點右側「Releases」→ 「Create a new release」
2. **Tag**：填 `v1.0`
3. **Release title**：`SRS Vocab v1.0 — 跨平台英文單字學習系統`
4. **Description**：貼以下範本：

```
## 下載對應平台版本

- 🍎 **macOS**: 下載 `SRS_Vocab_v1.0_macOS.app.zip`
- 🪟 **Windows**: 下載 `SRS_Vocab_v1.0_Windows.exe`
- 🤖 **Android**: 下載 `SRS_Vocab_v1.0.apk`

## 系統需求

- macOS 12+ / Windows 10+ / Android 8+

## 主要功能

- SM-2 間隔重複排程
- Trie 即時字典搜尋 (6,122 字)
- 分類池 MCQ 測驗
- 明暗主題切換
- 跨平台資料格式一致
```

5. 拖放檔案到下方「Attach binaries」區域：
   - `SRS_Vocab_v1.0_macOS.app.zip`（先把 .app 壓縮成 zip）
   - `SRS_Vocab_v1.0_Windows.exe`
   - `SRS_Vocab_v1.0.apk`
6. 點「Publish release」

> 💡 GitHub Releases 單一檔案上限 2 GB，你的應該遠低於這限制。

### 如何把 .app 壓縮成 zip？

```bash
cd ~/Desktop  # 或 .app 所在資料夾
zip -r SRS_Vocab_v1.0_macOS.app.zip SRS_Vocab.app
```

---

## 🔄 日後更新程式碼

假設你修了 macOS 版的 bug：

```bash
cd ~/srs-vocab-all/mac

# 確認在 macos branch
git branch  # 應該顯示 * macos

# 修改檔案後
git add .
git commit -m "fix: 修正統計頁卡頓"
git push
```

---

## ❓ 常見錯誤排除

### 錯誤 1：`error: failed to push some refs`

原因：遠端有更新你沒 pull。

```bash
git pull origin 你的branch --rebase
git push
```

### 錯誤 2：不小心 commit 了 .db 檔案

```bash
# 從追蹤中移除（但保留本機檔案）
git rm --cached srs_vocab.db
git commit -m "remove db from tracking"
git push
```

### 錯誤 3：`Permission denied (publickey)`

SSH 金鑰沒設好，回到事前準備第 4 步重做。

---

## 📝 交件 checklist

繳交期末時，老師應能看到：

- ✅ GitHub repo URL（例：`https://github.com/你的帳號/srs-vocab`）
- ✅ 四個 branch：`main` / `macos` / `windows` / `android`
- ✅ Releases 頁面有三個可下載的編譯檔
- ✅ README.md 說明清楚

有問題隨時問！
