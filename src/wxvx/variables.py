from __future__ import annotations

import logging
import re
import sys
from functools import cache
from typing import TYPE_CHECKING, Any, Literal

import netCDF4  # noqa: F401 # import before xarray cf. https://github.com/pydata/xarray/issues/7259
import numpy as np
import xarray as xr
from pyproj import Proj

from wxvx.strings import EC, MET, NCEP, S
from wxvx.types import Coords, VarMeta
from wxvx.util import WXVXError, render

if TYPE_CHECKING:
    from wxvx.times import TimeCoords
    from wxvx.types import Config

# Public

UNKNOWN = "unknown"

VARMETA = {
    x.name: x
    for x in [  # blocks ordered by description
        VarMeta(
            description="2m Temperature",
            cf_standard_name="air_temperature",
            level_type=S.heightAboveGround,
            met_stats=[MET.ME, MET.RMSE],
            name=EC.t2,
            units="K",
        ),
        VarMeta(
            description="Composite Reflectivity",
            cat_thresh=[">=20", ">=30", ">=40"],
            cf_standard_name="unknown",
            cnt_thresh=[">15"],
            level_type=S.atmosphere,
            met_stats=[MET.FSS, MET.PODY],
            name=EC.refc,
            nbrhd_shape=MET.CIRCLE,
            nbrhd_width=[3, 5, 11],
            units="dBZ",
        ),
        VarMeta(
            description="Geopotential Height at {level} mb",
            cf_standard_name="geopotential_height",
            level_type=S.isobaricInhPa,
            met_stats=[MET.ME, MET.RMSE],
            name=EC.gh,
            units="m",
        ),
        VarMeta(
            description="Specific Humidity at {level} mb",
            cf_standard_name="specific_humidity",
            level_type=S.isobaricInhPa,
            met_stats=[MET.ME, MET.RMSE],
            name=EC.q,
            units="1",
        ),
        VarMeta(
            description="Surface Pressure",
            cf_standard_name="surface_air_pressure",
            level_type=S.surface,
            met_stats=[MET.ME, MET.RMSE],
            name=EC.sp,
            units="Pa",
        ),
        VarMeta(
            description="Temperature at {level} mb",
            cf_standard_name="air_temperature",
            level_type=S.isobaricInhPa,
            met_stats=[MET.ME, MET.RMSE],
            name=EC.t,
            units="K",
        ),
        VarMeta(
            description="U-Component of Wind at {level} mb",
            cf_standard_name="eastward_wind",
            level_type=S.isobaricInhPa,
            met_stats=[MET.ME, MET.RMSE],
            name=EC.u,
            units="m s-1",
        ),
        VarMeta(
            description="U-Component of Wind at 10m",
            cf_standard_name="eastward_wind",
            level_type=S.heightAboveGround,
            met_stats=[MET.ME, MET.RMSE],
            name=EC.u_10m,
            units="m s-1",
        ),
        VarMeta(
            description="V-Component of Wind at {level} mb",
            cf_standard_name="northward_wind",
            level_type=S.isobaricInhPa,
            met_stats=[MET.ME, MET.RMSE],
            name=EC.v,
            units="m s-1",
        ),
        VarMeta(
            description="V-Component of Wind at 10m",
            cf_standard_name="northward_wind",
            level_type=S.heightAboveGround,
            met_stats=[MET.ME, MET.RMSE],
            name=EC.v_10m,
            units="m s-1",
        ),
        VarMeta(
            description="Vertical Velocity at {level} mb",
            cf_standard_name="lagrangian_tendency_of_air_pressure",
            level_type=S.isobaricInhPa,
            met_stats=[MET.ME, MET.RMSE],
            name=EC.w,
            units="Pa s-1",
        ),
    ]
}


class Var:
    """
    A generic variable.
    """

    def __init__(self, name: str, level_type: str, level: float | None = None):
        self.name = name
        self.level_type = level_type
        self.level = level
        self._keys = (
            {S.name, S.level_type, S.level} if self.level is not None else {S.name, S.level_type}
        )

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return hash((self.name, self.level_type, self.level))

    def __lt__(self, other):
        return str(self) < str(other)

    def __repr__(self):
        keys = sorted(self._keys)
        vals = [
            f"{k}='{v}'" if isinstance(v, str) else f"{k}={v}"
            for k, v in zip(keys, [getattr(self, key) for key in keys], strict=True)
        ]
        return "%s(%s)" % (self.__class__.__name__, ", ".join(vals))

    def __str__(self):
        level = f"{self.level:04}" if self.level is not None else None
        vals = filter(None, [self.name, self.level_type, level])
        return "-".join(vals)


