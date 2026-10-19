"""imaging 共用設定 — 資料路徑與批號格式的唯一定義（core.py、traits_2d、overlays 共用）。

imaging 只讀寫檔案、不連資料庫。路徑一律環境變數優先，否則取 repo 內的相對位置；
QC_ROOT／RASPI_ROOT 的解析與 qc/server.py 相同，imaging 寫出的 data/ 由 QC 工具直接讀取。
"""
import os
import re
from pathlib import Path

# imaging/ 程式碼所在
CODE_ROOT = Path(__file__).resolve().parent

# --- 批號正規形式 ---
# canonical batch_code = 西元年 4 碼 + 'B' + 序號 2 碼，如 2025B08。
# 短名（B08）一律拒絕：批號同時是 staging 檔名的 key，入口形式不一會讀到別批的舊產物。
BATCH_CODE_RE = re.compile(r"^\d{4}B\d{2}$")


def require_batch_code(batch_code):
    """驗證並回傳 canonical batch_code；不合格丟 ValueError。所有吃 --batch 的入口都要先過。"""
    if not batch_code or not BATCH_CODE_RE.match(batch_code):
        raise ValueError(
            f"bad batch_code {batch_code!r}: needs a full batch code such as 2025B08, not B08")
    return batch_code


# --- 輸入 ---
# QC_ROOT：QC 工具的根，其下 data/（frames.json）與 qc.sqlite（人工逐葉覆寫）
QC_ROOT = Path(os.environ.get("QC_ROOT", CODE_ROOT.parent / "qc"))
QC_DATA = QC_ROOT / "data"
QC_DB = QC_ROOT / "qc.sqlite"

# RASPI_ROOT：單株裁切影像 <batch>/<cultivar>/<treatment>/rep-<n>/*.png
_raspi_env = os.environ.get("RASPI_ROOT")
RASPI_ROOT = (Path(_raspi_env) if _raspi_env
              else QC_ROOT / "raspi_RGB" if (QC_ROOT / "raspi_RGB").exists()
              else QC_ROOT.parent / "raspi_RGB")

# WEIGHTS_DIR：四個模型權重放同一個目錄
WEIGHTS_DIR = Path(os.environ.get("WEIGHTS_DIR", CODE_ROOT / "weights"))

# --- 輸出（可重生）---
# 分割與歸屬的透明疊層 PNG，與 RASPI_ROOT 同結構的獨立樹
OVERLAY_ROOT = Path(os.environ.get("OVERLAY_ROOT", RASPI_ROOT.parent / "raspi_RGB_overlay"))
# traits_2d 的 staging CSV
OUT = Path(os.environ.get("OUT_DIR", CODE_ROOT / "out"))
