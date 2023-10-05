from pathlib import Path
import numpy as np
from miniccpy.driver import run_scf_gamess, run_cc_calc, run_guess, run_eomcc_calc, get_hbar

TEST_DATA_DIR = str(Path(__file__).parents[1].absolute() / "data")

fock, g, e_hf, o, v = run_scf_gamess(TEST_DATA_DIR + "/chplus.FCIDUMP", 6, 26, 0, rhf=True)

T, Ecorr  = run_cc_calc(fock, g, o, v, method='rccsd')

H1, H2 = get_hbar(T, fock, g, o, v, method='rccsd')

R0, omega0 = run_guess(H1, H2, o, v, 10, method="rcis")
R, omega, r0 = run_eomcc_calc(R0, omega0, T, H1, H2, o, v, method='eomrccsd', state_index=[0, 1, 2, 3, 4, 5, 6, 7, 8], maxit=200)
    






