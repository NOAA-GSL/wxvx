from textwrap import dedent

from pytest import mark, raises

from wxvx import metconf

config = {
    "fcst": {
        "field": [{"cat_thresh": [">=20", ">=30", ">=40"], "level": ["(0,0,*,*)"], "name": "T2M"}]
    },
    "mask": {"poly": ["a.nc"]},
    "model": "GraphHRRR",
    "nbrhd": {"shape": "CIRCLE", "width": [3, 5, 11]},
    "nc_pairs_flag": "FALSE",
    "obs": {"field": [{"cat_thresh": [">=20", ">=30", ">=40"], "level": ["Z2"], "name": "TMP"}]},
    "obtype": "HRRR",
    "output_flag": {"cnt": "BOTH"},
    "output_prefix": "foo_bar",
    "regrid": {"to_grid": "FCST"},
    "tmp_dir": "/path/to/dir",
}

expected = """
fcst = {
  field = [
    {
      cat_thresh = [
        >=20,
        >=30,
        >=40
      ];
      level = [
        "(0,0,*,*)"
      ];
      name = "T2M";
    }
  ];
}
mask = {
  poly = [
    "a.nc"
  ];
}
model = "GraphHRRR";
nbrhd = {
  shape = CIRCLE;
  width = [
    3,
    5,
    11
  ];
}
nc_pairs_flag = FALSE;
obs = {
  field = [
    {
      cat_thresh = [
        >=20,
        >=30,
        >=40
      ];
      level = [
        "Z2"
      ];
      name = "TMP";
    }
  ];
}
obtype = "HRRR";
output_flag = {
  cnt = BOTH;
}
output_prefix = "foo_bar";
regrid = {
  to_grid = FCST;
}
tmp_dir = "/path/to/dir";
"""


# Generic:


@mark.parametrize("v", ["foo", 42])
def test_metconf__bare(v):
    assert metconf._bare(v=v) == str(v)


def test_metconf__collect():
    f = lambda k, v, level: ["%s%s = %s" % ("  " * level, k, v)]
    expected = ["    1 = one", "    2 = two"]
    assert metconf._collect(f=f, d={"2": "two", "1": "one"}, level=2) == expected


def test_metconf__fail():
    key = "foo"
    msg = f"Unsupported key: {key}"
    with raises(ValueError, match=msg) as e:
        metconf._fail(k=key)
    assert str(e.value) == msg


def test_metconf__indent():
    assert metconf._indent(v="foo", level=2) == "    foo"


def test_metconf__kvpair():
    assert metconf._kvpair(k="1", v="one", level=2) == ["    1 = one;"]


def test_metconf__key_val_map_list():
    text = """
    maplist = [
      {
        key = "1";
        val = "one";
      },
      {
        key = "2";
        val = "two";
      }
    ];
    """
    expected = dedent(text).strip().split("\n")
    assert metconf._key_val_map_list(k="maplist", v={"1": "one", "2": "two"}, level=0) == expected


def test_metconf__mapping():
    expected = ["  m = {", '    1 = "one";', '    2 = "two";', "  }"]
    assert metconf._mapping(k="m", v=['    1 = "one";', '    2 = "two";'], level=1) == expected


@mark.parametrize("v", ["foo", 42])
def test_metconf__quoted(v):
    assert metconf._quoted(v=v) == f'"{v}"'


def test_metconf__sequence():
    text = """
    s = [
      FOO,
        BAR
    ];
    """
    expected = dedent(text).strip().split("\n")
    v = ["foo", "  bar"]
    handler = lambda x: x.upper()
    assert metconf._sequence(k="s", v=v, handler=handler, level=0) == expected


def test_metconf__sequence__blank():
    assert metconf._sequence(k="s", v=[], handler=lambda x: x, level=1) == ["  s = [];"]


# Item-specific:


def test_metconf__dataset_fail():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._dataset(k="foo", v=[], level=0)


@mark.skip()
def test_metconf__field_mapping():
    pass


def test_metconf__field_mapping_kvpairs():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._field_mapping_kvpairs(k="foo", v=None, level=0)


@mark.skip()
def test_metconf__field_sequence():
    pass


@mark.skip()
def test_metconf__interp():
    pass


def test_metconf__mask():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._mask(k="foo", v=[], level=0)


def test_metconf__nbrhd():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._nbrhd(k="foo", v=None, level=0)


@mark.skip()
def test_metconf__obs_window():
    pass


def test_metconf__output_flag():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._output_flag(k="foo", v="bar", level=0)


def test_metconf__regrid():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._regrid(k="foo", v="bar", level=0)


@mark.skip()
def test_metconf__time_summary():
    pass


def test_metconf__top():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._top(k="foo", v=None, level=0)


@mark.skip()
def test_metconf__type():
    pass


# API:


def test_metconf_render():
    assert metconf.render(config=config).strip() == expected.strip()


def test_metconf_render_fail():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf.render(config={"foo": "bar"})
