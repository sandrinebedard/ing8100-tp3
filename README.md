# ing8100 — Data processing and analysis (TP3)

This repository contains tools and scripts used for the third practical assignment (TP3) in the ing8100 course. It includes scripts to download data from a Dataverse/Borealis dataset, preprocess microscopy images, and organize data for analysis.

Goals
- Provide reproducible steps to download and prepare dataset files used in the project
- Keep raw data separate from processed data
- Provide minimal, dependency-light scripts for common tasks

Contents
- `scripts/download_dataverse.py` — discover and download all files from a Dataverse dataset into `data/raw`.
- `scripts/preprocess_images.py` — rename and copy microscopy images into `data/processed`.
- `environment.yml` — conda environment specification used to run the scripts and analysis.

Quick start
1. Create the conda environment (recommended):

```bash
conda env create -f environment.yml
conda activate venv-tp3
```

2. Download dataset files (saves into `data/raw`):

```bash
python3 scripts/download_dataverse.py
```

3. Preprocess microscopy images (renames and copies into `data/processed`):

```bash
python3 scripts/preprocess_images.py
```

Both scripts support options; run with `--help` to see available flags.

Environment
- The repository includes `environment.yml`. It installs `requests` (used by the downloader) plus other analysis packages. Use conda to create the `venv-tp3` environment as shown above.

Data layout and conventions
- `data/raw/` — raw dataset files downloaded from Dataverse. The downloader writes files directly under `data/raw` preserving subfolders from the dataset.
- `data/Even Illuminated Macro Images/` and `data/raw/Uneven Illuminated Macro Images/` — source folders containing microscopy `.jpg` files. The preprocess script reads from these (by default) and other provided input paths.
- `data/processed/` — flat directory of renamed microscopy images produced by `scripts/preprocess_images.py`.

Preprocessing details
- The preprocessing script looks recursively for `.jpg`/`.jpeg` files in the specified input directories.
- It renames files matching the pattern `{id}_Orig.{ext}` to `sub-{id}_original.{ext}` (case-insensitive), copies them into `data/processed`, and does not modify originals.
- If a name collision occurs in `data/processed` the script appends `_1`, `_2`, ... to the filename to avoid overwriting and prints a message.

How to run the preprocessing script (examples)

- Dry run (show actions only):

```bash
python3 scripts/preprocess_images.py --dry-run
```

- Specify custom inputs and output:

```bash
python3 scripts/preprocess_images.py --input-dirs "data/Even Illuminated Macro Images" "data/raw/Uneven Illuminated Macro Images" --output-dir data/processed
```

Project notes
- Scripts are written to be minimal and use only standard Python libraries where possible.
- Files that don't match the expected naming pattern are skipped with a warning.
- The downloader supports providing a `DATAVERSE_API_TOKEN` or `--token` for protected datasets.

Folder structure

```
data/
  raw/                       # downloaded dataset files and dataset subfolders
  processed/                 # renamed microscopy images (flat layout)
scripts/
  download_dataverse.py
  preprocess_images.py
environment.yml
README.md
```

If you want any changes to behavior (e.g. change collision policy to skip instead of disambiguate), tell me and I will update the scripts accordingly.
