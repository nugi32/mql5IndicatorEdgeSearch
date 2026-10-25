"""Post-run ranker: reads walk-forward results and writes ranker_result.md."""

from edge_research.ranking.ranker import (  # noqa: F401
    RankerConfig,
    ranker_config_from_dict,
    run_ranker,
)
