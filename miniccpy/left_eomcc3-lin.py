import time
import numpy as np
from miniccpy.energy import lccsd_energy as lcc_energy
from miniccpy.diis import DIIS
from miniccpy.helper_cc3 import compute_l3, compute_leftcc3_intermediates

def get_ccsdt_intermediates(l2, l3, t2, t3, o, v):
    nu, _, no, _ = t2.shape
    X1 = {"vo": []}
    X2 = {"ooov": [], "vovv": []}
    # (L2 * T3)_C
    X1["vo"] = 0.25 * np.einsum("efmn,aefimn->ai", l2, t3, optimize=True)
    # (L3 * T2)_C
    X2["ooov"] = 0.5 * np.einsum('aefijn,efmn->jima', l3, t2, optimize=True)
    X2["vovv"] = -0.5 * np.einsum('abfimn,efmn->eiba', l3, t2, optimize=True)
    return X1, X2

def LH_singles(l1, l2, t1, t2, H1, H2, X1, X2, h_voov, h_vvvv, h_oooo, o, v):
    """Compute the projection of the CCSD Hamiltonian on singles
        X[a, i] = < 0 | (1 + L1 + L2)*(H_N exp(T1+T2))_C | 0 >
    """
    LH = np.einsum("ea,ei->ai", H1[v, v], l1, optimize=True)
    LH -= np.einsum("im,am->ai", H1[o, o], l1, optimize=True)
    LH += np.einsum("eima,em->ai", H2[v, o, o, v], l1, optimize=True)
    LH += 0.5 * np.einsum("fena,efin->ai", H2[v, v, o, v], l2, optimize=True)
    LH -= 0.5 * np.einsum("finm,afmn->ai", H2[v, o, o, o], l2, optimize=True)

    I1 = 0.25 * np.einsum("efmn,fgnm->ge", l2, t2, optimize=True)
    I2 = -0.25 * np.einsum("efmn,egnm->gf", l2, t2, optimize=True)
    I3 = -0.25 * np.einsum("efmo,efno->mn", l2, t2, optimize=True)
    I4 = 0.25 * np.einsum("efmo,efnm->on", l2, t2, optimize=True)

    LH += np.einsum("ge,eiga->ai", I1, H2[v, o, v, v], optimize=True)
    LH += np.einsum("gf,figa->ai", I2, H2[v, o, v, v], optimize=True)
    LH += np.einsum("mn,nima->ai", I3, H2[o, o, o, v], optimize=True)
    LH += np.einsum("on,nioa->ai", I4, H2[o, o, o, v], optimize=True)

    # < 0 | L2 * (H(2) * T3)_C | ia >
    LH += np.einsum("em,imae->ai", X1["vo"], H2[o, o, v, v], optimize=True)
    LH += 0.5 * np.einsum("nmoa,iomn->ai", X2["ooov"], h_oooo, optimize=True)
    LH += np.einsum("fmae,eimf->ai", X2["vovv"], h_voov, optimize=True)
    LH -= 0.5 * np.einsum("gife,efag->ai", X2["vovv"], h_vvvv, optimize=True)
    LH -= np.einsum("imne,enma->ai", X2["ooov"], h_voov, optimize=True)
    return LH

def LH_doubles(l1, l2, l3, t1, t2, H1, H2, X1, X2, h_vvov, h_vooo, o, v):
    """Compute the projection of the CCSD Hamiltonian on doubles
        X[a, b, i, j] = < ijab | (H_N exp(T1+T2))_C | 0 >
    """
    LH = 0.5 * np.einsum("ea,ebij->abij", H1[v, v], l2, optimize=True)
    LH -= 0.5 * np.einsum("im,abmj->abij", H1[o, o], l2, optimize=True)
    LH += np.einsum("jb,ai->abij", H1[o, v], l1, optimize=True)

    I1 = (
          -0.5 * np.einsum("afmn,efmn->ea", l2, t2, optimize=True)
    )
    LH += 0.5 * np.einsum("ea,ijeb->abij", I1, H2[o, o, v, v], optimize=True)

    I1 = (
          0.5 * np.einsum("efin,efmn->im", l2, t2, optimize=True)
    )
    LH -= 0.5 * np.einsum("im,mjab->abij", I1, H2[o, o, v, v], optimize=True)

    LH += np.einsum("eima,ebmj->abij", H2[v, o, o, v], l2, optimize=True)
    LH += 0.125 * np.einsum("ijmn,abmn->abij", H2[o, o, o, o], l2, optimize=True)
    LH += 0.125 * np.einsum("efab,efij->abij", H2[v, v, v, v], l2, optimize=True)
    LH += 0.5 * np.einsum("ejab,ei->abij", H2[v, o, v, v], l1, optimize=True)
    LH -= 0.5 * np.einsum("ijmb,am->abij", H2[o, o, o, v], l1, optimize=True)
    # Moment-like terms
    LH += 0.25 * np.einsum("ebfijn,fena->abij", l3, h_vvov, optimize=True) # 1
    LH -= 0.25 * np.einsum("abfmjn,finm->abij", l3, h_vooo, optimize=True) # 3
    LH -= np.transpose(LH, (1, 0, 2, 3))
    LH -= np.transpose(LH, (0, 1, 3, 2))
    return LH

