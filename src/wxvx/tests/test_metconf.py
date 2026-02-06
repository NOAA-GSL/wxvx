from collections.abc import Callable

from pytest import mark, raises

from wxvx import metconf
from wxvx.strings import MET
from wxvx.types import ToGridVal

# Public


def test_metconf_render(tidy):
    config = {
        MET.fcst: {
            MET.field: [
                {
                    MET.cat_thresh: [
                        ">=20",
                        ">=30",
                    ],
                    MET.level: [
                        "(0,0,*,*)",
                    ],
                    MET.name: "T2M",
                }
            ]
        },
        MET.interp: {
            MET.shape: "SQUARE",
            MET.type: {
                MET.method: "BILIN",
                MET.width: 2,
            },
            MET.vld_thresh: 1.0,
        },
        MET.mask: {
            MET.poly: [
                "a.nc",
            ],
        },
        MET.message_type: [
            "AIRUPA",
        ],
        MET.message_type_group_map: {
            "AIRUPA": "ADPUPA,AIRCAR,AIRCFT",
        },
        MET.model: "GraphHRRR",
        MET.nbrhd: {
            MET.shape: "CIRCLE",
            MET.width: [
                3,
                5,
            ],
        },
        MET.nc_pairs_flag: {
            MET.climo: MET.FALSE,
            MET.raw: MET.FALSE,
        },
        MET.obs: {
            MET.field: [
                {
                    MET.cat_thresh: [
                        ">=20",
                        ">=30",
                    ],
                    MET.level: [
                        "Z2",
                    ],
                    MET.name: "TMP",
                },
            ]
        },
        MET.obs_bufr_var: [
            "D_RH",
            "QOB",
        ],
        MET.obs_window: {
            MET.beg: -1800,
            MET.end: 1800,
        },
        MET.obtype: "HRRR",
        MET.output_flag: {
            MET.cnt: "BOTH",
        },
        MET.output_prefix: "foo_bar",
        MET.regrid: {
            MET.to_grid: ToGridVal.FCST.name,
        },
        MET.time_summary: {
            MET.obs_var: [],
            MET.step: 3600,
            MET.type: [
                "min",
                "max",
            ],
            MET.width: 3600,
        },
        MET.tmp_dir: "/path/to/dir",
    }
    text = """
    fcst = {
      field = [
        {
          cat_thresh = [
            >=20,
            >=30
          ];
          level = [
            "(0,0,*,*)"
          ];
          name = "T2M";
        }
      ];
    }
    interp = {
      shape = SQUARE;
      type = {
        method = BILIN;
        width = 2;
      }
      vld_thresh = 1.0;
    }
    mask = {
      poly = [
        "a.nc"
      ];
    }
    message_type = [
      "AIRUPA"
    ];
    message_type_group_map = [
      {
        key = "AIRUPA";
        val = "ADPUPA,AIRCAR,AIRCFT";
      }
    ];
    model = "GraphHRRR";
    nbrhd = {
      shape = CIRCLE;
      width = [
        3,
        5
      ];
    }
    nc_pairs_flag = {
      climo = FALSE;
      raw = FALSE;
    }
    obs = {
      field = [
        {
          cat_thresh = [
            >=20,
            >=30
          ];
          level = [
            "Z2"
          ];
          name = "TMP";
        }
      ];
    }
    obs_bufr_var = [
      "D_RH",
      "QOB"
    ];
    obs_window = {
      beg = -1800;
      end = 1800;
    }
    obtype = "HRRR";
    output_flag = {
      cnt = BOTH;
    }
    output_prefix = "foo_bar";
    regrid = {
      to_grid = FCST;
    }
    time_summary = {
      obs_var = [];
      step = 3600;
      type = [
        "min",
        "max"
      ];
      width = 3600;
    }
    tmp_dir = "/path/to/dir";
    """
    expected = tidy(text)
    assert metconf.render(config=config).strip() == expected


def test_metconf_render__nc_pairs_flag_false():
    config = {MET.nc_pairs_flag: MET.FALSE}
    assert metconf.render(config=config) == "nc_pairs_flag = FALSE;"


def test_metconf_render__fail():
    _fail(metconf.render, config={"foo": "bar"})


# Private


@mark.parametrize("v", ["foo", 42])
def test_metconf__bare(v):
    assert metconf._bare(v=v) == str(v)


def test_metconf__collect():
    f = lambda k, v, level: ["%s%s = %s" % ("  " * level, k, v)]
    expected = ["    1 = one", "    2 = two"]
    assert metconf._collect(f=f, d={"2": "two", "1": "one"}, level=2) == expected


def test_metconf__dataset__fail():
    _fail(metconf._dataset)


def test_metconf__fail():
    key = "foo"
    msg = f"Unsupported key: {key}"
    with raises(ValueError, match=msg):
        metconf._fail(k=key)


def test_metconf__field_mapping(tidy):
    text = """
    {
      cnt_thresh = [
        1,
        2
      ];
      level = [
        "(0,0,*,*)"
      ];
      name = "foo";
    }
    """
    expected = tidy(text)
    assert (
        metconf._field_mapping(
            d={MET.name: "foo", MET.cnt_thresh: [1, 2], MET.level: ["(0,0,*,*)"]}, level=0
        )
        == expected
    )


