"""
edge_research: Systematic market-edge discovery pipeline.

Phases:
  1. Ingestion: Load MQL5-exported CSV -> Parquet
  2. Known-At: Determine when each indicator is available
  3. Conditions: Build atomic and combined signal conditions
  4. Frequency: Pre-filter conditions by occurrence rate
  5. Forward Profile: Compute probability profiles across horizons
  6. Significance: Statistical testing + FDR correction
  7. Validation: Walk-forward, regime stress, parameter sensitivity, cost
  8. Reporting: Generate edge reports in YAML
  9. MQL5 CodeGen: Render compilable .mq5 EAs
"""

__version__ = "0.1.0"

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)