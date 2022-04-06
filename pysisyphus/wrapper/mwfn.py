import logging
import os
from pathlib import Path
import shutil
from subprocess import PIPE, Popen

import numpy as np

from pysisyphus.config import get_cmd
from pysisyphus.constants import AU2EV


logger = logging.getLogger("mwfn")


def log(msg):
    logger.debug(msg)


def wrap_stdin(stdin):
    return f"<< EOF\n{stdin}\nEOF"


def call_mwfn(inp_fn, stdin, cwd=None):
    if cwd is None:
        cwd = Path(".")
    mwfn_cmd = get_cmd("mwfn")
    cmd = [mwfn_cmd, inp_fn]
    log(f"\n{mwfn_cmd} {inp_fn} {wrap_stdin(stdin)}")
    proc = Popen(
        cmd, universal_newlines=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=cwd
    )
    stdout, stderr = proc.communicate(stdin)
    proc.terminate()
    return stdout, stderr


def make_cdd(inp_fn, state, log_fn, cwd=None, keep=False, quality=2):
    """Create CDD cube in cwd.

    Parameters
    ----------
    inp_fn : str
        Filename of a .molden/.fchk file.
    state : int
        CDD cubes will be generated up to this state.
    log_fn : str
        Filename of the .log file.
    cwd : str or Path, optional
        If a different cwd should be used.
    keep : bool
        Wether to keep electron.cub and hole.cub, default is False.
    quality : int
        Quality of the cube. (1=low, 2=medium, 3=high).
    """

    assert quality in (1, 2, 3)

    msg = (
        f"Requested CDD calculation from Multiwfn for state {state} using "
        f"{inp_fn} and {log_fn}"
    )
    log(msg)

    stdin = f"""18
    1
    {log_fn}
    {state}

    1
    {quality}
    10
    1
    11
    1
    15
    """
    stdout, stderr = call_mwfn(inp_fn, stdin, cwd=cwd)

    if cwd is None:
        cwd = "."
    cwd = Path(cwd)

    cube_fns = ("electron.cub", "hole.cub", "CDD.cub")
    if not keep:
        # always keep CDD.cub
        for fn in cube_fns[:2]:
            full_path = cwd / fn
            os.remove(full_path)
    # Rename cubes according to the current state
    new_paths = list()
    for fn in cube_fns:
        old_path = cwd / fn
        root, ext = os.path.splitext(fn)
        new_path = cwd / f"S_{state:03d}_{root}{ext}"
        try:
            shutil.copy(old_path, new_path)
            os.remove(old_path)
            new_paths.append(new_path)
        except FileNotFoundError:
            pass
    return new_paths


def get_mwfn_exc_str(energies, ci_coeffs, thresh=1e-3):
    exc_energies = (energies[1:] - energies[0]) * AU2EV
    # states, occ, virt
    _, occ_mos, _ = ci_coeffs.shape

    exc_str = ""
    mult = 1
    log(f"Using dummy multiplicity={mult} in get_mwfn_exc_str")
    for root_, (root_ci_coeffs, exc_en) in enumerate(zip(ci_coeffs, exc_energies), 1):
        exc_str += f"Excited State {root_} {mult} {exc_en:.4f}\n"
        for (occ, virt), coeff in np.ndenumerate(root_ci_coeffs):
            if abs(coeff) < thresh:
                continue
            occ_mo = occ + 1
            virt_mo = occ_mos + 1 + virt
            exc_str += f"{occ_mo:>8d} -> {virt_mo}       {coeff: .5f}\n"
        exc_str += "\n"
    return exc_str
