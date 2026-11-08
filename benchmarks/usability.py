"""Run a local, synthetic review exercise through the built frontend."""

import argparse
import difflib
import html
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from api import AnalyzeRequest, AnalyzeResponse
from git_analyzer import analyze_change
from web import FRONTEND_DIST


EXERCISE_URL = "https://github.com/impactlens-local/review-exercise"
BEFORE = "def shipping_fee(subtotal):\n    return 0 if subtotal >= 50 else 5\n"
AFTER = "def shipping_fee(subtotal):\n    return 0 if subtotal >= 75 else 5\n"
SOURCES = {
    "pricing.py": BEFORE,
    "routes.py": (
        "from fastapi import APIRouter\n"
        "from pricing import shipping_fee\n\n"
        "router = APIRouter(prefix='/checkout')\n\n"
        "@router.get('/shipping')\n"
        "def shipping(subtotal: float):\n"
        "    return {'fee': shipping_fee(subtotal)}\n\n"
        "@router.get('/health')\n"
        "def health():\n"
        "    return {'status': 'ok'}\n"
    ),
    "main.py": (
        "from fastapi import FastAPI\n"
        "from routes import router\n\n"
        "app = FastAPI()\n"
        "app.include_router(router, prefix='/api')\n"
    ),
    "tests/test_shipping.py": (
        "from routes import shipping\n\n"
        "def test_free_shipping():\n"
        "    assert shipping(60) == {'fee': 0}\n"
    ),
    "tests/test_health.py": (
        "from routes import health\n\n"
        "def test_health():\n"
        "    assert health() == {'status': 'ok'}\n"
    ),
}


@dataclass(frozen=True)
class Exercise:
    repository: Path
    base: str
    target: str

    @property
    def request(self):
        return {"repository": EXERCISE_URL, "base_commit": self.base, "target_commit": self.target}


def build_exercise(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    repository = output / "repository"
    repository.mkdir()
    environment = dict(os.environ)
    environment.update({
        "GIT_AUTHOR_NAME": "ImpactLens Exercise",
        "GIT_COMMITTER_NAME": "ImpactLens Exercise",
        "GIT_AUTHOR_EMAIL": "exercise@example.invalid",
        "GIT_COMMITTER_EMAIL": "exercise@example.invalid",
        "GIT_AUTHOR_DATE": "2026-11-08T12:00:00Z",
        "GIT_COMMITTER_DATE": "2026-11-08T12:00:00Z",
    })

    def git(*arguments):
        return subprocess.run(
            ["git", "-C", str(repository), "-c", "core.autocrlf=false",
             "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={output / 'no-hooks'}",
             *arguments], env=environment, check=True, capture_output=True, text=True,
            timeout=30,
        ).stdout.strip()

    git("-c", "init.templateDir=", "init", "--initial-branch=exercise")
    for relative, source in SOURCES.items():
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.encode("utf-8"))
    git("add", "--all")
    git("commit", "-m", "Exercise: shipping before threshold change")
    base = git("rev-parse", "HEAD")
    (repository / "pricing.py").write_bytes(AFTER.encode("utf-8"))
    git("add", "pricing.py")
    git("commit", "-m", "Exercise: raise free shipping threshold")
    exercise = Exercise(repository, base, git("rev-parse", "HEAD"))
    (output / "comparison.json").write_text(json.dumps(exercise.request, indent=2) + "\n", encoding="utf-8")
    return exercise


def create_exercise_app(exercise, frontend_directory=FRONTEND_DIST):
    directory = Path(frontend_directory)
    index = (directory / "index.html").read_text(encoding="utf-8")
    banner = (
        '<aside style="padding:12px 24px;border-bottom:1px solid #777">'
        '<strong>Local review exercise</strong> · Synthetic code; no GitHub fetch. '
        'The repository URL is an exercise label. '
        '<a href="/exercise">Comparison details and task</a></aside>'
    )
    app = FastAPI(title="ImpactLens local review exercise")

    @app.get("/", response_class=HTMLResponse)
    def home():
        return index.replace("<body>", "<body>" + banner, 1)

    @app.get("/exercise", response_class=HTMLResponse)
    def task():
        fields = "".join(f"<dt>{label}</dt><dd><code>{html.escape(value)}</code></dd>" for label, value in [
            ("Repository (local exercise label)", EXERCISE_URL),
            ("Older commit", exercise.base), ("Newer commit", exercise.target),
        ])
        diff = "".join(difflib.unified_diff(
            BEFORE.splitlines(keepends=True), AFTER.splitlines(keepends=True),
            fromfile="older/pricing.py", tofile="newer/pricing.py",
        ))
        return (
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>ImpactLens review exercise</title>'
            '<body style="font-family:system-ui;max-width:760px;margin:32px auto;padding:0 20px;line-height:1.6">'
            '<h1>Review a shipping-price change</h1>'
            '<p>A small shop proposes raising its free-shipping threshold from $50 to $75. '
            'You are reviewing this change before it is merged.</p>'
            f'<pre style="overflow:auto">{html.escape(diff)}</pre>'
            '<p>Use ImpactLens to decide what you would inspect or test and why. '
            'Please describe what you are thinking as you work. You can stop at any time.</p>'
            '<p>When ready, explain one potentially affected app URL, one test file you would consider, '
            'and the source evidence behind a connection. Does the report tell you whether '
            'the change is safe to merge?</p>'
            f'<h2>Comparison details</h2><dl style="overflow-wrap:anywhere">{fields}</dl>'
            '<p>This server analyzes a local synthetic Git repository. Nothing is downloaded '
            'from that GitHub label. It does not execute the example app or its tests.</p>'
            '<p><a href="/" target="_blank" rel="noopener">Open ImpactLens</a> '
            '(keep this sheet available to copy the comparison details).</p></body></html>'
        )

    @app.post("/analyze", response_model=AnalyzeResponse, response_model_exclude_none=True)
    def analyze(request: AnalyzeRequest):
        if request.model_dump() != exercise.request:
            raise HTTPException(400, "This local exercise accepts only the comparison on the exercise sheet. No GitHub fetch was attempted.")
        return analyze_change(exercise.repository, exercise.base, exercise.target)

    app.mount("/", StaticFiles(directory=directory), name="exercise-frontend")
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New folder for the synthetic Git repository and comparison details")
    parser.add_argument("--port", default=8003, type=int)
    args = parser.parse_args()
    if not (FRONTEND_DIST / "index.html").is_file():
        parser.error("Build the frontend first with npm run build in frontend/.")
    if args.output.exists():
        parser.error("Choose a new output folder; existing folders are never overwritten.")
    exercise = build_exercise(args.output)
    print(f"Local synthetic exercise: http://127.0.0.1:{args.port}/exercise", flush=True)
    print(f"Files retained at {exercise.repository.parent}; no GitHub fetch or fixture test execution.", flush=True)
    import uvicorn
    uvicorn.run(create_exercise_app(exercise), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
