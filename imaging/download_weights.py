"""Download the four model weights into WEIGHTS_DIR (default imaging/weights/) and verify SHA-256.

A file already present with the right hash is kept. Exits with status 1 if any weight is
missing or fails verification.

  python imaging/download_weights.py
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import WEIGHTS_DIR  # noqa: E402

# name, url, sha256, size in bytes
# Our three weights are attached to this repository's GitHub Release; URLs are filled in at release time.
# GenYOLO-Leaf is not redistributed here: it comes from the authors' own release.
WEIGHTS = [
    ("run_v11m_640_s1_v3_best.pt", "",
     "5b8c2212c3580542b76d248f58865f9f83b7cb889a1456cd3d44fbb133054e11", 45185270),
    ("yolov8mseg_train31.pt", "",
     "bd64449929a6f15004b82982b7fa8e74e87299a7b2f0560a28a4d3cd1f68b849", 54936837),
    ("stage8_keypoint_v8.pth", "",
     "66974ed99cf90bc00ab1caf51bb10805624e76623b38215e1d5a4b0519f45186", 55827489),
    ("genyolo_leaf_yolov11m.pt",
     "https://github.com/aaslihanyildirim/GenYOLO-Leaf/releases/download/shared_best_models/genyolo_leaf_yolov11m.pt",
     "b8773479950c22b8862e029f6c129b1d60c69e562ae3442ce278ff7d158beb02", 45186308),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path) -> None:
    part = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(url) as r, open(part, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    part.replace(dest)


def main() -> int:
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"weights directory: {WEIGHTS_DIR}")
    failed = []
    for name, url, digest, size in WEIGHTS:
        dest = WEIGHTS_DIR / name
        if dest.exists() and sha256(dest) == digest:
            print(f"  ok        {name}")
            continue
        if not url:
            print(f"  MISSING   {name}: download URL not published yet")
            failed.append(name)
            continue
        print(f"  download  {name} ({size / 1e6:.1f} MB)")
        try:
            fetch(url, dest)
        except OSError as e:
            print(f"  FAILED    {name}: {e}")
            failed.append(name)
            continue
        if sha256(dest) != digest:
            dest.unlink()
            print(f"  FAILED    {name}: SHA-256 mismatch, file removed")
            failed.append(name)
            continue
        print(f"  ok        {name}")
    if failed:
        print(f"{len(failed)} weight(s) not available: {', '.join(failed)}")
        return 1
    print("all weights present and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
