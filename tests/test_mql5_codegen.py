"""Tests for Phase 9: MQL5 Code Generation."""

import pytest

from edge_research.conditions.condition_library import (
    AtomicCondition,
    Operator,
)
from edge_research.mql5_codegen.generator import MQL5CodeGenerator
from edge_research.reporting.edge_report_schema import EdgeReport, FrequencyReport


def test_atomic_to_mql5():
    """Test atomic condition to MQL5 conversion."""
    cond = AtomicCondition('rsi_14', Operator.LT, 30.0)
    mql5_code = MQL5CodeGenerator.atomic_to_mql5(cond)
    
    assert 'iClose' in mql5_code or 'rsi_14' in mql5_code
    assert '<' in mql5_code
    assert '30' in mql5_code


def test_condition_to_mql5():
    """Test condition string to MQL5 conversion."""
    cond_str = "rsi_14 < 30 AND ma_20_ema > ma_50_ema"
    mql5_code = MQL5CodeGenerator.condition_to_mql5(cond_str)
    
    assert '&&' in mql5_code  # AND should be converted to &&


def test_generate_ea_code():
    """Test full EA code generation."""
    report = EdgeReport(
        edge_id="TEST_EDGE_001",
        hypothesis="RSI oversold reversal",
        entry_condition="rsi_14 < 30",
        frequency=FrequencyReport(100, 15.0, "2023-01-01", "2024-01-01"),
        optimal_horizon=5,
        significance_results=[],
        baseline_prob=0.5,
        robustness=None,
        validated_period="2023-2024",
        holdout_result={},
        mql5_mapping="",
        timestamp="2024-01-01T00:00:00",
    )
    
    code = MQL5CodeGenerator.generate_ea_code(report)
    
    assert 'CheckEntryCondition' in code
    assert 'TEST_EDGE_001' in code
    assert 'RSI oversold reversal' in code


def test_mql5_operator_mapping():
    """Test all operator mappings."""
    operators = [
        (Operator.LT, '<'),
        (Operator.GT, '>'),
        (Operator.LTE, '<='),
        (Operator.GTE, '>='),
    ]
    
    for op, expected_symbol in operators:
        mapped = MQL5CodeGenerator.OPERATOR_MAP.get(op)
        assert mapped == expected_symbol
