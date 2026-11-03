# Troubleshooting Guide: Broker Connection Issues

## Issue 1: Zerodha Login Redirect Fails (HTTPS Error)

### Symptom
When trying to connect to Zerodha, you are redirected to `https://127.0.0.1:3000/settings?...` and the browser shows "Connection Refused" or "SSL Error".

### Root Cause
The React development server runs on **HTTP** (`http://localhost:3000`), not HTTPS. If your Zerodha Kite Developer Console has the redirect URI configured as `https://127.0.0.1:3000`, the browser will fail to connect because:
1. The local server doesn't support SSL/TLS
2. Browsers treat `http` and `https` as different origins

### Solution
1. **Go to your Zerodha Kite Developer Console**: https://developers.kite.trade/apps
2. **Edit your app settings**
3. **Change the Redirect URL** from:
   ```
   https://127.0.0.1:3000/settings
   ```
   to:
   ```
   http://localhost:3000/settings
   ```
4. **Save the changes**
5. **Try connecting again** from the Settings page

### Alternative: Use the Auto-Login Feature
If you don't want to deal with browser redirects, use the **Auto-Login** feature:
1. Go to **Settings** → **Zerodha Integration**
2. Click **"Auto-Login"**
3. Enter your Zerodha User ID, Password, and TOTP Secret
4. The system will handle the login automatically without any browser redirect

---

## Issue 2: IBKR Positions Not Showing

### Symptom
You have TWS (Trader Workstation) or IB Gateway running and have enabled "Socket Clients", but the Global Portfolio shows "OFFLINE" for IBKR and no positions appear.

### Root Cause
There are three common reasons:

#### 1. Wrong Port
- **TWS Paper Trading** uses port `7497`
- **TWS Live Trading** uses port `7496`
- **IB Gateway Paper** uses port `4002`
- **IB Gateway Live** uses port `4001`

The system defaults to port `7497`. If you're using a Live account, it will fail to connect.

#### 2. Socket Clients Not Enabled
TWS/Gateway must explicitly allow API connections.

#### 3. Connection Timeout
The `ib_insync` library requires an active event loop. If the connection drops, it won't auto-reconnect.

### Solution

#### Step 1: Verify TWS/Gateway Settings
1. **Open TWS or IB Gateway**
2. **Log in to your account**
3. Go to **Global Configuration** → **API** → **Settings**
4. **Check the following**:
   - ✅ **"Enable ActiveX and Socket Clients"** must be checked
   - ✅ **"Socket port"** should show `7496` (Live) or `7497` (Paper)
   - ✅ **"Trusted IP Addresses"** should include `127.0.0.1`
5. Click **Apply** and **OK**

#### Step 2: Configure the Correct Port (Optional)
If you're using a Live account, create a `backend/.env` file and add:
```bash
IBKR_PORT=7496
```

For Paper Trading (default):
```bash
IBKR_PORT=7497
```

#### Step 3: Restart the Backend
The updated `ibkr_client.py` now automatically tries both ports (7496 and 7497), so you don't need to manually configure the port unless you're using IB Gateway.

```bash
./start.sh
```

#### Step 4: Verify Connection
1. Check the backend logs for:
   ```
   INFO:ibkr_client:Attempting IBKR connection on 127.0.0.1:7497...
   INFO:ibkr_client:Successfully connected to IBKR at 127.0.0.1:7497
   ```
2. If you see "Connection failed on port 7497", it will automatically try 7496.
3. Go to **Global Portfolio** and check if the IBKR status badge shows **"● LIVE"**

---

## Issue 3: No Positions Showing Even After Connection

### Symptom
IBKR shows "● LIVE" but the positions list is empty, even though you have open positions in TWS.

### Root Cause
The `ib_insync` library caches position data. If you opened positions **before** connecting the app, they might not be fetched immediately.

### Solution
1. **Refresh the page** (F5 or Ctrl+R)
2. **Wait 30 seconds** for the auto-refresh cycle
3. **Check TWS**: Ensure the positions are actually open (not closed or pending)
4. **Restart TWS and the Backend**: Sometimes TWS needs a fresh session

---

## Quick Diagnostic Commands

### Test Zerodha Connection
```bash
cd backend
python3 test_connections.py
```

Expected output:
```
--- Testing ZERODHA Connection ---
Status: {'installed': True, 'configured': True, 'connected': True, ...}
✅ Connection Successful!
```

### Test IBKR Connection
```bash
cd backend
python3 test_connections.py
```

Expected output:
```
--- Testing IBKR Connection ---
Status: {'connected': True, 'message': 'Connected to IBKR'}
✅ Connection Successful!
```

---

## Still Having Issues?

### Check Backend Logs
The backend logs show detailed connection attempts:
```bash
# If using start.sh, logs are printed to the terminal
# Look for lines starting with:
INFO:ibkr_client:...
INFO:zerodha_client:...
```

### Common Error Messages

| Error | Meaning | Solution |
|-------|---------|----------|
| `Connection refused` | TWS/Gateway not running | Launch TWS/Gateway and log in |
| `Socket Clients not enabled` | API access blocked | Enable in TWS settings |
| `Invalid request_token` | Zerodha redirect failed | Check redirect URI in Kite Console |
| `Session expired` | Zerodha token expired | Reconnect via Settings |
| `Port 7497 failed` | Wrong port for Live account | Set `IBKR_PORT=7496` in `.env` |

---

## Summary Checklist

### For Zerodha:
- [ ] API Key and Secret are in `backend/.env`
- [ ] Redirect URI in Kite Console is `http://localhost:3000/settings`
- [ ] You clicked "Connect to Zerodha" in Settings
- [ ] The browser successfully redirected back with a `request_token`

### For IBKR:
- [ ] TWS or IB Gateway is running and logged in
- [ ] "Enable ActiveX and Socket Clients" is checked in TWS settings
- [ ] The correct port is configured (7496 for Live, 7497 for Paper)
- [ ] The backend logs show "Successfully connected to IBKR"
- [ ] The Global Portfolio shows "● LIVE" for IBKR

Once both are connected, your positions will appear in the **Global Portfolio** page automatically.