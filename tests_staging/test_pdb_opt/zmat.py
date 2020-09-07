from collections import namedtuple

import numpy as np
import pytest
from rmsd import kabsch_rmsd

from pysisyphus.constants import ANG2BOHR as ANG2BOHR
from pysisyphus.helpers import geom_loader
from pysisyphus.Geometry import Geometry


ZLine = namedtuple("ZLine",
                   "atom rind r aind a dind d",
                   defaults=(None, None, None, None, None, None)
)


def geom_from_zmat(zmat, coords3d=None, start_at=None):
    """Adapted from https://github.com/robashaw/geomConvert by Robert Shaw."""
    atoms = [zline.atom for zline in zmat]
    if coords3d is None:
        coords3d = np.zeros((len(zmat), 3), dtype=float)

    if start_at is None:
        start_at = 0

    for i, zline in enumerate(zmat[start_at:], start_at):
        r = zline.r
        if i == 0:
            continue
        # Bond along x-axis
        elif i == 1:
            coords3d[i,0] = r
        # Angle in xy-plane from polar coordinates
        elif i == 2:
            """
            M       P <- add
             \     /
              u   v
               \ /
                O
            """
            theta = np.deg2rad(zline.a)
            # Center
            O = coords3d[zline.rind]
            # Bond, pointing away from O to M
            u = coords3d[zline.aind] - O
            # Direction of u along x axis (left/right)
            sign = np.sign(u[0])
            # Polar coordinates
            x = r * np.cos(theta)
            y = r * np.sin(theta)
            # Translate from center with correct orientation
            coords3d[i] = O + (sign*x, sign*y, 0.)
        # Dihedral in xyz-space from spherical coordinates
        else:
            theta, phi = np.deg2rad((zline.a, zline.d))

            sin_theta = np.sin(theta)
            cos_theta = np.cos(theta)
            sin_phi = np.sin(phi)
            cos_phi = np.cos(phi)

            x = r * cos_theta
            y = r * sin_theta * cos_phi
            z = r * sin_theta * sin_phi

            """
            M <- add      N
             \           /
              u         v
               \       /
                O--w--P
            """

            O = coords3d[zline.rind]
            P = coords3d[zline.aind]
            N = coords3d[zline.dind]

            # Local axis system
            v_ = P - N
            v = v_ / np.linalg.norm(v_)
            w_ = O - P
            w = w_ / np.linalg.norm(w_)
            a = np.cross(v, w)
            a /= np.linalg.norm(a)
            b = np.cross(a, w)
            b /= np.linalg.norm(b)
            coords3d[i] = O - w*x + b*y + a*z

    geom = Geometry(atoms, coords3d)
    return geom


def zmat_from_str(text):
    def dec(str_):
        return int(str_) - 1

    def to_bohr(str_):
        return float(str_) * ANG2BOHR

    def convert(items):
        funcs = (str, dec, to_bohr, dec, float, dec, float)
        return [f(item) for f, item in zip(funcs, items)]

    zmat = list()
    for line in text.strip().split("\n"):
        zmat.append(
            ZLine(*convert(line.strip().split()))
        )
    return zmat


def zmat_from_fn(fn):
    with open(fn) as handle:
        text = handle.read()
    return zmat_from_str(text)


def assert_geom(ref_fn, zmat_fn, atol=2.5e-5):
    zmat = zmat_from_fn(zmat_fn)
    geom = geom_from_zmat(zmat)

    ref = geom_loader(ref_fn)
    rmsd = kabsch_rmsd(geom.coords3d, ref.coords3d, translate=True)
    print(f"RMSD: {rmsd:.6f}")
    assert rmsd == pytest.approx(0., abs=atol)


rzmat = zmat_from_fn("glycine_resorted.zmat")
print(rzmat)
for zl in rzmat:
    print(zl)
rg = geom_from_zmat(rzmat)
assert_geom("glycine_resorted.xyz", "glycine_resorted.zmat")

AB = ANG2BOHR
zmat = [
    ZLine("C"),
    ZLine("C", 0, 1.510486*AB),
    ZLine("N", 0, 1.459785*AB, 1, 112.257683),
    ZLine("O", 1, 1.220389*AB, 0, 118.653885, 2, -179.541229),
    ZLine("O", 1, 1.353023*AB, 0, 122.591621, 2, 0.825231),
]

geom = geom_from_zmat(zmat)
# geom.jmol()
with open("from_zmat.xyz", "w") as handle:
    handle.write(geom.as_xyz())


reference = geom_loader("glycine_noh.xyz")
rmsd = kabsch_rmsd(geom.coords3d, reference.coords3d, translate=True)
print("rmsd", rmsd)
assert rmsd == pytest.approx(0., abs=1e-6)
