# edge_research

A systematic market-edge discovery pipeline that consumes MQL5-exported indicator data and validates trading edges through statistical rigor, walk-forward testing, and robustness checks.

## Features

- **Phase 1**: Ingest MQL5 CSV → validate → store as Parquet
- **Phase 2**: Known-at tagging (forward compatibility for indicator delays)
- **Phase 3**: Condition DSL (atomic + combined boolean conditions)
- **Phase 4**: Frequency filtering (min occurrence / per-year thresholds)
- **Phase 5**: Forward probability profiling (1 to MAX_HORIZON bars ahead)
- **Phase 6**: Statistical significance testing (two-sided z-test + Benjamini-Hochberg FDR)
- **Phase 7**: Robustness validation (walk-forward, regime stress, parameter sensitivity, cost modeling)
- **Phase 8**: YAML edge reports with full provenance
- **Phase 9**: Auto-generate compilable MQL5 Expert Advisors

## Installation

```bash  
pip install -e .  
Or with dev dependencies:
