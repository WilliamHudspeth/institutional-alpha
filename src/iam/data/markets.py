"""Live market-data layer for the Alpha Terminal.

Provides a single, cached source of truth for:
    * per-ticker quotes (last, % change, intraday history for sparklines)
    * a global macro snapshot (US / Europe / Asia indices, the rates curve,
      FX, commodities, vol)

Design goals
------------
* **Never block the render loop.**  Panels call :func:`get_snapshot` /
  :func:`get_quote`, which return instantly from an in-memory cache and kick off
  a *background* refresh when data is stale.
* **Fail soft.**  A network error returns the last good (stale-flagged) value;
  it never raises into the UI thread.
* **Polite to Yahoo.**  TTL caching (quotes ~60s, macro ~10min) plus a single
  shared refresh thread per key prevents hammering the source.
* **Degrades without yfinance.**  If the dependency is missing the module emits
  deterministic mock data so the TUI still runs (mirrors the repo's mock mode).

yfinance is unofficial and rate-limited; for production rates you'd prefer FRED
(DGS2/DGS10/DGS30).  A FRED hook point is marked below.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

try:  # pragma: no cover - exercised implicitly
    import yfinance as yf

    _HAS_YF = True
except Exception:  # noqa: BLE001
    yf = None  # type: ignore
    _HAS_YF = False


# ── Symbol universe ──────────────────────────────────────────────────────────
# (yahoo symbol, display label, group, is_rate)
MARKET_GROUPS: dict[str, list[tuple[str, str]]] = {
    "US": [
        ("^GSPC", "S&P 500"),
        ("^IXIC", "Nasdaq"),
        ("^DJI", "Dow"),
        ("^RUT", "Russell 2K"),
    ],
    "EUROPE": [
        ("^STOXX50E", "Euro Stoxx 50"),
        ("^GDAXI", "DAX"),
        ("^FTSE", "FTSE 100"),
        ("^FCHI", "CAC 40"),
    ],
    "ASIA": [
        ("^N225", "Nikkei 225"),
        ("^HSI", "Hang Seng"),
        ("000001.SS", "Shanghai"),
        ("^KS11", "KOSPI"),
    ],
    "RATES": [
        ("^IRX", "13wk Bill"),
        ("^FVX", "US 5Y"),
        ("^TNX", "US 10Y"),
        ("^TYX", "US 30Y"),
    ],
    "FX_COMMODITIES": [
        ("DX-Y.NYB", "Dollar (DXY)"),
        ("EURUSD=X", "EUR/USD"),
        ("USDJPY=X", "USD/JPY"),
        ("GC=F", "Gold"),
        ("CL=F", "WTI Crude"),
        ("BTC-USD", "Bitcoin"),
    ],
    "VOL": [
        ("^VIX", "VIX"),
    ],
}

# Symbols quoted as yield x10 by Yahoo (^TNX = 42.8 means 4.28%).
_RATE_SYMBOLS = {"^IRX", "^FVX", "^TNX", "^TYX"}

# Tenor in years for the curve sparkline ordering.
_RATE_TENOR = {"^IRX": 0.25, "^FVX": 5.0, "^TNX": 10.0, "^TYX": 30.0}


# ── Data containers ──────────────────────────────────────────────────────────
@dataclass
class Quote:
    symbol: str
    label: str = ""
    last: float | None = None
    prev_close: float | None = None
    history: list[float] = field(default_factory=list)
    is_rate: bool = False
    stale: bool = False
    updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def change(self) -> float | None:
        if self.last is None or self.prev_close in (None, 0):
            return None
        return self.last - self.prev_close  # type: ignore[operator]

    @property
    def change_pct(self) -> float | None:
        if self.last is None or self.prev_close in (None, 0):
            return None
        return (self.last - self.prev_close) / self.prev_close  # type: ignore[operator]

    @property
    def change_bps(self) -> float | None:
        """For rates: change expressed in basis points (level diff * 100)."""
        c = self.change
        return None if c is None else c * 100.0


@dataclass
class MarketSnapshot:
    quotes: dict[str, Quote] = field(default_factory=dict)
    updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stale: bool = False

    def group(self, name: str) -> list[Quote]:
        out = []
        for sym, _label in MARKET_GROUPS.get(name, []):
            q = self.quotes.get(sym)
            if q is not None:
                out.append(q)
        return out

    def get(self, symbol: str) -> Quote | None:
        return self.quotes.get(symbol)

    def rate_curve(self) -> list[tuple[str, float]]:
        pts: list[tuple[float, str, float]] = []
        for sym in _RATE_SYMBOLS:
            q = self.quotes.get(sym)
            if q and q.last is not None:
                label = next((lbl for s, lbl in MARKET_GROUPS["RATES"] if s == sym), sym)
                pts.append((_RATE_TENOR[sym], label, q.last))
        pts.sort(key=lambda t: t[0])
        return [(lbl, y) for _t, lbl, y in pts]


# ── Caches ───────────────────────────────────────────────────────────────────
_QUOTE_TTL = 60.0  # seconds
_MACRO_TTL = 600.0  # seconds

_quote_cache: dict[str, Quote] = {}
_quote_ts: dict[str, float] = {}
_snapshot: MarketSnapshot | None = None
_snapshot_ts: float = 0.0

_lock = threading.Lock()
_inflight: set[str] = set()  # keys currently being refreshed


def configure(quote_ttl: float | None = None, macro_ttl: float | None = None) -> None:
    """Override cache TTLs (wire from settings)."""
    global _QUOTE_TTL, _MACRO_TTL
    if quote_ttl is not None:
        _QUOTE_TTL = float(quote_ttl)
    if macro_ttl is not None:
        _MACRO_TTL = float(macro_ttl)


# ── Low-level fetch (blocking; only ever called off the UI thread) ───────────
def _fetch_one(symbol: str, want_history: bool = True) -> Quote:
    """Fetch a single symbol.  Raises on hard failure (caller catches)."""
    is_rate = symbol in _RATE_SYMBOLS
    if not _HAS_YF:
        return _mock_quote(symbol, is_rate)

    t = yf.Ticker(symbol)
    last: float | None = None
    prev: float | None = None

    # fast_info is cheap and avoids the heavy .info payload.
    try:
        fi = t.fast_info
        last = _num(getattr(fi, "last_price", None))
        prev = _num(getattr(fi, "previous_close", None))
    except Exception:  # noqa: BLE001
        pass

    history: list[float] = []
    if last is None or prev is None or want_history:
        try:
            hist = t.history(period="5d", interval="60m")
            closes = [float(x) for x in hist["Close"].dropna().tolist()]
            if closes:
                history = closes[-48:]
                if last is None:
                    last = closes[-1]
            # previous close = last close of prior day
            daily = t.history(period="2d", interval="1d")
            dcloses = [float(x) for x in daily["Close"].dropna().tolist()]
            if prev is None and len(dcloses) >= 2:
                prev = dcloses[-2]
            elif prev is None and dcloses:
                prev = dcloses[0]
        except Exception:  # noqa: BLE001
            pass

    if last is None:
        raise RuntimeError(f"no price for {symbol}")

    if is_rate:
        # Yahoo reports yields x10.
        last = last / 10.0
        if prev is not None:
            prev = prev / 10.0
        history = [h / 10.0 for h in history]

    label = _label_for(symbol)
    return Quote(
        symbol=symbol,
        label=label,
        last=last,
        prev_close=prev,
        history=history,
        is_rate=is_rate,
        stale=False,
    )


def _num(x) -> float | None:
    try:
        v = float(x)
        return v if v == v else None  # NaN check
    except (TypeError, ValueError):
        return None


def _label_for(symbol: str) -> str:
    for group in MARKET_GROUPS.values():
        for sym, lbl in group:
            if sym == symbol:
                return lbl
    return symbol


def _mock_quote(symbol: str, is_rate: bool) -> Quote:
    rnd = random.Random(hash(symbol) & 0xFFFF)
    if is_rate:
        base = rnd.uniform(3.5, 5.2)
        prev = base + rnd.uniform(-0.05, 0.05)
        hist = [base + rnd.uniform(-0.08, 0.08) for _ in range(30)]
    else:
        base = rnd.uniform(80, 6000)
        prev = base * rnd.uniform(0.985, 1.015)
        hist = [base * rnd.uniform(0.97, 1.03) for _ in range(30)]
    hist.append(base)
    return Quote(
        symbol=symbol,
        label=_label_for(symbol),
        last=base,
        prev_close=prev,
        history=hist,
        is_rate=is_rate,
        stale=True,  # mark mock data as stale so UI can flag it
    )


# ── Public, non-blocking accessors ───────────────────────────────────────────
def get_quote(symbol: str, *, refresh: bool = True) -> Quote | None:
    """Return cached quote immediately; trigger a background refresh if stale."""
    now = time.time()
    with _lock:
        q = _quote_cache.get(symbol)
        age = now - _quote_ts.get(symbol, 0.0)
        fresh = q is not None and age < _QUOTE_TTL
    if not fresh and refresh:
        _spawn_quote_refresh(symbol)
    if q is not None:
        q.stale = not fresh
    return q


def get_snapshot(*, refresh: bool = True) -> MarketSnapshot | None:
    """Return the cached macro snapshot; refresh in background if stale."""
    now = time.time()
    with _lock:
        snap = _snapshot
        age = now - _snapshot_ts
        fresh = snap is not None and age < _MACRO_TTL
    if not fresh and refresh:
        _spawn_snapshot_refresh()
    if snap is not None:
        snap.stale = not fresh
    return snap


def _spawn_quote_refresh(symbol: str) -> None:
    key = f"q:{symbol}"
    with _lock:
        if key in _inflight:
            return
        _inflight.add(key)
    threading.Thread(target=_refresh_quote_worker, args=(symbol, key), daemon=True).start()


def _refresh_quote_worker(symbol: str, key: str) -> None:
    try:
        q = _fetch_one(symbol)
        with _lock:
            _quote_cache[symbol] = q
            _quote_ts[symbol] = time.time()
    except Exception:  # noqa: BLE001
        # keep the prior cached value; just don't update the timestamp much
        with _lock:
            if symbol in _quote_cache:
                _quote_cache[symbol].stale = True
    finally:
        with _lock:
            _inflight.discard(key)


def _spawn_snapshot_refresh() -> None:
    key = "snapshot"
    with _lock:
        if key in _inflight:
            return
        _inflight.add(key)
    threading.Thread(target=_refresh_snapshot_worker, args=(key,), daemon=True).start()


def _refresh_snapshot_worker(key: str) -> None:
    try:
        snap = fetch_market_snapshot()
        with _lock:
            global _snapshot, _snapshot_ts
            _snapshot = snap
            _snapshot_ts = time.time()
    except Exception:  # noqa: BLE001
        pass
    finally:
        with _lock:
            _inflight.discard(key)


# ── Blocking builders (call from a worker thread) ────────────────────────────
def fetch_market_snapshot() -> MarketSnapshot:
    """Fetch the full macro tape.  Tolerant of individual symbol failures."""
    quotes: dict[str, Quote] = {}
    for group in MARKET_GROUPS.values():
        for sym, _lbl in group:
            try:
                quotes[sym] = _fetch_one(sym, want_history=True)
            except Exception:  # noqa: BLE001
                # fall back to mock so the panel still has a row
                quotes[sym] = _mock_quote(sym, sym in _RATE_SYMBOLS)
    return MarketSnapshot(quotes=quotes, updated=datetime.now(timezone.utc))


# ── Market-hours helper (US cash session, naive ET approximation) ────────────
def us_market_open(now: datetime | None = None) -> bool:
    """Rough check of whether US equities are in the regular cash session.

    Uses naive ET (UTC-4/5 not resolved precisely); good enough to decide
    whether to back off the live-tick refresh after hours.
    """
    now = now or datetime.now(timezone.utc)
    # crude ET conversion (assume EDT, UTC-4)
    et_hour = (now.hour - 4) % 24
    weekday = now.weekday()  # 0=Mon
    if weekday >= 5:
        return False
    minutes = et_hour * 60 + now.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60


def session_label(now: datetime | None = None) -> str:
    return "MKT OPEN" if us_market_open(now) else "MKT CLOSED"


# ── FRED hook point (optional, more reliable rates) ──────────────────────────
def fetch_rates_fred(api_key: str | None = None) -> dict[str, float]:  # pragma: no cover
    """Placeholder for a FRED rates fetch (DGS2/DGS10/DGS30).

    Wire this in when a FRED key is configured via the credentials wizard; it is
    more reliable than ^TNX et al.  Returns {tenor_label: yield_pct}.
    """
    raise NotImplementedError("FRED rates not yet wired; using yfinance ^TNX family.")


if __name__ == "__main__":  # quick smoke
    print("yfinance available:", _HAS_YF)
    snap = fetch_market_snapshot()
    for grp in ("US", "EUROPE", "ASIA", "RATES"):
        print(f"\n{grp}")
        for q in snap.group(grp):
            chg = q.change_pct
            chg_s = f"{chg * 100:+.2f}%" if chg is not None else "  n/a"
            print(f"  {q.label:<16} {q.last:>10.2f}  {chg_s}")
