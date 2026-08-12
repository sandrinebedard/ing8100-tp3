#!/usr/bin/env python3
"""
melanoma_features.py

Simple feature extraction for melanoma macro/dermoscopy JPG images.

For each image in an input folder, this script:
  1. Segments the lesion from the background using Otsu thresholding
     on the saturation channel (works reasonably well for skin lesions
     which tend to be more saturated / darker than surrounding skin).
  2. Extracts simple SHAPE features from the segmentation mask:
       - area (pixels)
       - perimeter (pixels)
       - circularity (4*pi*area / perimeter^2) -> 1.0 = perfect circle
       - equivalent diameter
       - asymmetry index (based on ABCD "A" rule: overlap of the
         lesion mask with its own horizontal/vertical mirror)
  3. Extracts simple COLOR features from the pixels inside the mask:
       - mean and std of R, G, B channels
       - mean and std of Hue, Saturation, Value
  4. Saves, for each image, a 2-panel figure:
       - Panel 1: original image with lesion contour overlay
       - Panel 2: color histogram (R/G/B) of pixels inside the lesion
  5. Writes a CSV with all extracted features for every image, plus a
     short plain-text summary report.

Usage:
    python melanoma_features.py --input data/processed --output results

Dependencies (pip install):
    opencv-python numpy matplotlib pandas
"""

import argparse
import sys
from pathlib import Path
from typing import Tuple, Optional

import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def segment_lesion(bgr_image: np.ndarray) -> Tuple[np.ndarray, float]:
    """Segment the lesion using Otsu thresholding on grayscale intensity.

    Returns a binary mask (uint8, values 0/255) of the largest connected
    component found, with small morphological cleanup applied.
    """
    # Use grayscale intensity (black & white) instead of saturation.
    gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
    # small blur helps Otsu be more stable
    gray_blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # Otsu picks a threshold separating bright vs dark regions.
    # Depending on image characteristics the lesion may be darker than
    # surrounding skin, so invert the binary mask when the foreground
    # picked by Otsu corresponds to the brighter background.
    thresh_val, mask = cv2.threshold(gray_blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # If the masked region (mask==255) is brighter than the image mean,
    # it likely represents background; invert so lesion becomes foreground.
    try:
        if mask.dtype == np.uint8 and np.any(mask == 255):
            mean_mask = float(gray[mask == 255].mean())
            if mean_mask > float(gray.mean()):
                mask = cv2.bitwise_not(mask)
    except Exception:
        # If any unexpected issue occurs, fall back to the raw mask.
        pass

    # Morphological cleanup: remove small noise, fill small holes.
    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # Keep only the largest connected component (assume it's the lesion).
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return mask, float(thresh_val)  # empty / all-zero mask, caller should handle this

    largest = max(contours, key=cv2.contourArea)
    clean_mask = np.zeros_like(mask)
    cv2.drawContours(clean_mask, [largest], -1, 255, thickness=cv2.FILLED)
    return clean_mask, float(thresh_val)


def asymmetry_index(mask: np.ndarray) -> float:
    """Rough ABCD-style asymmetry score: 0 = perfectly symmetric.

    Crops the mask to its bounding box, then compares the mask to its
    own horizontal and vertical mirror. The fraction of non-overlapping
    pixels (averaged over both axes) is returned.
    """
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return np.nan

    x0, x1 = xs.min(), xs.max() + 1
    y0, y1 = ys.min(), ys.max() + 1
    crop = mask[y0:y1, x0:x1] > 0

    horiz_flip = np.fliplr(crop)
    vert_flip = np.flipud(crop)

    horiz_diff = np.logical_xor(crop, horiz_flip).sum() / crop.sum()
    vert_diff = np.logical_xor(crop, vert_flip).sum() / crop.sum()

    return float((horiz_diff + vert_diff) / 2)


def extract_shape_features(mask: np.ndarray) -> dict:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {
            "area_px": np.nan,
            "perimeter_px": np.nan,
            "circularity": np.nan,
            "equiv_diameter_px": np.nan,
            "asymmetry_index": np.nan,
        }

    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    perimeter = cv2.arcLength(largest, closed=True)
    circularity = (4 * np.pi * area / (perimeter ** 2)) if perimeter > 0 else np.nan
    equiv_diameter = np.sqrt(4 * area / np.pi) if area > 0 else np.nan

    return {
        "area_px": area,
        "perimeter_px": perimeter,
        "circularity": circularity,
        "equiv_diameter_px": equiv_diameter,
        "asymmetry_index": asymmetry_index(mask),
    }


def extract_color_features(bgr_image: np.ndarray, mask: np.ndarray) -> dict:
    hsv = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2HSV)
    m = mask > 0

    if m.sum() == 0:
        keys = ["r", "g", "b", "h", "s", "v"]
        feats = {}
        for k in keys:
            feats[f"mean_{k}"] = np.nan
            feats[f"std_{k}"] = np.nan
        return feats

    b, g, r = cv2.split(bgr_image)
    h, s, v = cv2.split(hsv)

    feats = {}
    for name, channel in [("r", r), ("g", g), ("b", b), ("h", h), ("s", s), ("v", v)]:
        vals = channel[m].astype(np.float64)
        feats[f"mean_{name}"] = float(vals.mean())
        feats[f"std_{name}"] = float(vals.std())
    return feats


