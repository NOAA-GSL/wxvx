from typing import Any, Callable, NoReturn

# Generic:


def _bare(v: str) -> str:
    return f"{v}"


def _collect(f: Callable, d: dict, level: int) -> list[str]:
    lines = []
    for k, v in sorted(d.items()):
        lines.extend(f(k, v, level))
    return lines


def _fail(k: str) -> NoReturn:
    msg = f"Unsupported key: {k}"
    raise ValueError(msg)


def _indent(v: str, level: int) -> str:
    return "  " * level + v


def _kvpair(k: str, v: str, level: int) -> list[str]:
    return [_indent(f"{k} = {v};", level)]


def _mapping(k: str, v: list[str], level: int) -> list[str]:
    return [_indent("%s = {" % k, level), *v, _indent("}", level)]


def _quoted(v: str) -> str:
    return f'"{v}"'


def _sequence(k: str, v: list, handler: Callable, level: int) -> list[str]:
    if v:
        return [
            _indent(f"{k} = [", level),
            *",\n".join([_indent(handler(x), level + 1) for x in v]).split("\n"),
            _indent("];", level),
        ]
    return [_indent(f"{k} = [];", level)]


# Item-specific:


def _dataset(k: str, v: list[dict], level: int) -> list[str]:
    match k:
        case "field":
            return _field_sequence(k, v, level)
    _fail(k)


def _field_mapping(d: dict, level: int) -> str:
    lines = [
        _indent("{", level),
        *_collect(_field_mapping_kvpairs, d, level + 1),
        _indent("}", level),
    ]
    return "\n".join(lines)


def _field_mapping_kvpairs(k: str, v: Any, level: int) -> list[str]:
    match k:
        # Scalar: quoted.
        case "name" | "set_attr_level":
            return _kvpair(k, _quoted(v), level)
        # Sequence: bare.
        case "cat_thresh" | "cnt_thresh":
            return _sequence(k, v, _bare, level)
        # Sequence: quoted.
        case "level":
            return _sequence(k, v, _quoted, level)
    _fail(k)


def _field_sequence(k: str, v: list[dict], level: int) -> list[str]:
    mappings = ",\n".join([_field_mapping(d, level + 1) for d in v]).split("\n")
    return [_indent("%s = [" % k, level), *mappings, _indent("];", level)]


def _mask(k: str, v: list, level: int) -> list[str]:
    match k:
        case "grid" | "poly":
            return _sequence(k, v, _quoted, level)
    _fail(k)


def _nbrhd(k: str, v: Any, level: int) -> list[str]:
    match k:
        case "shape":
            return _kvpair(k, _bare(v), level)
        case "width":
            return _sequence(k, v, _bare, level)
    _fail(k)


def _output_flag(k: str, v: str, level: int) -> list[str]:
    match k:
        case "cnt" | "cts" | "nbrcnt":
            return _kvpair(k, _bare(v), level)
    _fail(k)


def _regrid(k: str, v: Any, level: int) -> list[str]:
    match k:
        case "method":
            return _kvpair(k, _bare(v), level)
        case "to_grid":
            return _kvpair(k, _bare(v), level)
    _fail(k)


def _top(k: str, v: Any, level: int) -> list[str]:
    match k:
        # Dictionary: datasets.
        case "fcst" | "obs":
            return _mapping(k, _collect(_dataset, v, level + 1), level)
        # Dictionary: mask.
        case "mask":
            return _mapping(k, _collect(_mask, v, level + 1), level)
        # Dictionary: nbrhd.
        case "nbrhd":
            return _mapping(k, _collect(_nbrhd, v, level + 1), level)
        # Dictionary: output_flag.
        case "output_flag":
            return _mapping(k, _collect(_output_flag, v, level + 1), level)
        # Dictionary: regrid.
        case "regrid":
            return _mapping(k, _collect(_regrid, v, level + 1), level)
        # Scalar: quoted.
        case "model" | "obtype" | "output_prefix" | "tmp_dir":
            return _kvpair(k, _quoted(v), level)
        # Scalar: bare.
        case "nc_pairs_flag":
            return _kvpair(k, _bare(v), level)
    _fail(k)


# API:


def render(config: dict) -> str:
    return "\n".join(_collect(_top, config, 0))
