from pytest import raises

from wxvx import types
from wxvx.strings import EC, MET, S


def test_types_VarMeta():
    def fails(k, v):
        with raises(AssertionError):
            types.VarMeta(**{**kwargs, k: type(v)()})

    kwargs: dict = dict(
        cat_thresh=[">=20", ">=30", ">=40"],
        cf_standard_name="unknown",
        cnt_thresh=[">15"],
        description="Composite Reflectivity",
        level_type=S.atmosphere,
        met_stats=[MET.FSS, MET.PODY],
        name=EC.refc,
        nbrhd_shape=MET.CIRCLE,
        nbrhd_width=[3, 5, 11],
        units="dBZ",
    )
    x = types.VarMeta(**kwargs)
    for k, v in kwargs.items():
        assert getattr(x, k) == v
    # Must not be empty:
    for k, v in kwargs.items():
        fails(k, type(v)())
    # Must not have None values:
    for k in ["cf_standard_name", "description", S.level_type, "met_stats", S.name, "units"]:
        fails(k, None)
    # Must not have unrecognized values:
    for k, v in [
        (S.level_type, "intergalactic"),
        ("met_stats", ["XYZ"]),
        (MET.nbrhd_shape, "TRIANGLE"),
    ]:
        fails(k, v)
