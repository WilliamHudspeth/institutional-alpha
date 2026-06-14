# Data Sources — Free by Design

Institutional Alpha is built to run on **entirely free data**. You can clone the
repo and run a full backtest without paying for anything and, for most of the
stack, without even creating an account. This is a core project principle, not
an afterthought: the free, open core must "just work."

Most of the pipeline needs **no API key at all**. Two optional premium feeds
(FMP and Tiingo) have *perpetual free tiers* — adding their free keys simply
promotes them ahead of the keyless sources for higher-quality fundamentals. They
are never required.

---

## The tiered fallback chain

Data requests are routed by **tier** (authority) and **capability** (what a
source can actually serve). Each field falls through to the next tier only if a
higher one is unavailable or fails, and the source that answered is recorded in
the run's audit trail.

| Tier | Source | Key needed? | Serves | Notes |
|------|--------|-------------|--------|-------|
| PREMIUM | Financial Modeling Prep | Free key | prices, debt, fundamentals, history | 250 requests/day free |
| PREMIUM | Tiingo | Free key | prices, history | ~50 requests/hour free (EOD) |
| OFFICIAL | SEC EDGAR | **No key** | fundamentals, debt (point-in-time) | Official filings, 10 req/sec |
| COMMUNITY | Yahoo (yfinance) | **No key** | prices, debt, fundamentals, history | Primary keyless source |
| FALLBACK | Stooq | **No key** | prices, history | Price-only CSV, last resort |

Because routing is capability-aware, a fundamentals request (e.g. total debt) is
**only** sent to sources that actually provide fundamentals — it never silently
accepts a price-only source's empty `0.0` as if it were real data.

**Zero-config path:** with no keys set, the chain is
`SEC EDGAR → Yahoo → Stooq`, which already covers prices and point-in-time
fundamentals for free.

---

## Set up keys from the terminal

Run the interactive setup wizard:

```bash
python -m iam.config.credentials
```

It walks through each source, shows where to get the free key, and saves your
entries. Keys are stored in `~/.institutional-alpha/credentials.json` with
owner-only (0600) permissions — **never in the repo**, so they are never
committed. You can re-run the wizard anytime to update or clear a key.

Resolution order for every source: an explicit value in code, then the
environment variable, then the saved credentials file. So you can also export
environment variables instead of using the wizard:

```bash
export FMP_API_KEY="your-fmp-key"
export TIINGO_API_KEY="your-tiingo-token"
export SEC_USER_AGENT="Your Name your-email@example.com"
```

---

## Getting each free key

### SEC EDGAR — no account, no key

SEC EDGAR is free and requires no signup. The SEC only asks that automated
requests identify themselves with a descriptive **User-Agent** containing your
name and an email, so they can contact you if a script misbehaves.

- Provide a contact string such as `Will Hudspeth will@example.com`.
- Fair-access limit: **10 requests/second** (the client throttles below this).
- Coverage: official US filings, XBRL fundamentals, history back to ~1994.
- Why it matters: EDGAR is filtered on the actual **filing date**, so a snapshot
  as of date *T* only ever sees data that was genuinely public by *T* — no
  look-ahead bias.

Enter your contact string in the wizard (or set `SEC_USER_AGENT`). That's all.

### Financial Modeling Prep (FMP) — free, 250 requests/day

1. Go to <https://site.financialmodelingprep.com> and sign up with your email.
2. Verify your email and log in.
3. Open the **Dashboard** — your free API key is shown there.
4. Paste it into the wizard.

The free plan is **perpetual** (no credit card): **250 requests/day**, resetting
every 24 hours, plus a 500 MB trailing-30-day bandwidth allowance. If you exceed
the daily limit you get a `429` and the chain falls through to the free tiers.

### Tiingo — free, ~50 requests/hour (EOD prices)

1. Sign up at <https://www.tiingo.com> (free).
2. Log in and open <https://www.tiingo.com/account/api/token>.
3. Copy your API token and paste it into the wizard.

The free tier covers **end-of-day prices** at roughly 50 requests/hour (with
daily and monthly bandwidth caps). Tiingo's fundamentals are a separate paid
add-on, so this source is wired for prices/history only — the router will never
ask it for fundamentals.

### Yahoo (yfinance) and Stooq — no keys

Both are keyless and installed with the backtest extras. Yahoo is the primary
free source for prices and basic fundamentals; Stooq is a price-only CSV
fallback used when Yahoo is throttled. Nothing to configure.

---

## Checking your configuration

```python
from iam.config.credentials import status
for name, info in status().items():
    mark = "✓" if info["configured"] else "—"
    print(f"{mark} {info['label']}  [{info['source']}]  {info['free_tier']}")
```

The status view never prints the secret values — only whether each source is
configured and where the value came from (env vs. file).

---

## Provenance in the run manifest

Every backtest can record which tiers actually served the run. When a request
falls back to a lower tier, the manifest flags it (`_meta.degraded_data`) and
lists the degraded fields, so a run that leaned on a weaker free source is
visible and reproducible rather than silent.
