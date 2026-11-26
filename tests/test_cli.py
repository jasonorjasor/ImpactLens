import json

import pytest

import cli


def sample_report():
    return {
        "base_commit": "old",
        "target_commit": "new",
        "changed_symbols": [
            {"id": "auth.py::verify_user", "changed_lines": [2]}
        ],
        "affected_symbols": [
            "services.py::login",
            "tests/test_login.py::test_login_route",
            "tests/test_login.py::helper",
        ],
        "affected_routes": [
            {
                "symbol_id": "routes.py::login_route",
                "method": "POST",
                "path": "/api/login",
            }
        ],
        "related_tests": ["tests/test_login.py::test_login_route"],
        "evidence_paths": [
            {"source": "target", "symbols": ["auth.py::verify_user", "services.py::login"]}
        ],
        "historical_impact": {
            "affected_symbols": [], "affected_routes": [], "related_tests": [],
        },
        "analysis_errors": [],
    }


def test_main_prints_human_readable_report(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "analyze_change", lambda *args: sample_report())

    assert cli.main([str(tmp_path), "old", "new"]) == 0

    output = capsys.readouterr().out
    assert "Changed symbols (1)" in output
    assert "Affected code symbols (1)" in output
    assert "tests/test_login.py::helper" not in output
    assert "POST /api/login" in output
    assert "auth.py::verify_user -> services.py::login" in output


