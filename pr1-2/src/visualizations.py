"""Matplotlib/Seaborn chart builders.

Each function takes the flights DataFrame and returns a
``matplotlib.figure.Figure`` (or ``None`` when the data cannot support the
chart). The terminal app saves the figures to ``visualizations/``; the GUI
embeds the same figures in a Qt canvas - identical output either way.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

import matplotlib

matplotlib.use("Agg")  # safe default; the GUI swaps in a Qt canvas

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from . import analytics, config
from .utils import get_logger, timestamp_for_filename

logger = get_logger()

sns.set_theme(style="whitegrid")
_PALETTE = "viridis"


def _empty_figure(message: str) -> plt.Figure:
    """A figure that explains *why* a chart is unavailable."""
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.text(0.5, 0.5, message, ha="center", va="center",
            fontsize=12, color="#666666", wrap=True)
    ax.set_axis_off()
    fig.tight_layout()
    return fig


def _top_n_barh(labels, values, title, xlabel, color=None) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(range(len(labels))[::-1], values,
            color=color or sns.color_palette(_PALETTE, len(labels)))
    ax.set_yticks(range(len(labels))[::-1])
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def chart_status_distribution(df: pd.DataFrame) -> plt.Figure:
    dist = analytics.status_distribution(df)
    if dist.empty:
        return _empty_figure("No flight-status data available yet.")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    colors = sns.color_palette("Set2", len(dist))
    ax.bar(dist["flight_status"].str.title(), dist["flights"], color=colors)
    for i, (count, share) in enumerate(zip(dist["flights"], dist["share_pct"])):
        ax.text(i, count, f"{count}\n({share}%)", ha="center", va="bottom",
                fontsize=9)
    ax.set_title("Flight Status Distribution", fontsize=13, fontweight="bold")
    ax.set_xlabel("Status")
    ax.set_ylabel("Number of flights")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def chart_top_airlines(df: pd.DataFrame, n: int = 10) -> plt.Figure:
    top = analytics.top_airlines(df, n)
    if top.empty:
        return _empty_figure("No airline data available yet.")
    return _top_n_barh(
        list(top["airline"]), list(top["flights"]),
        f"Top {len(top)} Airlines by Stored Flights", "Flights",
    )


def chart_top_departure_airports(df: pd.DataFrame, n: int = 10) -> plt.Figure:
    top = analytics.top_airports(df, "dep", n)
    if top.empty:
        return _empty_figure("No departure airport data available yet.")
    labels = [f"{a} ({i})" if pd.notna(i) else str(a)
              for a, i in zip(top["airport"], top["iata"])]
    return _top_n_barh(
        labels, list(top["flights"]),
        f"Top {len(top)} Departure Airports", "Departing flights",
    )


def chart_top_arrival_airports(df: pd.DataFrame, n: int = 10) -> plt.Figure:
    top = analytics.top_airports(df, "arr", n)
    if top.empty:
        return _empty_figure("No arrival airport data available yet.")
    labels = [f"{a} ({i})" if pd.notna(i) else str(a)
              for a, i in zip(top["airport"], top["iata"])]
    return _top_n_barh(
        labels, list(top["flights"]),
        f"Top {len(top)} Arrival Airports", "Arriving flights",
    )


def chart_top_routes(df: pd.DataFrame, n: int = 10) -> plt.Figure:
    top = analytics.top_routes(df, n)
    if top.empty:
        return _empty_figure("No route data available yet.")
    return _top_n_barh(
        list(top["route"]), list(top["flights"]),
        f"Top {len(top)} Routes", "Flights",
    )


def chart_delay_histogram(df: pd.DataFrame) -> plt.Figure:
    stats = analytics.delay_statistics(df)
    if not stats.get("available"):
        return _empty_figure(
            stats.get("reason", "No delay data in the dataset."))
    fig, ax = plt.subplots(figsize=(7, 4.5))
    delays = df["max_delay_min"].dropna()
    ax.hist(delays, bins=25, color="#e8a33d", edgecolor="white")
    ax.axvline(delays.mean(), color="#d9534f", linestyle="--",
               label=f"Mean: {delays.mean():.0f} min")
    ax.set_title("Distribution of Reported Delays", fontsize=13,
                 fontweight="bold")
    ax.set_xlabel("Delay (minutes)")
    ax.set_ylabel("Flights")
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def chart_departure_hours(df: pd.DataFrame) -> plt.Figure:
    dist = analytics.departure_hour_distribution(df)
    if dist.empty:
        return _empty_figure(
            "Scheduled departure times are unavailable or unparsable.")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(dist["hour"], dist["flights"],
           color=sns.color_palette(_PALETTE, 1)[0])
    ax.set_xticks(range(0, 24, 2))
    ax.set_title("Flights by Scheduled Departure Hour (UTC)",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Flights")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


# Registry shared by the terminal menu and the GUI chart selector.
CHART_TYPES: Dict[str, Dict[str, object]] = {
    "status": {"title": "Flight Status Distribution",
               "builder": chart_status_distribution},
    "airlines": {"title": "Top Airlines",
                 "builder": chart_top_airlines},
    "dep_airports": {"title": "Top Departure Airports",
                     "builder": chart_top_departure_airports},
    "arr_airports": {"title": "Top Arrival Airports",
                     "builder": chart_top_arrival_airports},
    "routes": {"title": "Top Routes",
               "builder": chart_top_routes},
    "delays": {"title": "Delay Distribution",
               "builder": chart_delay_histogram},
    "dep_hours": {"title": "Departures by Hour",
                  "builder": chart_departure_hours},
}


def build_chart(chart_key: str, df: pd.DataFrame) -> plt.Figure:
    """Build one registered chart by key."""
    entry = CHART_TYPES.get(chart_key)
    if not entry:
        return _empty_figure(f"Unknown chart '{chart_key}'.")
    builder: Callable[[pd.DataFrame], plt.Figure] = entry["builder"]  # type: ignore
    return builder(df)


def save_chart(chart_key: str, df: pd.DataFrame,
               out_dir: Optional[Path] = None) -> Path:
    """Render a chart and save it as PNG under ``visualizations/``."""
    fig = build_chart(chart_key, df)
    out_dir = Path(out_dir) if out_dir else config.VISUALIZATIONS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{chart_key}_{timestamp_for_filename()}.png"
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info("Chart saved to %s", path)
    return path


def save_all_charts(df: pd.DataFrame) -> Dict[str, Path]:
    """Generate and save every supported chart; returns key -> path."""
    paths = {}
    for key in CHART_TYPES:
        try:
            paths[key] = save_chart(key, df)
        except Exception as exc:  # keep going even if one chart fails
            logger.warning("Chart %s failed: %s", key, exc)
    return paths
