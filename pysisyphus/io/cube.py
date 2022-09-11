from dataclasses import dataclass
from typing import Tuple

import jinja2
import numpy as np
from numpy.typing import NDArray
import pyparsing as pp

from pysisyphus.elem_data import ATOMIC_NUMBERS, INV_ATOMIC_NUMBERS
from pysisyphus.Geometry import Geometry
from pysisyphus.helpers_pure import file_or_str


@dataclass
class Cube:
    atoms: Tuple
    coords3d: NDArray
    origin: NDArray
    npoints: NDArray
    axes: NDArray
    comment1: str
    comment2: str
    vol_data: NDArray

    @staticmethod
    def from_file(fn):
        return parse_cube(fn)


@file_or_str(".cube", ".cub")
def parse_cube(text):
    int_ = pp.common.integer
    sci_real = pp.common.sci_real

    def get_line_word(*args):
        return pp.Word(*args).setWhitespaceChars("\n")

    comment = get_line_word(pp.printables + " \t")
    cart_vec = pp.Group(sci_real + sci_real + sci_real)
    axis = pp.Group(int_ + cart_vec)
    atom_line = pp.Group(
        int_.set_results_name("atomic_num")
        + sci_real.set_results_name("charge")
        + cart_vec.set_results_name("coords")
        + pp.LineEnd()
    )

    parser = (
        comment.set_results_name("comment1")
        + comment.set_results_name("comment2")
        + int_.set_results_name("atom_num")
        + cart_vec.set_results_name("origin")
        + axis.set_results_name("axis1")
        + axis.set_results_name("axis2")
        + axis.set_results_name("axis3")
        + pp.ZeroOrMore(atom_line).set_results_name("atom_lines")
        + pp.ZeroOrMore(sci_real).set_results_name("vol_data")
    )
    res = parser.parseString(text).as_dict()

    comment1 = " ".join(res["comment1"])
    comment2 = " ".join(res["comment2"])
    atom_num = res["atom_num"]
    atom_lines = res["atom_lines"]
    assert atom_num == len(atom_lines)

    atom_nums, coords3d = zip(*[(al["atomic_num"], al["coords"]) for al in atom_lines])
    atoms = [INV_ATOMIC_NUMBERS[an].capitalize() for an in atom_nums]
    coords3d = np.array(coords3d)
    origin = np.array(res["origin"])

    npoints, axes = zip(*[res[k] for k in ("axis1", "axis2", "axis3")])
    npoints = np.array(npoints, int)
    assert all(npoints > 0), "Only Bohr are supported!"
    axes = np.array(axes, float)
    vol_data = np.array(res["vol_data"]).reshape(*npoints)

    cube = Cube(
        atoms=atoms,
        coords3d=coords3d,
        origin=origin,
        npoints=npoints,
        axes=axes,
        comment1=comment1,
        comment2=comment2,
        vol_data=vol_data,
    )

    return cube


@file_or_str(".cube", ".cub")
def geom_from_cube(text, **kwargs):
    cube = parse_cube(text)
    geom = Geometry(cube.atoms, cube.coords3d, **kwargs)
    return geom


CUBE_TPL = """{{ comment1 }}
{{ comment2 }}
{{ atom_nums|length }} {{ fmt(origin_x) }} {{ fmt(origin_y) }} {{ fmt(origin_z) }}
{% for n_points, (x, y, z) in zip(axes_npoints, axes) %}
{{ n_points }} {{ fmt(x) }} {{ fmt(y) }} {{ fmt(z) }}
{% endfor %}
{% for atomic_num, (x, y, z) in zip(atom_nums, coords3d) %}
{{ atomic_num }} 0.000000 {{ fmt(x) }} {{ fmt(y) }} {{ fmt(z) }}
{% endfor %}
{{ grid_str }}
"""


def write_cube(atoms, coords3d, vol_data, origin, axes):
    env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True)
    env.globals.update(zip=zip)
    tpl = env.from_string(CUBE_TPL)

    org_x, org_y, org_z = origin
    axes_npoints = vol_data.shape
    atom_nums = [ATOMIC_NUMBERS[atom.lower()] for atom in atoms]

    nx, ny, nz = axes_npoints
    grid_str = ""
    for x in range(nx):
        for y in range(ny):
            for z in range(nz):
                d = "{: >14.8e} ".format(vol_data[x, y, z])
                grid_str += d
                if z % 6 == 5:
                    grid_str += "\n"
            grid_str += "\n"

    def fmt(num):
        return f"{num: >14.8f}"

    rendered = tpl.render(
        fmt=fmt,
        origin_x=org_x,
        origin_y=org_y,
        origin_z=org_z,
        comment1="Generated by pysisyphus",
        comment2=f"Total of {nx*ny*nz} points",
        axes=axes,
        axes_npoints=axes_npoints,
        atom_nums=atom_nums,
        coords3d=coords3d,
        grid_str=grid_str,
    )
    return rendered
