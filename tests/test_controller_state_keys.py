"""Every controller-state key the integration reads has a writer.

Keys are declared once: ``StateKey[T]`` constants (or containers of them), key
families (functions returning a key) and base-less classes whose fields are all
keys. An entity description that carries a key is not a key family.
This test resolves each reference to its declaration and fails when a
declaration is read but never written. A write calls a key with its value
(``KEY(value)``) or passes the key to ``forward_controller_state_update``,
``handle_controller_state_update`` or ``sided_updates``.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
CORE = "adjustable_bed.controller_state"
WRITERS = frozenset(
    {"forward_controller_state_update", "handle_controller_state_update", "sided_updates"}
)

type Symbol = tuple[str, str]


def _mentions_state_key(node: ast.AST | None) -> bool:
    return node is not None and any(
        isinstance(n, ast.Name) and n.id == "StateKey" for n in ast.walk(node)
    )


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


@dataclass
class _Module:
    name: str
    tree: ast.Module
    # Key families: functions returning a key and classes holding only keys.
    families: set[str] = field(default_factory=set)
    # Module-level key constants and containers, with the names they hold.
    constants: dict[str, ast.expr] = field(default_factory=dict)
    imports: dict[str, Symbol] = field(default_factory=dict)


def _load() -> dict[str, _Module]:
    modules: dict[str, _Module] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        name = ".".join(path.relative_to(PACKAGE.parent).with_suffix("").parts)
        modules[name] = _Module(name, ast.parse(path.read_text()))
    for module in modules.values():
        package = module.name.rsplit(".", 1)[0].split(".")
        for node in ast.walk(module.tree):
            if isinstance(node, ast.FunctionDef) and _mentions_state_key(node.returns):
                module.families.add(node.name)
            elif isinstance(node, ast.ClassDef):
                fields = [item for item in node.body if isinstance(item, ast.AnnAssign)]
                if (
                    fields
                    and not node.bases
                    and all(_mentions_state_key(item.annotation) for item in fields)
                ):
                    module.families.add(node.name)
            elif isinstance(node, ast.ImportFrom) and node.level:
                base = package[: len(package) - node.level + 1]
                source = ".".join([*base, *(node.module.split(".") if node.module else [])])
                for alias in node.names:
                    module.imports[alias.asname or alias.name] = (source, alias.name)
        for node in module.tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                target, value, annotation = node.targets[0], node.value, None
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.value is not None
            ):
                target, value, annotation = node.target, node.value, node.annotation
            else:
                continue
            if (
                _mentions_state_key(value)
                or _mentions_state_key(annotation)
                or any(
                    (isinstance(n, ast.Name) and n.id in module.families)
                    or (isinstance(n, ast.Call) and _call_name(n) in module.families)
                    for n in ast.walk(value)
                )
            ):
                module.constants[target.id] = value
    return modules


class _Resolver:
    def __init__(self, modules: dict[str, _Module]) -> None:
        self.modules = modules

    def symbol(self, module: _Module, name: str) -> Symbol | None:
        """The declaration a module-level name refers to, through imports."""
        current: Symbol | None = (module.name, name)
        for _ in range(5):
            if current is None or (owner := self.modules.get(current[0])) is None:
                return None
            if current[1] in owner.families or current[1] in owner.constants:
                return current
            current = owner.imports.get(current[1])
        return None

    def is_family(self, symbol: Symbol) -> bool:
        return symbol[1] in self.modules[symbol[0]].families

    def roots(self, module: _Module, node: ast.expr, local: dict[str, set[Symbol]]) -> set[Symbol]:
        """Declarations a key expression comes from."""
        match node:
            case ast.Name(id=name):
                if name in local:
                    return local[name]
                symbol = self.symbol(module, name)
                return {symbol} if symbol else set()
            case ast.Attribute(value=ast.Name(id="self" | "cls"), attr=attr):
                symbol = self.symbol(module, attr)
                return {symbol} if symbol else set()
            case ast.Attribute(value=value) | ast.Subscript(value=value):
                return self.roots(module, value, local)
            case ast.IfExp(body=body, orelse=orelse):
                return self.roots(module, body, local) | self.roots(module, orelse, local)
            case ast.NamedExpr(value=value):
                return self.roots(module, value, local)
            case ast.Call(func=func, args=args):
                # A family keeps the identity of a key it derives from, e.g. ``sided``.
                derived = (self.roots(module, arg, local) for arg in args)
                return self.roots(module, func, local).union(*derived)
        return set()

    def members(self, symbol: Symbol) -> set[Symbol]:
        """``symbol`` and the declarations a container constant holds."""
        found = {symbol}
        module = self.modules[symbol[0]]
        if (value := module.constants.get(symbol[1])) is not None:
            for node in ast.walk(value):
                if isinstance(node, ast.Name) and (
                    (held := self.symbol(module, node.id)) and held != symbol
                ):
                    found |= self.members(held)
        return found


def _scopes(tree: ast.Module) -> Iterator[ast.AST]:
    yield tree
    yield from (
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
    )


def _aliases(resolver: _Resolver, module: _Module, scope: ast.AST) -> dict[str, set[Symbol]]:
    """Local names bound to key expressions."""
    local: dict[str, set[Symbol]] = {}
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
            target, value = node.target, node.value
        elif isinstance(node, (ast.For, ast.comprehension)):
            target, value = node.target, node.iter
        else:
            continue
        if isinstance(target, ast.Name) and (roots := resolver.roots(module, value, local)):
            local.setdefault(target.id, set()).update(roots)
    return local


def _usage() -> tuple[dict[Symbol, set[str]], set[Symbol]]:
    """Read declarations with their reading modules, and written declarations."""
    resolver = _Resolver(_load())
    reads: dict[Symbol, set[str]] = {}
    writes: set[Symbol] = set()
    for module in resolver.modules.values():
        for scope in _scopes(module.tree):
            local = _aliases(resolver, module, scope)
            for node in ast.walk(scope):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    for symbol in resolver.roots(module, node, local):
                        reads.setdefault(symbol, set()).add(module.name)
                if not isinstance(node, ast.Call) or not (node.args or node.keywords):
                    continue
                if _call_name(node) in WRITERS:
                    written = resolver.roots(module, node.args[0], local)
                else:
                    written = resolver.roots(module, node.func, local)
                    # A family call builds a key; calling the built key writes it.
                    if isinstance(node.func, (ast.Name, ast.Attribute)) and any(
                        resolver.is_family(symbol)
                        for symbol in resolver.roots(module, node.func, {})
                    ):
                        written = set()
                for symbol in written:
                    writes |= resolver.members(symbol)
    return reads, writes


def test_every_read_state_key_has_a_writer() -> None:
    reads, writes = _usage()
    assert writes, "No controller-state writes found"
    resolver = _Resolver(_load())
    # A key built from a family is written through that family.
    unwritten = {
        f"{module}.{name}": sorted(readers)
        for (module, name), readers in reads.items()
        if module != CORE and not resolver.members((module, name)) & writes
    }
    assert unwritten == {}


def test_massage_entities_read_published_keys() -> None:
    """The massage number, timer select and sensors read keys controllers write."""
    reads, writes = _usage()
    readers = {
        ("adjustable_bed.state_keys", "massage_intensity"): {
            "adjustable_bed.number",
            "adjustable_bed.sensor",
        },
        ("adjustable_bed.state_keys", "MASSAGE_TIMER_MINUTES"): {
            "adjustable_bed.select",
            "adjustable_bed.sensor",
        },
    }
    for symbol, platforms in readers.items():
        assert platforms <= reads[symbol]
        assert symbol in writes


def test_state_is_never_read_by_a_raw_name() -> None:
    raw = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            target = None
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
            ):
                owner, target = node.func.value, node.args[0]
            elif isinstance(node, ast.Subscript):
                owner, target = node.value, node.slice
            else:
                continue
            if (
                isinstance(owner, ast.Attribute)
                and owner.attr == "controller_state"
                and isinstance(target, (ast.Constant, ast.JoinedStr))
            ):
                raw.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
    assert raw == []
