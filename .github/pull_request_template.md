## Summary

<!-- What does this change and why? Link the issue it fixes, e.g. "Fixes #12". -->

## Checklist

- [ ] `uv run pytest -q` passes
- [ ] `uv run ruff check src scraper tests` and `uv run ruff format --check src scraper tests` are clean
- [ ] `CHANGELOG.md` has an entry under `## [Unreleased]` (for user-visible changes)
- [ ] If the pipeline or curated data changed: rebuilt with `uv run python -m scraper refresh` (or `parse` + `build`) and committed the regenerated `data/parsed_sites.json`, `data/wiki_state.json` and `src/expo_catalog/data/catalog.sqlite`
