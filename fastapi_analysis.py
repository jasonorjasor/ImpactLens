"""Static FastAPI declarations; analyzed applications are never imported."""

import ast

from request_budget import check_deadline


METHODS = {"delete", "get", "head", "options", "patch", "post", "put", "websocket"}


def _name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _keyword(call, name):
    return next((item.value for item in call.keywords if item.arg == name), None)


def _literal(node, default=""):
    if node is None:
        return default
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class ModuleWrites(ast.NodeVisitor):
    def __init__(self):
        self.names = []

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.append(node.id)

    def visit_FunctionDef(self, node):
        self.names.append(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_Lambda(self, node):
        pass

    def visit_Import(self, node):
        self.names.extend(alias.asname or alias.name.split(".")[0] for alias in node.names)

    def visit_ImportFrom(self, node):
        self.names.extend(alias.asname or alias.name for alias in node.names)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.names.append(node.name)
        self.generic_visit(node)


def _bindings(tree, module):
    bindings = {}
    for statement in tree.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                local = alias.asname or alias.name.split(".")[0]
                bindings.setdefault(local, []).append(alias.name if alias.asname else local)
        elif isinstance(statement, ast.ImportFrom):
            imported = statement.module or ""
            if statement.level:
                package = module.split(".")[:-statement.level]
                imported = ".".join(package + ([imported] if imported else []))
            for alias in statement.names:
                bindings.setdefault(alias.asname or alias.name, []).append(f"{imported}.{alias.name}")
        else:
            # A reassigned import is not evidence of framework identity.
            writes = ModuleWrites()
            writes.visit(statement)
            for name in writes.names:
                bindings.setdefault(name, []).append(None)
    return {name: values[0] for name, values in bindings.items() if len(values) == 1}


def _qualified(node, bindings):
    name = _name(node)
    if not name:
        return None
    root, *rest = name.split(".")
    target = bindings.get(root)
    return ".".join([target, *rest]) if target else None


def declarations(tree, module, path):
    bindings = _bindings(tree, module)
    facts = {"bindings": bindings, "objects": {}, "routes": [], "includes": [], "dependencies": [], "warnings": []}
    facts["function_names"] = {
        statement.name for statement in tree.body
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) and statement.name in bindings
    }

    def warn(node, message):
        item = {"path": path, "line": node.lineno, "message": message}
        if item not in facts["warnings"]:
            facts["warnings"].append(item)

    def dependency(node, caller):
        if not isinstance(node, ast.Call) or _qualified(node.func, bindings) != "fastapi.Depends":
            return False
        target = node.args[0] if len(node.args) == 1 else _keyword(node, "dependency") if not node.args else None
        if target is None or _name(target) is None or any(item.arg is None for item in node.keywords):
            warn(node, "A FastAPI dependency could not be resolved: use an explicit function name in Depends().")
        else:
            facts["dependencies"].append({
                "caller": caller, "callee": _name(target), "line": node.lineno,
                "line_end": node.end_lineno, "column": node.col_offset,
                "expression": ast.unparse(node), "relationship": "fastapi_dependency",
            })
        return True

    for statement in tree.body:
        check_deadline()
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
            name = statement.targets[0].id
            value = statement.value
            if isinstance(value, ast.Call):
                constructor = _qualified(value.func, bindings)
                if constructor in {"fastapi.FastAPI", "fastapi.APIRouter"}:
                    if name not in bindings:
                        warn(statement, "A reassigned FastAPI app or router was omitted from route registration analysis.")
                        continue
                    prefix = _literal(_keyword(value, "prefix")) if constructor.endswith("APIRouter") else ""
                    if prefix is not None and prefix and (not prefix.startswith("/") or prefix.endswith("/")):
                        prefix = None
                    if prefix is None or any(item.arg is None for item in value.keywords):
                        warn(value, "A FastAPI router has a dynamic or unsupported prefix/configuration; its full routes are unknown.")
                        prefix = None
                    facts["objects"][name] = {"kind": constructor.rsplit(".", 1)[1], "prefix": prefix}
                    if _keyword(value, "dependencies") is not None:
                        warn(value, "App- and router-level FastAPI dependencies are not traced yet; parameter dependencies are supported.")

    for statement in tree.body:
        check_deadline()
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in statement.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                method = decorator.func.attr.lower()
                if method not in METHODS:
                    continue
                owner = _name(decorator.func.value)
                if not owner:
                    continue
                route_path = _literal(decorator.args[0] if decorator.args else _keyword(decorator, "path"), default=None)
                facts["routes"].append({"qualname": statement.name, "method": method.upper(), "path": route_path, "owner": owner, "node": decorator})
            arguments = statement.args
            for default in [*arguments.defaults, *arguments.kw_defaults]:
                dependency(default, statement.name)
            for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]:
                annotation = argument.annotation
                if isinstance(annotation, ast.Subscript) and _qualified(annotation.value, bindings) in {"typing.Annotated", "typing_extensions.Annotated"}:
                    elements = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else []
                    for metadata in elements[1:]:
                        dependency(metadata, statement.name)
        elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            call = statement.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == "include_router":
                owner = _name(call.func.value)
                child = call.args[0] if len(call.args) == 1 else _keyword(call, "router") if not call.args else None
                prefix = _literal(_keyword(call, "prefix"))
                if prefix and (not prefix.startswith("/") or prefix.endswith("/")):
                    prefix = None
                facts["includes"].append({"owner": owner, "child": _name(child), "prefix": prefix, "node": call})
                if _keyword(call, "dependencies") is not None:
                    warn(call, "include_router dependencies are not traced yet; parameter dependencies are supported.")

    # Flag recognizable Depends declarations outside the supported parameter forms.
    handled = {(item["line"], item["column"]) for item in facts["dependencies"]}
    included = {id(item["node"]) for item in facts["includes"]}
    constructors = {id(statement.value) for statement in tree.body if isinstance(statement, ast.Assign)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _qualified(node.func, bindings) == "fastapi.Depends" and (node.lineno, node.col_offset) not in handled:
            warn(node, "This Depends() declaration is outside the supported explicit top-level function parameter forms.")
        if isinstance(node, ast.Call) and _qualified(node.func, bindings) in {"fastapi.FastAPI", "fastapi.APIRouter"} and id(node) not in constructors:
            warn(node, "FastAPI app/router construction outside a simple module-level assignment is not supported.")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "include_router" and id(node) not in included:
            child = node.args[0] if node.args else _keyword(node, "router")
            facts["includes"].append({"owner": _name(node.func.value), "child": _name(child), "prefix": None, "node": node})
    return facts


def apply_fastapi(files, facts_by_path):
    by_module = {}
    for file in files:
        by_module.setdefault(file["module"], []).append(file["path"])

    def object_ref(path, name):
        if not name:
            return None
        facts = facts_by_path[path]
        if name in facts["objects"]:
            return path, name
        root, *rest = name.split(".")
        binding = facts["bindings"].get(root)
        if not binding:
            return None
        qualified = ".".join([binding, *rest])
        module, _, attribute = qualified.rpartition(".")
        paths = by_module.get(module, [])
        if len(paths) == 1 and attribute in facts_by_path[paths[0]]["objects"]:
            return paths[0], attribute
        return None

    warnings = []

    def warn(path, node, message):
        item = {"path": path, "line": node.lineno, "message": message}
        if item not in warnings:
            warnings.append(item)

    mounts = {}
    blocked = set()
    for path, facts in facts_by_path.items():
        check_deadline()
        warnings.extend(facts["warnings"])
        for include in facts["includes"]:
            parent = object_ref(path, include["owner"])
            child = object_ref(path, include["child"])
            if parent is None:
                continue
            if child is None:
                warn(path, include["node"], "An included router could not be resolved; registered route coverage may be incomplete.")
                continue
            obj = facts_by_path[parent[0]]["objects"][parent[1]]
            if obj["kind"] != "FastAPI":
                blocked.add(child)
                warn(path, include["node"], "Nested router registration is not supported yet; these full routes are unknown.")
                continue
            child_obj = facts_by_path[child[0]]["objects"][child[1]]
            prefix = include["prefix"]
            if child_obj["kind"] != "APIRouter" or prefix is None or any(item.arg is None for item in include["node"].keywords):
                blocked.add(child)
                warn(path, include["node"], "A router registration has unsupported configuration; these full routes are unknown.")
                continue
            mounts.setdefault(child, []).append((prefix, path, include["node"].lineno))

    for file in files:
        path = file["path"]
        facts = facts_by_path[path]
        file["routes"] = []
        for route in facts["routes"]:
            check_deadline()
            owner = object_ref(path, route["owner"])
            if owner is None:
                continue
            obj = facts_by_path[owner[0]]["objects"][owner[1]]
            if _keyword(route["node"], "dependencies") is not None:
                warn(path, route["node"], "Decorator-level FastAPI dependencies are not traced yet; parameter dependencies are supported.")
            if route["path"] is None or obj["prefix"] is None:
                warn(path, route["node"], "A FastAPI route path or prefix is not a literal string; its full address was omitted.")
                continue
            if obj["kind"] == "FastAPI":
                registrations = [("", "registered")]
            else:
                registrations = []
                for prefix, mount_path, line in mounts.get(owner, []):
                    if path == mount_path and route["node"].lineno > line:
                        warn(path, route["node"], "A route declared after include_router was omitted from that registration.")
                    else:
                        registrations.append((prefix, "registered"))
                if not mounts.get(owner) and owner not in blocked:
                    registrations = [("", "declared")]
            for prefix, registration in registrations:
                item = {"id": f"{path}::{route['qualname']}", "qualname": route["qualname"], "method": route["method"], "path": prefix + obj["prefix"] + route["path"], "registration": registration}
                if item not in file["routes"]:
                    file["routes"].append(item)
        for call in file["calls"]:
            if call.get("relationship") != "fastapi_dependency":
                continue
            if call["callee_id"]:
                target_path, target_name = call["callee_id"].split("::", 1)
                root = call["callee"].split(".")[0]
                if root not in facts["bindings"] or target_name not in facts_by_path[target_path]["function_names"]:
                    call["callee_id"] = None
                    call["resolution"] = "unresolved"
            if call["callee_id"] is None:
                item = {"path": path, "line": call["line"], "message": f"FastAPI dependency {call['callee']} could not be matched to a unique Python function."}
                if item not in warnings:
                    warnings.append(item)
    return warnings
