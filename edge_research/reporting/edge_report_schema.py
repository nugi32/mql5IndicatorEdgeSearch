"""
Phase 8: Edge Report Schema

Data structures for edge reports.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class AtomicConditionReport:
    """Report format for an atomic condition."""
    column: str
    operator: str
    threshold: float | str


@dataclass
class FrequencyReport:
    """Frequency statistics."""
    n_occurrence: int
    freq_per_year: float
    date_range_start: str
    date_range_end: str


@dataclass
class SignificanceReport:
    """Significance test results for one horizon."""
    horizon: int
    prob_bull: float
    sample_size: int
    p_value: float
    p_adjusted: float
    significant: bool
    ci_lower: float
    ci_upper: float
    effect_size: float


@dataclass
class RobustnessReport:
    """Robustness validation results."""
    walk_forward: Dict[str, Any] = field(default_factory=dict)
    regime_stress: Dict[str, Any] = field(default_factory=dict)
    parameter_sensitivity: Dict[str, Any] = field(default_factory=dict)
    cost_model: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EdgeReport:
    """Complete edge report."""
    edge_id: str
    hypothesis: str
    entry_condition: str
    frequency: FrequencyReport
    optimal_horizon: int
    significance_results: List[SignificanceReport]
    baseline_prob: float
    robustness: RobustnessReport
    validated_period: str
    holdout_result: Dict[str, Any]
    mql5_mapping: str
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return asdict(self)

    def to_yaml_string(self) -> str:
        """Convert to YAML string."""
        data = self.to_dict()
        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def save_yaml(self, filepath: str) -> None:
        """Save to YAML file."""
        with open(filepath, 'w') as f:
            f.write(self.to_yaml_string())
