"""Reusable static-analysis functions for the ImpactLens lessons."""

import ast
import io
import tokenize
from pathlib import Path

from request_budget import check_deadline


EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__"}


class SymbolVisitor(ast.NodeVisitor):
    def __init__(self):
        self.scope = []
        self.symbols = []

    def _visit_symbol(self, node, kind):
        qualname = ".".join(self.scope + [node.name])
        self.symbols.append(
            {
                "kind": kind,
                "name": node.name,
                "qualname": qualname,
                "line_start": node.lineno,
                "line_end": node.end_lineno,
            }
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_ClassDef(self, node):
        self._visit_symbol(node, "class")

    def visit_FunctionDef(self, node):
        self._visit_symbol(node, "function")

    def visit_AsyncFunctionDef(self, node):
        self._visit_symbol(node, "async_function")


def extract_symbols(source):
    tree = ast.parse(source)
    visitor = SymbolVisitor()
    visitor.visit(tree)
    return visitor.symbols


def decode_python_source(source):
    if isinstance(source, str):
        return source
    encoding, _ = tokenize.detect_encoding(io.BytesIO(source).readline)
    return source.decode(encoding)


def extract_functions(source):
    
    symbols = extract_symbols(source)

    return [symbol for symbol in symbols if symbol["kind"] in {"function", "async_function"}]


class CallVisitor(ast.NodeVisitor):

    def __init__(self):
        self.current_function = None
        self.scope = []
        self.class_scope = []
        self.calls = []

    def _visit_function(self, node):
        previous_function = self.current_function
        self.scope.append(node.name)
        self.current_function = ".".join(self.scope)

        self.generic_visit(node)

        self.scope.pop()
        self.current_function = previous_function

    def visit_ClassDef(self, node):
        self.scope.append(node.name)
        self.class_scope.append(".".join(self.scope))
        self.generic_visit(node)
        self.class_scope.pop()
        self.scope.pop()

    def visit_FunctionDef(self, node):
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node):
        self._visit_function(node)

    def visit_Call(self, node):
        if isinstance(node.func, (ast.Name, ast.Attribute)):
            callee = ast.unparse(node.func)
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"self", "cls"}
                and self.class_scope
            ):
                callee = f"{self.class_scope[-1]}.{node.func.attr}"

            self.calls.append(
                {
                    "caller": self.current_function,
                    "callee": callee,
                    "line": node.lineno,
                }
            )

        self.generic_visit(node)


def extract_calls(source):
    tree = ast.parse(source)
    visitor = CallVisitor()
    visitor.visit(tree)
    return visitor.calls


def extract_imports(source):
    tree = ast.parse(source)
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(
                    {
                        "local_name": alias.asname or alias.name.split(".")[0],
                        "module": alias.name,
                        "name": None,
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            for alias in node.names:
                if alias.name != "*":
                    imports.append(
                        {
                            "local_name": alias.asname or alias.name,
                            "module": module,
                            "name": alias.name,
                        }
                    )

    return imports


FASTAPI_METHODS = {"delete", "get", "head", "options", "patch", "post", "put", "websocket"}


class RouteVisitor(ast.NodeVisitor):
    def __init__(self):
        self.scope = []
        self.routes = []

    def visit_ClassDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def _visit_function(self, node):
        qualname = ".".join(self.scope + [node.name])
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.lower()
            if method not in FASTAPI_METHODS:
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            if not isinstance(decorator.args[0].value, str):
                continue
            self.routes.append(
                {
                    "qualname": qualname,
                    "method": method.upper(),
                    "path": decorator.args[0].value,
                }
            )

        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node):
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node):
        self._visit_function(node)


def extract_routes(source):
    tree = ast.parse(source)
    visitor = RouteVisitor()
    visitor.visit(tree)
    return visitor.routes


def is_test_symbol(relative_path, symbol):
    path = Path(relative_path)
    is_test_file = (
        "tests" in path.parts
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
    )
    return is_test_file and (
        symbol["name"].startswith("test_")
        or (symbol["kind"] == "class" and symbol["name"].startswith("Test"))
    )


def build_reverse_graph(calls):
    reverse_graph = {}

    for call in calls:
        check_deadline()
        caller = call.get("caller_id", call.get("caller"))
        if "callee_id" in call:
            callee = call["callee_id"]
        else:
            callee = call.get("callee")

        if caller is not None and callee is not None:
            reverse_graph.setdefault(callee, []).append(caller)

    return reverse_graph


def find_affected_functions(changed_function, graph):
    affected = []
    to_visit = [changed_function]
    visited = {changed_function}

    while to_visit:
        check_deadline()
        current = to_visit.pop()

        for caller in graph.get(current, []):
            if caller not in visited:
                visited.add(caller)
                affected.append(caller)
                to_visit.append(caller)

    return affected


