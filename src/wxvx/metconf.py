from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

from wxvx.strings import MET
from wxvx.types import ToGridVal

if TYPE_CHECKING:
    from collections.abc import Callable


# Public:


def render(config: dict) -> str:
    return "\n".join(_collect(_top, config, 0))


# Private:


def _bare(v: Any) -> str:
    return str(v)


def _collect(f: Callable, d: dict, level: int) -> list[str]:
    lines = []
    for k, v in sorted(d.items()):
        lines.extend(f(k, v, level))
    return lines


def _dataset(k: str, v: list[dict], level: int) -> list[str]:
    match k:
        # Sequence: custom.
        case "field":
            return _field_sequence(k, v, level)
    return _fail(k)


def _fail(k: str) -> NoReturn:
    msg = f"Unsupported key: {k}"
    raise ValueError(msg)


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
    return _fail(k)


def _field_sequence(k: str, v: list[dict], level: int) -> list[str]:
    mappings = ",\n".join([_field_mapping(d, level + 1) for d in v]).split("\n")
    return [_indent("%s = [" % k, level), *mappings, _indent("];", level)]


def _indent(v: str, level: int) -> str:
    return "  " * level + v


def _interp(k: str, v: Any, level: int) -> list[str]:
    match k:
        # Key-Value Pair: bare.
        case "shape" | "vld_thresh":
            return _kvpair(k, _bare(v), level)
        # Mapping: custom.
        case "type":
            return _mapping(k, _collect(_type, v, level + 1), level)
    return _fail(k)


def _key_val_map_list(k: str, v: dict[str, str], level: int) -> list[str]:
    lines = [_indent(f"{k} = [", level)]
    for key, val in sorted(v.items()):
        block = [
            _indent("{", level + 1),
            *_kvpair("key", _quoted(key), level + 2),
            *_kvpair("val", _quoted(val), level + 2),
            _indent("},", level + 1),
        ]
        lines.extend(block)
    lines[-1] = lines[-1].rstrip(",")
    lines.append(_indent("];", level))
    return lines


def _kvpair(k: str, v: str, level: int) -> list[str]:
    return [_indent(f"{k} = {v};", level)]


def _mapping(k: str, v: list[str], level: int) -> list[str]:
    return [_indent("%s = {" % k, level), *v, _indent("}", level)]


def _mask(k: str, v: list[str] | str, level: int) -> list[str]:
    # An inconsistency uncharacteristic of MET: The pb2nc 'mask' setting is formatted differently
    # than for grid_stat and point_stat. For pb2nc, the format is
    #   mask = { grid = ""; poly = ""; }
    # with 'grid' and 'poly' as single strings, while for grid/point_stat it's
    #   mask = { grid = [""]; poly = [""]; }
    # with 'grid' and 'poly' as string sequences.
    match k:
        case "grid" | "poly":
            if isinstance(v, list):
                # Sequence: quoted.
                return _sequence(k, v, _quoted, level)
            # Key-Value Pair: quoted.
            return _kvpair(k, _quoted(v), level)
    return _fail(k)


def _nbrhd(k: str, v: Any, level: int) -> list[str]:
    match k:
        # Key-Value Pair: bare.
        case "shape":
            return _kvpair(k, _bare(v), level)
        # Sequence: bare.
        case "width":
            return _sequence(k, v, _bare, level)
    return _fail(k)


def _obs_window(k: str, v: Any, level: int) -> list[str]:
    match k:
        # Key-Value Pair: bare.
        case "beg" | "end":
            return _kvpair(k, _bare(v), level)
    return _fail(k)


def _output_flag(k: str, v: str, level: int) -> list[str]:
    match k:
        # Key-Value Pair: bare.
        case MET.cnt | MET.cts | MET.nbrcnt:
            return _kvpair(k, _bare(v), level)
    return _fail(k)


def _quoted(v: str) -> str:
    return f'"{v}"'


def _regrid(k: str, v: Any, level: int) -> list[str]:
    match k:
        # Scalar: bare.
        case "method" | "width":
            return _kvpair(k, _bare(v), level)
        # Scalar: custom.
        case "to_grid":
            f = _bare if v in [x.name for x in ToGridVal] else _quoted
            return _kvpair(k, f(v), level)
    return _fail(k)


def _sequence(k: str, v: list, handler: Callable, level: int) -> list[str]:
    if v:
        return [
            _indent(f"{k} = [", level),
            *",\n".join([_indent(handler(x), level + 1) for x in v]).split("\n"),
            _indent("];", level),
        ]
    return [_indent(f"{k} = [];", level)]


def _time_summary(k: str, v: Any, level: int) -> list[str]:
    match k:
        # Scalar: bare.
        case "step" | "width":
            return _kvpair(k, _bare(v), level)
        # Sequence: quoted.
        case "obs_var" | "type":
            return _sequence(k, v, _quoted, level)
    return _fail(k)


def _top(k: str, v: Any, level: int) -> list[str]:
    match k:
        # Mapping: custom.
        case "fcst":
            return _mapping(k, _collect(_dataset, v, level + 1), level)
        case "interp":
            return _mapping(k, _collect(_interp, v, level + 1), level)
        case "mask":
            return _mapping(k, _collect(_mask, v, level + 1), level)
        case "nbrhd":
            return _mapping(k, _collect(_nbrhd, v, level + 1), level)
        case "obs":
            return _mapping(k, _collect(_dataset, v, level + 1), level)
        case "obs_window":
            return _mapping(k, _collect(_obs_window, v, level + 1), level)
        case "output_flag":
            return _mapping(k, _collect(_output_flag, v, level + 1), level)
        case "regrid":
            return _mapping(k, _collect(_regrid, v, level + 1), level)
        case "time_summary":
            return _mapping(k, _collect(_time_summary, v, level + 1), level)
        # Scalar: bare.
        case "nc_pairs_flag" | "quality_mark_thresh":
            return _kvpair(k, _bare(v), level)
        # Scalar: quoted.
        case "model" | "obtype" | "output_prefix" | "tmp_dir":
            return _kvpair(k, _quoted(v), level)
        # Sequence: quoted.
        case "message_type" | "obs_bufr_var":
            return _sequence(k, v, _quoted, level)
        # Sequence: list of single key-val dictionaries.
        case "message_type_group_map" | "obs_bufr_map":
            return _key_val_map_list(k, v, level)
    return _fail(k)


def _type(k: str, v: Any, level: int) -> list[str]:
    match k:
        # Key-Value Pair: bare.
        case "method" | "width":
            return _kvpair(k, _bare(v), level)
    return _fail(k)
