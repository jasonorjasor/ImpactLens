"""Tests for repository-level analysis."""

from analyzer import analyze_repository


def test_analyzes_nested_python_files_and_keeps_paths(tmp_path):
    source_root = tmp_path / "repo"
    package = source_root / "package"
    ignored = source_root / "__pycache__"
    package.mkdir(parents=True)
    ignored.mkdir()

    (source_root / "main.py").write_text(
        "def main():\n    return True\n", encoding="utf-8"
    )
    (package / "auth.py").write_text(
        "def verify_user():\n    return True\n", encoding="utf-8"
    )
    (ignored / "generated.py").write_text(
        "def should_not_be_seen():\n    return False\n", encoding="utf-8"
    )

    report = analyze_repository(source_root)

    assert [file["path"] for file in report["files"]] == ["main.py", "package/auth.py"]
    assert report["files"][1]["functions"][0]["path"] == "package/auth.py"
    assert report["errors"] == []


def test_assigns_stable_ids_and_resolves_unique_cross_file_calls(tmp_path):
    source_root = tmp_path / "repo"
    source_root.mkdir()
    (source_root / "auth.py").write_text(
        "def verify_user():\n    return True\n", encoding="utf-8"
    )
    (source_root / "services.py").write_text(
        "from auth import verify_user\n\n"
        "def login():\n    return verify_user()\n",
        encoding="utf-8",
    )

    report = analyze_repository(source_root)
    files = {file["path"]: file for file in report["files"]}
    login_call = files["services.py"]["calls"][0]

    assert files["auth.py"]["functions"][0]["id"] == "auth.py::verify_user"
    assert login_call["caller_id"] == "services.py::login"
    assert login_call["callee_id"] == "auth.py::verify_user"
    assert login_call["resolution"] == "import"


def test_does_not_guess_an_unimported_function(tmp_path):
    source_root = tmp_path / "repo"
    source_root.mkdir()
    (source_root / "auth.py").write_text(
        "def verify_user():\n    return True\n", encoding="utf-8"
    )
    (source_root / "services.py").write_text(
        "def login():\n    return verify_user()\n", encoding="utf-8"
    )

    report = analyze_repository(source_root)
    services = next(file for file in report["files"] if file["path"] == "services.py")
    call = services["calls"][0]

    assert call["callee_id"] is None
    assert call["resolution"] == "unresolved"


def test_assigns_class_qualified_ids(tmp_path):
    source_root = tmp_path / "repo"
    source_root.mkdir()
    (source_root / "users.py").write_text(
        "class User:\n"
        "    def login(self):\n"
        "        return self.verify_user()\n"
        "\n"
        "    def verify_user(self):\n"
        "        return True\n",
        encoding="utf-8",
    )

    report = analyze_repository(source_root)
    users = report["files"][0]

    assert [symbol["id"] for symbol in users["symbols"]] == [
        "users.py::User",
        "users.py::User.login",
        "users.py::User.verify_user",
    ]
    assert users["calls"][0]["caller_id"] == "users.py::User.login"
    assert users["calls"][0]["callee_id"] == "users.py::User.verify_user"


def test_resolves_relative_package_imports(tmp_path):
    source_root = tmp_path / "repo"
    package = source_root / "package"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "auth.py").write_text(
        "def verify_user():\n    return True\n", encoding="utf-8"
    )
    (package / "services.py").write_text(
        "from .auth import verify_user\n\n"
        "def login():\n    return verify_user()\n",
        encoding="utf-8",
    )

    report = analyze_repository(source_root)
    services = next(file for file in report["files"] if file["path"] == "package/services.py")
    imported = services["imports"][0]
    call = services["calls"][0]

    assert imported["module"] == ".auth"
    assert imported["resolved_module"] == "package.auth"
    assert call["callee_id"] == "package/auth.py::verify_user"
    assert call["resolution"] == "import"