def test_metconf__field_mapping_kvpairs():
    _fail(metconf._field_mapping_kvpairs)


def test_metconf__field_sequence(tidy):
    text = """
    field = [
      {
        cnt_thresh = [
          1,
          2
        ];
        level = [
          "(0,0,*,*)"
        ];
        name = "foo";
      },
      {
        cat_thresh = [
          3,
          4
        ];
        level = [
          "P1000"
        ];
        name = "bar";
      }
    ];
    """
    expected = tidy(text).split("\n")
    d1 = {MET.name: "foo", MET.cnt_thresh: [1, 2], MET.level: ["(0,0,*,*)"]}
    d2 = {MET.name: "bar", MET.cat_thresh: [3, 4], MET.level: ["P1000"]}
    assert metconf._field_sequence(k=MET.field, v=[d1, d2], level=0) == expected


def test_metconf__indent():
    assert metconf._indent(v="foo", level=2) == "    foo"


def test_metconf__interp__fail():
    _fail(metconf._interp)


@mark.parametrize(("k", "v"), [(MET.shape, MET.SQUARE), (MET.vld_thresh, 1.0)])
def test_metconf__interp__kvpair(k, v):
    assert metconf._interp(k=k, v=v, level=1) == [f"  {k} = {v};"]


def test_metconf__interp__type(tidy):
    text = """
    type = {
      method = BILIN;
      width = 2;
    }
    """
    expected = tidy(text).split("\n")
    assert metconf._interp(k=MET.type, v={MET.method: MET.BILIN, MET.width: 2}, level=0) == expected


def test_metconf__key_val_map_list(tidy):
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
    expected = tidy(text).split("\n")
    assert metconf._key_val_map_list(k="maplist", v={"1": "one", "2": "two"}, level=0) == expected


def test_metconf__kvpair():
    assert metconf._kvpair(k="1", v="one", level=2) == ["    1 = one;"]


def test_metconf__mapping():
    expected = ["  m = {", '    1 = "one";', '    2 = "two";', "  }"]
    assert metconf._mapping(k="m", v=['    1 = "one";', '    2 = "two";'], level=1) == expected


def test_metconf__mask_bad_key():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._mask(k="foo", v=[], level=0)


def test_metconf__mask__grid_list(tidy):
    text = """
    grid = [
      "G104"
    ];
    """
    expected = tidy(text).split("\n")
    assert metconf._mask(k=MET.grid, v=["G104"], level=0) == expected


def test_metconf__mask__grid_str():
    assert metconf._mask(k=MET.grid, v="G104", level=1) == ['  grid = "G104";']


def test_metconf__nbrhd():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._nbrhd(k="foo", v=None, level=0)


def test_metconf__nc_pairs_flag():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._nc_pairs_flag(k="foo", v=None, level=0)


@mark.parametrize(("k", "v"), [(MET.beg, -1800), (MET.end, 1800)])
def test_metconf__obs_window(k, v):
    assert metconf._obs_window(k=k, v=v, level=1) == [f"  {k} = {v};"]


def test_metconf__obs_window__fail():
    _fail(metconf._obs_window)


def test_metconf__output_flag():
    _fail(metconf._output_flag)


@mark.parametrize("v", ["foo", 42])
def test_metconf__quoted(v):
    assert metconf._quoted(v=v) == f'"{v}"'


def test_metconf__regrid():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._regrid(k="foo", v="bar", level=0)


def test_metconf__sequence(tidy):
    text = """
    s = [
      FOO,
        BAR
    ];
    """
    expected = tidy(text).split("\n")
    v = ["foo", "  bar"]
    handler = lambda x: x.upper()
    assert metconf._sequence(k="s", v=v, handler=handler, level=0) == expected


def test_metconf__sequence__blank():
    assert metconf._sequence(k="s", v=[], handler=lambda x: x, level=1) == ["  s = [];"]


def test_metconf__time_summary__fail():
    _fail(metconf._time_summary)


@mark.parametrize(("k", "v"), [(MET.step, 3600), (MET.width, 2)])
def test_metconf__time_summary__scalar(k, v):
    assert metconf._time_summary(k=k, v=v, level=1) == [f"  {k} = {v};"]


@mark.parametrize(("k", "v"), [(MET.obs_var, ["foo", "bar"]), (MET.type, ["min", "max"])])
def test_metconf__time_summary__sequence(k, tidy, v):
    text = f'''
    {k} = [
      "{v[0]}",
      "{v[1]}"
    ];
    '''  # noqa: Q001
    expected = tidy(text).split("\n")
    assert metconf._time_summary(k=k, v=v, level=0) == expected


def test_metconf__top():
    with raises(ValueError, match="Unsupported key: foo"):
        metconf._top(k="foo", v=None, level=0)


@mark.parametrize(("k", "v"), [(MET.method, MET.BILIN), (MET.width, 2)])
def test_metconf__type(k, v):
    assert metconf._type(k=k, v=v, level=1) == [f"  {k} = {v};"]


def test_metconf__type__fail():
    _fail(metconf._type)


# Helpers


def _fail(f: Callable, **kwargs):
    kwargs = kwargs or dict(k="foo", v=None, level=0)
    with raises(ValueError, match="Unsupported key: foo"):
        f(**kwargs)
