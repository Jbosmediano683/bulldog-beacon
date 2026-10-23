"""Start Bulldog Beacon: one command, one process, then open http://127.0.0.1:8000

    python run.py              # start (creates and seeds data/beacon.db on first run)
    python run.py --reset      # wipe the database and re-seed fresh demo data first
    python run.py --port 8010  # use another port
"""

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))


def main() -> None:
    if sys.version_info < (3, 11):
        sys.exit("Bulldog Beacon needs Python 3.11 or newer.")
    parser = argparse.ArgumentParser(description="Run Bulldog Beacon")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reset", action="store_true", help="wipe and re-seed the database first")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    import config  # loads .env from this folder, then the folder above
    import events
    import shuttle
    import uvicorn
    from db import connect
    from seed import seed

    where = config.env_file_used()
    if not where:
        print("\n!! PORTKEY_API_KEY not found. Put it in a .env file in this folder or the folder above it.")
        print("   The app will start, but the AI features will show a friendly error.\n")
    else:
        print(f"PORTKEY_API_KEY found ({where}). Model: {config.MODEL_NAME}")

    conn = connect()
    seed(conn, reset=args.reset)
    conn.close()
    if args.reset:
        print("Database reset and re-seeded.")

    # Fetch Yale's events calendar and shuttle routes now, not on the first visit.
    threading.Thread(target=events.refresh, daemon=True).start()
    threading.Thread(target=shuttle.system, daemon=True).start()

    url = f"http://127.0.0.1:{args.port}"
    print(f"\nBulldog Beacon is running at {url}\n  Demo sign-in: NetID hd2026 / password Bulldog#2026\n")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("main:app", app_dir=str(ROOT / "backend"), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
