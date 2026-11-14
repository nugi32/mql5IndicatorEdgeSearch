# Archived Configuration Profiles

This directory contains older configuration layouts retained for reference. New runs should use the current symbol/timeframe profiles under `config/<SYMBOL>/<TIMEFRAME>/`, `config/SHORT_DATA/<SYMBOL>/<TIMEFRAME>/`, or `config/WALKFORWARD/<SYMBOL>/<TIMEFRAME>/`.

- `no-symbol-prefix/` contains the older timeframe-only layout.
- `xauusd/` and `eurusd/` contain older single-file-per-timeframe layouts.

Do not use these archived profiles for new research unless a specific legacy workflow requires them. The current structure and profile-selection guidance are documented in the [Configuration Guide](../../docs/configuration.md).
