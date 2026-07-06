# Release Schedule & Versioning Policy

This is the canonical release-cadence document for Phase 1.1 (Release Management &
Community Trust, see [`ROADMAP.md`](../ROADMAP.md)). [`GOVERNANCE.md`](../.github/GOVERNANCE.md)
and [`CONTRIBUTING.md`](../CONTRIBUTING.md) both summarize the cadence; this file is the
detailed version they point to.

**Philosophy:** fast, frequent, transparent releases so retail users get the same
trustworthy artifact as institutional ones — no silent drift between what's on `main`
and what users are running.

---

## 1. Versioning scheme

Semantic Versioning (`MAJOR.MINOR.PATCH`, optionally `-rcN` for release candidates).

| Bump | Trigger |
|---|---|
| **Patch** (`0.4.2`) | Bugfixes, security patches, data updates. No API or output-format changes. |
| **Minor** (`0.5.0`) | New features, new factors/lenses, UI enhancements. Backward-compatible. |
| **Major** (`1.0.0`) | Breaking changes — factor contract changes, composite formula changes, removed public API. |

### Current known drift (not yet resolved)

Three places currently disagree on version and are **not** wired together:

- `pyproject.toml` → `version = "0.2.0a0"`
- `src/iam/version.py` → `VERSION = "0.4.0-rc1"`
- `git tag -l` → latest is `v0.2.0-beta`

Until these are unified under one source of truth (recommend: `src/iam/version.py` as
the single source, read by `pyproject.toml` via `setuptools` dynamic versioning, and
git tags cut from it), do not assume the git tag or PyPI-style version in `pyproject.toml`
reflects what's actually running. This should be resolved before the first Phase 1.1
tagged release goes out under this policy.

---

## 2. Cadence

> **⚠️ Important: Cadence is a ceiling, not a quota.** A Friday with nothing merge-worthy is skipped. The schedule below represents the *maximum* frequency — we do not ship empty releases to hit a calendar target.

| Release type | Frequency | Contents |
|---|---|---|
| **Patch** | Every Friday, if there's something ready | Bugfixes, security patches, data/universe updates |
| **Minor** | Every 6 weeks | Features, factor/lens improvements, UI changes |
| **Major** | Quarterly | Breaking changes, architectural shifts |
| **Security** | Within 24 hours of confirmed vulnerability | Out-of-band, does not wait for the next scheduled window |

---

## 3. What's automated today

Grounded in the actual workflow files in `.github/workflows/`:

- **`pr-title.yml`** — validates every PR title against Conventional Commits via
  `amannn/action-semantic-pull-request`. This is the enforcement point for the
  changelog categories below (see [`CONVENTIONAL_COMMITS.md`](CONVENTIONAL_COMMITS.md)).
- **`release-drafter.yml`** + **`.github/release-drafter.yml`** — drafts release notes
  from merged PRs, categorized by label (`feat` → 🎉 Features, `fix` → 🐛 Bug Fixes,
  `security` → 🚨 Security, etc.), autolabeled from the PR title prefix.
- **`release.yml`** — triggers on `v*` tag push:
  1. Builds sdist/wheel (`python -m build`) and publishes a GitHub Release with
     `generate_release_notes: true`.
  2. Builds standalone executables via PyInstaller for Windows (`.exe`) and macOS
     (`.dmg`, via `create-dmg`), uploaded to the same release.
- **`.pre-commit-config.yaml`** — `conventional-pre-commit` hook enforces the commit
  message format locally at `commit-msg` stage, before it ever reaches CI.

### What is NOT yet automated (planned, not live)

- **Checksums** (SHA256) and **GPG signatures** for release artifacts — `release.yml`
  does not currently generate or attach either. Do not tell users artifacts are signed
  until this is added.
- **Linux artifact** (AppImage or `.tar.gz`) — the build matrix only covers
  Windows and macOS today.
- **End-of-life labeling** on releases >12 months old.
- **Version pinning / downgrade UX** beyond "old tags still exist on GitHub Releases."

---

## 4. Release process (current, manual steps in bold)

1. PRs merge to `main` with Conventional Commit titles (enforced by `pr-title.yml`).
2. **Maintainer decides a release is ready** (Friday patch, 6-week minor, or quarterly major).
3. Release Drafter's draft (already accumulating on the Releases page) is reviewed and edited.
4. **Maintainer resolves the version-drift issue in §1** for this release, then bumps
   `src/iam/version.py` (and `pyproject.toml` until unified) in a `chore(release): vX.Y.Z` commit.
5. **Maintainer tags** `git tag vX.Y.Z && git push origin vX.Y.Z`.
6. `release.yml` builds and attaches sdist/wheel/exe/dmg automatically.
7. Publish the drafted release notes.

---

## 5. Hotfix / security patch process

Security patches do not wait for Friday:

1. Fix lands on a `fix/` or `security/` branch off `main`.
2. Commit tagged `security:` (see [`CONVENTIONAL_COMMITS.md`](CONVENTIONAL_COMMITS.md)) —
   this routes it into the 🚨 Security category in release notes automatically.
3. Expedited review (see escalation path in [`GOVERNANCE.md`](../.github/GOVERNANCE.md)).
4. Tag and release same-day. Target: identification → patch released within 24 hours.
5. If the vulnerability affects data integrity or user funds/decisions, disclose in the
   release notes even though this project has no formal security-advisory process yet
   (GitHub Security Advisories are the recommended next step — not yet configured).

---

## 6. Distribution targets (aspirational — see gaps in §3)

| Platform | Artifact | Status |
|---|---|---|
| Windows | `institutional-alpha-windows.exe` | Built by `release.yml` today |
| macOS | `institutional-alpha-macos.dmg` | Built by `release.yml` today |
| Linux | `.AppImage` or `.tar.gz` | Not yet in the build matrix |
| Python package | `pip install institutional-alpha` | Sdist/wheel built and attached to GitHub Releases; not yet published to PyPI |

Goal (per `ROADMAP.md`): zero-dependency single-file executables (<50MB), no installer,
no license key, no telemetry beyond opt-in usage stats.

---

## 7. Success criteria (from `ROADMAP.md` Phase 1.1)

- New release every Friday (patch) or every 6 weeks (minor)
- Release notes auto-generated from commits — zero manual writing per release
- Security patches within 24 hours of identification
- 90%+ of users on the latest version once auto-update exists

## References

- [`CONVENTIONAL_COMMITS.md`](CONVENTIONAL_COMMITS.md) — commit format this cadence depends on
- [`COMMUNITY_CONTRIBUTIONS.md`](COMMUNITY_CONTRIBUTIONS.md) — how external PRs feed releases
- [`../.github/GOVERNANCE.md`](../.github/GOVERNANCE.md) — merge gate and escalation policy
- [`../CHANGELOG.md`](../CHANGELOG.md) — Keep-a-Changelog commit-level history
- [`releases.md`](releases.md) — release-by-release narrative notes
