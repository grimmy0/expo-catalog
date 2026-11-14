# Security policy

## Supported versions

Only the latest release and the `main` branch get fixes. There are no
long-term support branches; update to the newest version before reporting.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's private vulnerability
reporting:

**<https://github.com/grimmy0/expo-catalog/security/advisories/new>**

Do not open a public issue, pull request or discussion for a security problem.

Include what you found, how to reproduce it, the version (`expo-catalog
--version`) or commit you tested, and the impact you expect.

This is a hobby project maintained by one person, so handling is best effort.
I aim to acknowledge a report within a week and will keep you updated in the
advisory thread. Once a fix is released the advisory is published, with credit
to you unless you prefer otherwise.

## Scope

expo-catalog is a local terminal application:

- The TUI only reads a bundled SQLite file (or one you point it at with `--db`
  / `EXPO_CATALOG_DB`). It opens no network connections.
- The scraper (`python -m scraper`, also run by `expo-catalog --refresh`)
  calls the public [EVE University wiki](https://wiki.eveuniversity.org) API
  and [ESI](https://esi.evetech.net) over HTTPS, parses the responses and
  writes files under `data/` and `src/expo_catalog/data/`.
- There are no user accounts, no authentication, and no secrets or API keys
  in the project or its workflows.

Relevant reports include, for example, wiki or ESI content that makes the
parser or the TUI execute code or write outside the repository, and problems
in the GitHub Actions workflows. Wrong site data is not a security issue: use
the [data correction form](https://github.com/grimmy0/expo-catalog/issues/new?template=data_correction.yml)
instead.
