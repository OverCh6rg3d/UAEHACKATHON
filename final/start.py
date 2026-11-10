"""Start the DABAB demo in one step.

    python final/start.py        (or double-click final/run.bat on Windows, ./final/run.sh on macOS/Linux)

1. If the engine output is missing (fresh clone: processed data is not in git), copy the
   bundled demo data from final/demo_data/ into place. Existing data is never overwritten.
2. Start the backend (server.py, Python standard library only) on http://localhost:8000.
3. Open the ATC decision panel in the default browser.
"""
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "final" / "demo_data"
PROCESSED = ROOT / "dabab_data_pipeline" / "dabab_data" / "processed"
URL = "http://localhost:8000"


def ensure_data():
    copied = []
    for src in DEMO.rglob("*"):
        if src.is_file():
            dst = PROCESSED / src.relative_to(DEMO)
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(str(src.relative_to(DEMO)))
    print("Demo data copied:\n  " + "\n  ".join(copied) if copied else "Engine data found, using it.")


def open_browser():
    time.sleep(2)
    webbrowser.open(URL)


if __name__ == "__main__":
    if sys.version_info < (3, 9):
        sys.exit("DABAB needs Python 3.9 or newer.")
    ensure_data()
    print(f"Starting DABAB at {URL}  (Ctrl+C to stop)")
    threading.Thread(target=open_browser, daemon=True).start()
    try:
        subprocess.run([sys.executable, str(ROOT / "server.py")], cwd=ROOT)
    except KeyboardInterrupt:
        pass
