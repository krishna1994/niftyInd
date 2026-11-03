# Windows Setup Guide — Nifty Signal Analyzer

This guide covers running the app natively on Windows (no WSL required).

---

## Prerequisites

Install these once:

| Tool | Version | Download |
|---|---|---|
| Python | 3.10+ | https://python.org/downloads — ✅ check "Add to PATH" |
| Node.js | 18+ | https://nodejs.org/en/download |
| Git | any | https://git-scm.com/download/win |
| curl | built-in Win10/11 | (already available in cmd/PowerShell) |

> **Python tip**: When installing, check **"Add Python to PATH"** and **"Install pip"**. After install, verify with `python --version` and `pip --version` in a new cmd window.

---

## First-Time Setup

1. **Clone or copy the project** to a local folder, e.g. `C:\niftyInd\`

2. **Open Command Prompt** (or PowerShell) in the project folder:
   ```
   cd C:\niftyInd
   ```

3. **Install all dependencies** (first time only):
   ```
   start.bat --install
   ```
   This runs `pip install -r backend\requirements.txt` and `npm install` in the frontend.

4. **Configure Zerodha** (optional — app works without it):
   - Copy `backend\.env.example` → `backend\.env`
   - Fill in `ZERODHA_API_KEY` and `ZERODHA_API_SECRET`

---

## Running the App

```
start.bat
```

This opens two minimized Command Prompt windows:
- **NiftyBackend** — FastAPI on http://localhost:8000
- **NiftyFrontend** — React on http://localhost:3000

Open http://localhost:3000 in your browser.

### Stopping

```
stop.bat
```

Or close the NiftyBackend and NiftyFrontend windows manually.

---

## Key Differences from WSL/Linux

| Feature | Linux/WSL | Windows |
|---|---|---|
| Start command | `./start.sh` | `start.bat` |
| Stop command | Ctrl-C | `stop.bat` |
| Python command | `python3` | `python` |
| pip command | `pip3` | `pip` |
| Port cleanup | `fuser -k` | `netstat + taskkill` |
| Process kill | `kill -9` | `taskkill /F` |

The backend Python code is fully cross-platform — all file paths use `os.path.join()`, all timezone handling uses `pytz`.

---

## IBKR (Interactive Brokers) on Windows

`ib_insync` requires **SelectorEventLoop** but Python 3.8+ defaults to **ProactorEventLoop** on Windows. This is already fixed in `backend/ibkr_client.py`:

```python
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

You still need **TWS** or **IB Gateway** running locally on port 7497 (paper) or 7496 (live).

---

## QGenie AI Integration on Windows

QGenie is already Windows-aware. The backend auto-detects Windows and routes through `cmd.exe`:

```python
# From backend/qgenie_client.py — already handles Windows
if sys.platform == "win32":
    cmd = ["cmd.exe", "/c", "qgenie", ...]
```

If `qgenie.exe` is in `C:\Users\<you>\AppData\Local\bin\`, add that folder to your PATH.

---

## Troubleshooting

### "python is not recognized"
Add Python to PATH: open **System Properties → Environment Variables → Path** and add `C:\Users\<you>\AppData\Local\Programs\Python\Python3xx\` and `...\Scripts\`.

### "npm is not recognized"
Reinstall Node.js and check "Add to PATH" during installation.

### Port already in use
Run `stop.bat` first, then `start.bat`.

### Backend starts but frontend shows blank page
Wait ~30 seconds — the React dev server takes time to compile on first run. The backend CAS model warm-start also takes ~10s.

### `kiteconnect` not found
```
pip install kiteconnect
```

### `ib_insync` asyncio error on Windows
Already fixed. If you still see it, ensure you're on Python 3.8+ and the fix in `ibkr_client.py` is present.

### NSE option chain returns empty
NSE rate-limits requests. The app retries automatically. Outside market hours (9:15 AM – 3:40 PM IST), the chain may be unavailable.

---

## Environment Variables (backend\.env)

```env
# Zerodha Kite Connect (optional)
ZERODHA_API_KEY=your_api_key_here
ZERODHA_API_SECRET=your_api_secret_here

# IBKR (optional — defaults shown)
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=1
```

Copy `backend\.env.example` to `backend\.env` and fill in your values.