def LH_triples(l1, l2, l3, t1, t2, f, g, H1, H2, o, v):
    # < 0 | L1 * H(2) | ijkabc >
    LH = (9.0 / 36.0) * np.einsum("ai,jkbc->abcijk", l1, g[o, o, v, v], optimize=True)
    # < 0 | L2 * H(2) | ijkabc >
    LH += (9.0 / 36.0) * np.einsum("bcjk,ia->abcijk", l2, H1[o, v], optimize=True)
    LH += (9.0 / 36.0) * np.einsum("ebij,ekac->abcijk", l2, H2[v, o, v, v], optimize=True)
    LH -= (9.0 / 36.0) * np.einsum("abmj,ikmc->abcijk", l2, H2[o, o, o, v], optimize=True)
    #
    LH += (3.0 / 36.0) * np.einsum("ea,ebcijk->abcijk", f[v, v], l3, optimize=True)
    LH -= (3.0 / 36.0) * np.einsum("im,abcmjk->abcijk", f[o, o], l3, optimize=True)
    # antisymmetrize terms and add up: A(abc)A(ijk) = A(a/bc)A(bc)A(i/jk)A(jk)
    LH -= np.transpose(LH, (0, 1, 2, 3, 5, 4))
    LH -= np.transpose(LH, (0, 1, 2, 4, 3, 5)) + np.transpose(LH, (0, 1, 2, 5, 4, 3))
    LH -= np.transpose(LH, (0, 2, 1, 3, 4, 5))
    LH -= np.transpose(LH, (1, 0, 2, 3, 4, 5)) + np.transpose(LH, (2, 1, 0, 3, 4, 5))
    return LH

def update(l1, l2, l3, omega, e_ai, e_abij, e_abcijk):
    """Perform the diagonally preconditioned residual (DPR) update
    to get the next correction vector."""
    l1 /= (omega - e_ai)
    l2 /= (omega - e_abij)
    l3 /= (omega - e_abcijk)
    return np.hstack([l1.flatten(), l2.flatten(), l3.flatten()])

def LH(l1, l2, l3, t1, t2, t3, f, g, H1, H2, o, v):
    """Compute the matrix-vector product L * H, where
    H is the CCSDT similarity-transformed Hamiltonian and L is
    the EOMCCSDT linear de-excitation operator."""
    # Get CCS intermediates (it would be nice to not have to recompute these in left-CC)
    h_vvov, h_vooo, h_voov, h_vvvv, h_oooo = compute_leftcc3_intermediates(t1, t2, f, g, o, v)
    # comptute L*T intermediates
    X1, X2 = get_ccsdt_intermediates(l2, l3, t2, t3, o, v)
    # update L1
    LH1 = LH_singles(l1, l2, t1, t2, H1, H2, X1, X2, h_voov, h_vvvv, h_oooo, o, v)
    # update L2
    LH2 = LH_doubles(l1, l2, l3, t1, t2, H1, H2, X1, X2, h_vvov, h_vooo, o, v)
    # update L3
    LH3 = LH_triples(l1, l2, l3, t1, t2, f, g, H1, H2, o, v)
    return np.hstack( [LH1.flatten(), LH2.flatten(), LH3.flatten()] )

def calc_LR(L, R, nocc, nunocc):
    n1 = nocc*nunocc
    n2 = nocc**2 * nunocc**2
    n3 = nocc**3 * nunocc**3
    # unpack L
    l1 = L[:n1].reshape(nunocc, nocc)
    l2 = L[n1:n1+n2].reshape(nunocc, nunocc, nocc, nocc)
    l3 = L[n1+n2:].reshape(nunocc, nunocc, nunocc, nocc, nocc, nocc)
    # unpack R
    r1, r2, r3 = R
    # compute LR
    LR = np.einsum("ai,ai->", l1, r1, optimize=True)
    LR += 0.25 * np.einsum("abij,abij->", l2, r2, optimize=True)
    LR += (1.0 / 36.0) * np.einsum("abcijk,abcijk->", l3, r3, optimize=True)
    return LR

