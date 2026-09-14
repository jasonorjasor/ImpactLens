import json

import cli


def sample_report():
    return {
        "base_commit": "old",
        "target_commit": "new",
        "changed_symbols": [
            {"id": "auth.py::verify_user", "changed_lines": [2]}
        ],
        "affected_symbols": ["services.py::login"],
        "affected_routes": [
            {
                "symbol_id": "routes.py::login_route",
                "method": "POST",
                "path": "/api/login",
            }
        ],
        "related_tests": ["tests/test_login.py::test_login_route"],
        "evidence_paths": [
            ["auth.py::verify_user", "services.py::login"]
        ],
    }


def test_main_prints_human_readable_report(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "analyze_change", lambda *args: sample_report())

    assert cli.main([str(tmp_path), "old", "new"]) == 0

    output = capsys.readouterr().out
    assert "Changed symbols (1)" in output
    assert "POST /api/login" in output
    assert "auth.py::verify_user -> services.py::login" in output


def test_main_can_print_json(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "analyze_change", lambda *args: sample_report())

    assert cli.main([str(tmp_path), "old", "new", "--json"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["target_commit"] == "new"
    assert output["affected_routes"][0]["path"] == "/api/login"


def test_main_can_analyze_the_working_tree(monkeypatch, capsys, tmp_path):
    calls = []

    def fake_analyze_working_tree(*args):
        calls.append(args)
        return sample_report()

    monkeypatch.setattr(cli, "analyze_working_tree", fake_analyze_working_tree)

    assert cli.main([str(tmp_path), "HEAD", "--working-tree"]) == 0

    assert calls == [(str(tmp_path), "HEAD")]
    assert "Comparison: old -> new" in capsys.readouterr().out
