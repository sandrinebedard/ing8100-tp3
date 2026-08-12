#!/usr/bin/env python3
"""
plot_lesion_sizes.py

Create a scatter plot of lesion sizes from a features CSV produced
by `scripts/extract_features.py`.

Usage:
    python scripts/plot_lesion_sizes.py --csv results/features.csv --output results/lesion_size_scatter.png

Depends on: pandas, matplotlib, numpy
"""

import argparse
from pathlib import Path
import sys

import pandas as pd
import matplotlib.pyplot as plt


def plot_sizes(csv_path: Path, out_path: Path, xcol: str = "equiv_diameter_px", ycol: str = "area_px"):
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        raise SystemExit(2)

    df = pd.read_csv(csv_path)
    if df.empty:
        print("CSV is empty, nothing to plot.", file=sys.stderr)
        raise SystemExit(0)

    if ycol not in df.columns:
        print(f"Required column '{ycol}' not found in CSV.", file=sys.stderr)
        raise SystemExit(2)

    # Choose x-axis: prefer equiv_diameter_px, fallback to perimeter_px, else index
    if xcol not in df.columns:
        if "perimeter_px" in df.columns:
            xcol = "perimeter_px"
        else:
            df = df.reset_index(drop=True)
            df["index"] = df.index
            xcol = "index"

    plot_df = df[[xcol, ycol]].dropna()
    if plot_df.empty:
        print("No valid numeric pairs to plot (NaNs removed).", file=sys.stderr)
        raise SystemExit(0)

    plt.figure(figsize=(6, 5))
    plt.scatter(plot_df[xcol], plot_df[ycol], s=40, alpha=0.7)
    plt.xlabel(xcol.replace("_", " "))
    plt.ylabel(ycol.replace("_", " "))
    plt.title("Lesion size scatter plot")
    plt.grid(True, linestyle="--", alpha=0.4)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Scatter plot written to: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Plot lesion sizes from features CSV.")
    parser.add_argument("--csv", type=Path, default=Path("results/features.csv"), help="Path to features CSV")
    parser.add_argument("--output", type=Path, default=Path("results/lesion_size_scatter.png"), help="Output image path")
    parser.add_argument("--xcol", type=str, default="equiv_diameter_px", help="Column for x-axis (fallbacks applied)")
    parser.add_argument("--ycol", type=str, default="area_px", help="Column for y-axis")
    args = parser.parse_args()

    plot_sizes(args.csv, args.output, xcol=args.xcol, ycol=args.ycol)


if __name__ == "__main__":
    main()
