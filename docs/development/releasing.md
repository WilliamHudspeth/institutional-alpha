# Releasing

Release notes for each version live in [CHANGELOG.md](../../CHANGELOG.md). This page covers
versioning, cadence and the release procedure.

## Versioning

Semantic Versioning (`MAJOR.MINOR.PATCH`, with `-rcN` for release candidates).

| Bump | Trigger |
|---|---|
| Patch (`0.4.1`) | Bug fixes, security patches, data updates. No API or output-format change. |
| Minor (`0.5.0`) | New features, factors, lenses, UI changes. Backward compatible. |
| Major (`1.0.0`) | Breaking changes: factor contract, composite formula, removed public API. |

The current version is `0.4.0-rc1`. The version string is defined in `pyproject.toml` and
`src/iam/version.py`; keep the two in step when bumping.

## Cadence

Cadence is a ceiling, not a quota. A week with nothing worth releasing is skipped.

| Release | Frequency | Contents |
|---|---|---|
| Patch | Fridays, if something is ready | Fixes, security patches, data updates |
| Minor | At most every 6 weeks | Features and improvements |
| Major | At most quarterly | Breaking changes |
| Security | As soon as a vulnerability is confirmed | Out of band |

## What is automated

From `.github/workflows/`:

- `pr-title.yml` validates every PR title against
  [Conventional Commits](commit-conventions.md).
- `release-drafter.yml` (configured in `.github/release-drafter.yml`) drafts release notes from
  merged PRs, grouped by the label derived from the PR title prefix.
- `release.yml` runs on a `v*` tag push. It builds the sdist and wheel, publishes a GitHub
  Release, and builds standalone executables with PyInstaller for Windows (`.exe`) and macOS
  (`.dmg`).

Not automated yet:

- Checksums and GPG signatures for release artifacts. Do not describe artifacts as signed.
- A Linux artifact.
- Publication to PyPI. The sdist and wheel are attached to GitHub Releases only.

## Release procedure

1. PRs merge to `main` with Conventional Commit titles.
2. The maintainer decides a release is ready and reviews the drafted notes.
3. Update `CHANGELOG.md` (move `Unreleased` entries under the new version), bump the version in
   `pyproject.toml` and `src/iam/version.py`, and commit as `chore(release): vX.Y.Z`.
4. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
5. `release.yml` builds and attaches the artifacts. Publish the drafted notes.

## Security patches

1. Fix on a `fix/` or `security/` branch off `main`.
2. Use the `security:` commit type so the change lands in the Security section of the notes.
3. Review on an expedited basis.
4. Tag and release the same day where possible, and disclose in the release notes if the issue
   affects data integrity or the validity of outputs. See [SECURITY.md](../../SECURITY.md).

## Branch and merge policy

Merges to `main` require a review, passing checks and an up-to-date branch. See
[branch protection](branch-protection.md), [CI/CD](ci-cd.md) and
[coverage policy](coverage-policy.md).
