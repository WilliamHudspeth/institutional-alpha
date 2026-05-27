# Changelog

## [Unreleased]

### Added
- **Thesis Engine** (`src/iam/thesis/`) — Logic for evaluating multiple bull/base/bear scenarios.
  - Cross-scenario validation to prevent logical errors (e.g., Bull < Bear).
  - `simulate()` method for dynamic assumption perturbation.
  - `render_report()` for actionable verdict generation (e.g., [HIGH DISPERSION]).