def test_main_can_print_json(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "analyze_change", lambda *args: sample_report())

    assert cli.main([str(tmp_path), "old", "new", "--json"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["target_commit"] == "new"
    assert output["affected_routes"][0]["path"] == "/api/login"


def test_main_can_show_all_impact_paths(monkeypatch, capsys, tmp_path):
    report = sample_report()
    report["evidence_paths"] = [
        {"source": "target", "symbols": [f"symbol_{index}"]} for index in range(21)
    ]
    monkeypatch.setattr(cli, "analyze_change", lambda *args: report)

    assert cli.main([str(tmp_path), "old", "new", "--all-paths"]) == 0

    output = capsys.readouterr().out
    assert "symbol_20" in output
    assert "more paths" not in output


def test_format_report_limits_paths_by_default():
    report = sample_report()
    report["evidence_paths"] = [
        {"source": "target", "symbols": [f"symbol_{index}"]} for index in range(21)
    ]

    output = cli.format_report(report)

    assert "Impact paths (21)" in output
    assert "- 1 more paths (use --all-paths)" in output
    assert "symbol_20" not in output


def test_format_report_shows_rename_source():
    report = sample_report()
    report["changed_symbols"] = [
        {
            "id": "renamed.py::old_function",
            "changed_lines": [1],
            "change_type": "renamed",
            "previous_id": "old.py::old_function",
        }
    ]

    output = cli.format_report(report)

    assert "renamed.py::old_function (renamed; from old.py::old_function; lines: 1)" in output


def test_main_can_analyze_the_working_tree(monkeypatch, capsys, tmp_path):
    calls = []

    def fake_analyze_working_tree(*args):
        calls.append(args)
        return sample_report()

    monkeypatch.setattr(cli, "analyze_working_tree", fake_analyze_working_tree)

    assert cli.main([str(tmp_path), "HEAD", "--working-tree"]) == 0

    assert calls == [(tmp_path.resolve(), "HEAD")]
    assert "Comparison: old -> new" in capsys.readouterr().out


def test_format_report_labels_historical_results():
    report = sample_report()
    report["changed_symbols"] = [{
        "id": "auth.py::verify_user", "change_type": "deleted",
        "changed_lines": [], "removed_lines": [1, 2],
    }]
    report["historical_impact"] = {
        key: report[key] for key in ["affected_symbols", "affected_routes", "related_tests"]
    }
    for key in report["historical_impact"]:
        report[key] = []
    report["evidence_paths"][0]["source"] = "base"

    output = cli.format_report(report)

    assert "deleted; removed lines (base): 1, 2" in output
    assert "Affected routes (0)" in output
    assert "Historical routes (1)" in output
    assert "Historical related tests (1)" in output
    assert "[base, historical] auth.py::verify_user -> services.py::login" in output


def test_format_report_shows_unanalyzed_files():
    report = sample_report()
    report["analysis_errors"] = [{
        "source": "target", "path": "broken.py", "error": "invalid syntax",
    }]

    output = cli.format_report(report)

    assert "Files not analyzed (1)" in output
    assert "[target] broken.py: invalid syntax" in output
    assert "Results may be incomplete." in output


def test_format_report_explains_direct_changes_without_repeating_tests():
    report = sample_report()
    report["changed_symbols"].extend([
        {"id": "routes.py::login_route", "changed_lines": [4]},
        {"id": "tests/test_login.py::test_login_route", "changed_lines": [3]},
    ])

    output = cli.format_report(report)

    assert "POST /api/login (routes.py::login_route; changed directly)" in output
    assert "Related tests (0)" in output
    assert output.count("tests/test_login.py::test_login_route") == 1


def test_format_report_keeps_historical_route_without_callers():
    report = sample_report()
    report["changed_symbols"] = [{
        "id": "routes.py::login_route", "changed_lines": [], "change_type": "deleted",
    }]
    report["evidence_paths"] = []
    report["historical_impact"] = {
        "affected_symbols": [],
        "affected_routes": report["affected_routes"],
        "related_tests": [],
    }
    report["affected_routes"] = []

    output = cli.format_report(report)

    assert "Historical routes (1)" in output
    assert "POST /api/login (routes.py::login_route; changed directly)" in output
    assert "- no caller paths found" in output


def test_import_root_finds_unchanged_callers_and_keeps_repository_paths(comparison, capsys):
    repository, commit = comparison
    helper = "backend/app/crud.py"
    route = "backend/app/routes.py"
    base = commit({
        "backend/app/__init__.py": "",
        helper: "def price():\n    return 1\n",
        route: "from app import crud\nfrom fastapi import APIRouter\nrouter = APIRouter()\n\n"
        "@router.get('/price')\ndef read_price():\n    return crud.price()\n",
        "backend/main.py": "from fastapi import FastAPI\nfrom app.routes import router\n"
        "app = FastAPI()\napp.include_router(router, prefix='/shop')\n",
        "tests/test_price.py": "from app.routes import read_price\n\n"
        "def test_price():\n    assert read_price() == 1\n",
    })
    head = commit({helper: "def price():\n    return 2\n"})
    arguments = [str(repository), base, head, "--json"]
    assert cli.main(arguments) == 0
    default = json.loads(capsys.readouterr().out)
    assert default["evidence_paths"] == []

    assert cli.main([*arguments, "--import-root", "backend"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["import_root"] == "backend"
    assert report["resolved_commits"] == {"base": base, "target": head}
    assert report["evidence_paths"] == [{"source": "target", "symbols": [
        f"{helper}::price", f"{route}::read_price", "tests/test_price.py::test_price",
    ]}]
    assert report["affected_routes"] == [{
        "symbol_id": f"{route}::read_price", "method": "GET", "path": "/shop/price", "registration": "registered",
    }]
    assert report["related_tests"] == ["tests/test_price.py::test_price"]
    assert {(site["path"], site["line"], site["expression"]) for site in report["call_sites"]} == {
        (route, 7, "crud.price"), ("tests/test_price.py", 4, "read_price"),
    }

    assert cli.main([str(repository), base, "--working-tree", "--json", "--import-root", ".\\backend\\"]) == 0
    working_tree = json.loads(capsys.readouterr().out)
    assert working_tree["import_root"] == "backend"
    assert working_tree["resolved_commits"]["target"] is None
    assert working_tree["evidence_paths"] == report["evidence_paths"]


def test_import_root_rejects_ambiguous_names_instead_of_linking_wrong_file(comparison, capsys):
    repository, commit = comparison
    base = commit({
        "backend/app.py": "def value():\n    return 1\n",
        "app.py": "def value():\n    return 8\n",
        "caller.py": "from app import value\ndef read():\n    return value()\n",
    })
    head = commit({"backend/app.py": "def value():\n    return 2\n"})
    with pytest.raises(SystemExit) as error:
        cli.main([str(repository), base, head, "--json", "--import-root", "backend"])
    output = capsys.readouterr()
    assert error.value.code == 2 and not output.out
    assert "ambiguous" in output.err and "backend/app.py" in output.err


def test_import_root_handles_removed_directory_and_invalid_root(comparison, capsys):
    repository, commit = comparison
    helper = "backend/pkg.py"
    base = commit({
        helper: "def calculate():\n    return 1\n",
        "routes.py": "from pkg import calculate\ndef run():\n    return calculate()\n",
    })
    (repository / helper).unlink()
    head = commit({})
    arguments = [str(repository), base, head, "--json", "--import-root"]
    assert cli.main([*arguments, "backend"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["evidence_paths"] == [{"source": "base", "symbols": [f"{helper}::calculate", "routes.py::run"]}]

    for folder, message in [("missing", "not found in either version"), ("../backend", "repository-relative folder")]:
        with pytest.raises(SystemExit) as error:
            cli.main([*arguments, folder])
        output = capsys.readouterr()
        assert error.value.code == 2 and not output.out
        assert message in output.err
