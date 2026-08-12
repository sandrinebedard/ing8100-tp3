# ing8100 — Data processing and analysis (TP3)

This repository contains tools and scripts used for the third practical assignment (TP3) in the ing8100 course. It includes scripts to download data from a Dataverse/Borealis dataset, preprocess microscopy images, and organize data for analysis.


## Goals
- Provide reproducible steps to download and prepare dataset files used in the project
- Keep raw data separate from processed data
- Provide minimal, dependency-light scripts for common tasks

## Table of contents
- [Quick start](#quick-start)
- [Environment](#environment)
- [Data layout and conventions](#data-layout-and-conventions)
- [Preprocessing](#preprocessing)


## Contents
- `scripts/download_dataverse.py` — discover and download all files from a Dataverse dataset into `data/raw`.
- `scripts/preprocess_images.py` — rename and copy microscopy images into `data/processed`.
- `environment.yml` — conda environment specification used to run the scripts and analysis.

## Quick start
1. Create the conda environment (recommended):

```bash
conda env create -f environment.yml
conda activate venv-tp3
```

2. Download dataset files (saves into `data/raw`):

```bash
# Make sure you are in the venv before running the command
python scripts/download_dataverse.py
```

3. Preprocess images (renames and copies into `data/processed`):

```bash
python3 scripts/preprocess_images.py
```

Both scripts support options; run with `--help` to see available flags.

## Environment
- The repository includes `environment.yml`. It installs `requests` (used by the downloader) plus other analysis packages. Use conda to create the `venv-tp3` environment as shown above.

## Data layout and conventions
- `data/raw/` — raw dataset files downloaded from Dataverse. The downloader writes files directly under `data/raw` preserving subfolders from the dataset.
- `data/Even Illuminated Macro Images/` and `data/raw/Uneven Illuminated Macro Images/` — source folders containing microscopy `.jpg` files. The preprocess script reads from these (by default) and other provided input paths.
- `data/processed/` — flat directory of renamed microscopy images produced by `scripts/preprocess_images.py`.

## Preprocessing
- The preprocessing script looks recursively for `.jpg`/`.jpeg` files in the specified input directories.
- It renames files matching the pattern `{id}_Orig.{ext}` to `sub-{id}_original.{ext}` (case-insensitive), copies them into `data/processed`, and does not modify originals.
- If a name collision occurs in `data/processed` the script appends `_1`, `_2`, ... to the filename to avoid overwriting and prints a message.

### How to run the preprocessing script

```bash
python3 scripts/preprocess_images.py --input-dirs "data/Even Illuminated Macro Images" "data/raw/Uneven Illuminated Macro Images" --output-dir data/processed
```