def kernel(R, T, omega, fock, g, H1, H2, o, v, maxit=80, convergence=1.0e-07, max_size=20, nrest=1):
    """
    Diagonalize the similarity-transformed CCSD Hamiltonian using the
    non-Hermitian Davidson algorithm for a specific root defined by an initial
    guess vector.
    """
    eps = np.diagonal(H1)
    f_eps = np.diagonal(fock)
    n = np.newaxis
    e_abcijk = (f_eps[v, n, n, n, n, n] + f_eps[n, v, n, n, n, n] + f_eps[n, n, v, n, n, n]
                - f_eps[n, n, n, o, n, n] - f_eps[n, n, n, n, o, n] - f_eps[n, n, n, n, n, o])
    e_abij = (eps[v, n, n, n] + eps[n, v, n, n] - eps[n, n, o, n] - eps[n, n, n, o])
    e_ai = (eps[v, n] - eps[n, o])

    t1, t2, t3 = T

    nunocc, nocc = e_ai.shape
    n1 = nunocc * nocc
    n2 = nocc**2 * nunocc**2
    n3 = nocc**3 * nunocc**3
    ndim = n1 + n2 + n3

    # Set the initial vector to be R
    r1, r2, r3 = R
    Rvec = np.hstack([r1.flatten(), r2.flatten(), r3.flatten()])
    L = Rvec.copy()

    # Allocate the B and sigma matrices
    sigma = np.zeros((ndim, max_size))
    B = np.zeros((ndim, max_size))
    restart_block = np.zeros((ndim, nrest))

    # Initial values
    B[:, 0] = L
    sigma[:, 0] = LH(L[:n1].reshape(nunocc, nocc),
                     L[n1:n1+n2].reshape(nunocc, nunocc, nocc, nocc),
                     L[n1+n2:].reshape(nunocc, nunocc, nunocc, nocc, nocc, nocc),
                     t1, t2, t3, fock, g, H1, H2, o, v)

    print("    ==> Left-EOMCC3 iterations <==")
    print("    The initial guess energy = ", omega)
    print("")
    print("     Iter               Energy                 |dE|                 |dR|")
    curr_size = 1
    for niter in range(maxit):
        tic = time.time()
        # store old energy
        omega_old = omega

        # solve projection subspace eigenproblem
        G = np.dot(B[:, :curr_size].T, sigma[:, :curr_size])
        e, alpha = np.linalg.eig(G)

        # select root based on maximum overlap with initial guess
        idx = np.argsort(abs(alpha[0, :]))
        alpha = np.real(alpha[:, idx[-1]])

        # Get the eigenpair of interest
        omega = np.real(e[idx[-1]])
        L = np.dot(B[:, :curr_size], alpha)
        restart_block[:, niter % nrest] = L

        # calculate residual vector
        residual = np.dot(sigma[:, :curr_size], alpha) - omega * L
        res_norm = np.linalg.norm(residual)
        delta_e = omega - omega_old

        toc = time.time()
        minutes, seconds = divmod(toc - tic, 60)
        print("    {: 5d} {: 20.12f} {: 20.12f} {: 20.12f}    {:.2f}m {:.2f}s".format(niter, omega, delta_e, res_norm, minutes, seconds))
        if res_norm < convergence and abs(delta_e) < convergence:
            break

        # update residual vector
        q = update(residual[:n1].reshape(nunocc, nocc),
                   residual[n1:n1+n2].reshape(nunocc, nunocc, nocc, nocc),
                   residual[n1+n2:].reshape(nunocc, nunocc, nunocc, nocc, nocc, nocc),
                   omega,
                   e_ai,
                   e_abij,
                   e_abcijk)
        for p in range(curr_size):
            b = B[:, p] / np.linalg.norm(B[:, p])
            q -= np.dot(b.T, q) * b
        q *= 1.0 / np.linalg.norm(q)

        # If below maximum subspace size, expand the subspace
        if curr_size < max_size:
            B[:, curr_size] = q
            sigma[:, curr_size] = LH(q[:n1].reshape(nunocc, nocc),
                                     q[n1:n1+n2].reshape(nunocc, nunocc, nocc, nocc),
                                     q[n1+n2:].reshape(nunocc, nunocc, nunocc, nocc, nocc, nocc),
                                     t1, t2, t3, fock, g, H1, H2, o, v)
        else:
            # Basic restart - use the last approximation to the eigenvector
            print("       **Deflating subspace**")
            restart_block, _ = np.linalg.qr(restart_block)
            for j in range(restart_block.shape[1]):
                B[:, j] = restart_block[:, j]
                sigma[:, j] = LH(restart_block[:n1, j].reshape(nunocc, nocc),
                                 restart_block[n1:n1+n2, j].reshape(nunocc, nunocc, nocc, nocc),
                                 restart_block[n1+n2:, j].reshape(nunocc, nunocc, nunocc, nocc, nocc, nocc),
                                 t1, t2, t3, fock, g, H1, H2, o, v)
            curr_size = restart_block.shape[1] - 1

        curr_size += 1
    else:
        print("Left-EOMCC3 iterations did not converge")

    # Normalize <L|R> = 1
    LR = calc_LR(L, R, nocc, nunocc)
    L /= LR
    # Save the final converged root in an excitation tuple
    L = (L[:n1].reshape(nunocc, nocc), L[n1:n1+n2].reshape(nunocc, nunocc, nocc, nocc), L[n1+n2:].reshape(nunocc, nunocc, nunocc, nocc, nocc, nocc))
    return L, omega
