# AGY coding round 1 (2026-10-02)

AGY wrote the code. Claude specified each task, reviewed every diff, and merged. Each coder ran
headless (`agy -p --dangerously-skip-permissions --sandbox`) in its own throwaway git worktree on
an `agy/<task>` branch. Then each branch was reviewed read-only by AGY models from a different
family (agent `iam-reviewer`) and by Claude.

## What we learned about AGY 1.2.14

- A custom agent without a `tools:` list gets read-only tools (view, search, web). Coders therefore
  run as the default agent, with `.agents/agents/iam-coder.md` and `.agents/rules/iam-rules.md`
  inlined into the prompt. For the reviewer, read-only is exactly what we want.
- `--effort` is rejected for Claude models and for any model id that already carries a tier
  (`-low`, `-medium`, `-high`). The model id sets the effort.
- Quotas: Claude Opus 4.6 and Sonnet 4.6 hit HTTP 429 partway through their tasks, and GPT-OSS
  120B hit it partway through reviewing. Gemini 3.6 Flash returned intermittent 503 "no capacity".

## Branches

| Branch | Coder | Reviews | Outcome |
|---|---|---|---|
| `agy/fair-value-frontier` | gemini-3.8-flash-high | gemini-3.1-pro-high APPROVE; gpt-oss-120b CHANGES (disputed) | **Merged.** GPT-OSS claimed the map test fails because `~~~~~` is never drawn. Disputed: frontier cells render as `"~" * (cell_w - 1)` and the suite passes (1,412). |
| `agy/test-net-guard` | gemini-3.6-flash-high | gemini-3.7-flash-medium APPROVE; gpt-oss-120b APPROVE | **Merged.** Follow-up: `data/fetcher.py` uses `requests`, which the urlopen guard does not cover. |
| `agy/gui-pwev-na` | gemini-3.7-flash-high | gemini-3.1-pro-low APPROVE; gpt-oss-120b (quota) | **Merged.** Also removed invented sidebar values PBO 4.2% and DSR 1.48x, plus `0.0` fills in the scenario, Kelly and risk-parity tables. The script is now wrapped in `main()`, which `streamlit run` still executes. |
| `agy/tui-demo-flag` | claude-sonnet-4-6 (quota-stopped; finished by Claude) | gemini-3.1-pro-high CHANGES (accepted: three test-robustness fixes); gpt-oss-120b (quota) | **Merged.** Claude changed `--demo` to always mean demo data, so the DEMO banner never sits on top of real data. |
| `agy/adapter-defaults` | gemini-3.1-pro-high | Claude CHANGES; gemini-3.8-flash-high CHANGES (same findings plus two tautological tests, one asserting the invented 10% ROIC) | **Round 2.** Round 1 made the multiples regression treat a missing ROE as 0% (`predict_multiple` uses `inputs.get(key, 0.0)`), left the 0.15/1.0/0.10 fallbacks, and stored ROA as "roic". |
| `agy/wacc-provenance` | claude-opus-4-6-thinking (quota-stopped; partial discarded) | n/a | **Round 2, redesigned.** `_calculate_dynamic_wacc` hardcodes ke 9%, rf 4.3% and tax 21% for every company, and the result overrides the discount rate of the FCFE reverse DCF (Stage 1), which must use the cost of equity. This changes every verdict, so it needs owner sign-off before merge. |