class GFS(Var):
    """
    A GFS variable.
    """

    def __init__(self, name: str, levstr: str, firstbyte: int, lastbyte: int):
        level_type, level = self._levinfo(levstr=levstr)
        name = self._canonicalize(name=name, level_type=level_type)
        super().__init__(name=name, level_type=level_type, level=level)
        self.firstbyte: int = firstbyte
        self.lastbyte: int | None = lastbyte if lastbyte > -1 else None
        self._keys = (
            {S.name, S.level_type, S.level, S.firstbyte, S.lastbyte}
            if self.level is not None
            else {S.name, S.level_type, S.firstbyte, S.lastbyte}
        )

    @staticmethod
    def varname(name: str) -> str:
        return {
            EC.t2: NCEP.TMP,
            EC.gh: NCEP.HGT,
            EC.q: NCEP.SPFH,
            EC.refc: NCEP.REFC,
            EC.sp: NCEP.PRES,
            EC.t: NCEP.TMP,
            EC.u: NCEP.UGRD,
            EC.u_10m: NCEP.UGRD,
            EC.v: NCEP.VGRD,
            EC.v_10m: NCEP.VGRD,
            EC.w: NCEP.VVEL,
        }.get(name, UNKNOWN)

    @staticmethod
    def _canonicalize(name: str, level_type: str) -> str:
        return {
            (NCEP.HGT, S.isobaricInhPa): EC.gh,
            (NCEP.PRES, S.surface): EC.sp,
            (NCEP.REFC, S.atmosphere): EC.refc,
            (NCEP.SPFH, S.isobaricInhPa): EC.q,
            (NCEP.TMP, S.heightAboveGround): EC.t2,
            (NCEP.TMP, S.isobaricInhPa): EC.t,
            (NCEP.UGRD, S.heightAboveGround): EC.u_10m,
            (NCEP.UGRD, S.isobaricInhPa): EC.u,
            (NCEP.VGRD, S.heightAboveGround): EC.v_10m,
            (NCEP.VGRD, S.isobaricInhPa): EC.v,
            (NCEP.VVEL, S.isobaricInhPa): EC.w,
        }.get((name, level_type), UNKNOWN)

    @staticmethod
    def _levinfo(levstr: str) -> tuple[str, float | int | None]:
        if m := re.match(r"^entire atmosphere$", levstr):
            return (S.atmosphere, None)
        if m := re.match(r"^(\d+(\.\d+)?) m above ground$", levstr):
            return (S.heightAboveGround, _levelstr2num(m[1]))
        if m := re.match(r"^(\d+(\.\d+)?) mb$", levstr):
            return (S.isobaricInhPa, _levelstr2num(m[1]))
        if m := re.match(r"^surface$", levstr):
            return (S.surface, None)
        return (UNKNOWN, None)


class HRRR(GFS):
    """
    A HRRR variable.
    """

    proj = Proj(
        {
            "a": 6371229,
            "b": 6371229,
            "lat_0": 38.5,
            "lat_1": 38.5,
            "lat_2": 38.5,
            "lon_0": 262.5,
            S.proj: "lcc",
        }
    )


class PREPBUFR(GFS):
    """
    Observations in PREPBUFR format, following GFS conventions.
    """


def da_construct(c: Config, da: xr.DataArray) -> xr.DataArray:
    # This function is called only for netCDF/Zarr forecast datasets, for which 'coords' config
    # blocks will have been provided. So, for the typechecker, assert that this is the case.
    assert isinstance(c.forecast.coords, Coords)
    inittime = _da_val(da, c.forecast.coords.time.inittime, "initialization time", np.datetime64)
    leadtime = c.forecast.coords.time.leadtime
    validtime = c.forecast.coords.time.validtime
    if leadtime is not None:
        time = inittime + _da_val(da, leadtime, S.leadtime, np.timedelta64)
    else:
        assert validtime is not None
        time = _da_val(da, validtime, S.validtime, np.datetime64)
    return xr.DataArray(
        data=da.expand_dims(dim=[S.forecast_reference_time, S.time]),
        coords=dict(
            forecast_reference_time=[inittime + np.timedelta64(0, "s")],
            time=[time],
            latitude=da[c.forecast.coords.latitude],
            longitude=da[c.forecast.coords.longitude],
        ),
        dims=(S.forecast_reference_time, S.time, S.latitude, S.longitude),
        name=da.name,
    )


