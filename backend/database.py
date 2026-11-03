"""
SQLite database layer for Nifty Signal Analyzer.

Tables:
  backtest_cache  — cache expensive backtest runs (keyed by params + date)
  dry_run_trades  — paper trading journal
  signal_log      — history of every signal generated
"""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "nifty_signal.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_conn()
    c = conn.cursor()

    # ── Backtest cache ────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS backtest_cache (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            period              TEXT    NOT NULL,
            confidence_threshold REAL   NOT NULL,
            signal_type         TEXT    NOT NULL,
            run_date            TEXT    NOT NULL,
            result_json         TEXT    NOT NULL,
            created_at          TEXT    NOT NULL
        )
    """)
    c.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_backtest_cache_key
        ON backtest_cache (period, confidence_threshold, signal_type, run_date)
    """)

    # ── Dry run (paper trading) trades ────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS dry_run_trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date      TEXT    NOT NULL,
            signal          TEXT    NOT NULL,
            strike          TEXT    NOT NULL,
            entry_spot      REAL    NOT NULL,
            sl              REAL    NOT NULL,
            target          REAL    NOT NULL,
            dte             INTEGER NOT NULL,
            max_hold_days   INTEGER NOT NULL,
            confidence      REAL    NOT NULL,
            vix             REAL    NOT NULL DEFAULT 15.0,
            status          TEXT    NOT NULL DEFAULT 'OPEN',
            exit_date       TEXT,
            exit_spot       REAL,
            exit_reason     TEXT,
            pct_return      REAL,
            result          TEXT,
            notes           TEXT,
            created_at      TEXT    NOT NULL
        )
    """)

    # ── Signal history log ────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS signal_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL,
            signal          TEXT    NOT NULL,
            direction       TEXT    NOT NULL,
            confidence      REAL    NOT NULL,
            spot            REAL    NOT NULL,
            vix             REAL    NOT NULL,
            indicators_json TEXT
        )
    """)

    # ── Generic app settings (key-value store) ────────────────────────────────
    # Used for things like the cached Zerodha access token, and any other
    # small pieces of app state that need to survive server restarts but
    # don't warrant their own dedicated table.
    c.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key         TEXT PRIMARY KEY,
            value       TEXT,
            updated_at  TEXT NOT NULL
        )
    """)

    # ── User-added custom watchlist symbols ──────────────────────────────────
    # Lets the user search for and add ANY stock/ETF ticker (beyond the
    # fixed built-in watchlist) to get the same live tracker + signal
    # analysis. Persisted so custom symbols survive server restarts.
    c.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_custom_symbols (
            symbol      TEXT PRIMARY KEY,
            name        TEXT,
            added_at    TEXT NOT NULL
        )
    """)

    # ── Manually-entered eToro portfolio holdings ─────────────────────────────
    # eToro does not offer a public/self-serve API for retail accounts (no
    # equivalent to Zerodha's Kite Connect) — confirmed via direct testing
    # (their endpoints return 401/403 without partner-level credentials, and
    # no maintained Python client exists). So this is a MANUAL entry table:
    # the user types in what they actually hold on eToro (symbol, quantity,
    # entry price), and the app applies live price + the same technical
    # analysis engine used elsewhere to compute real P&L and a suggestion.
    c.execute("""
        CREATE TABLE IF NOT EXISTS etoro_holdings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT    NOT NULL,
            name            TEXT,
            quantity        REAL    NOT NULL,
            entry_price     REAL    NOT NULL,
            notes           TEXT,
            added_at        TEXT    NOT NULL
        )
    """)

    # ── Auto-trader audit log ──────────────────────────────────────────────────
    # Every decision the auto-trader makes — whether it actually placed a real
    # order or skipped one (and why) — is logged here. This is the audit trail
    # for a feature that touches real money; nothing about auto-trading
    # activity should ever be invisible/undebuggable.
    c.execute("""
        CREATE TABLE IF NOT EXISTS auto_trade_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp           TEXT    NOT NULL,
            action              TEXT    NOT NULL,   -- TRADE_PLACED, SKIPPED, ERROR, EXIT_PLACED, KILL_SWITCH
            reason              TEXT,               -- human-readable explanation
            signal_direction    TEXT,               -- BULLISH / BEARISH
            strike              INTEGER,
            option_type         TEXT,               -- CE / PE
            tradingsymbol       TEXT,
            quantity            INTEGER,
            entry_price         REAL,
            sl_price            REAL,
            target_price        REAL,
            order_id            TEXT,
            gtt_id              TEXT,
            pop                 REAL,               -- calibrated POP at time of decision
            high_conviction     INTEGER,            -- 1/0
            details_json        TEXT
        )
    """)

    conn.commit()
    conn.close()


