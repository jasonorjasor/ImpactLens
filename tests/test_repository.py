"""Tests for repository-level analysis."""

from analyzer import analyze_repository


def test_reports_invalid_source_encoding_without_guessing(tmp_path):
    (tmp_path / "invalid.py").write_bytes(b"def broken():\n    return '\xff'\n")

    report = analyze_repository(tmp_path)

    assert report["files"] == []
    assert len(report["errors"]) == 1
    assert report["errors"][0]["path"] == "invalid.py"


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


def _write_package(source_root, files):
    for relative_path, source in files.items():
        path = source_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")


def _call(report, path):
    file = next(file for file in report["files"] if file["path"] == path)
    return file["calls"][0]


def test_resolves_calls_through_imported_submodules(tmp_path):
    _write_package(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/services.py": "def create_user():\n    return 1\n",
        "routes.py": "from pkg import services\n\ndef a():\n    return services.create_user()\n",
        "aliased.py": "from pkg import services as svc\n\ndef b():\n    return svc.create_user()\n",
        "pkg/relative.py": "from . import services\n\ndef c():\n    return services.create_user()\n",
    })

    report = analyze_repository(tmp_path)

    for path in ("routes.py", "aliased.py", "pkg/relative.py"):
        call = _call(report, path)
        assert call["callee_id"] == "pkg/services.py::create_user"
        assert call["resolution"] == "import"


def test_does_not_treat_an_imported_class_as_a_submodule(tmp_path):
    _write_package(tmp_path, {
        "pkg/__init__.py": "class Service:\n    @staticmethod\n    def create():\n        return 1\n",
        "routes.py": "from pkg import Service\n\ndef a():\n    return Service.create()\n",
    })

    call = _call(analyze_repository(tmp_path), "routes.py")

    assert call["callee_id"] is None
    assert call["resolution"] == "unresolved"


def test_package_export_takes_precedence_over_same_named_submodule(tmp_path):
    _write_package(tmp_path, {
        "pkg/__init__.py": "class Service:\n    @staticmethod\n    def create():\n        return 1\n",
        "pkg/Service.py": "def create():\n    return 2\n",
        "routes.py": "from pkg import Service\n\ndef a():\n    return Service.create()\n",
    })

    call = _call(analyze_repository(tmp_path), "routes.py")

    assert call["callee_id"] is None


def test_package_reexport_of_its_own_submodule_still_resolves(tmp_path):
    _write_package(tmp_path, {
        "pkg/__init__.py": "from . import services\n",
        "pkg/services.py": "def create_user():\n    return 1\n",
        "routes.py": "from pkg import services\n\ndef a():\n    return services.create_user()\n",
    })

    call = _call(analyze_repository(tmp_path), "routes.py")

    assert call["callee_id"] == "pkg/services.py::create_user"


def test_relative_imports_in_package_initializer_stay_inside_the_package(tmp_path):
    _write_package(tmp_path, {
        "services.py": "def create_user():\n    return 0\n",
        "pkg/services.py": "def create_user():\n    return 1\n",
        "pkg/__init__.py": (
            "from . import services\nfrom .services import create_user\n\n"
            "def a():\n    return services.create_user()\n\n"
            "def b():\n    return create_user()\n"
        ),
    })

    report = analyze_repository(tmp_path)
    initializer = next(file for file in report["files"] if file["path"] == "pkg/__init__.py")

    assert [item["resolved_module"] for item in initializer["imports"]] == ["pkg", "pkg.services"]
    assert [call["callee_id"] for call in initializer["calls"]] == [
        "pkg/services.py::create_user",
        "pkg/services.py::create_user",
    ]


def test_package_reassignment_after_submodule_import_is_not_followed(tmp_path):
    _write_package(tmp_path, {
        "pkg/__init__.py": "from . import services\nservices = object()\n",
        "pkg/services.py": "def create_user():\n    return 1\n",
        "routes.py": "from pkg import services\n\ndef a():\n    return services.create_user()\n",
    })

    assert _call(analyze_repository(tmp_path), "routes.py")["callee_id"] is None


def test_function_level_import_does_not_count_as_package_reexport(tmp_path):
    _write_package(tmp_path, {
        "pkg/__init__.py": "services = object()\n\ndef load():\n    from . import services\n    return services\n",
        "pkg/services.py": "def create_user():\n    return 1\n",
        "routes.py": "from pkg import services\n\ndef a():\n    return services.create_user()\n",
    })

    assert _call(analyze_repository(tmp_path), "routes.py")["callee_id"] is None
