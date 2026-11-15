# Contributing to expo-catalog

Thanks for helping. Bug reports, data corrections and pull requests are all
welcome. Everyone taking part is expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting problems

- **Wrong or missing site data** (danger level, enemies, minimal ship, space,
  status …): open a
  [data correction](https://github.com/grimmy0/expo-catalog/issues/new?template=data_correction.yml)
  issue and link a source. Most data comes from the
  [EVE University wiki](https://wiki.eveuniversity.org), so if the wiki itself
  is wrong, please fix it there too; the weekly refresh then picks the change
  up for everyone.
- **Bugs in the TUI or the scraper**: open a
  [bug report](https://github.com/grimmy0/expo-catalog/issues/new?template=bug_report.yml)
  with the output of `expo-catalog --version`, your OS and terminal, and the
  steps to reproduce.
- **Ideas**: open a
  [feature request](https://github.com/grimmy0/expo-catalog/issues/new?template=feature_request.yml).
- **Security vulnerabilities**: do not open an issue; follow
  [SECURITY.md](SECURITY.md).

## Development setup

You need Python 3.15 and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/grimmy0/expo-catalog.git
cd expo-catalog
uv sync                      # create .venv with the app and the dev tools
uv run expo-catalog          # run the TUI from the checkout
```

Before opening a pull request, run the same checks as CI:

```sh
uv run pytest -q                              # tests (offline; the TUI tests run headless)
uv run ruff check src scraper tests           # lint
uv run ruff format --check src scraper tests  # formatting (drop --check to apply it)
```

CI also audits the GitHub Actions workflows with
[zizmor](https://docs.zizmor.sh); if you change anything under
`.github/workflows/`, keep actions pinned to a full commit SHA and give each
job only the permissions it needs.

## How the data gets in

The [Data pipeline](README.md#data-pipeline) section of the README has the
details. In short:

1. `uv run python -m scraper fetch` downloads the tracked wiki pages into the
   git-ignored `data/raw/` cache.
2. `uv run python -m scraper parse` turns them into `data/parsed_sites.json`.
3. `uv run python -m scraper build` writes the bundled
   `src/expo_catalog/data/catalog.sqlite`.

`uv run python -m scraper refresh` runs all three. The schema in
`src/expo_catalog/db.py` is shared by the builder and the TUI.

Where to make a change:

- A site the wiki describes wrongly or inconsistently: add or adjust its entry
  in `OVERRIDES` in `scraper/curated.py`, ideally with a comment saying why.
- Sites the wiki does not describe per page (generic data/relic sites, ghost
  sites, FW plexes, insurgency, homefront, …): the curated lists in
  `scraper/curated.py`.
- Danger levels, minimal ships and classification: `scraper/rules.py`.
- Hand-maintained inputs: `data/event_sites.json`, `data/npcwh_codes.json`,
  `data/Template_Whisk.wiki`, `data/wormholes.json`, `data/systems.json`.

If your change affects the pipeline output, rebuild with
`uv run python -m scraper refresh` (or `parse` + `build` if you have a fresh
cache) and commit the regenerated `data/parsed_sites.json`,
`data/wiki_state.json` and `src/expo_catalog/data/catalog.sqlite` together
with the code change.

A scheduled workflow (`Wiki refresh`) checks the wiki every Monday and opens a
pull request on the `auto/wiki-refresh` branch when pages changed. If you see
one open, there is no need to send a separate data refresh.

## Pull requests

- Keep each pull request small and focused on one change; open an issue first
  for anything large.
- Add or update tests for behaviour changes.
- Tests pass and ruff is clean (see above).
- Add a line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) for
  user-visible changes.
- Write commit messages in the imperative mood ("Add …", "Fix …") with a short
  summary line.

## License of contributions

By contributing you agree that your contributions are licensed under the
project's licenses: [MIT](LICENSE) for code, and
[CC BY-SA 4.0](LICENSE-DATA) for data derived from the EVE University wiki
(see [License](README.md#license) in the README).
