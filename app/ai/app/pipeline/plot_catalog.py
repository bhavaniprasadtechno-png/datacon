"""Plot Catalog & Recommendation Engine — stores available visualization types
and maps recommended plots dynamically to native UI Recharts visualizations.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

PLOTS: List[Dict[str, str]] = [
    # =====================================================
    # MATPLOTLIB - BASIC PLOTS
    # =====================================================
    {
        "plot_name": "Line Plot",
        "plot_type": "Basic Plots",
        "plot_library": "matplotlib",
        "description": "Visualize trends and changes over time."
    },
    {
        "plot_name": "Scatter Plot",
        "plot_type": "Basic Plots",
        "plot_library": "matplotlib",
        "description": "Show relationships between numerical variables."
    },
    {
        "plot_name": "Bar Plot",
        "plot_type": "Basic Plots",
        "plot_library": "matplotlib",
        "description": "Compare values across categories."
    },
    {
        "plot_name": "Horizontal Bar Plot",
        "plot_type": "Basic Plots",
        "plot_library": "matplotlib",
        "description": "Compare categories with long labels."
    },
    {
        "plot_name": "Histogram",
        "plot_type": "Basic Plots",
        "plot_library": "matplotlib",
        "description": "Display frequency distribution of numeric data."
    },
    {
        "plot_name": "Pie Chart",
        "plot_type": "Basic Plots",
        "plot_library": "matplotlib",
        "description": "Show proportions of a whole."
    },
    {
        "plot_name": "Stem Plot",
        "plot_type": "Basic Plots",
        "plot_library": "matplotlib",
        "description": "Display discrete data values."
    },
    {
        "plot_name": "Step Plot",
        "plot_type": "Basic Plots",
        "plot_library": "matplotlib",
        "description": "Show changes occurring at specific intervals."
    },

    # =====================================================
    # MATPLOTLIB - STATISTICAL PLOTS
    # =====================================================
    {
        "plot_name": "Box Plot",
        "plot_type": "Statistical Plots",
        "plot_library": "matplotlib",
        "description": "Identify spread, quartiles, and outliers."
    },
    {
        "plot_name": "Violin Plot",
        "plot_type": "Statistical Plots",
        "plot_library": "matplotlib",
        "description": "Visualize distribution and density."
    },
    {
        "plot_name": "Error Bar Plot",
        "plot_type": "Statistical Plots",
        "plot_library": "matplotlib",
        "description": "Display variability or uncertainty."
    },
    {
        "plot_name": "Event Plot",
        "plot_type": "Statistical Plots",
        "plot_library": "matplotlib",
        "description": "Visualize timing of events."
    },

    # =====================================================
    # MATPLOTLIB - DISTRIBUTION PLOTS
    # =====================================================
    {
        "plot_name": "Density Plot",
        "plot_type": "Distribution Plots",
        "plot_library": "matplotlib",
        "description": "Estimate the probability density of data."
    },
    {
        "plot_name": "Cumulative Distribution Plot",
        "plot_type": "Distribution Plots",
        "plot_library": "matplotlib",
        "description": "Show cumulative probability distribution."
    },

    # =====================================================
    # MATPLOTLIB - MATRIX AND IMAGE PLOTS
    # =====================================================
    {
        "plot_name": "Heatmap",
        "plot_type": "Matrix and Image Plots",
        "plot_library": "matplotlib",
        "description": "Visualize matrix values using color."
    },
    {
        "plot_name": "Matrix Plot",
        "plot_type": "Matrix and Image Plots",
        "plot_library": "matplotlib",
        "description": "Display matrix data structures."
    },
    {
        "plot_name": "Contour Plot",
        "plot_type": "Matrix and Image Plots",
        "plot_library": "matplotlib",
        "description": "Represent 3D surfaces on 2D planes."
    },
    {
        "plot_name": "Filled Contour Plot",
        "plot_type": "Matrix and Image Plots",
        "plot_library": "matplotlib",
        "description": "Contour plot with filled color regions."
    },
    {
        "plot_name": "Image Display",
        "plot_type": "Matrix and Image Plots",
        "plot_library": "matplotlib",
        "description": "Display image data."
    },

    # =====================================================
    # MATPLOTLIB - 3D PLOTS
    # =====================================================
    {
        "plot_name": "3D Scatter Plot",
        "plot_type": "3D Plots",
        "plot_library": "matplotlib",
        "description": "Visualize points in three dimensions."
    },
    {
        "plot_name": "3D Line Plot",
        "plot_type": "3D Plots",
        "plot_library": "matplotlib",
        "description": "Visualize line relationships in 3D."
    },
    {
        "plot_name": "3D Surface Plot",
        "plot_type": "3D Plots",
        "plot_library": "matplotlib",
        "description": "Display continuous surfaces in 3D."
    },
    {
        "plot_name": "3D Wireframe Plot",
        "plot_type": "3D Plots",
        "plot_library": "matplotlib",
        "description": "Represent surfaces using wireframes."
    },
    {
        "plot_name": "3D Contour Plot",
        "plot_type": "3D Plots",
        "plot_library": "matplotlib",
        "description": "Display contour levels in 3D."
    },
    {
        "plot_name": "3D Bar Plot",
        "plot_type": "3D Plots",
        "plot_library": "matplotlib",
        "description": "Compare values using 3D bars."
    },

    # =====================================================
    # MATPLOTLIB - SPECIALIZED PLOTS
    # =====================================================
    {
        "plot_name": "Polar Plot",
        "plot_type": "Specialized Plots",
        "plot_library": "matplotlib",
        "description": "Visualize data in polar coordinates."
    },
    {
        "plot_name": "Quiver Plot",
        "plot_type": "Specialized Plots",
        "plot_library": "matplotlib",
        "description": "Display vector fields."
    },
    {
        "plot_name": "Stream Plot",
        "plot_type": "Specialized Plots",
        "plot_library": "matplotlib",
        "description": "Visualize flow fields."
    },
    {
        "plot_name": "Hexbin Plot",
        "plot_type": "Specialized Plots",
        "plot_library": "matplotlib",
        "description": "Visualize dense scatter data using hexagons."
    },
    {
        "plot_name": "Area Plot",
        "plot_type": "Specialized Plots",
        "plot_library": "matplotlib",
        "description": "Show cumulative totals over time."
    },
    {
        "plot_name": "Stack Plot",
        "plot_type": "Specialized Plots",
        "plot_library": "matplotlib",
        "description": "Display part-to-whole relationships over time."
    },
    {
        "plot_name": "Broken Bar Plot",
        "plot_type": "Specialized Plots",
        "plot_library": "matplotlib",
        "description": "Represent intervals on a timeline."
    },

    # =====================================================
    # SEABORN - RELATIONAL PLOTS
    # =====================================================
    {
        "plot_name": "Scatter Plot",
        "plot_type": "Relational Plots",
        "plot_library": "seaborn",
        "description": "Visualize relationships between variables."
    },
    {
        "plot_name": "Line Plot",
        "plot_type": "Relational Plots",
        "plot_library": "seaborn",
        "description": "Visualize trends with confidence intervals."
    },
    {
        "plot_name": "Relational Plot",
        "plot_type": "Relational Plots",
        "plot_library": "seaborn",
        "description": "Flexible interface for relational visualizations."
    },

    # =====================================================
    # SEABORN - DISTRIBUTION PLOTS
    # =====================================================
    {
        "plot_name": "Histogram",
        "plot_type": "Distribution Plots",
        "plot_library": "seaborn",
        "description": "Display frequency distributions."
    },
    {
        "plot_name": "KDE Plot",
        "plot_type": "Distribution Plots",
        "plot_library": "seaborn",
        "description": "Estimate probability density."
    },
    {
        "plot_name": "Distribution Plot",
        "plot_type": "Distribution Plots",
        "plot_library": "seaborn",
        "description": "Analyze distributions of variables."
    },
    {
        "plot_name": "ECDF Plot",
        "plot_type": "Distribution Plots",
        "plot_library": "seaborn",
        "description": "Visualize cumulative distributions."
    },
    {
        "plot_name": "Rug Plot",
        "plot_type": "Distribution Plots",
        "plot_library": "seaborn",
        "description": "Show individual observations on an axis."
    },

    # =====================================================
    # SEABORN - CATEGORICAL PLOTS
    # =====================================================
    {
        "plot_name": "Bar Plot",
        "plot_type": "Categorical Plots",
        "plot_library": "seaborn",
        "description": "Compare aggregated category values."
    },
    {
        "plot_name": "Count Plot",
        "plot_type": "Categorical Plots",
        "plot_library": "seaborn",
        "description": "Count category occurrences."
    },
    {
        "plot_name": "Box Plot",
        "plot_type": "Categorical Plots",
        "plot_library": "seaborn",
        "description": "Compare category distributions."
    },
    {
        "plot_name": "Violin Plot",
        "plot_type": "Categorical Plots",
        "plot_library": "seaborn",
        "description": "Display category density distributions."
    },
    {
        "plot_name": "Strip Plot",
        "plot_type": "Categorical Plots",
        "plot_library": "seaborn",
        "description": "Display individual observations."
    },
    {
        "plot_name": "Swarm Plot",
        "plot_type": "Categorical Plots",
        "plot_library": "seaborn",
        "description": "Display observations without overlap."
    },
    {
        "plot_name": "Point Plot",
        "plot_type": "Categorical Plots",
        "plot_library": "seaborn",
        "description": "Show estimates and confidence intervals."
    },
    {
        "plot_name": "Boxen Plot",
        "plot_type": "Categorical Plots",
        "plot_library": "seaborn",
        "description": "Enhanced box plot for large datasets."
    },
    {
        "plot_name": "Categorical Plot",
        "plot_type": "Categorical Plots",
        "plot_library": "seaborn",
        "description": "General categorical visualization interface."
    },

    # =====================================================
    # SEABORN - MATRIX PLOTS
    # =====================================================
    {
        "plot_name": "Heatmap",
        "plot_type": "Matrix Plots",
        "plot_library": "seaborn",
        "description": "Visualize matrices using color gradients."
    },
    {
        "plot_name": "Clustermap",
        "plot_type": "Matrix Plots",
        "plot_library": "seaborn",
        "description": "Cluster rows and columns in a heatmap."
    },

    # =====================================================
    # SEABORN - REGRESSION PLOTS
    # =====================================================
    {
        "plot_name": "Regression Plot",
        "plot_type": "Regression Plots",
        "plot_library": "seaborn",
        "description": "Show regression relationships."
    },
    {
        "plot_name": "Linear Model Plot",
        "plot_type": "Regression Plots",
        "plot_library": "seaborn",
        "description": "Visualize linear models across subsets."
    },
    {
        "plot_name": "Residual Plot",
        "plot_type": "Regression Plots",
        "plot_library": "seaborn",
        "description": "Evaluate regression residuals."
    },

    # =====================================================
    # SEABORN - MULTIVARIATE PLOTS
    # =====================================================
    {
        "plot_name": "Pair Plot",
        "plot_type": "Multivariate Plots",
        "plot_library": "seaborn",
        "description": "Visualize pairwise variable relationships."
    },
    {
        "plot_name": "Joint Plot",
        "plot_type": "Multivariate Plots",
        "plot_library": "seaborn",
        "description": "Combine bivariate and univariate visualizations."
    },
    {
        "plot_name": "PairGrid",
        "plot_type": "Multivariate Plots",
        "plot_library": "seaborn",
        "description": "Customizable pairwise relationship grid."
    },
    {
        "plot_name": "FacetGrid",
        "plot_type": "Multivariate Plots",
        "plot_library": "seaborn",
        "description": "Create multi-panel visualizations by subsets."
    }
]

_TEMPORAL_KEYWORDS = {
    "date", "time", "month", "year", "quarter", "day", "week",
    "period", "timestamp", "hour", "dt", "created_at", "updated_at",
    "order_date", "daily", "monthly", "yearly", "trend", "history"
}


def recommend_plot_from_catalog(
    columns: List[str],
    row_count: int,
    numeric_cols: List[str],
    categorical_cols: List[str],
    date_cols: List[str],
    sample_labels: Optional[List[str]] = None,
    user_query: str = ""
) -> Dict[str, str]:
    """
    Analyzes dataset metadata and selects the most suitable plot from the catalog.
    Returns the catalog entry and maps it to a native UI chart type.
    """
    query_lower = (user_query or "").lower()

    # 1. Temporal / Time-Series Data -> Line Plot
    has_temporal = bool(date_cols) or any(
        any(k in c.lower() for k in _TEMPORAL_KEYWORDS) for c in (categorical_cols + columns)
    ) or any(k in query_lower for k in ("trend", "over time", "monthly", "daily", "yearly", "growth", "history"))

    if has_temporal and (numeric_cols or row_count > 1):
        for plot in PLOTS:
            if plot["plot_name"] == "Line Plot" and plot["plot_library"] == "matplotlib":
                return {**plot, "ui_chart_type": "line", "reason": "Visualize chronological trends over time."}

    # 2. Categorical comparisons with multiple items or long labels -> Horizontal Bar Plot
    avg_label_len = (
        sum(len(str(l)) for l in sample_labels) / max(len(sample_labels), 1)
        if sample_labels else 0
    )
    if (len(sample_labels or []) > 6 or avg_label_len > 12) and (categorical_cols and numeric_cols):
        for plot in PLOTS:
            if plot["plot_name"] == "Horizontal Bar Plot":
                return {**plot, "ui_chart_type": "horizontal_bar", "reason": "Compare categories with long labels clearly."}

    # 3. Discrete categories / Short comparisons -> Bar Plot
    if categorical_cols and numeric_cols:
        for plot in PLOTS:
            if plot["plot_name"] == "Bar Plot" and plot["plot_library"] == "matplotlib":
                return {**plot, "ui_chart_type": "bar", "reason": "Compare values across distinct categories."}

    # 4. Single numeric distribution -> Histogram or Bar
    if numeric_cols and row_count > 1:
        for plot in PLOTS:
            if plot["plot_name"] == "Bar Plot":
                return {**plot, "ui_chart_type": "bar", "reason": "Display aggregated numeric metrics."}

    # Default fallback
    return {
        "plot_name": "Horizontal Bar Plot",
        "plot_type": "Basic Plots",
        "plot_library": "matplotlib",
        "description": "Compare categories with long labels.",
        "ui_chart_type": "horizontal_bar",
        "reason": "Default responsive category comparison."
    }