def da_select(c: Config, ds: xr.Dataset, varname: str, tc: TimeCoords, var: Var) -> xr.DataArray:
    # This function is called only for netCDF/Zarr forecast datasets, for which 'coords' config
    # blocks will have been provided. So, for the typechecker, assert that this is the case.
    assert isinstance(c.forecast.coords, Coords)
    coords = ds.coords.keys()
    dt = lambda x: np.datetime64(str(x.isoformat()))
    try:
        da = ds[varname]
        da.attrs.update(ds.attrs)
        key_inittime = c.forecast.coords.time.inittime
        if key_inittime in coords:
            da = _narrow(da, key_inittime, dt(tc.cycle))
        key_leadtime = c.forecast.coords.time.leadtime
        if key_leadtime in coords:
            da = _narrow(da, key_leadtime, np.timedelta64(int(tc.leadtime.total_seconds()), "s"))
        key_validtime = c.forecast.coords.time.validtime
        if key_validtime in coords:
            da = _narrow(da, key_validtime, dt(tc.validtime))
        key_level = c.forecast.coords.level
        if key_level in coords and var.level is not None:
            da = _narrow(da, key_level, var.level)
    except KeyError as e:
        forecast_path = render(c.forecast.path, tc, context=c.raw)
        msg = "Variable %s valid at %s not found in %s" % (varname, tc, forecast_path)
        raise WXVXError(msg) from e
    return da


def ds_construct(c: Config, da: xr.DataArray, taskname: str, level: float | None) -> xr.Dataset:
    logging.info("%s: Creating CF-compliant %s dataset", taskname, da.name)
    coord_names = (S.forecast_reference_time, S.time, S.latitude, S.longitude)
    assert len(da.shape) == len(coord_names)
    proj = Proj(c.forecast.projection)
    latlon = proj.name == "longlat"  # yes, "longlat"
    dims = [S.forecast_reference_time, S.time]
    dims.extend([S.latitude, S.longitude] if latlon else ["y", "x"])
    crs = "CRS"
    meta = VARMETA[c.variables[da.name][S.name]]
    attrs = dict(grid_mapping=crs, standard_name=meta.cf_standard_name, units=meta.units)
    dims_lat, dims_lon = ([k] if latlon else ["y", "x"] for k in [S.latitude, S.longitude])
    coords = dict(
        zip(
            coord_names,
            [
                _da_to_forecast_reference_time(da),
                _da_to_time(da),
                _da_to_latitude(da, dims_lat),
                _da_to_longitude(da, dims_lon),
            ],
            strict=True,
        )
    )
    if not latlon:
        coords = {**coords, "y": _da_to_y(da, proj), "x": _da_to_x(da, proj)}
    return xr.Dataset(
        data_vars={
            da.name: xr.DataArray(data=da.values, dims=dims, attrs=attrs),
            crs: _da_crs(proj),
        },
        coords=coords,
        attrs=dict(Conventions="CF-1.8", level=level or np.nan),
    )


def metlevel(level_type: str, level: float | None) -> str:
    try:
        prefix = {
            S.atmosphere: "L",
            S.heightAboveGround: "Z",
            S.isobaricInhPa: "P",
            S.surface: "Z",
        }[level_type]
    except KeyError as e:
        raise WXVXError("No MET level defined for level type %s" % level_type) from e
    return f"{prefix}%03d" % int(level or 0)


def model_class(name: str) -> Any:
    if name in model_names():
        return getattr(sys.modules[__name__], name)
    msg = f"Truth model {name}"
    raise NotImplementedError(msg)


@cache
def model_names(current: type = Var) -> set[str]:
    s = set()
    for subclass in current.__subclasses__():
        s.add(subclass.__name__)
        s |= model_names(subclass)
    return s


