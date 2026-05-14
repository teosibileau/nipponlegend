# nipponlegend

Private archive of vehicle restoration work — parts hunts, identification notes, and per-site adapter scoring for a fleet of older Toyotas. Built as a static site so each hunt is a permanent, citable document and not a chat-thread bookmark.

The site is published at https://teosibileau.github.io/nipponlegend/ — content in Argentinian Spanish, code in English.

## What's in here

| Path | Purpose |
| --- | --- |
| `src/content/vehicles/` | Vehicle profile (chassis, engine code, displacement, drive, VIN decomposition). |
| `src/content/sites/` | Per-site adapter config — base URL, search strategy, vocabulary. |
| `src/content/hunts/` | A dated list of parts to find for one vehicle, with status (`missing` / `confirmed` / `purchased`), the chosen alternate, and other candidate matches. |
| `scripts/hunt.py` | Python CLI that scores catalog entries against each hunt item and writes alternates back into the hunt's MDX frontmatter. |
| `scripts/adapters/` | One module per parts site implementing `fetch_catalog()` against its public API. |
| `data/catalogs/` | Cached catalog dumps (one JSON file per `<site>-<vehicle>` pair). |
| `data/runs/` | Snapshot of each hunt run for diffing across time. |

## Local development

Requirements: Node 22, [pnpm](https://pnpm.io) 10, Python 3.11+, and PyYAML (`pip install pyyaml`).

```bash
pnpm install
pnpm dev          # Astro dev server on http://localhost:4321
pnpm run build    # Static build into ./dist
pnpm exec astro check  # Type-check content collections
```

The `packageManager` field in `package.json` pins the pnpm version — Corepack and `pnpm/action-setup` will both honor it.

## Running a hunt

```bash
pnpm run hunt <hunt-slug>
# e.g.
pnpm run hunt 2026-05-revision-tren-delantero
```

The matcher:

1. Reads the hunt frontmatter and resolves its `vehicle` reference.
2. For every site listed in the vehicle's `huntOn`, loads (or fetches) the catalog under `data/catalogs/`.
3. Scores each catalog entry against each hunt item using token-bag matching plus heuristics from the vehicle profile (year range, displacement, engine code, chassis, drive, qualifiers, disqualifiers).
4. Writes the top alternates back into the hunt MDX and refreshes `lastRun`.
5. Saves a run snapshot under `data/runs/<hunt>.<YYYY-MM-DD>.json`.

Heuristics live in `src/content/vehicles/*.mdx` so they version alongside the vehicle, not the code.

## Content model

Content collections are schema-validated by Zod (`src/content.config.ts`). Highlights:

- **`vehicles`**: identification fields plus a `sources[]` array of cited URLs that back any claim about chassis/engine/year — so a stranger looking at the page can audit the identification, not just trust it.
- **`hunts`**: an `items[]` array where each item carries its own status, chosen alternate, and ranked alternates. The site renders progress pips (missing/confirmed/purchased) at the page header and per item.
- **`sites`**: opaque config consumed by the matching adapter — base URL, search strategy, vocabulary normalization.

## VIN handling

The vehicle profile stores the VIN with the serial portion masked (`XXXXXX`). Full VINs are never written to disk or committed. Positional decoding (WMI / VDS / check digit / year / plant / serial) is rendered from the masked value.

## Deployment

Two workflows in `.github/workflows/`:

- **`ci.yml`** — runs on every PR and on push to `main`. Installs deps, runs `astro check`, and builds the site as a smoke test.
- **`deploy.yml`** — runs on push to `main` only. Builds and publishes to GitHub Pages via `actions/deploy-pages@v4`.

Both use Node 22 + `corepack enable` — pnpm is auto-activated from the `packageManager` field in `package.json`, so there is no second action to keep in sync.

To verify CI locally before pushing:

```bash
act push -W .github/workflows/ci.yml -j check
```

`act` config lives in `~/.actrc` (runner image + amd64 arch for Apple Silicon). The Pages deploy job can only be exercised on a real GitHub push.

## License

Private personal project. No license granted.
