from pytest import raises

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


def test_metconf__dataset_fail():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._dataset(k="foo", v=[], level=0)


def test_metconf__field_mapping_kvpairs():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._field_mapping_kvpairs(k="foo", v=None, level=0)


def test_metconf__mask():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._mask(k="foo", v=[], level=0)


def test_metconf__nbrhd():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._nbrhd(k="foo", v=None, level=0)


def test_metconf__output_flag():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._output_flag(k="foo", v="bar", level=0)


def test_metconf__regrid():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._regrid(k="foo", v="bar", level=0)


def test_metconf__top():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._top(k="foo", v=None, level=0)


def test_metconf_render():
    assert metconf.render(config=config).strip() == expected.strip()


def test_metconf_render_fail():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf.render(config={"foo": "bar"})