def make_figure(bgr_image: np.ndarray, mask: np.ndarray, out_path: Path, title: str, threshold: Optional[float] = None):
    rgb = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))

    # Panel 1: image with lesion contour overlay
    axes[0].imshow(rgb)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        c = c.reshape(-1, 2)
        axes[0].plot(c[:, 0], c[:, 1], linewidth=2, color="yellow")
    axes[0].set_title("Segmented lesion")
    axes[0].axis("off")

    # Panel 2: grayscale intensity histogram (black & white)
    m = mask > 0
    gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
    vals = gray[m]
    if vals.size > 0:
        axes[1].hist(vals, bins=32, range=(0, 255), color="black")
        if threshold is not None:
            axes[1].axvline(threshold, color="red", linestyle="--", linewidth=1.5, label=f"Otsu={threshold:.0f}")
            axes[1].legend()
    axes[1].set_title("Intensity histogram (lesion pixels)")
    axes[1].set_xlabel("Pixel intensity")
    axes[1].set_ylabel("Count")
    axes[1].set_xlim(0, 255)

    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def process_folder(input_dir: Path, output_dir: Path) -> pd.DataFrame:
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    image_paths = sorted(
        p for p in input_dir.rglob("*") if p.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not image_paths:
        print(f"No images found in {input_dir}", file=sys.stderr)
        return pd.DataFrame()

    rows = []
    for path in image_paths:
        bgr = cv2.imread(str(path))
        if bgr is None:
            print(f"  [skip] could not read: {path}", file=sys.stderr)
            continue

        mask, thresh = segment_lesion(bgr)
        shape_feats = extract_shape_features(mask)
        color_feats = extract_color_features(bgr, mask)

        row = {"filename": path.name}
        row.update(shape_feats)
        row.update(color_feats)
        rows.append(row)

        fig_path = figures_dir / f"{path.stem}_features.png"
        make_figure(bgr, mask, fig_path, title=path.name, threshold=thresh)
        print(f"  [ok] {path.name} -> {fig_path.name}")

    return pd.DataFrame(rows)


def write_summary_report(df: pd.DataFrame, output_dir: Path):
    report_path = output_dir / "summary_report.txt"
    lines = []
    lines.append("Melanoma image feature extraction — summary report")
    lines.append("=" * 55)
    lines.append(f"Number of images processed: {len(df)}")
    lines.append("")

    if len(df) > 0:
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        lines.append("Feature averages (mean ± std) across all images:")
        for col in numeric_cols:
            mean = df[col].mean()
            std = df[col].std()
            lines.append(f"  {col:20s}: {mean:8.3f} ± {std:8.3f}")

        lines.append("")
        lines.append("Most circular lesion:  "
                      f"{df.loc[df['circularity'].idxmax(), 'filename']} "
                      f"(circularity={df['circularity'].max():.3f})")
        lines.append("Least circular lesion: "
                      f"{df.loc[df['circularity'].idxmin(), 'filename']} "
                      f"(circularity={df['circularity'].min():.3f})")
        lines.append("Most asymmetric lesion: "
                      f"{df.loc[df['asymmetry_index'].idxmax(), 'filename']} "
                      f"(asymmetry={df['asymmetry_index'].max():.3f})")

    report_text = "\n".join(lines)
    report_path.write_text(report_text)
    print("\n" + report_text)
    print(f"\nSummary report written to: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Extract simple shape/color features from melanoma images.")
    parser.add_argument("--input", type=Path, default=Path("data/processed"),
                         help="Folder containing input JPG/PNG images (default: data/processed)")
    parser.add_argument("--output", type=Path, default=Path("results"),
                         help="Folder to write CSV, figures, and report to (default: results)")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    print(f"Processing images in: {args.input}")
    df = process_folder(args.input, args.output)

    if df.empty:
        print("No results to save.")
        return

    csv_path = args.output / "features.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nFeatures CSV written to: {csv_path}")

    write_summary_report(df, args.output)


if __name__ == "__main__":
    main()