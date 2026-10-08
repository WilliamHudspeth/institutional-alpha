# Conventional Commits Guide

Commit and PR-title convention for this repository, summarised in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md).

The project follows [Conventional Commits](https://www.conventionalcommits.org/). The type drives
the drafted release notes, so a wrong type can put a security fix in the wrong section.

---

## Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

## Type (required)

| Type | Use for | Release Drafter category |
|---|---|---|
| `feat` | New feature or capability | Features |
| `fix` | Bug fix | Bug Fixes |
| `security` | Security fix or hardening | Security |
| `docs` | Documentation only | Documentation |
| `perf` | Performance improvement | Performance |
| `refactor` | Code restructuring, no behavior change | Refactoring |
| `test` | Test additions/improvements only | Tests |
| `chore` | Build, deps, config — no user-facing change | Chores |

This mapping is not just convention — it's `.github/release-drafter.yml`'s `autolabeler`
config, which regexes the PR title (`/^feat(\(.+\))?:/i`, etc.) to apply a GitHub label,
which then buckets the entry in the drafted release notes. Get the prefix wrong and the
entry lands in the wrong section (or none, if it doesn't match).

## Scope (optional)

Use the subpackage under `src/iam/` the change lives in — matches the
subpackage inventory in [architecture](../architecture.md):

`analytics`, `api`, `arbitration`, `assumptions`, `audit`, `backtest`, `compliance`,
`config`, `data`, `elasticity`, `engine`, `factors`, `governance`, `integration`, `laws`,
`learning`, `lenses`, `monitoring`, `pipeline`, `portfolio`, `reasoning`, `reports`,
`thesis`, `ui`, `validation`, `valuation`

For cross-cutting changes, omit the scope rather than guessing.

## Subject (required)

- Imperative mood: "add feature", not "added feature" or "adds feature"
- Lowercase first letter, no trailing period
- Under 50 characters (aim for 40)

## Body (optional)

- Explain *why*, not *what* — the diff already shows what changed
- Wrap at 72 characters

## Footer (optional)

```
BREAKING CHANGE: <description>

Closes #123
```

---

## Where this is enforced

The PR title is checked in CI by `.github/workflows/pr-title.yml`
(`amannn/action-semantic-pull-request`). Release Drafter builds the notes from merged PR titles,
so when a PR is squashed the PR title is what must conform. Intermediate commits are not
blocked. There is no local commit-message hook configured.

---

## Examples

### Good

```
feat(reasoning): add business reality engine

Adds a theory-first
reasoning layer that decodes business durability across six dimensions.

Closes #41
```

```
fix(factors): guard against empty roic_history in quality factor

Prevents IndexError when roic_history has fewer than 3 elements.
```

```
security(data): validate ticker input before shell-adjacent cache path build

Untrusted ticker strings were interpolated into a cache filename;
an adversarial value could traverse outside data_cache/.
```

```
docs: update roadmap status for the data layer
```

### Bad (and why)

```
Update stuff
```
No type, no imperative mood, no information — release notes would show "Update stuff"
under no category and it'd be dropped by the drafter.

```
feat: fixed the bug in the DCF calc
```
Wrong type — this is a `fix`, not a `feat`. It'll land in Features, misleading anyone
scanning the changelog for bug fixes.

```
chore: rewrite the composite scoring engine to use a new weighting model
```
Wrong type for the size of the change — a new weighting model is user-facing behavior,
not a chore. Should be `feat` or, if it changes existing output, called out with a
`BREAKING CHANGE:` footer.

---

## References

- [Releasing](releasing.md): how commits become releases.
- [CONTRIBUTING.md](../../CONTRIBUTING.md): contributor guide.
