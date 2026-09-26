"""Small, hand-reviewed comparisons; see benchmarks/ACCURACY.md."""

import subprocess

import pytest

from git_analyzer import analyze_change


BASE_FUNCTION = "def calculate():\n    return 1\n"
TARGET_FUNCTION = "def calculate():\n    return 2\n"
CALLER = "from service import calculate as compute\n\ndef run():\n    return compute()\n"
TEST = "from caller import run\n\ndef test_run():\n    assert run() == 1\n"
CHAIN = ["service.py::calculate", "caller.py::run", "tests/test_run.py::test_run"]


@pytest.mark.parametrize("case", ["alias", "ambiguous_imports", "deletion", "dynamic"])
def test_hand_reviewed_comparison(tmp_path, case):
    repository = tmp_path / "repo"
    repository.mkdir()

    def git(*arguments):
        return subprocess.run(
            ["git", "-C", str(repository), *arguments], check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    git("init")
    git("config", "user.email", "impactlens@example.com")
    git("config", "user.name", "ImpactLens Review")
    git("config", "commit.gpgsign", "false")
    sources = {"service.py": BASE_FUNCTION, "caller.py": CALLER, "tests/test_run.py": TEST}
    if case == "ambiguous_imports":
        sources["other.py"] = "def calculate():\n    return 10\n"
        sources["caller.py"] = (
            "from service import *\nfrom other import *\n\n"
            "def run():\n    return calculate()\n"
        )
    elif case == "dynamic":
        sources["caller.py"] = (
            "import service\n\ndef run():\n"
            "    return getattr(service, 'calculate')()\n"
        )
    for path, source in sources.items():
        destination = repository / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")

    (repository / "service.py").write_text(
        "" if case == "deletion" else TARGET_FUNCTION, encoding="utf-8"
    )
    git("add", ".")
    git("commit", "-m", "change")
    report = analyze_change(repository, base, git("rev-parse", "HEAD"))

    assert report["analysis_errors"] == []
    assert [symbol["id"] for symbol in report["changed_symbols"]] == ["service.py::calculate"]
    expected_paths = [] if case == "ambiguous_imports" else [
        {"source": "base" if case == "deletion" else "target", "symbols": CHAIN}
    ]
    if case == "deletion":
        assert report["changed_symbols"][0]["change_type"] == "deleted"
        assert report["affected_symbols"] == []
        assert report["historical_impact"]["related_tests"] == ["tests/test_run.py::test_run"]
    elif case == "alias":
        assert report["related_tests"] == ["tests/test_run.py::test_run"]

    if case == "dynamic" and report["evidence_paths"] == []:
        pytest.xfail("Known missed dependency: getattr(service, 'calculate')()")
    assert report["evidence_paths"] == expected_paths
