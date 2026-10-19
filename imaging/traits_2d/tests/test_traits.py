"""traits_2d 最小測試（S2）：COLUMN_MAP 完整性、葉數、空 mask、business key。
跑法：conda run -n pheno python -m pytest traits_2d/tests/ -q
"""
import numpy as np
import cv2

from traits_2d import traits as T


def test_db_trait_cols_count():
    # DB trait_observations 113 實體欄 − 9 個非 trait 欄（id / plant_id / sensor_id /
    # observation_timestamp / day_after_sewing / image_file / qc_status /
    # pipeline_version / analysis_run_id）= 104 trait 欄。
    # 沿革：121 →（007 DROP mer_angle）→ 120 →（012 DROP 三個全表 NULL 欄）→ 117
    #      →（013 DROP 三個 radius 欄，抽取器不產且僅 20 列 legacy 值）→ 114
    #      →（014 DROP source_hash，宣告但從未填；非 trait 欄故不動 104）→ 113。
    assert len(T.DB_TRAIT_COLS) == 104
    assert len(set(T.DB_TRAIT_COLS)) == 104  # 無重複
    assert "mer_angle" not in T.DB_TRAIT_COLS


def test_leaf_count_is_computed_not_null():
    assert "leaf_count" in T.COMPUTED_COLS
    assert "leaf_count" not in T.NULL_COLS


def test_null_cols_are_db_cols():
    for c in T.NULL_COLS:
        assert c in T.DB_TRAIT_COLS


def test_to_db_row_empty_mask_leaf_count_zero():
    row = T.to_db_row({}, n_leaves=0)
    assert set(row) == set(T.DB_TRAIT_COLS)
    assert row["leaf_count"] == 0
    assert row["area_pixels"] == ""          # 空 mask → NULL
    assert row["solidity"] == ""             # 空 mask → extractor 無輸出 → NULL


def test_to_db_row_maps_extractor_by_name_and_drops_extras():
    raw = {"area_pixels": 123.0, "solidity": 0.8,
           "boundary_method": 1, "my_custom_trait_1": 9}  # 後兩者非 DB 欄應丟棄
    row = T.to_db_row(raw, n_leaves=3)
    assert row["leaf_count"] == 3
    assert row["area_pixels"] == 123.0
    assert row["solidity"] == 0.8
    assert "boundary_method" not in row
    assert "my_custom_trait_1" not in row


def test_to_db_row_nan_becomes_null():
    row = T.to_db_row({"solidity": float("nan")}, n_leaves=1)
    assert row["solidity"] == ""


def test_leaf_area_aliases_area_pixels():
    # extractor 不產 leaf_area；須以 area_pixels 填（消費端 batch_correction 讀 leaf_area）
    row = T.to_db_row({"area_pixels": 500.0}, n_leaves=2)
    assert row["leaf_area"] == 500.0
    assert row["area_pixels"] == 500.0
    # 空 mask → 兩者皆 NULL
    assert T.to_db_row({}, n_leaves=0)["leaf_area"] == ""


def test_dropped_columns_are_not_written():
    # 2026-08-17 兩支 migration 把六個死欄從 DB DROP 掉；即使 extractor 誤帶，
    # 也不可再出現在寫入列裡（欄位不存在 → INSERT 會炸）
    #   012  compactness / roundness / gap_fraction_canopy_porosity（全表 NULL）
    #   013  max_ / mean_ / median_radius_from_centroid（抽取器 2026-07-07 起不產）
    raw = {"roundness": 0.9, "compactness": 0.5, "gap_fraction_canopy_porosity": 0.3,
           "max_radius_from_centroid": 1.0, "mean_radius_from_centroid": 2.0,
           "median_radius_from_centroid": 3.0}
    row = T.to_db_row(raw, n_leaves=1)
    for col in raw:
        assert col not in row
    # 同族仍在產的兩欄不受影響
    assert "min_radius_from_centroid" in T.DB_TRAIT_COLS
    assert "std_radius_from_centroid" in T.DB_TRAIT_COLS


def test_parse_business_key():
    # Phase 3 rename 後路徑結構 = <batch>/<cultivar>/<treatment>/rep-<n>
    rel = "2025B08/s0128/Control/rep-1"
    k = T.parse_business_key(rel)
    assert k["batch_code"] == "2025B08"
    assert k["cultivar_code"] == "s0128"
    assert k["replicate_code"] == "1"
    assert k["sensor_code"] == ""             # sensor 已不在路徑 → resolver 查 DB chamberhistory
    assert k["old_plant_id"] == ""            # id 已不在路徑（provenance 留空）
    assert k["plant_type"] == "observation_individual"
    assert "treatment_code" not in k          # 刻意留 S3 解析


def test_business_key_underscore():
    rel = "2025B08/s0128/Control/rep-1"
    assert T.parse_rel(rel) == ("2025B08", "s0128", "Control", "1")
    assert T.business_key(rel) == "2025B08_s0128_Control_1"    # ＝ re-key 後 qc.sqlite plant_id


def test_ts_to_timestamp():
    assert T.ts_to_timestamp("raspi_202508071230_x") == "2025-08-07 12:30:00"
    assert T.ts_to_timestamp("nodigits") == ""


def test_effective_keep_override_wins():
    ov = {"t1": 0, "t2": 1}
    assert T.effective_keep({"tid": "t1", "keep": True}, ov) is False   # override reject 勝
    assert T.effective_keep({"tid": "t2", "keep": False}, ov) is True   # override keep 勝
    assert T.effective_keep({"tid": "t9", "keep": True}, ov) is True    # 無 override → M2 keep
    assert T.effective_keep({"tid": "t9", "keep": False}, ov) is False


def test_build_mask_fills_polygon():
    leaves = [{"points": [[10, 10], [100, 10], [100, 100], [10, 100]]}]
    m = T.build_mask(leaves)
    assert m.shape == (T.CANVAS, T.CANVAS)
    assert m.sum() > 0
    # 太少點的葉不畫
    assert T.build_mask([{"points": [[1, 1], [2, 2]]}]).sum() == 0
