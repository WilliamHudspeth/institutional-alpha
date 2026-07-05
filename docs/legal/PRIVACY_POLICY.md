# Privacy Policy

**Effective Date:** 2026-07-03  
**Product:** Institutional Alpha  
**Author:** William Hudspeth

---

## 1. What We Collect

Institutional Alpha runs **locally on your machine**. We do not operate a SaaS platform and do not collect personal information by default.

When you use the tool, the following data may be generated **locally**:

| Data | Location | Purpose |
|------|----------|---------|
| Ticker queries | `~/.iam/audit.jsonl` | Audit trail (SEC compliance) |
| Model/factor/assumption changes | `~/.iam/governance/*.jsonl` | Model governance audit trail — see [`docs/legal/MODEL_GOVERNANCE.md`](MODEL_GOVERNANCE.md) |
| Valuation outputs | Local only | Your research |
| Error logs | Local only | Debugging |

## 2. Third-Party Data Sources

Institutional Alpha fetches **public market data** from:
- **Yahoo Finance** (`yfinance`) — subject to Yahoo's terms of service
- **Stooq** — subject to Stooq's terms of service

We do not transmit your ticker queries to these services with any personally identifying information.

## 3. No Telemetry by Default

We do **not** collect telemetry, usage analytics, or crash reports unless you explicitly opt in via the `IAM_TELEMETRY=1` environment variable.

## 4. Data Retention

Local audit logs are retained for **2 years** (regulatory minimum). You may delete them at any time by removing `~/.iam/audit.jsonl`.

## 5. Your Rights

- **Access**: Your data is stored locally. You have full access at all times.
- **Deletion**: Delete `~/.iam/` to remove all local data.
- **Portability**: All logs are plain JSON Lines format — human-readable and portable.

## 6. GDPR / CCPA

Because this is a locally-run open-source tool with no cloud backend, standard SaaS data-protection obligations do not apply. If you integrate Institutional Alpha into a server environment that processes EU/California user data, you are responsible for your own GDPR/CCPA compliance.

## 7. Contact

For privacy questions, open a GitHub issue at:  
`https://github.com/WilliamHudspeth/institutional-alpha/issues`
