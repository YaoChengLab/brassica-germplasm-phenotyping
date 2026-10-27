"""server.py — back end of the leaf-to-plant assignment review tool (self-contained; it does not
import imaging/core.py, so it does not need torch).

Endpoints:
  GET  /                          -> gui/index.html
  GET  /static/*                  -> static files in gui/
  GET  /api/tree                  -> batch > accession > plant tree (scans data/) with reviewed / cotyledon_done flags
  GET  /api/plant?id=<id>         -> frames.json (leaves and automatic keep decisions)
  GET  /api/after?id=<id>[&exclude_class=cotyledon]  -> per-image count_after / area_after with review
                                     decisions applied; exclude_class also leaves out leaves of that class
  GET  /img?id=<id>&stem=<stem>   -> single-plant image (RASPI_ROOT)
  GET  /api/overrides?id=<id>     -> {tid: state}
  POST /api/override {id,tid,state}  state 1/0 = keep/reject set by the reviewer; -1 = clear (back to automatic)
  GET  /api/classes?id=<id>       -> {tid: klass} leaf class
  POST /api/class {id,tid,klass}  klass='cotyledon' marks a cotyledon; an empty string clears it
  POST /api/reviewed {id,reviewed}
  POST /api/cotyledon_done {id,done}  flag: cotyledon marking finished for the plant
  GET  /api/note?id=<id>          -> {text} free-text note on the plant
  POST /api/note {id,text}        an empty text deletes the note
qc.sqlite: leaf_override(plant_id,tid,state) / leaf_class(plant_id,tid,klass) / reviewed(plant_id,ts) / cotyledon_done(plant_id,ts) / note(plant_id,text,ts).

Run (env bgp-imaging; needs fastapi, uvicorn and numpy):
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

IMG_CACHE = {}          # path str -> png bytes (in RAM; after warm-up images are served from memory)
IMG_CACHE_CAP = 2500    # about 10 plants; beyond this the oldest entries are dropped
# QC_ROOT defaults to the directory of server.py (gui/, data/ and qc.sqlite all sit under it),
# so it runs without configuration; the environment variable overrides it.
QC_ROOT = Path(os.environ.get("QC_ROOT", Path(__file__).resolve().parent))
DATA_ROOT = QC_ROOT / "data"
# Image location: RASPI_ROOT if set, else raspi_RGB/ inside QC_ROOT, else raspi_RGB/ next to QC_ROOT.
_raspi_env = os.environ.get("RASPI_ROOT")
RASPI_ROOT = (Path(_raspi_env) if _raspi_env
             else QC_ROOT / "raspi_RGB" if (QC_ROOT / "raspi_RGB").exists()
             else QC_ROOT.parent / "raspi_RGB")
GUI = Path(__file__).resolve().parent / "gui"   # the interface stays with the code, not with QC_ROOT
DB = QC_ROOT / "qc.sqlite"
CANVAS = 600


# The plant_id in qc.sqlite is batch_cultivar_treatment_rep, independent of the file paths.
# API ids always use this key (opaque to the front end); it is turned back into a path only to
# read files. None of the four parts contains an underscore, so split('_') gives exactly 4 parts.
def pid_of(path: str) -> str:
    """Relative path <batch>/<cultivar>/<treatment>/rep-<n> -> plant_id in qc.sqlite."""
    b, c, t, r = path.split("/")
    return f"{b}_{c}_{t}_{r[4:] if r.startswith('rep-') else r}"


def path_of(pid: str) -> str:
    """plant_id in qc.sqlite -> relative path."""
    b, c, t, n = pid.split("_")
    return f"{b}/{c}/{t}/rep-{n}"

_db_local = threading.local()   # thread-local connection, reused instead of reopened

def db():
    """One SQLite connection per thread; CREATE TABLE IF NOT EXISTS also runs only once."""
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
    """Union area of polygons by a numpy-vectorised even-odd scanline fill (no cv2 or PIL).

    Known issue: this is not the rasterisation used by imaging/core.py and traits.py
    (cv2.fillPoly), and it gives a few percent smaller areas for the same polygons. Days with
    review decisions are recomputed here while other days keep the area cached by build.py,
    so the review curve can drop on an edited day without any change in the plant.
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


@app.get("/api/tree")
def tree():
    conn = db()
    rev = {r[0] for r in conn.execute("SELECT plant_id FROM reviewed")}
    cot = {r[0] for r in conn.execute("SELECT plant_id FROM cotyledon_done")}
    t = defaultdict(lambda: defaultdict(list))
    for fj in sorted(DATA_ROOT.glob("20[0-9][0-9]B*/s*/*/*/frames.json")):
        rel = fj.parent.relative_to(DATA_ROOT).as_posix()  # <batch>/<cultivar>/<treatment>/rep-<n>
        batch, cult, treat, rep = rel.split("/")
        pid = pid_of(rel)   # plant_id in qc.sqlite; opaque to the front end
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
    """Per-image count_after / area_after with the review decisions applied.

    A non-empty exclude_class also treats leaves of that class as rejected (e.g. 'cotyledon').
    The keep/reject decisions themselves are unchanged; the class is only filtered on output, so
    the same decisions give curves with and without cotyledons.

    count_after is always cheap. area_after is recomputed with the scanline fill only for dates
    touched by a review decision or an excluded class (about 13 images per day, ~0.5 s); other
    dates keep the keep_area cached by build.py, so a plant without decisions loads at once and
    an edit recomputes only the edited day. See union_area for the known area difference.
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
    # tid = "YYYY-MM-DD#idx"; dates with excluded leaves are recomputed too (their area changes)
    affected = {tid.split("#")[0] for tid in ov} | {tid.split("#")[0] for tid in excl}

    # per-image count_after / area_after; area is recomputed only on affected dates, else cached
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
        if len(IMG_CACHE) > IMG_CACHE_CAP:           # rough LRU: drop the oldest 500
            for k in list(IMG_CACHE)[:500]:
                IMG_CACHE.pop(k, None)
        IMG_CACHE[key] = b
    return b


@app.get("/img")
def img(id: str, stem: str):
    b = _read_cached(RASPI_ROOT / path_of(id) / f"{stem}.png")
    if b is None:
        return JSONResponse({"error": "no img"}, status_code=404)
    # Cache-Control lets the browser cache too, so scrubbing back does not refetch
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
    """Read all images of the plant into the RAM cache in the background, so later requests avoid disk seeks."""
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
    return {"ok": True}


@app.get("/api/classes")
def classes(id: str):
    """Leaf classes of the plant as {tid: klass} (no row = ordinary true leaf)."""
    rows = db().execute("SELECT tid,klass FROM leaf_class WHERE plant_id=?", (id,)).fetchall()
    return JSONResponse({t: k for t, k in rows})


class Cls(BaseModel):
    id: str
    tid: str
    klass: str   # e.g. 'cotyledon'; an empty string clears it (ordinary true leaf)


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


@app.get("/api/note")
def get_note(id: str):
    row = db().execute("SELECT text FROM note WHERE plant_id=?", (id,)).fetchone()
    return JSONResponse({"text": row[0] if row else ""})


class Note(BaseModel):
    id: str
    text: str


@app.post("/api/note")
def set_note(n: Note):
    """Free-text note on the plant; an empty string deletes it."""
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
    print(f"[qc] serving on http://{a.host}:{a.port}")
    uvicorn.run(app, host=a.host, port=a.port)
