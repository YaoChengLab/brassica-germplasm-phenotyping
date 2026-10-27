"""Render transparent segmentation and assignment overlays (RGBA PNG) for the single-plant images.

  - Reads the existing frames.json (leaf polygons and the automatic keep decision); it does not
    run the segmentation models or recompute anything. Like traits_2d it is an offline batch
    step, so the platform only serves static PNG files.
  - The output is a transparent overlay (RGBA, transparent background) that the web interface
    draws over the original image, which stays untouched; its opacity can be adjusted.
  - Output tree OVERLAY_ROOT/<batch>/<cultivar>/<treatment>/rep-<n>/<stem>.png mirrors RASPI_ROOT,
    so the image tree itself stays clean.
  - Colours: green = retained leaf (keep=True, enters the growth curves); red dashed outline =
    rejected leaf (assigned to a neighbouring plant). Base and tip points are drawn as small dots
    on retained leaves only.
  - Keep decisions: the automatic ones from frames.json by default. `--effective` applies the
    review decisions in qc.sqlite, so the overlays match the traits of reviewed plants (still
    read from files, not recomputed).

Usage (from the repository root):
  python imaging/overlays/render_overlays.py --plant 2025B08/s0123/Control/rep-3   # one plant
  python imaging/overlays/render_overlays.py --batch 2025B08                       # whole batch
  python imaging/overlays/render_overlays.py --batch 2025B08 --effective           # with review decisions
  Add --force to overwrite existing files (by default existing files are skipped, so a rerun resumes).
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import QC_DATA, QC_DB, OVERLAY_ROOT, require_batch_code  # noqa: E402

CANVAS = 600                       # fixed size of the single-plant images (same coordinates as ref_circle)
TS_RE = re.compile(r"(\d{12})")

# Overlay colours (RGBA)
KEEP_LINE = (46, 160, 44, 255)     # green: outline of retained leaves (enter the curves)
KEEP_FILL = (46, 160, 44, 55)      # green, translucent fill
REJECT_LINE = (214, 39, 40, 235)   # red: dashed outline of rejected leaves (neighbouring plant)
BASE_DOT = (31, 119, 180, 255)     # blue: base point
TIP_DOT = (255, 127, 14, 255)      # orange: tip point
DASH, GAP = 7, 5                   # dash length / gap (px)


def _ipts(points):
    return [(int(round(x)), int(round(y))) for x, y in points]


def _dashed_polygon(draw: ImageDraw.ImageDraw, pts, color, width=2):
    """PIL has no dashed lines, so draw the dashes segment by segment along the closed polygon."""
    if len(pts) < 2:
        return
    ring = pts + [pts[0]]
    carry = 0.0                    # dash phase carried across segments
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        seg = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        if seg == 0:
            continue
        dx, dy = (x1 - x0) / seg, (y1 - y0) / seg
        d = -carry
        while d < seg:
            a = max(d, 0.0)
            b = min(d + DASH, seg)
            if b > a:
                draw.line([(x0 + dx * a, y0 + dy * a), (x0 + dx * b, y0 + dy * b)], fill=color, width=width)
            d += DASH + GAP
        carry = (carry + seg) % (DASH + GAP)


def _load_overrides(bkey: str) -> dict:
    """leaf_override rows of qc.sqlite as {tid: state}; plant key = batch_cultivar_treatment_rep."""
    try:
        c = sqlite3.connect(QC_DB)
        try:
            return {tid: state for tid, state in
                    c.execute("SELECT tid,state FROM leaf_override WHERE plant_id=?", (bkey,))}
        finally:
            c.close()
    except Exception:
        return {}


def _keep(leaf: dict, ov: dict) -> bool:
    tid = leaf.get("tid")
    if tid in ov:
        return ov[tid] == 1
    return bool(leaf.get("keep"))


def render_frame(leaves, ov) -> Image.Image:
    """One image -> transparent RGBA overlay: rejected leaves first (bottom), then retained leaves, then points."""
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    kept = []
    for lv in leaves:
        pts = lv.get("points") or []
        if len(pts) < 3:
            continue
        ip = _ipts(pts)
        if _keep(lv, ov):
            kept.append((lv, ip))
        else:
            _dashed_polygon(dr, ip, REJECT_LINE, width=2)
    for lv, ip in kept:
        dr.polygon(ip, fill=KEEP_FILL)
        dr.line(ip + [ip[0]], fill=KEEP_LINE, width=2)
    for lv, ip in kept:                       # points on top, retained leaves only
        for pt, col in ((lv.get("base"), BASE_DOT), (lv.get("tip"), TIP_DOT)):
            if pt:
                x, y = int(round(pt[0])), int(round(pt[1]))
                dr.ellipse([x - 3, y - 3, x + 3, y + 3], fill=col)
    return img


def render_plant(rel: str, effective: bool, force: bool) -> tuple[int, int]:
    """Return (images written, images skipped)."""
    fjp = Path(QC_DATA) / rel / "frames.json"
    if not fjp.is_file():
        print(f"[overlay] no frames.json: {rel}", file=sys.stderr)
        return 0, 0
    fj = json.load(open(fjp))
    ov = {}
    if effective:
        b, c, t, rep = rel.split("/")[:4]
        m = re.search(r"rep-(\d+)", rep)
        bkey = f"{b}_{c}_{t}_{m.group(1) if m else rep}"
        ov = _load_overrides(bkey)
    outdir = Path(OVERLAY_ROOT) / rel
    outdir.mkdir(parents=True, exist_ok=True)
    wrote = skipped = 0
    for fr in fj.get("frames", []):
        leaves = fr.get("leaves") or []
        stem = fr.get("stem")
        if not stem:
            continue
        outp = outdir / f"{stem}.png"
        if outp.exists() and not force:
            skipped += 1
            continue
        render_frame(leaves, ov).save(outp, "PNG", optimize=True)
        wrote += 1
    return wrote, skipped


def find_plants(batch: str) -> list[str]:
    """rel paths (relative to QC_DATA) of all plants in a batch; batch must be a full code (2025B08)."""
    root = Path(QC_DATA)
    bdir = root / require_batch_code(batch)
    if not bdir.is_dir():
        return []
    bname = bdir.name
    return [f"{bname}/{fj.parent.relative_to(bdir)}"
            for fj in sorted(bdir.glob("*/*/rep-*/frames.json"))]


def main():
    ap = argparse.ArgumentParser(description="Render transparent segmentation and assignment overlays from frames.json")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plant", help="one plant, e.g. 2025B08/s0123/Control/rep-3")
    g.add_argument("--batch", help="a whole batch, full batch code e.g. 2025B08 (not B08)")
    ap.add_argument("--effective", action="store_true", help="apply the review decisions in qc.sqlite")
    ap.add_argument("--force", action="store_true", help="overwrite existing files (default: skip them)")
    a = ap.parse_args()
    if a.batch:
        try:
            require_batch_code(a.batch)
        except ValueError as e:
            ap.error(str(e))

    rels = [a.plant] if a.plant else find_plants(a.batch)
    if not rels:
        print(f"[overlay] no plants found for '{a.batch or a.plant}' under {QC_DATA}", file=sys.stderr)
        sys.exit(1)
    print(f"[overlay] {len(rels)} plant(s) → {OVERLAY_ROOT}  (keep={'effective' if a.effective else 'auto'})")
    tot_w = tot_s = 0
    for rel in rels:
        w, s = render_plant(rel, a.effective, a.force)
        tot_w += w
        tot_s += s
        print(f"  {rel}: wrote {w}, skipped {s}")
    print(f"[overlay] done: wrote {tot_w}, skipped {tot_s}")


if __name__ == "__main__":
    main()
