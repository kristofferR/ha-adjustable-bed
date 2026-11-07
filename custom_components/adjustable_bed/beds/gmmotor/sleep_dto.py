"""Typed evaluation of the GM Control sleep module's source DTO field layouts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from .notifications import Value
from .protocol import MalformedNotification

type Path = tuple[str | int, ...]


def _paths(tree: Value) -> Iterator[Path]:
    if isinstance(tree, dict):
        if "from" in tree:
            path = tree["from"]
            if not isinstance(path, list) or any(type(k) not in (str, int) for k in path):
                raise ValueError("Invalid generated field path")
            yield tuple(k for k in path if isinstance(k, (str, int)))
        else:
            for value in tree.values():
                yield from _paths(value)
    elif isinstance(tree, list):
        for value in tree:
            yield from _paths(value)


def _at(root: Value, path: Path, indices: Mapping[Path, int]) -> Value:
    value = root
    prefix: Path = ()
    for original in path:
        key = indices.get(prefix, original) if isinstance(original, int) else original
        if value is None:
            return None
        if isinstance(key, int):
            if not isinstance(value, list) or not 0 <= key < len(value):
                raise MalformedNotification("Sleep DTO array lacks a required member")
            value = value[key]
        else:
            if not isinstance(value, dict):
                raise MalformedNotification("Sleep DTO expects a JSON object")
            value = value.get(key)
        prefix += (original,)
    return value


def _render(tree: Value, root: Value, indices: Mapping[Path, int]) -> Value:
    if isinstance(tree, list):
        if not tree:
            return []
        prefixes = []
        for path in _paths(tree[0]):
            prefix = next(
                (
                    path[:i]
                    for i, k in enumerate(path)
                    if isinstance(k, int) and path[:i] not in indices
                ),
                None,
            )
            if prefix is not None:
                prefixes.append(prefix)
        if prefixes:
            prefix = min(prefixes, key=len)
            values = _at(root, prefix, indices)
            if values is None:
                return None
            if not isinstance(values, list):
                raise MalformedNotification("Sleep DTO expects a JSON array")
            return [_render(tree[0], root, {**indices, prefix: i}) for i in range(len(values))]
        return [_render(value, root, indices) for value in tree]
    if isinstance(tree, dict):
        if "from" in tree:
            path = next(_paths(tree))
            value = _at(root, path, indices)
            if value is None:
                return None
            kind = tree["cast"]
            if kind == "string":
                if not isinstance(value, str):
                    raise MalformedNotification("Sleep DTO expects a string")
                return value
            if type(value) not in (int, float):
                raise MalformedNotification("Sleep DTO expects a number")
            if not isinstance(value, (int, float)):
                raise MalformedNotification("Invalid sleep numeric value")
            return int(value) if kind == "int" else float(value) if kind == "double" else value
        return {key: _render(value, root, indices) for key, value in tree.items()}
    return tree


def parse(address: str, value: dict[str, Value]) -> Value:
    """Apply exact default/null branches, then render every nested source field.

    Invalid-type failures are HA validation errors; this is not a claim that
    Python exceptions reproduce the Dart runtime's malformed-type exceptions.
    """
    from .sleep_layouts import LAYOUTS, NULL_BRANCHES

    model = LAYOUTS[address]
    if not isinstance(model, dict) or not isinstance(model.get("fields"), dict):
        raise ValueError("Invalid generated sleep DTO model")
    fields = model["fields"]
    assert isinstance(fields, dict)
    fields = dict(fields)
    for (entry, key), branch in NULL_BRANCHES.items():
        if entry != address or value.get(key) is not None:
            continue
        if branch is None:
            raise MalformedNotification("Sleep response lacks a required non-null map")
        if not isinstance(branch, dict):
            raise ValueError("Invalid generated sleep DTO null branch")
        defaults = branch
        for offset, subtree in fields.items():
            if offset in defaults and any(path and path[0] == key for path in _paths(subtree)):
                fields[offset] = defaults[offset]
    return _render({"class": model["class"], "fields": fields}, value, {})
