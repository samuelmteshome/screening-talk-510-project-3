"""Screenshot the MLflow UI (run list and the final heart run) into docs/mlflow/ for the README.

Run after training, from the repo root:
    python scripts/mlflow_screenshots.py            # uses sqlite:///mlflow.db
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
import mlflow  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "mlflow"
URI = os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{ROOT / 'mlflow.db'}")
PORT = 5055


def wait_for(url: str, seconds: int = 90) -> None:
    for _ in range(seconds):
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(1)
    sys.exit(f"MLflow UI did not start at {url}")


def main() -> None:
    mlflow.set_tracking_uri(URI)
    exp = mlflow.get_experiment_by_name("screening-talk") or mlflow.search_experiments()[0]
    runs = mlflow.search_runs([exp.experiment_id], order_by=["start_time DESC"])
    heart = runs[runs["tags.mlflow.runName"].fillna("").str.contains("heart")]
    pick = (heart if len(heart) else runs).iloc[0]["run_id"]

    ui = subprocess.Popen(["mlflow", "ui", "--backend-store-uri", URI, "--port", str(PORT)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{PORT}"
        wait_for(base)
        OUT.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
            for name, path, height in (("runs.png", f"/#/experiments/{exp.experiment_id}/runs", 700),
                                       ("run.png", f"/#/experiments/{exp.experiment_id}/runs/{pick}", 1300)):
                page = browser.new_page(viewport={"width": 1500, "height": height}, device_scale_factor=2)
                page.goto(base + path)
                page.get_by_text("heart").first.wait_for(timeout=60000)  # run names have loaded
                time.sleep(3)
                try:  # close the assistant side panel so the run fills the picture
                    page.locator("text=MLflow Assistant").locator("xpath=ancestor::*[.//button][1]").locator("button").last.click(timeout=3000)
                    time.sleep(1)
                except Exception:
                    pass
                page.screenshot(path=str(OUT / name))
                print("wrote", OUT / name)
    finally:
        ui.terminate()


if __name__ == "__main__":
    main()
