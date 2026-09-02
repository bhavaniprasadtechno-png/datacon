"""Re-export insight_analyzer module for flexible import resolution."""
import sys
from pathlib import Path

# Add app/ai to sys.path if needed
_ai_path = str(Path(__file__).parent / "app" / "ai")
if _ai_path not in sys.path:
    sys.path.insert(0, _ai_path)

from app.agents.insight_analyzer import (
    _detect_columns,
    _format_num,
    determine_analytical_intent,
    analyze_time_series,
    analyze_ranking,
    analyze_comparison,
    analyze_anomaly,
    analyze_aggregate,
    analyze_distribution,
    analyze_filtering,
    analyze_small_table,
    select_important_rows,
    format_compact_analytical_context,
    build_insight_context,
    get_output_token_budget,
)

__all__ = [
    "_detect_columns",
    "_format_num",
    "determine_analytical_intent",
    "analyze_time_series",
    "analyze_ranking",
    "analyze_comparison",
    "analyze_anomaly",
    "analyze_aggregate",
    "analyze_distribution",
    "analyze_filtering",
    "analyze_small_table",
    "select_important_rows",
    "format_compact_analytical_context",
    "build_insight_context",
    "get_output_token_budget",
]
