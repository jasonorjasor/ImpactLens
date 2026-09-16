import json

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