# ── Backtest cache helpers ─────────────────────────────────────────────────────

def get_cached_backtest(period: str, confidence_threshold: float, signal_type: str):
    """Return cached backtest result for today's date, or None."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    row = conn.execute(
        """SELECT result_json FROM backtest_cache
           WHERE period=? AND confidence_threshold=? AND signal_type=? AND run_date=?""",
        (period, confidence_threshold, signal_type, today)
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row["result_json"])
    return None


def save_backtest_cache(period: str, confidence_threshold: float, signal_type: str, result: dict):
    """Upsert a backtest result into the cache."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    conn.execute(
        """INSERT INTO backtest_cache
               (period, confidence_threshold, signal_type, run_date, result_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(period, confidence_threshold, signal_type, run_date)
           DO UPDATE SET result_json=excluded.result_json, created_at=excluded.created_at""",
        (period, confidence_threshold, signal_type, today,
         json.dumps(result), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def clear_backtest_cache():
    """Delete all cached backtest results."""
    conn = get_conn()
    conn.execute("DELETE FROM backtest_cache")
    conn.commit()
    conn.close()


# ── Dry run trade helpers ──────────────────────────────────────────────────────

def create_dry_run_trade(trade: dict) -> int:
    """Insert a new paper trade. Returns the new row id."""
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO dry_run_trades
               (entry_date, signal, strike, entry_spot, sl, target,
                dte, max_hold_days, confidence, vix, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)""",
        (
            trade["entry_date"], trade["signal"], trade["strike"],
            trade["entry_spot"], trade["sl"], trade["target"],
            trade["dte"], trade["max_hold_days"], trade["confidence"],
            trade.get("vix", 15.0), datetime.now().isoformat()
        )
    )
    conn.commit()
    trade_id = cur.lastrowid
    conn.close()
    return trade_id


def get_dry_run_trades(status: str = None):
    """Return all dry run trades, optionally filtered by status."""
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM dry_run_trades WHERE status=? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM dry_run_trades ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def close_dry_run_trade(trade_id: int, exit_spot: float, exit_reason: str,
                         pct_return: float, result: str):
    """Mark a paper trade as closed."""
    conn = get_conn()
    conn.execute(
        """UPDATE dry_run_trades
           SET status='CLOSED', exit_date=?, exit_spot=?, exit_reason=?,
               pct_return=?, result=?
           WHERE id=?""",
        (datetime.now().strftime("%Y-%m-%d"), exit_spot, exit_reason,
         pct_return, result, trade_id)
    )
    conn.commit()
    conn.close()


def delete_dry_run_trade(trade_id: int):
    """Hard-delete a paper trade."""
    conn = get_conn()
    conn.execute("DELETE FROM dry_run_trades WHERE id=?", (trade_id,))
    conn.commit()
    conn.close()


def clear_dry_run_trades():
    """Delete all paper trades."""
    conn = get_conn()
    conn.execute("DELETE FROM dry_run_trades")
    conn.commit()
    conn.close()


# ── Signal log helpers ─────────────────────────────────────────────────────────

def log_signal(signal_data: dict):
    """Append a signal to the history log."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO signal_log
               (timestamp, signal, direction, confidence, spot, vix, indicators_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(),
            signal_data.get("signal", ""),
            signal_data.get("direction", ""),
            signal_data.get("confidence", 0.0),
            signal_data.get("spot", 0.0),
            signal_data.get("vix", 0.0),
            json.dumps(signal_data.get("indicators", {}))
        )
    )
    conn.commit()
    conn.close()


