"""
Phase 9: MQL5 Code Generation

Render edge definitions into compilable .mq5 EA code.
"""

import logging
from pathlib import Path
from typing import Dict

from jinja2 import Template

from edge_research.conditions.condition_library import (
    AtomicCondition,
    CombinedCondition,
    Operator,
)
from edge_research.reporting.edge_report_schema import EdgeReport

logger = logging.getLogger(__name__)


class MQL5CodeGenerator:
    """Generate MQL5 code from edge reports."""

    OPERATOR_MAP = {
        Operator.LT: "<",
        Operator.GT: ">",
        Operator.LTE: "<=",
        Operator.GTE: ">=",
        Operator.EQ: "==",
        Operator.NEQ: "!=",
        Operator.CROSSES_ABOVE: ">",  # Simplified
        Operator.CROSSES_BELOW: "<",  # Simplified
    }

    @staticmethod
    def condition_to_mql5(condition_str: str) -> str:
        """
        Convert edge_research condition string to MQL5 boolean expression.

        Parameters
        ----------
        condition_str : str
            Condition description (e.g., "rsi_14 < 30 AND ma_20_ema > ma_50_ema").

        Returns
        -------
        str
            MQL5-compatible boolean expression.

        Notes
        -----
        Simple regex-based translation. For complex conditions, manual review recommended.
        """
        # Replace common operators
        mql5_expr = condition_str
        mql5_expr = mql5_expr.replace(" AND ", " && ")
        mql5_expr = mql5_expr.replace(" OR ", " || ")
        mql5_expr = mql5_expr.replace(" NOT ", " !")
        
        # Wrap column names with iClose/iCustom if needed
        # (This is simplified; real implementation would parse more carefully)
        
        return mql5_expr

    @staticmethod
    def atomic_to_mql5(atom: AtomicCondition) -> str:
        """
        Convert an atomic condition to MQL5 code.

        Parameters
        ----------
        atom : AtomicCondition
            Atomic condition.

        Returns
        -------
        str
            MQL5 boolean expression.
        """
        op = MQL5CodeGenerator.OPERATOR_MAP.get(atom.operator, str(atom.operator.value))
        
        if isinstance(atom.threshold, str):
            # Column-to-column comparison
            threshold_str = atom.threshold
        else:
            # Fixed threshold
            threshold_str = str(atom.threshold)
        
        return f"(iClose(Symbol(), Period(), 0) {op} {threshold_str})"

    @staticmethod
    def combined_to_mql5(combined: CombinedCondition) -> str:
        """
        Convert a combined condition to MQL5 code.

        Parameters
        ----------
        combined : CombinedCondition
            Combined condition.

        Returns
        -------
        str
            MQL5 boolean expression (AND of atoms).
        """
        atoms_mql5 = [MQL5CodeGenerator.atomic_to_mql5(atom) for atom in combined.atoms]
        return " && ".join(atoms_mql5)

    @staticmethod
    def generate_ea_code(
        edge_report: EdgeReport,
        template_path: str | Path = None,
    ) -> str:
        """
        Generate complete .mq5 EA code from edge report.

        Parameters
        ----------
        edge_report : EdgeReport
            Edge report with validated condition.
        template_path : str | Path, optional
            Path to Jinja2 template. If None, uses built-in template.

        Returns
        -------
        str
            Compiled MQL5 source code.

        Notes
        -----
        Template variables:
        - EA_NAME
        - EDGE_ID
        - HYPOTHESIS
        - MAGIC_NUMBER (derived from edge_id hash)
        - EXIT_BARS
        - ENTRY_CONDITION
        """
        # Load template
        if template_path:
            template_path = Path(template_path)
            with open(template_path) as f:
                template_str = f.read()
        else:
            # Use default built-in template (simplified version here)
            template_str = """
//--- EA: {{ EDGE_ID }}
//--- Hypothesis: {{ HYPOTHESIS }}
//--- Entry Condition: {{ ENTRY_CONDITION }}
bool CheckEntryCondition() {
    return {{ ENTRY_CONDITION }};
}
"""
        
        template = Template(template_str)
        
        # Derive magic number from edge_id
        magic_number = hash(edge_report.edge_id) % 1000000
        
        # Convert condition to MQL5
        mql5_condition = MQL5CodeGenerator.condition_to_mql5(
            edge_report.entry_condition
        )
        
        # Render
        code = template.render(
            EA_NAME=edge_report.edge_id.replace(" ", "_"),
            EDGE_ID=edge_report.edge_id,
            HYPOTHESIS=edge_report.hypothesis,
            MAGIC_NUMBER=magic_number,
            EXIT_BARS=edge_report.optimal_horizon,
            ENTRY_CONDITION=mql5_condition,
        )
        
        return code

    @staticmethod
    def save_ea_file(
        edge_report: EdgeReport,
        output_dir: str | Path,
        template_path: str | Path = None,
    ) -> Path:
        """
        Generate and save .mq5 EA file.

        Parameters
        ----------
        edge_report : EdgeReport
            Edge report.
        output_dir : str | Path
            Directory to save .mq5 file.
        template_path : str | Path, optional
            Path to custom Jinja2 template.

        Returns
        -------
        Path
            Path to generated .mq5 file.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        code = MQL5CodeGenerator.generate_ea_code(edge_report, template_path)
        
        filename = f"{edge_report.edge_id.replace(' ', '_')}.mq5"
        filepath = output_dir / filename
        
        filepath.write_text(code)
        logger.info(f"Generated MQL5 EA: {filepath}")
        
        return filepath
