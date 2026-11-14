# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-14

First release.

### Added

- Textual TUI listing every EVE Online cosmic signature and anomaly across
  known space, wormhole space (C1–C6, Thera, shattered, Drifter) and Pochven,
  with Name, Type, Space, Danger, Enemies and Min ship columns and a detail
  panel with the full record and per-wave enemy rows.
- fzf-style filtering (fuzzy terms, `'exact`, `!exclude`, `^prefix`,
  `suffix$`) plus `field:value` terms for `space:`, `type:`, `danger:`,
  `ship:`, `faction:`, `name:`, `ewar:` and `status:`, each negatable with `!`.
- Removed and unverified sites hidden by default; `ctrl+r`, `--all` or a
  `status:` term shows them.
- Catalog database bundled in the package, so `uv tool install` works without
  a checkout; `--db`, `EXPO_CATALOG_DB`, `--refresh` and `--version` options.
- Scraper CLI `python -m scraper fetch|parse|build|check|refresh` over the
  EVE University wiki API, with curated lists for sites the wiki does not
  describe consistently and wiki change detection against
  `data/wiki_state.json`.
- COSMOS complexes and other site pages outside the tracked wiki categories,
  with system security and region resolved through ESI.
- Weekly `Wiki refresh` workflow that rebuilds the catalog and opens a pull
  request when the wiki changed, and a CI workflow running tests, ruff lint
  and format checks.
- MIT license for the code and CC BY-SA 4.0 license for the data derived from
  the EVE University wiki, with attribution and a CCP trademark disclaimer in
  the README and a data credit line in the TUI help.
- Community files: contributing guide, Code of Conduct (Contributor Covenant
  3.0), security policy, issue forms (bug report, data correction, feature
  request), pull request template and CODEOWNERS.
- Dependabot version updates for GitHub Actions and uv dependencies.
- README screenshot, badges, and Contributing / License / Disclaimer sections.

### Security

- CI hardening: actions pinned to commit SHAs, least-privilege workflow
  permissions, no persisted checkout credentials, and a zizmor audit of the
  workflows.

[Unreleased]: https://github.com/grimmy0/expo-catalog/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/grimmy0/expo-catalog/releases/tag/v0.1.0
