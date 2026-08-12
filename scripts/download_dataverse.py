#!/usr/bin/env python3
"""
download_dataverse.py

Download all files from a Dataverse/Borealis dataset automatically.

Usage:
  pip install requests
  python scripts/download_dataverse.py

Options (CLI or environment variables):
  --doi DOI                 Dataset DOI (default: doi:10.80240/FK2/GZDEYI)
  --server-url URL          Dataverse server base URL (default: https://demo.borealisdata.ca)
  --output-dir PATH         Base output directory (default: data/raw)
  --token TOKEN             Dataverse API token (or set DATAVERSE_API_TOKEN env var)
  --force                   Re-download files even if they already exist

Requirements satisfied by installing only:
  pip install requests

Features:
- Uses the Dataverse "dirindex" API endpoint to discover files and folders.
- Recursively traverses subfolders and preserves directory structure locally.
- Skips files already present locally (unless --force).
- Displays simple progress for each file using content-length.
- Retries network operations with exponential backoff using requests' adapters.
- Supports API token auth via header `X-Dataverse-key` or `Authorization: Bearer`.

This script is designed to run on Windows, Linux and macOS.

"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util.retry import Retry


# ---------------------- Configuration ----------------------
DEFAULT_SERVER = "https://demo.borealisdata.ca"
DEFAULT_DOI = "doi:10.80240/FK2/GZDEYI"
CHUNK_SIZE = 8192
RETRY_STRATEGY = Retry(total=5, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))


# ---------------------- Helpers ----------------------
class AnchorTextParser(HTMLParser):
    """Parse <a href> elements and capture their href and visible text."""

    def __init__(self):
        super().__init__()
        self._current_href: Optional[str] = None
        self._capture = False
        self._text_fragments: List[str] = []
        self.links: List[Tuple[str, str]] = []  # (href, text)

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            for (k, v) in attrs:
                if k.lower() == "href" and v:
                    self._current_href = v
                    self._capture = True
                    self._text_fragments = []

    def handle_data(self, data):
        if self._capture:
            self._text_fragments.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._capture and self._current_href is not None:
            text = "".join(self._text_fragments).strip()
            self.links.append((self._current_href, text))
            self._current_href = None
            self._capture = False
            self._text_fragments = []


def sanitize_filename(filename: str) -> str:
    # Remove path separators and control characters
    filename = filename.strip()
    filename = filename.replace("\x00", "")
    # On Windows, avoid trailing spaces or dots
    filename = filename.rstrip(" .")
    # Replace path separators
    filename = filename.replace("/", "_").replace("\\", "_")
    return filename


def safe_join(base: Path, *parts: str) -> Path:
    """Join parts under base, preventing directory traversal."""
    joined = base.joinpath(*parts)
    resolved = joined.resolve()
    # Ensure the resolved path starts with the base resolved path
    try:
        if not str(resolved).startswith(str(base.resolve())):
            raise RuntimeError("Path traversal detected")
    except Exception:
        # If resolve or startswith fails, fallback to joined
        return joined
    return joined


def make_session(token: Optional[str] = None) -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=RETRY_STRATEGY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    headers = {"User-Agent": "dataverse-downloader/1.0"}
    if token:
        headers["X-Dataverse-key"] = token
        headers["Authorization"] = f"Bearer {token}"
    session.headers.update(headers)
    return session


def is_dir_link(href: str) -> bool:
    # heuristics: trailing slash or contains 'dirindex' or contains folder= param
    if href.endswith("/"):
        return True
    if "dirindex" in href.lower():
        return True
    if "folder=" in href.lower():
        return True
    return False


def is_datafile_link(href: str) -> bool:
    # Dataverse datafile access endpoints
    low = href.lower()
    return "/api/access/datafile/" in low or "/access/datafile/" in low or "/api/access/datafile" in low


# ---------------------- Core crawler & downloader ----------------------
class DataverseDownloader:
    def __init__(self, server_url: str, persistent_id: str, out_base: Path, token: Optional[str] = None, force: bool = False):
        self.server = server_url.rstrip("/")
        self.pid = persistent_id
        self.out_base = out_base
        self.force = force
        self.session = make_session(token)
        self.visited_dirs = set()

    def dataset_dirindex_url(self) -> str:
        return f"{self.server}/api/datasets/:persistentId/dirindex?persistentId={self.pid}"

    def download_all(self):
        # Save directly under the provided base output directory (omit DOI top-level folder)
        dataset_dir = self.out_base.resolve()
        dataset_dir.mkdir(parents=True, exist_ok=True)
        print(f"Saving dataset to: {dataset_dir}")

        start_url = self.dataset_dirindex_url()
        # crawl starting directory (relative path = empty)
        self._crawl_dir(start_url, dataset_dir, rel_path="")

    def _crawl_dir(self, url: str, target_dir: Path, rel_path: str, depth: int = 0):
        if depth > 8:
            return
        norm = url
        if norm in self.visited_dirs:
            return
        self.visited_dirs.add(norm)

        print(f"Crawling: {url} (rel: '{rel_path}')")
        try:
            # Try JSON first (some Dataverse instances may support JSON); else fetch HTML
            resp = self.session.get(url, headers={"Accept": "application/json"}, timeout=30)
            if resp.status_code == 200 and resp.headers.get("Content-Type", "").lower().startswith("application/json"):
                try:
                    data = resp.json()
                    self._process_dir_json(data, url, target_dir, rel_path, depth)
                    return
                except ValueError:
                    pass

            # fallback: treat as HTML directory index
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            html = resp.text
            parser = AnchorTextParser()
            parser.feed(html)

            # process each anchor
            for href, text in parser.links:
                href = href.strip()
                if not href:
                    continue
                full = urljoin(url, href)
                # directory link
                if is_dir_link(href) or (href.endswith("/") or href.lower().startswith("?folder=")):
                    # determine subfolder name: prefer anchor text if looks like a folder
                    subname = text or extract_folder_name_from_href(href)
                    if subname.endswith("/"):
                        subname = subname[:-1]
                    subname = sanitize_filename(subname) or extract_folder_name_from_href(href) or "subfolder"
                    new_rel = os.path.join(rel_path, subname) if rel_path else subname
                    new_target = safe_join(target_dir, subname)
                    new_target.mkdir(parents=True, exist_ok=True)
                    self._crawl_dir(full, target_dir, new_rel, depth + 1)
                elif is_datafile_link(href):
                    filename = sanitize_filename(text) or basename_from_url(href) or "file"
                    out_path = safe_join(target_dir, rel_path, filename)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    self._download_single(full, out_path)
                else:
                    # sometimes file links are relative and not recognized; use anchor text filename heuristic
                    if looks_like_filename(text):
                        filename = sanitize_filename(text)
                        out_path = safe_join(target_dir, rel_path, filename)
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        # resolve link absolute
                        full = urljoin(url, href)
                        self._download_single(full, out_path)
                    else:
                        # ignore other links
                        continue
        except RequestException as e:
            print(f"Network error crawling {url}: {e}")

    def _process_dir_json(self, data, base_url: str, target_dir: Path, rel_path: str, depth: int):
        # Walk JSON and find datafile links or directory indicators
        strings = []

        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)
            elif isinstance(obj, str):
                strings.append(obj)

        walk(data)

        # find file links and dirs
        for s in strings:
            s_strip = s.strip()
            if not s_strip:
                continue
            if is_datafile_link(s_strip):
                full = urljoin(base_url, s_strip)
                filename = basename_from_url(full)
                out_path = safe_join(target_dir, rel_path, sanitize_filename(filename))
                out_path.parent.mkdir(parents=True, exist_ok=True)
                self._download_single(full, out_path)
            elif is_dir_link(s_strip):
                full = urljoin(base_url, s_strip)
                subname = extract_folder_name_from_href(s_strip)
                subname = sanitize_filename(subname) or "subfolder"
                self._crawl_dir(full, target_dir, os.path.join(rel_path, subname), depth + 1)

    def _download_single(self, url: str, out_path: Path):
        if out_path.exists() and not self.force:
            print(f"Skipping existing: {out_path}")
            return

        print(f"Downloading: {url} -> {out_path}")
        try:
            with self.session.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                total = r.headers.get("Content-Length")
                try:
                    total = int(total) if total is not None else None
                except Exception:
                    total = None

                tmp = out_path.with_suffix(out_path.suffix + ".part")
                with tmp.open("wb") as f:
                    downloaded = 0
                    start = time.time()
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                pct = downloaded * 100 / total
                                elapsed = time.time() - start
                                speed = downloaded / 1024 / elapsed if elapsed > 0 else 0
                                sys.stdout.write(f"\r{downloaded}/{total} bytes ({pct:.1f}%) {speed:.1f} KB/s")
                            else:
                                sys.stdout.write(f"\r{downloaded} bytes")
                            sys.stdout.flush()
                    sys.stdout.write("\n")
                tmp.replace(out_path)
                print(f"Saved: {out_path}")
        except RequestException as e:
            print(f"Error downloading {url}: {e}")


# ---------------------- Utility functions ----------------------

def basename_from_url(url: str) -> str:
    p = urlparse(url).path
    name = os.path.basename(p)
    if name:
        return unquote(name)
    # fallback to query filename
    q = urlparse(url).query
    params = parse_qs(q)
    for k in ("filename", "file", "name"):
        if k in params:
            return params[k][0]
    return "file"


def extract_folder_name_from_href(href: str) -> str:
    # attempt to extract folder name from query param folder= or from last path component
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    if "folder" in qs:
        return qs["folder"][0]
    # last path segment
    p = parsed.path.rstrip("/")
    if p:
        return os.path.basename(p)
    return ""


def looks_like_filename(text: str) -> bool:
    # simple heuristic: contains a dot with 2-6 char extension or common names
    if not text:
        return False
    if re.search(r"\.[A-Za-z0-9]{1,6}$", text.strip()):
        return True
    # common readme names
    if text.lower() in ("readme", "readme.md", "license", "changelog"):
        return True
    return False


# ---------------------- CLI ----------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Download all files from a Dataverse dataset DOI")
    parser.add_argument("--doi", default=os.environ.get("PERSISTENT_ID") or DEFAULT_DOI, help="Dataset persistent ID (DOI)")
    parser.add_argument("--server-url", default=os.environ.get("SERVER_URL") or DEFAULT_SERVER, help="Dataverse server base URL")
    parser.add_argument("--output-dir", default="data/raw", help="Output base directory")
    parser.add_argument("--token", default=os.environ.get("DATAVERSE_API_TOKEN"), help="Dataverse API token (or set DATAVERSE_API_TOKEN env var)")
    parser.add_argument("--force", action="store_true", help="Re-download files even if they exist locally")
    args = parser.parse_args(argv)

    out_base = Path(args.output_dir).resolve()
    downloader = DataverseDownloader(server_url=args.server_url, persistent_id=args.doi, out_base=out_base, token=args.token, force=args.force)
    downloader.download_all()


if __name__ == "__main__":
    main()