def get_signal_history(limit: int = 50):
    """Return the most recent signal log entries."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM signal_log ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Generic app settings (key-value store) ────────────────────────────────────
# Simple persistent key-value storage, e.g. used by zerodha_client.py to cache
# the daily access token across server restarts.

def get_setting(key: str) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return row["value"]


def set_setting(key: str, value: str):
    conn = get_conn()
    conn.execute(
        """INSERT INTO app_settings (key, value, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (key, value, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


# ── Custom watchlist symbols (user-searched, added beyond the built-in list) ──

def add_custom_watchlist_symbol(symbol: str, name: str = None):
    """Persist a user-added custom watchlist ticker. Idempotent (upsert)."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO watchlist_custom_symbols (symbol, name, added_at)
           VALUES (?, ?, ?)
           ON CONFLICT(symbol) DO UPDATE SET name=excluded.name""",
        (symbol.upper(), name, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_custom_watchlist_symbols():
    """Returns [{"symbol": ..., "name": ..., "added_at": ...}, ...] in the
    order they were added (oldest first)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT symbol, name, added_at FROM watchlist_custom_symbols ORDER BY added_at ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remove_custom_watchlist_symbol(symbol: str):
    conn = get_conn()
    conn.execute("DELETE FROM watchlist_custom_symbols WHERE symbol=?", (symbol.upper(),))
    conn.commit()
    conn.close()


# ── Manually-entered eToro portfolio holdings ─────────────────────────────────
# See the etoro_holdings table comment above for why this is manual entry
# rather than a live API sync (eToro has no self-serve retail API).

def add_etoro_holding(symbol: str, name: str, quantity: float, entry_price: float, notes: str = "") -> int:
    """Insert a new manually-entered eToro holding. Returns the new row id."""
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO etoro_holdings (symbol, name, quantity, entry_price, notes, added_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (symbol.upper(), name, quantity, entry_price, notes, datetime.now().isoformat())
    )
    conn.commit()
    holding_id = cur.lastrowid
    conn.close()
    return holding_id


def get_etoro_holdings():
    """Returns all manually-entered eToro holdings (oldest first)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM etoro_holdings ORDER BY added_at ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_etoro_holding(holding_id: int, quantity: float = None, entry_price: float = None, notes: str = None):
    """Partial update of an existing eToro holding (e.g. after averaging up/down)."""
    conn = get_conn()
    existing = conn.execute("SELECT * FROM etoro_holdings WHERE id=?", (holding_id,)).fetchone()
    if not existing:
        conn.close()
        return False
    new_quantity = quantity if quantity is not None else existing["quantity"]
    new_entry = entry_price if entry_price is not None else existing["entry_price"]
    new_notes = notes if notes is not None else existing["notes"]
    conn.execute(
        "UPDATE etoro_holdings SET quantity=?, entry_price=?, notes=? WHERE id=?",
        (new_quantity, new_entry, new_notes, holding_id)
    )
    conn.commit()
    conn.close()
    return True


def delete_etoro_holding(holding_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM etoro_holdings WHERE id=?", (holding_id,))
    conn.commit()
    conn.close()


# ── Auto-trader audit log helpers ──────────────────────────────────────────────

def log_auto_trade_event(event: dict):
    """
    Append one entry to the auto-trader audit log. `event` should include at
    minimum `action` and `reason`; all other fields are optional and default
    to None. Called for EVERY decision (placed, skipped, error) so the full
    history is always inspectable — this is the safety-critical audit trail
    for a feature that can place real orders with real money.
    """
    conn = get_conn()
    conn.execute(
        """INSERT INTO auto_trade_log
               (timestamp, action, reason, signal_direction, strike, option_type,
                tradingsymbol, quantity, entry_price, sl_price, target_price,
                order_id, gtt_id, pop, high_conviction, details_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(),
            event.get("action", "UNKNOWN"),
            event.get("reason"),
            event.get("signal_direction"),
            event.get("strike"),
            event.get("option_type"),
            event.get("tradingsymbol"),
            event.get("quantity"),
            event.get("entry_price"),
            event.get("sl_price"),
            event.get("target_price"),
            event.get("order_id"),
            event.get("gtt_id"),
            event.get("pop"),
            1 if event.get("high_conviction") else 0,
            json.dumps(event.get("details", {})),
        )
    )
    conn.commit()
    conn.close()


def get_auto_trade_log(limit: int = 100):
    """Return the most recent auto-trader audit log entries (newest first)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM auto_trade_log ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_auto_trades_today() -> int:
    """Count how many TRADE_PLACED events happened today (for the daily
    max-trades-per-day guardrail)."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM auto_trade_log
           WHERE action='TRADE_PLACED' AND timestamp LIKE ?""",
        (f"{today}%",)
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def sum_auto_trade_realized_pnl_today() -> float:
    """
    Sum of realized P&L (in rupees) from auto-trades closed today, based on
    details_json['realized_pnl'] recorded at EXIT_PLACED time. Used for the
    daily loss circuit-breaker. Returns 0.0 if no exits recorded yet today.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    rows = conn.execute(
        """SELECT details_json FROM auto_trade_log
           WHERE action='EXIT_RECORDED' AND timestamp LIKE ?""",
        (f"{today}%",)
    ).fetchall()
    conn.close()
    total = 0.0
    for r in rows:
        try:
            details = json.loads(r["details_json"] or "{}")
            total += float(details.get("realized_pnl", 0.0))
        except Exception:
            continue
    return total