def find_impact_paths(changed_function, graph):
    paths = []

    def visit(current_function, current_path):
        check_deadline()
        callers = graph.get(current_function, [])

        if not callers:
            paths.append(current_path)
            return

        for caller in callers:
            if caller in current_path:
                paths.append(current_path + [f"{caller} (cycle)"])
            else:
                visit(caller, current_path + [caller])

    visit(changed_function, [changed_function])
    return paths


def find_python_files(root):
    root = Path(root).resolve()

    for path in sorted(root.rglob("*.py")):
        if not any(part in EXCLUDED_DIRS for part in path.parts):
            yield path


def module_name(relative_path):
    name = relative_path[:-3].replace("/", ".")
    if name == "__init__":
        return ""
    return name[:-9] if name.endswith(".__init__") else name


def resolve_import_module(imported_module, current_module):
    if not imported_module.startswith("."):
        return imported_module

    level = len(imported_module) - len(imported_module.lstrip("."))
    remainder = imported_module[level:]
    current_parts = current_module.split(".") if current_module else []
    package_parts = current_parts[:-1]
    if level > 1:
        package_parts = package_parts[: -(level - 1)]

    parts = package_parts + ([remainder] if remainder else [])
    return ".".join(part for part in parts if part)


def _resolve_files(files):
    functions_by_file_and_qualname = {}
    for file in files:
        check_deadline()
        for function in file["functions"]:
            key = (function["path"], function["qualname"])
            functions_by_file_and_qualname.setdefault(key, []).append(function["id"])

    functions_by_module_and_name = {}
    for file in files:
        check_deadline()
        for function in file["functions"]:
            if function["name"] != function["qualname"]:
                continue
            key = (file["module"], function["name"])
            functions_by_module_and_name.setdefault(key, []).append(function["id"])

    for file in files:
        check_deadline()
        imports_by_local_name = {
            item["local_name"]: item for item in file["imports"]
        }

        for call in file["calls"]:
            local_ids = functions_by_file_and_qualname.get(
                (call["path"], call["callee"])
            )

            if local_ids and len(local_ids) == 1:
                call["callee_id"] = local_ids[0]
                call["resolution"] = "local"
            elif local_ids:
                call["callee_id"] = None
                call["resolution"] = "ambiguous"
            else:
                parts = call["callee"].split(".")
                binding = imports_by_local_name.get(parts[0])
                target_module = None
                target_name = None

                if len(parts) == 1 and binding and binding["name"]:
                    target_module = binding["resolved_module"]
                    target_name = binding["name"]
                elif len(parts) == 2 and binding and binding["name"] is None:
                    target_module = binding["resolved_module"]
                    target_name = parts[1]

                candidates = functions_by_module_and_name.get(
                    (target_module, target_name), []
                )
                if len(candidates) == 1:
                    call["callee_id"] = candidates[0]
                    call["resolution"] = "import"
                else:
                    call["callee_id"] = None
                    call["resolution"] = "ambiguous" if candidates else "unresolved"

    return files


def analyze_sources(source_by_path):
    files = []
    errors = []

    for relative_path in sorted(source_by_path):
        check_deadline()
        try:
            source = decode_python_source(source_by_path[relative_path])
            symbols = extract_symbols(source)
            functions = [
                symbol
                for symbol in symbols
                if symbol["kind"] in {"function", "async_function"}
            ]
            calls = extract_calls(source)
            imports = extract_imports(source)
            routes = extract_routes(source)
        except (SyntaxError, UnicodeDecodeError) as error:
            errors.append({"path": relative_path, "error": str(error)})
            continue

        for symbol in symbols:
            symbol["path"] = relative_path
            symbol["id"] = f"{relative_path}::{symbol['qualname']}"
        for call in calls:
            call["path"] = relative_path
            call["caller_id"] = (
                f"{relative_path}::{call['caller']}"
                if call["caller"] is not None
                else None
            )
        for item in imports:
            item["resolved_module"] = resolve_import_module(
                item["module"], module_name(relative_path)
            )
        for route in routes:
            route["id"] = f"{relative_path}::{route['qualname']}"

        tests = [
            {
                "id": f"{relative_path}::{symbol['qualname']}",
                "path": relative_path,
                "qualname": symbol["qualname"],
            }
            for symbol in symbols
            if is_test_symbol(relative_path, symbol)
        ]

        files.append(
            {
                "path": relative_path,
                "module": module_name(relative_path),
                "symbols": symbols,
                "functions": functions,
                "calls": calls,
                "imports": imports,
                "routes": routes,
                "tests": tests,
            }
        )

    return {"files": _resolve_files(files), "errors": errors}


def analyze_repository(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    sources = {}
    errors = []
    for path in find_python_files(root):
        check_deadline()
        relative_path = path.relative_to(root).as_posix()
        try:
            sources[relative_path] = path.read_bytes()
        except (OSError, UnicodeDecodeError) as error:
            errors.append({"path": relative_path, "error": str(error)})

    report = analyze_sources(sources)
    report["errors"] = errors + report["errors"]
    return report
