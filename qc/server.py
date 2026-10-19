"""server.py — leaf-canopy-qc GUI 後端 (自包含；不 import core，避免拖 torch)。

提供：
  GET  /                          → gui/index.html
  GET  /static/*                  → gui/ 靜態
  GET  /api/tree                  → batch▸品系▸植株 樹 (掃 data/) + reviewed / cotyledon_done 標記
  GET  /api/plant?id=<rel>        → frames.json (含 leaves + auto keep)
  GET  /api/after?id=<rel>[&exclude_class=cotyledon]  → 套用 override 後每日 count_after/area_after；exclude_class 額外排除該語意類別（DAPD 去子葉）
  GET  /img?id=<rel>&stem=<stem>  → 原始影像 (RASPI_ROOT)
  GET  /api/overrides?id=<rel>    → {tid: state}
  POST /api/override {id,tid,state}  state 1/0 = 人工設 keep/reject；state=-1 → 清除回 auto
  GET  /api/classes?id=<rel>      → {tid: klass} 葉語意類別
  POST /api/class {id,tid,klass}  klass='cotyledon' 標子葉；空字串 → 清除
  POST /api/reviewed {id,reviewed}
  POST /api/cotyledon_done {id,done}  植株子葉標記完成旗標
  GET  /api/note?id=<rel>         → {text} 植株級觀察註記
  POST /api/note {id,text}        text 空 → 刪除該株 note
qc.sqlite: leaf_override(plant_id,tid,state) / leaf_class(plant_id,tid,klass) / reviewed(plant_id,ts) / cotyledon_done(plant_id,ts) / note(plant_id,text,ts)。

執行 (base env，需 fastapi+uvicorn+numpy，area 重算需 cv2)：
  python qc/server.py --host 127.0.0.1 --port 8090
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import threading
from collections import defaultdict
from pathlib import Path

import numpy as np
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

IMG_CACHE = {}          # path str -> png bytes (in-RAM；warm 後 serve 走記憶體)
IMG_CACHE_CAP = 2500    # ~10 株；超過丟最舊一批
CURVES_CACHE = {}       # plant_id str -> list[day-dict] (curves.json 快取，無 override 快路徑)
PLANT_CURVE_CACHE = {}  # (plant_id, exclude_class) -> list[day-dict]
                        # 慢路徑結果快取；POST /api/override 或 /api/class 時對應植株失效


def _invalidate_plant(plant_id: str):
    for k in [k for k in PLANT_CURVE_CACHE if k[0] == plant_id]:
        del PLANT_CURVE_CACHE[k]

# QC_ROOT 預設 = server.py 自己所在目錄（repo 自包含：gui/ data/ qc.sqlite 都在其下），
# 跨機零設定即可跑；env 仍可覆蓋。
QC_ROOT = Path(os.environ.get("QC_ROOT", Path(__file__).resolve().parent))
DATA_ROOT = QC_ROOT / "data"
# RASPI 影像位置：env 優先 → repo 內(NUC 部署) → sibling(Ubuntu 開發) 自動偵測。
_raspi_env = os.environ.get("RASPI_ROOT")
RASPI_ROOT = (Path(_raspi_env) if _raspi_env
             else QC_ROOT / "raspi_RGB" if (QC_ROOT / "raspi_RGB").exists()
             else QC_ROOT.parent / "raspi_RGB")
GUI = Path(__file__).resolve().parent / "gui"   # 介面跟著程式碼走，不隨 QC_ROOT 移動
DB = QC_ROOT / "qc.sqlite"
CANVAS = 600


# 身分解耦（2026-07-21）：qc.sqlite plant_id ＝ underscore business key、與 FS 路徑脫鉤。
# API 的 id 一律用 underscore key（對前端不透明）；只在存取檔案系統時轉回路徑。
# 組成欄位（batch/cultivar/treatment/rep）皆無底線，故 split('_') 恰 4 段。
def pid_of(path: str) -> str:
    """FS 相對路徑 <batch>/<cultivar>/<treatment>/rep-<n> → qc.sqlite plant_id（underscore）。"""
    b, c, t, r = path.split("/")
    return f"{b}_{c}_{t}_{r[4:] if r.startswith('rep-') else r}"


def path_of(pid: str) -> str:
    """qc.sqlite plant_id（underscore）→ FS 相對路徑。"""
    b, c, t, n = pid.split("_")
    return f"{b}/{c}/{t}/rep-{n}"

_db_local = threading.local()   # thread-local 連線：重用而非每次開關

def db():
    """每 thread 只開一次 SQLite 連線；CREATE TABLE IF NOT EXISTS 也只跑一次。"""
    if not getattr(_db_local, "conn", None):
        c = sqlite3.connect(str(DB), timeout=30, check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE IF NOT EXISTS leaf_override(plant_id TEXT, tid TEXT, state INTEGER, PRIMARY KEY(plant_id,tid))")
        c.execute("CREATE TABLE IF NOT EXISTS reviewed(plant_id TEXT PRIMARY KEY, ts TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS note(plant_id TEXT PRIMARY KEY, text TEXT, ts TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS leaf_class(plant_id TEXT, tid TEXT, klass TEXT, PRIMARY KEY(plant_id,tid))")
        c.execute("CREATE TABLE IF NOT EXISTS cotyledon_done(plant_id TEXT PRIMARY KEY, ts TEXT)")
        _db_local.conn = c
    return _db_local.conn


def union_area(polys, sz=CANVAS):
    """numpy-vectorized scanline even-odd 多邊形 union 面積 (無 cv2/PIL，base env 可跑)。

    邊×掃描線交點向量化計算 (移除 per-edge python 內迴圈)，比逐點版快 ~數十倍。
    before/after 都用這支 → 內部一致。
    """
    if not polys:
        return 0
    mask = np.zeros((sz, sz), bool)
    for poly in polys:
        p = np.asarray(poly, float)
        x = p[:, 0]; y = p[:, 1]
        x2 = np.roll(x, -1); y2 = np.roll(y, -1)
        y0 = max(0, int(np.floor(y.min()))); y1 = min(sz - 1, int(np.ceil(y.max())))
        if y1 < y0:
            continue
        rows = np.arange(y0, y1 + 1)
        ys = rows[:, None]                                  # (R,1)
        cond = ((y[None, :] <= ys) & (ys < y2[None, :])) | ((y2[None, :] <= ys) & (ys < y[None, :]))
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = x[None, :] + (ys - y[None, :]) * (x2 - x)[None, :] / (y2 - y)[None, :]
        for ri in range(rows.size):
            xs = np.sort(xint[ri][cond[ri]])
            for k in range(0, xs.size - 1, 2):
                xa = max(0, int(np.ceil(xs[k]))); xb = min(sz - 1, int(np.floor(xs[k + 1])))
                if xb >= xa:
                    mask[rows[ri], xa:xb + 1] = True
    return int(mask.sum())


app = FastAPI()


@app.get("/")
def index():
    return FileResponse(GUI / "index.html")


@app.get("/curves")
def curves():
    return FileResponse(GUI / "cultivar_curves.html")


@app.get("/api/tree")
def tree():
    conn = db()
    rev = {r[0] for r in conn.execute("SELECT plant_id FROM reviewed")}
    cot = {r[0] for r in conn.execute("SELECT plant_id FROM cotyledon_done")}
    t = defaultdict(lambda: defaultdict(list))
    for fj in sorted(DATA_ROOT.glob("20[0-9][0-9]B*/s*/*/*/frames.json")):
        rel = fj.parent.relative_to(DATA_ROOT).as_posix()  # <batch>/<cultivar>/<treatment>/rep-<n>
        batch, cult, treat, rep = rel.split("/")
        pid = pid_of(rel)   # qc.sqlite plant_id（underscore）；對前端不透明
        t[batch][cult].append({"plant": f"{treat}/{rep}", "id": pid,
                               "reviewed": pid in rev, "cotyledon_done": pid in cot})
    return JSONResponse(t)


@app.get("/api/plant")
def plant(id: str):
    fj = DATA_ROOT / path_of(id) / "frames.json"
    if not fj.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(json.load(open(fj)))


@app.get("/api/overrides")
def overrides(id: str):
    rows = db().execute("SELECT tid,state FROM leaf_override WHERE plant_id=?", (id,)).fetchall()
    return JSONResponse({t: s for t, s in rows})


@app.get("/api/after")
def after(id: str, exclude_class: str = ""):
    """套用 override 後的每日 count_after / area。

    exclude_class 非空 → 額外把該 leaf_class 的葉視為 reject（DAPD 用 'cotyledon' 排除子葉）。
    keep/reject 真相不變，僅在輸出端 filter；故同一份 override 可導出「含子葉/不含子葉」兩份曲線。

    效能關鍵：count_after 永遠便宜計算；area_before 用 build 快取的 raw_area；
    area_after 只對「被 override 或被排除類別影響的日期」用 scanline 重算 (一天 ~13 幀，~0.5s)，
    其餘日期沿用 build 快取的 keep_area → 載入(無 override)即時、編輯只算被改的那天。
    """
    fj = DATA_ROOT / path_of(id) / "frames.json"
    if not fj.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    data = json.load(open(fj))
    ov = {t: s for t, s in db().execute("SELECT tid,state FROM leaf_override WHERE plant_id=?", (id,)).fetchall()}
    excl = set()
    if exclude_class:
        excl = {t for (t,) in db().execute(
            "SELECT tid FROM leaf_class WHERE plant_id=? AND klass=?", (id, exclude_class)).fetchall()}
    # tid = "YYYY-MM-DD#idx"；被排除的子葉所在日期也要重算 area（移除子葉後面積會變）
    affected = {tid.split("#")[0] for tid in ov} | {tid.split("#")[0] for tid in excl}

    # 逐幀 count_after / area_after。area 只對受影響日期的幀重算，其餘沿用 build 快取。
    out = []
    for fr in data["frames"]:
        keep = [lf for lf in fr["leaves"]
                if ov.get(lf["tid"], 1 if lf["keep"] else 0) == 1 and lf["tid"] not in excl]
        aa = union_area([lf["points"] for lf in keep]) if fr["date"] in affected else fr.get("keep_area", 0)
        out.append({"stem": fr["stem"], "count_after": len(keep), "area_after": aa})
    return JSONResponse({"frames": out, "area_enabled": True})


def _read_cached(p: Path):
    key = str(p)
    b = IMG_CACHE.get(key)
    if b is None:
        if not p.exists():
            return None
        b = p.read_bytes()
        if len(IMG_CACHE) > IMG_CACHE_CAP:           # 粗 LRU：丟最舊 500
            for k in list(IMG_CACHE)[:500]:
                IMG_CACHE.pop(k, None)
        IMG_CACHE[key] = b
    return b


@app.get("/img")
def img(id: str, stem: str):
    b = _read_cached(RASPI_ROOT / path_of(id) / f"{stem}.png")
    if b is None:
        return JSONResponse({"error": "no img"}, status_code=404)
    # Cache-Control → 瀏覽器也快取，scrub 回看不再重抓
    return Response(content=b, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


def _warm(id: str):
    fj = DATA_ROOT / path_of(id) / "frames.json"
    if not fj.exists():
        return
    for fr in json.load(open(fj))["frames"]:
        _read_cached(RASPI_ROOT / path_of(id) / f"{fr['stem']}.png")


@app.get("/api/warm")
def warm(id: str):
    """背景把該株所有幀讀進 RAM cache → 之後 serve 走記憶體 (避免 HDD 逐次 seek)。"""
    threading.Thread(target=_warm, args=(id,), daemon=True).start()
    return {"ok": True}


class Ov(BaseModel):
    id: str
    tid: str
    state: int   # 1 keep, 0 reject, -1 clear


@app.post("/api/override")
def set_override(o: Ov):
    c = db()
    if o.state == -1:
        c.execute("DELETE FROM leaf_override WHERE plant_id=? AND tid=?", (o.id, o.tid))
    else:
        c.execute("INSERT INTO leaf_override(plant_id,tid,state) VALUES(?,?,?) "
                  "ON CONFLICT(plant_id,tid) DO UPDATE SET state=excluded.state",
                  (o.id, o.tid, o.state))
    c.commit()
    _invalidate_plant(o.id)
    return {"ok": True}


@app.get("/api/classes")
def classes(id: str):
    """該株所有葉的語意類別 {tid: klass}（無列=普通真葉）。"""
    rows = db().execute("SELECT tid,klass FROM leaf_class WHERE plant_id=?", (id,)).fetchall()
    return JSONResponse({t: k for t, k in rows})


class Cls(BaseModel):
    id: str
    tid: str
    klass: str   # 'cotyledon' 等；空字串 → 清除（回復為普通真葉）


@app.post("/api/class")
def set_class(c_: Cls):
    c = db()
    if c_.klass.strip():
        c.execute("INSERT INTO leaf_class(plant_id,tid,klass) VALUES(?,?,?) "
                  "ON CONFLICT(plant_id,tid) DO UPDATE SET klass=excluded.klass",
                  (c_.id, c_.tid, c_.klass))
    else:
        c.execute("DELETE FROM leaf_class WHERE plant_id=? AND tid=?", (c_.id, c_.tid))
    c.commit()
    _invalidate_plant(c_.id)
    return {"ok": True}


class Rev(BaseModel):
    id: str
    reviewed: bool


@app.post("/api/reviewed")
def set_reviewed(r: Rev):
    c = db()
    if r.reviewed:
        c.execute("INSERT OR REPLACE INTO reviewed(plant_id,ts) VALUES(?,datetime('now'))", (r.id,))
    else:
        c.execute("DELETE FROM reviewed WHERE plant_id=?", (r.id,))
    c.commit()
    return {"ok": True}


class CotDone(BaseModel):
    id: str
    done: bool


@app.post("/api/cotyledon_done")
def set_cotyledon_done(r: CotDone):
    c = db()
    if r.done:
        c.execute("INSERT OR REPLACE INTO cotyledon_done(plant_id,ts) VALUES(?,datetime('now'))", (r.id,))
    else:
        c.execute("DELETE FROM cotyledon_done WHERE plant_id=?", (r.id,))
    c.commit()
    return {"ok": True}


@app.get("/api/cultivar_curves")
def cultivar_curves(batch: str, cultivar: str, exclude_class: str = "cotyledon"):
    """Per-day aggregated count/area for all replicates of a cultivar (with overrides + cotyledon filter).

    count: mean of all hourly frames per day.
    area: noon-representative frame per day (scanline only for override/class-affected days).
    """
    conn = db()
    # 一次查出本品系所有植株中有哪些有 override / cotyledon（兩條查詢取代每株 2 條）
    prefix = f"{batch}_{cultivar}_"
    plants_with_ov  = {r[0] for r in conn.execute(
        "SELECT DISTINCT plant_id FROM leaf_override WHERE plant_id LIKE ?", (prefix + "%",))}
    plants_with_cot = set()
    if exclude_class:
        plants_with_cot = {r[0] for r in conn.execute(
            "SELECT DISTINCT plant_id FROM leaf_class WHERE klass=? AND plant_id LIKE ?",
            (exclude_class, prefix + "%"))}

    result = []
    for fj in sorted(DATA_ROOT.glob(f"{batch}/{cultivar}/*/*/frames.json")):
        rel = fj.parent.relative_to(DATA_ROOT).as_posix()  # <batch>/<cultivar>/<treatment>/rep-<n>
        plant_id = pid_of(rel)
        rep = fj.parent.name   # 'rep-<n>'
        short = rep

        # Fast path: no overrides, no cotyledon marks → curves.json (3.9 KB vs 5.1 MB)
        if plant_id not in plants_with_ov and plant_id not in plants_with_cot:
            if plant_id not in CURVES_CACHE:
                cj = fj.parent / "curves.json"
                CURVES_CACHE[plant_id] = json.load(open(cj))["curves"] if cj.exists() else None
            curves = CURVES_CACHE[plant_id]
            if curves is not None:
                result.append({"plant_id": plant_id, "plant": short,
                                "days": [{"daf": c["daf"], "date": c["date"],
                                          "count": c["keep_count"], "area": c["keep_area"]}
                                         for c in curves]})
                continue

        # Slow path: recompute with frames.json (plants with overrides or cotyledon marks)
        cache_key = (plant_id, exclude_class)
        if cache_key in PLANT_CURVE_CACHE:
            result.append({"plant_id": plant_id, "plant": short, "days": PLANT_CURVE_CACHE[cache_key]})
            continue

        ov = {t: s for t, s in conn.execute(
            "SELECT tid,state FROM leaf_override WHERE plant_id=?", (plant_id,)).fetchall()}
        excl = set()
        if exclude_class:
            excl = {t for (t,) in conn.execute(
                "SELECT tid FROM leaf_class WHERE plant_id=? AND klass=?",
                (plant_id, exclude_class)).fetchall()}
        affected = {tid.split("#")[0] for tid in ov} | {tid.split("#")[0] for tid in excl}
        data = json.load(open(fj))
        by_date: dict = defaultdict(list)
        for fr in data["frames"]:
            by_date[fr["date"]].append(fr)

        days = []
        for date in sorted(by_date):
            day_frs = by_date[date]
            counts = [
                sum(1 for lf in fr["leaves"]
                    if ov.get(lf["tid"], 1 if lf["keep"] else 0) == 1 and lf["tid"] not in excl)
                for fr in day_frs
            ]
            noon = min(day_frs, key=lambda f: abs(f.get("hour", 12) - 12))
            if date in affected:
                keep = [lf for lf in noon["leaves"]
                        if ov.get(lf["tid"], 1 if lf["keep"] else 0) == 1 and lf["tid"] not in excl]
                area = union_area([lf["points"] for lf in keep])
            else:
                area = noon.get("keep_area", 0)
            days.append({"daf": day_frs[0]["daf"], "date": date,
                         "count": round(sum(counts) / len(counts), 1), "area": area})
        PLANT_CURVE_CACHE[cache_key] = days
        result.append({"plant_id": plant_id, "plant": short, "days": days})
    return JSONResponse({"replicates": result})


@app.get("/api/note")
def get_note(id: str):
    row = db().execute("SELECT text FROM note WHERE plant_id=?", (id,)).fetchone()
    return JSONResponse({"text": row[0] if row else ""})


class Note(BaseModel):
    id: str
    text: str


@app.post("/api/note")
def set_note(n: Note):
    """植株級自然語言註記；空字串 → 刪除該株 note。"""
    c = db()
    if n.text.strip():
        c.execute("INSERT INTO note(plant_id,text,ts) VALUES(?,?,datetime('now')) "
                  "ON CONFLICT(plant_id) DO UPDATE SET text=excluded.text, ts=excluded.ts",
                  (n.id, n.text))
    else:
        c.execute("DELETE FROM note WHERE plant_id=?", (n.id,))
    c.commit()
    return {"ok": True}


if GUI.exists():
    app.mount("/static", StaticFiles(directory=str(GUI)), name="static")

if __name__ == "__main__":
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8090)
    a = ap.parse_args()
    print(f"[leaf-canopy-qc] serving on {a.host}:{a.port}  (numpy scanline area)")
    uvicorn.run(app, host=a.host, port=a.port)
