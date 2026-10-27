"""Shared imaging settings: the single definition of data paths and the batch code format
(used by core.py, traits_2d and overlays).

The imaging steps only read and write files; they never connect to the database. Each path
comes from an environment variable if set, otherwise from a location inside the repository.
QC_ROOT and RASPI_ROOT are resolved the same way as in qc/server.py, so the data/ tree written
here is read directly by the review tool.
"""
import os
import re
from pathlib import Path

# Directory of the imaging/ code
CODE_ROOT = Path(__file__).resolve().parent

# --- Batch code format ---
# A full batch code is a four-digit year, 'B' and a two-digit number, e.g. 2025B08.
# Short codes (B08) are rejected: the batch code is also the key in staging file names, and
# accepting two forms could pick up an older output of another batch.
BATCH_CODE_RE = re.compile(r"^\d{4}B\d{2}$")


def require_batch_code(batch_code):
    """Validate and return a full batch code; raise ValueError otherwise. Every --batch entry point calls this."""
    if not batch_code or not BATCH_CODE_RE.match(batch_code):
        raise ValueError(
            f"bad batch_code {batch_code!r}: needs a full batch code such as 2025B08, not B08")
    return batch_code


# --- Inputs ---
# QC_ROOT: root of the review tool, holding data/ (frames.json) and qc.sqlite (per-leaf review decisions)
QC_ROOT = Path(os.environ.get("QC_ROOT", CODE_ROOT.parent / "qc"))
QC_DATA = QC_ROOT / "data"
QC_DB = QC_ROOT / "qc.sqlite"

# RASPI_ROOT: single-plant images, <batch>/<cultivar>/<treatment>/rep-<n>/*.png
_raspi_env = os.environ.get("RASPI_ROOT")
RASPI_ROOT = (Path(_raspi_env) if _raspi_env
              else QC_ROOT / "raspi_RGB" if (QC_ROOT / "raspi_RGB").exists()
              else QC_ROOT.parent / "raspi_RGB")

# WEIGHTS_DIR: one directory for the four model weights
WEIGHTS_DIR = Path(os.environ.get("WEIGHTS_DIR", CODE_ROOT / "weights"))

# --- Outputs (can be regenerated) ---
# Transparent segmentation and assignment overlays, in a tree that mirrors RASPI_ROOT
OVERLAY_ROOT = Path(os.environ.get("OVERLAY_ROOT", RASPI_ROOT.parent / "raspi_RGB_overlay"))
# Staging CSV written by traits_2d
OUT = Path(os.environ.get("OUT_DIR", CODE_ROOT / "out"))
