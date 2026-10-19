"""離線烤「分割 + 歸屬」透明疊層 PNG（RGB overlay 診斷圖）。

設計（見 vault 規劃筆記 / 對話 2026-07-23）：
  - 純讀現成 frames.json（polygon + M2 ownership），**不跑 YOLO、不重算**；跟 traits_2d 同性質的
    離線一次性批次。烤好後 api 只服務靜態 PNG，serve 時零計算。
  - 輸出是**透明 overlay**（RGBA，背景透明）——前端疊在原 crop 上，原圖不被覆蓋、可調透明度。
  - 平行樹 OVERLAY_ROOT/<batch>/<cultivar>/<treatment>/rep-<n>/<stem>.png，與 RASPI_ROOT 同結構，
    正本 raspi_RGB 保持乾淨。
  - ownership 語意：綠=owned（keep=True，進生長曲線）、紅虛線=rejected（鄰株葉，被排除）。
    base/tip 端點以小點標示（僅 owned 葉，供關鍵點檢視）。
  - keep 來源：預設 auto（frames.json keep = M2）。`--effective` 併 qc.sqlite override
    → 與 reviewed 批的生長曲線完全一致（一樣是離線讀檔，非重算）。

CLI：
  python -m overlays.render_overlays --plant 2025B06/s0075/Control/rep-2   # 單株
  python -m overlays.render_overlays --batch 2025B06                       # 整批
  python -m overlays.render_overlays --batch 2025B06 --effective           # 併人工 override
  加 --force 覆寫既有（預設 skip-existing，冪等可續跑）。
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

CANVAS = 600                       # 裁切圖固定尺寸（ref_circle 對得上；overlay 用同座標系）
TS_RE = re.compile(r"(\d{12})")

# 診斷配色（RGBA）
KEEP_LINE = (46, 160, 44, 255)     # 綠：owned 外框（進曲線）
KEEP_FILL = (46, 160, 44, 55)      # 綠半透明填色
REJECT_LINE = (214, 39, 40, 235)   # 紅：rejected 外框（鄰株葉，虛線）
BASE_DOT = (31, 119, 180, 255)     # 藍：base 端點
TIP_DOT = (255, 127, 14, 255)      # 橙：tip 端點
DASH, GAP = 7, 5                   # 虛線段長 / 間隔（px）


def _ipts(points):
    return [(int(round(x)), int(round(y))) for x, y in points]


def _dashed_polygon(draw: ImageDraw.ImageDraw, pts, color, width=2):
    """PIL 無原生虛線 → 沿封閉多邊形逐段畫虛線。"""
    if len(pts) < 2:
        return
    ring = pts + [pts[0]]
    carry = 0.0                    # 跨線段延續的 dash 相位
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
    """qc.sqlite leaf_override：{tid: state}，key = underscore business key（re-key 後）。"""
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
    """單幀 → 透明 RGBA overlay。先畫 reject（底），再畫 keep（上），最後端點。"""
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
    for lv, ip in kept:                       # 端點畫在最上層、僅 owned 葉
        for pt, col in ((lv.get("base"), BASE_DOT), (lv.get("tip"), TIP_DOT)):
            if pt:
                x, y = int(round(pt[0])), int(round(pt[1]))
                dr.ellipse([x - 3, y - 3, x + 3, y + 3], fill=col)
    return img


def render_plant(rel: str, effective: bool, force: bool) -> tuple[int, int]:
    """回傳 (寫出幀數, 略過幀數)。"""
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
    """batch 下所有 plant 的 rel（相對 QC_DATA）。batch 須為 canonical 批號（2025B06）。"""
    root = Path(QC_DATA)
    bdir = root / require_batch_code(batch)
    if not bdir.is_dir():
        return []
    bname = bdir.name
    return [f"{bname}/{fj.parent.relative_to(bdir)}"
            for fj in sorted(bdir.glob("*/*/rep-*/frames.json"))]


def main():
    ap = argparse.ArgumentParser(description="離線烤分割+歸屬透明 overlay PNG（純讀 frames.json）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plant", help="單株 rel，如 2025B06/s0075/Control/rep-2")
    g.add_argument("--batch", help="整批，完整批號如 2025B06（不接受短名 B06）")
    ap.add_argument("--effective", action="store_true", help="併 qc.sqlite override（reviewed 批對齊曲線）")
    ap.add_argument("--force", action="store_true", help="覆寫既有（預設 skip-existing）")
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
