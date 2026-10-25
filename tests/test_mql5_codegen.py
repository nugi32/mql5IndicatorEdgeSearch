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


def test_magic_number_is_deterministic_across_processes():
    """
    MAGIC_NUMBER in the generated EA must be identical every time the
    same edge_id is regenerated -- it's how MT5 (and this project's
    position-recovery logic) distinguishes this EA's own orders. Python's
    built-in hash() is process-randomized for strings by default and must
    NOT be used for this; this test pins the exact deterministic value
    (zlib.crc32) so a regression back to hash() would be caught even
    though such a regression wouldn't show up as a failure within a
    single test process (hash() is stable within one process, only
    unstable ACROSS process restarts).
    """
    import subprocess
    import sys

    script = (
        "import sys; sys.path.insert(0, '.'); "
        "from edge_research.reporting.edge_report_schema import EdgeReport, FrequencyReport; "
        "from edge_research.mql5_codegen.generator import MQL5CodeGenerator; "
        "report = EdgeReport(edge_id='XAUUSD_M30_42', hypothesis='x', entry_condition='rsi_14 < 30', "
        "frequency=FrequencyReport(100, 15.0, '2023-01-01', '2024-01-01'), optimal_horizon=5, "
        "significance_results=[], baseline_prob=0.5, robustness=None, validated_period='x', "
        "holdout_result={}, mql5_mapping='', timestamp='2024-01-01T00:00:00'); "
        "code = MQL5CodeGenerator.generate_ea_code(report); "
        "line = [l for l in code.splitlines() if 'MAGIC_NUMBER' in l and '=' in l][0]; "
        "print(line.split('=')[1].split(';')[0].strip())"
    )

    results = set()
    for _ in range(3):
        # PYTHONHASHSEED=random (the default) forces a fresh random hash
        # seed each subprocess -- if generate_ea_code still used hash(),
        # this loop would produce 3 different values.
        out = subprocess.run(
            [sys.executable, "-c", script],
            cwd=".", capture_output=True, text=True, env={"PYTHONHASHSEED": "random", "PATH": "/usr/bin:/bin"},
        )
        assert out.returncode == 0, out.stderr
        results.add(out.stdout.strip())

    assert len(results) == 1, f"MAGIC_NUMBER changed across process restarts: {results}"


def test_magic_number_matches_known_crc32_value():
    """Pin the exact algorithm (zlib.crc32 % 1_000_000) with a hand-computed value."""
    import zlib

    edge_id = "XAUUSD_M30_42"
    expected = zlib.crc32(edge_id.encode("utf-8")) % 1000000

    report = EdgeReport(
        edge_id=edge_id,
        hypothesis="x",
        entry_condition="rsi_14 < 30",
        frequency=FrequencyReport(100, 15.0, "2023-01-01", "2024-01-01"),
        optimal_horizon=5,
        significance_results=[],
        baseline_prob=0.5,
        robustness=None,
        validated_period="x",
        holdout_result={},
        mql5_mapping="",
        timestamp="2024-01-01T00:00:00",
    )
    code = MQL5CodeGenerator.generate_ea_code(report)
    line = [l for l in code.splitlines() if "MAGIC_NUMBER" in l and "=" in l][0]
    actual = int(line.split("=")[1].split(";")[0].strip())

    assert actual == expected
