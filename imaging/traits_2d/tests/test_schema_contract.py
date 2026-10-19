"""test_schema_contract.py — schema drift-guard（跨模組契約守衛）。

背景：imaging/traits_2d 與 platform 不共用 code，只共用「DB schema 契約」。
worker 的 `DB_TRAIT_COLS`（107 欄，2026-08-17 migration 012 後）是 platform
`trait_observations` 的一份**複本**；
若有人在 platform 改 schema，這裡會默默漂移。本測試查 live DB 的 information_schema，
斷言 worker 要寫的欄位全部存在於 DB，一漂移就紅。

契約（硬性）：worker 寫的每一欄（6 key 欄 + DB_TRAIT_COLS）必須存在於 DB
             → 否則 INSERT 會炸。用子集斷言（DB 可有 provenance 等額外欄）。

DB 不可達時 SKIP（不誤判為失敗）。連線走 docker exec，不需密碼。
跑法：conda run -n pheno python -m traits_2d.tests.test_schema_contract
"""
import subprocess

from traits_2d import traits as T

DB_CONTAINER = "bpp-database"
DB_USER, DB_NAME = "phenouser", "plant_phenotyping"
TABLE = "trait_observations"

# trait_observations 的 key/meta 欄（非 trait，但 worker 也寫）
KEY_DB_COLS = [
    "plant_id", "sensor_id", "observation_timestamp", "day_after_sewing",
]
# id（自增 PK）、image_file 由 DB/未來處理，不在 worker 直寫契約內但須存在
META_DB_COLS = ["id", "image_file"]


def _live_columns():
    """回傳 trait_observations 現有欄位集合；DB 不可達回 None（SKIP）。"""
    sql = (f"SELECT column_name FROM information_schema.columns "
           f"WHERE table_name='{TABLE}'")
    try:
        out = subprocess.run(
            ["docker", "exec", DB_CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME,
             "-tAc", sql],
            capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    cols = {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}
    return cols or None


def check() -> bool:
    live = _live_columns()
    if live is None:
        print("[SKIP] DB 不可達（bpp-database），略過 schema drift-guard")
        return True

    worker_writes = set(KEY_DB_COLS) | set(T.DB_TRAIT_COLS)
    missing = sorted(worker_writes - live)          # worker 要寫但 DB 沒有 → 硬錯
    extra_in_db = sorted(live - worker_writes - set(META_DB_COLS))  # DB 有、worker 沒填 → 資訊

    print(f"[schema] live trait_observations 欄位 {len(live)}；worker 寫 {len(worker_writes)}")
    if extra_in_db:
        print(f"[info] DB 有但 worker 未填的欄位（provenance/未來/deprecated，可接受）：{extra_in_db}")
    if missing:
        print(f"[FAIL] worker 要寫但 DB 不存在的欄位（會 INSERT 失敗）：{missing}")
        return False
    print("[PASS] worker 寫入的所有欄位皆存在於 DB（契約對齊）")
    return True


def test_worker_columns_exist_in_db():
    assert check(), "schema drift: worker 欄位與 platform trait_observations 不對齊"


if __name__ == "__main__":
    import sys
    sys.exit(0 if check() else 1)
