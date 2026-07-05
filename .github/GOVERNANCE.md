# Development Governance Policy

**Version**: 0.1.0  
**Effective**: Phase 1 (Research Maturity) — 2026-05-29

---

## Code Quality Gate

All merges to `main` require:

1. ✅ **At least one code review approval**
   - Enforces peer review of all changes
   - Prevents single-developer mistakes

2. ✅ **All status checks pass**
   - Tests: `pytest` suite (534+ tests)
   - Lint: `ruff` (PEP 8, import order, security)
   - Security: static analysis (bandit)
   - Coverage: new code ≥ 85% (enforced in Phase 0.5)

3. ✅ **Branch up to date with `main`**
   - Prevents merge conflicts
   - Ensures tests pass against latest code

4. ✅ **All conversations resolved**
   - Forces explicit resolution of feedback
   - Creates audit trail

---

## Commit Message Convention

**Format**: Conventional Commits (automates changelog generation)

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type** (required):
- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `test:` — test additions / improvements
- `perf:` — performance optimization
- `refactor:` — code refactoring (no feature change)
- `chore:` — build, config, deps (no user-facing change)
- `security:` — security fix or hardening

**Scope** (optional): module or component (e.g., `feat(reasoning):`, `fix(pipeline):`)

**Subject**: imperative, present tense, no period ("add feature" not "added feature")

**Body** (optional): explain *why*, not *what* (the diff shows what)

**Footer** (optional): breaking changes, issue references

### Examples

```
feat(lenses): add business reality lens diagnostic

Adds BusinessRealityLens to surface durability reasoning without
perturbing the valuation pipeline weights.

Closes #41
```

```
fix(factors): guard against empty roic_history in quality factor

Prevents crash when roic_history has fewer than 3 elements.
```

---

## Release Management

Full policy: [`docs/RELEASE_SCHEDULE.md`](../docs/RELEASE_SCHEDULE.md). Summary below.

**Cadence** (Phase 1.1 target):
- **Patch** (v0.4.2): Every Friday if ready; bugfixes + data updates + security patches
- **Minor** (v0.5.0): Every 6 weeks; features + factor improvements
- **Major** (v1.0.0): Quarterly; breaking changes + architectural shifts

**Process**:
1. Commits land on `main` with conventional message
2. CI passes + code review required
3. Release tool (release-drafter) generates changelog automatically
4. Create git tag (v0.4.2) and GitHub Release
5. Binaries + checksums published (future)

---

## Enforcement

- Branch protection rules on `main` (GitHub Settings → Branches)
- Pre-commit hooks (ruff, bandit) — local development
- CI/CD pipeline (GitHub Actions) — on every PR
- Semantic versioning + auto-changelog (release-drafter)

---

## Code Review Standards

**Reviewers should verify**:
1. Tests exist and pass
2. No silent failures or edge-case crashes
3. Assumptions are documented
4. Reuse existing patterns (don't reinvent)
5. Bounds and guards on all inputs (nil-safe, overflow-safe)
6. Consistency with existing code (naming, conventions, math)

**Red flags**:
- Hardcoded magic numbers (should be named constants)
- Missing null/empty checks
- Breaking changes without version bump
- New dependencies without justification

---

## Escalation Path

| Issue | Resolution |
|-------|-----------|
| PR stalled (no review after 24h) | Ping maintainer |
| Merge conflict | Rebase + re-run CI |
| Test flakiness | Diagnose + fix (don't bypass) |
| Security concern | Security advisory + patch immediately |
| Design disagreement | Escalate to architectural review (CONTRIBUTING.md) |

