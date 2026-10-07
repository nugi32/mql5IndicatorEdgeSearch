# Archived config profiles

Nothing here was deleted -- these are older config layouts, superseded by
the current `config/<SYMBOL>/<TIMEFRAME>/` structure (see the top-level
`config/` and the main `README.md`), kept in case anything outside this
repo still points at the old paths.

- **`no-symbol-prefix/`** -- the original `config/<TIMEFRAME>/` layout
  (e.g. `config/M1/`, `config/D1/`), from before configs were split per
  symbol. Referenced in `PROJECT_DIRECTION.md` / `howItWorks.md`, which
  predate the `config/XAUUSD/` / `config/EURUSD/` split. Superseded by
  `config/XAUUSD/<TF>/` and `config/EURUSD/<TF>/`.

- **`xauusd/`, `eurusd/`** -- an older single-file-per-timeframe layout
  (`xauusd/m30.yaml` etc., one shared `known_at_delay.yaml` per symbol).
  Not referenced anywhere in the current docs or code -- appears to be a
  format that was tried and abandoned in favor of the current
  `config/<SYMBOL>/<TF>/pipeline_config.yaml` + `known_at_delay.yaml`
  per-timeframe folder layout.

If you're not intentionally using one of these, use the current layout
under `config/XAUUSD/` or `config/EURUSD/` instead.