# Private


def _da_crs(proj: Proj) -> xr.DataArray:
    cf = proj.crs.to_cf()
    return xr.DataArray(
        data=0,
        attrs={
            k: cf[k]
            for k in [
                "false_easting",
                "false_northing",
                "grid_mapping_name",
                "latitude_of_projection_origin",
                "longitude_of_central_meridian",
                "standard_parallel",
            ]
            if k in cf
        },
    )


def _da_grid_coords(
    da: xr.DataArray, proj: Proj, k: Literal["latitude", "longitude"]
) -> np.ndarray:
    ks = (S.latitude, S.longitude)
    assert k in ks
    lats, lons = [da[k].values for k in ks]
    i1, i2 = {S.latitude: (lambda n: (n, 0), 1), S.longitude: (lambda n: (0, n), 0)}[k]
    return np.array([proj(lons[i1(n)], lats[i1(n)])[i2] for n in range(da.latitude.sizes[k])])


def _da_to_forecast_reference_time(da: xr.DataArray) -> xr.DataArray:
    var = da.forecast_reference_time
    return xr.DataArray(
        data=var.values,
        dims=[S.forecast_reference_time],
        name=var.name,
        attrs=dict(standard_name=S.forecast_reference_time),
    )


def _da_to_latitude(da: xr.DataArray, dims: list[str]) -> xr.DataArray:
    var = da.latitude
    return xr.DataArray(
        data=var.values,
        dims=dims,
        name=var.name,
        attrs=dict(standard_name=S.latitude, units="degrees_north"),
    )


def _da_to_longitude(da: xr.DataArray, dims=list[str]) -> xr.DataArray:
    var = da.longitude
    return xr.DataArray(
        data=var.values,
        dims=dims,
        name=var.name,
        attrs=dict(standard_name=S.longitude, units="degrees_east"),
    )


def _da_to_time(da: xr.DataArray) -> xr.DataArray:
    var = da.time
    return xr.DataArray(
        data=var.values, dims=[S.time], name=var.name, attrs=dict(standard_name=S.time)
    )


def _da_to_x(da: xr.DataArray, proj: Proj) -> xr.DataArray:
    return xr.DataArray(
        data=_da_grid_coords(da, proj, "longitude"),
        dims=["x"],
        attrs=dict(standard_name="projection_x_coordinate", units="m"),
    )


def _da_to_y(da: xr.DataArray, proj: Proj) -> xr.DataArray:
    return xr.DataArray(
        data=_da_grid_coords(da, proj, "latitude"),
        dims=["y"],
        attrs=dict(standard_name="projection_y_coordinate", units="m"),
    )


def _da_val(da: xr.DataArray, key: str, desc: str, t: type) -> Any:
    coords = da.coords.keys()
    if key in coords:
        val = da[key].values
    else:
        try:
            val = da.attrs[key]
        except KeyError as e:
            msg = f"Not found in forecast dataset coordinates or attributes: '{key}'"
            raise WXVXError(msg) from e
    if not isinstance(val, t):
        try:
            val = t(val)
        except Exception as e:
            msg = f"Could not parse '{val}' as {desc}"
            raise WXVXError(msg) from e
    return val


def _levelstr2num(levelstr: str) -> float | int:
    try:
        return int(levelstr)
    except ValueError:
        return float(levelstr)


def _narrow(da: xr.DataArray, key: str, value: Any) -> xr.DataArray:
    # If the value of the coordinate variable identified by the 'key' argument is a vector, reduce
    # it to a scalar by selecting the single element matching the 'value' argument. If it is already
    # a scalar, raise an exception if it does not match 'value'. For example, an array with a series
    # of forecast cycles might have a vector-valued 'key' = 'time' coordinate variable, while one
    # with a single forecast cycle might have a scalar 'time'. Either way, this function should
    # return a DataArray with a scalar 'time' coordinate variable with the expected value.
    try:
        coords = da[key].values
    except KeyError:
        logging.debug("No coordinate '%s' found for '%s', ignoring", key, da.name)
    else:
        if coords.shape:  # i.e. vector
            da = da.sel({key: value})
        elif coords != value:
            raise KeyError
    return da
