# Wage Tracker 工資記錄計算程式

A self-hosted wage tracking app. Record your daily work hours, overtime, leave days and deductions — see your monthly salary total instantly on both PC and phone.

自架的工資記錄程式：每天輸入上下班時間，自動計算加班費、扣款與當月總工資，電腦與手機共用同一份資料。

---

## Features

- **Bilingual UI** — switch between English and Traditional Chinese with one tap (auto-detects your browser language on first visit)
- **24-hour time input** — enter daily start/end times (e.g. `09:00`–`18:00`); overnight shifts across midnight are handled
- **Four pay modes**
  - *Daily wage*: fixed pay per day (e.g. 750/day)
  - *Monthly salary*: fixed pay per month (e.g. 15000/month); monthly total = salary + overtime − deductions
  - *Hourly wage*: regular hours × hourly rate, overtime hours at the overtime rate
  - *Manual*: type each day's amount yourself (no automatic calculation)
- **Overtime** — hours beyond your normal schedule are paid at a separate hourly rate (e.g. work `09:00`–`20:00` with a `09:00`–`18:00` schedule = 2 h overtime)
- **Leave / holiday records** — mark a day as a day off with a free-text note (e.g. "sick leave"), with an optional deduction amount
- **Lateness tracking** — a "Late" day type, plus automatic detection: if your start time is later than your normal schedule, the entry is flagged with the minutes late and counted in a monthly late-days stat
- **Deductions** — optional amount per day for leave, lateness or early departure
- **Custom currency** — type any currency label (HKD, USD, TWD, …)
- **Monthly overview** — total wage, work days, leave days, overtime hours and totals
- **Pick-any-days sum** — tick checkboxes on any records to see the total for just those days
- **Edit anything** — every record can be edited later, including its date
- **Phone friendly** — responsive mobile UI (cards instead of tables), QR code to open on your phone
- **Remote access** — NAT-PMP / UPnP automatic port forwarding so you can use it away from home
- **Password protected** — 5 wrong attempts locks login for 5 minutes; 5 more locks it until you press *Unlock* on the PC; logged-in devices stay logged in for 30 days of inactivity
- **Your data stays yours** — everything is stored in a JSON file on your own PC; no cloud, no account

## Requirements

- Windows with [Python 3](https://www.python.org/downloads/) installed
- One package: `py -m pip install qrcode` (auto-installed on first run if missing)

## Quick start

1. Download / clone this repository.
2. Double-click **`啟動器.pyw`** (the launcher).
   - A window opens showing a **QR code** — the local server is now running.
3. On first run a **`config.json`** is created with the default password **`123456`** — open it and change the password before anything else:
   ```json
   { "password": "your-password-here" }
   ```
4. Click **在電腦瀏覽器開啟** (Open in browser) on the PC, or scan the QR code with your phone (same Wi-Fi), then enter your password.

> The HTML file also works standalone (double-click it) without the launcher — in that mode data is stored in that browser only and there is no password or syncing.

## Using it

| Action | How |
|---|---|
| Record a work day | Pick the date, enter start/end time, press **新增記錄** (Add) |
| Record overtime | Just enter the real end time — extra hours beyond your normal schedule are computed automatically |
| Record a leave day | Set 類型 (Type) to **休假／假日** (Day off), optionally write a note and a deduction |
| Fix a mistake | Press the ✎ **edit** button on any record — you can change everything, including the date |
| Sum specific days | Tick the checkboxes next to records; the selected total updates instantly |
| Change settings | Currency, normal schedule, wage amounts — all saved automatically |

## Phone access from anywhere (remote)

The launcher automatically asks your router to forward port `8899` (NAT-PMP first, UPnP as fallback):

1. In the launcher window switch to **外網（任何網路）** (Remote) to show the remote QR code.
2. Scan it — works on 4G/5G or any network, protected by your password.
3. If the phone cannot connect, run **`開放防火牆_手機連線用.bat`** once as Administrator to open the Windows Firewall port.

Notes:
- Your home public IP may change occasionally; the launcher always shows the current URL.
- If your router supports neither NAT-PMP nor UPnP, forward TCP port `8899` to your PC manually in the router admin page.
- Traffic is plain HTTP — use a strong password, or keep remote access for trusted situations.

## Login lockout rules

| Event | Result |
|---|---|
| 5 wrong passwords | Locked for 5 minutes (even the correct password is rejected) |
| 5 more wrong passwords after the lock | **Hard-locked** — nobody can log in |
| Press **解鎖** (Unlock) in the launcher window | Resets everything and signs out all devices |
| A device logs in successfully | Stays logged in; only expires after 30 days without use |

## Data & files

| File | Purpose | In git? |
|---|---|---|
| `工資記錄計算程式.html` | The app (front end) | ✔ |
| `啟動器.pyw` | Launcher: server, QR codes, port forwarding, autostart | ✔ |
| `開放防火牆_手機連線用.bat` | One-time firewall helper | ✔ |
| `config.json` | **Your password** | ✘ (created on first run) |
| `wage_data.json` | **Your wage records** | ✘ |
| `auth_state.json`, `tokens.json` | Login state | ✘ |

Back up `wage_data.json` to keep your records safe.

## Version

- **1.4** — "Late" day type with automatic lateness detection and a monthly late-days stat
- **1.3** — collapsible settings panel (tap the header to expand/collapse, state remembered)
- **1.2** — two new pay modes: hourly wage and manual daily amount
- **1.1** — bilingual UI (English / 繁體中文) with one-tap language switch
- **1.0** — first public release

---

# 中文使用說明

## 快速開始

1. 安裝 [Python 3](https://www.python.org/downloads/)（Windows）
2. 雙擊 **`啟動器.pyw`** 開啟啟動器，視窗會顯示二維碼
3. 首次執行會自動產生 `config.json`，預設密碼 **`123456`**，請先打開改成自己的密碼
4. 電腦按「在電腦瀏覽器開啟」；手機連同一個 Wi-Fi 掃碼，輸入密碼即可使用

## 日常使用

- **記錄上班**：選日期、輸入上下班時間（24 小時制）、按「新增記錄」，超出正常時間的部分自動算加班費
- **記錄休假**：類型選「休假／假日」，可自由填備註（如「有事請假」）和扣款金額
- **修改記錄**：按記錄上的 ✎ 編輯按鈕，日期輸錯也能改
- **自選日數合計**：勾選任何幾天的記錄，即時顯示那幾天的工資合計
- **計薪方式**：日薪（每日固定）、月薪（每月固定 ＋ 加班 − 扣款）、時薪（正常時數 × 時薪 ＋ 加班費）、手動輸入（每天自行填金額）四種模式

## 外網連線

啟動器會自動向路由器申請開埠（NAT-PMP／UPnP）。視窗切到「外網」掃碼即可在任何網路使用。手機連不上時，用系統管理員身分執行一次 `開放防火牆_手機連線用.bat`。

## 密碼保護

錯 5 次鎖 5 分鐘；再錯 5 次鎖死，需在電腦啟動器按「解鎖」。登入過的裝置 30 天內免密碼。

## 資料備份

所有記錄存在電腦的 `wage_data.json`，建議定期備份。
