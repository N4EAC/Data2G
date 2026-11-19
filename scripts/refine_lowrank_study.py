"""equalizer.refine's time pass, exact vs low-rank (Woodbury), on captured refine calls (refine_capture.py).

    PYTHONPATH=.:scripts python scripts/refine_lowrank_study.py CALLS.pkl [TOL ...]

Per frame Rt = Q diag(lam) Q^T, keeping lam > TOL * (the window's least observation variance); per carrier
A^-1 = D^-1 - D^-1 U (diag(1/lam) + U^T D^-1 U)^-1 U^T D^-1 with D the observations' variances.
Reports the error in h relative to the exact estimate's own mse, the relative mse error, and the kept rank.
"""
import os
import pickle
import sys

import numpy as np

from data2g import equalizer as EQ


def windows(h_pilot, t_pilot, z, w, t_rows, support, est, bb=EQ.BB_FREQS):
    """refine up to its time pass: the observations (vals, var, times), p_sig and spread."""
    nc = len(bb)
    slack = int(est.get("slack", EQ.SUPPORT_SLACK))
    U, r, _ = EQ._support_basis(np.asarray(bb, dtype=np.float64).tobytes(), int(support[0]), int(support[1]), slack)
    p_sig, spread = est["p_sig"], est.get("filter_spread_hz", est["spread_hz"])
    hs_p = (h_pilot @ np.conj(U)) @ U.T
    d = np.arange(support[0] - slack, support[1] + slack + 1)
    B = np.exp(-2j * np.pi * np.outer(bb, d) / EQ.FS)
    Rf = p_sig / len(d) * (B @ B.conj().T)
    tr = t_rows.ravel()
    rows = np.flatnonzero(np.any(w > 0, axis=1))
    vals_d = np.zeros((len(rows), nc), dtype=np.complex128)
    var_d = np.zeros((len(rows), nc))
    known = w[rows] > 0
    _, group = np.unique(np.packbits(known, axis=1), axis=0, return_inverse=True)
    for gi in np.unique(group):
        sel = np.flatnonzero(group == gi)
        k = known[sel[0]]
        i_ = rows[sel]
        S = Rf[np.ix_(k, k)][None] + (1 / w[i_][:, k])[:, :, None] * np.eye(k.sum())
        G = np.linalg.solve(S, np.broadcast_to(Rf[k], (len(sel), k.sum(), nc))).conj().swapaxes(1, 2)
        vals_d[sel] = np.einsum("nck,nk->nc", G, z[i_][:, k])
        var_d[sel] = np.maximum(p_sig - np.real(np.sum(G * Rf[:, k].conj()[None], axis=2)), 1e-9 * p_sig)
    vals = np.concatenate([hs_p, vals_d])
    var = np.concatenate([np.full((len(hs_p), nc), est["n0"] * r / nc), var_d])
    times = np.concatenate([t_pilot, tr[rows]])
    return vals, var, times, p_sig, spread


def frame(f, vals, var, times, t_rows, p_sig, spread, tol):
    mid = t_rows[f].mean()
    o = np.flatnonzero(np.abs(times - mid) <= EQ.DD_TAPS * EQ.FRAME_S)
    tj, v, D = times[o], vals[o], var[o]  # (J,), (J, NC), (J, NC)
    Rt = p_sig * EQ._doppler_corr(tj[:, None] - tj[None, :], spread)
    Rdp = p_sig * EQ._doppler_corr(t_rows[f][:, None] - tj[None, :], spread)  # (S, J)
    # exact
    A = Rt[None] + D.T[:, :, None] * np.eye(len(o))  # (NC, J, J)
    W = np.linalg.solve(A, np.broadcast_to(Rdp.T[None], (A.shape[0], len(o), Rdp.shape[0])))  # (NC, J, S)
    h0 = np.einsum("cjs,jc->sc", W, v)
    m0 = p_sig - np.einsum("cjs,sj->sc", W, Rdp)
    # Woodbury on the kept eigenpairs
    lam, Q = np.linalg.eigh(Rt)
    keep = lam > tol * D.min()
    Uk, L = Q[:, keep], lam[keep]
    Di = 1 / D  # (J, NC)
    M = np.diag(1 / L)[None] + np.einsum("jr,jc,jq->crq", Uk, Di, Uk)  # (NC, r, r)
    a = np.einsum("jr,jc,sj->crs", Uk, Di, Rdp)  # (NC, r, S)
    q = np.einsum("jr,jc,jc->cr", Uk, Di, v)  # (NC, r)
    Mi_a = np.linalg.solve(M, a)
    h1 = np.einsum("sj,jc,jc->sc", Rdp, Di, v) - np.einsum("crs,cr->sc", Mi_a, q)
    m1 = p_sig - (np.einsum("sj,jc,sj->sc", Rdp, Di, Rdp) - np.einsum("crs,crs->sc", Mi_a, a))
    # reduced-rank GP: h(t) = psi(t) g, g ~ N(0, diag(L)), psi(tj) = U, psi(ts) = Rdp U / L (Nystrom)
    psi = Rdp @ Uk / L  # (S, r)
    q = np.einsum("jr,jc,jc->cr", Uk, Di, v)
    g = np.linalg.solve(M, q[..., None])[..., 0]  # (NC, r)
    h2 = np.einsum("sr,cr->sc", psi, g)
    Mi_psi = np.linalg.solve(M, np.broadcast_to(psi.T[None], (M.shape[0],) + psi.T.shape))  # (NC, r, S)
    m2 = p_sig - np.einsum("sr,r,sr->s", psi, L, psi)[:, None] + np.einsum("sr,crs->sc", psi, Mi_psi)
    return h0, m0, h1, m1, h2, m2, keep.sum(), len(o)


def main():
    calls = pickle.load(open(sys.argv[1], "rb"))
    tols = [float(t) for t in sys.argv[2:]] or [1e-2, 1e-3, 1e-4, 1e-6]
    stats = {t: [] for t in tols}
    meta = []
    for a, k in calls:
        h_pilot, t_pilot, z, w, t_rows, support, est = a[:7]
        if os.environ.get("SPREAD"):  # the time pass at another spread (the clamp's ends)
            est = dict(est, filter_spread_hz=float(os.environ["SPREAD"]))
        vals, var, times, p_sig, spread = windows(h_pilot, t_pilot, z, w, t_rows, support, est, *a[7:], **k)
        meta.append((spread, np.median(var) / p_sig, var.min() / p_sig))
        for f in range(t_rows.shape[0]):
            for t in tols:
                h0, m0, h1, m1, h2, m2, r, J = frame(f, vals, var, times, t_rows, p_sig, spread, t)
                m0 = np.maximum(m0, 1e-12 * p_sig)
                stats[t].append((np.max(np.abs(h1 - h0) ** 2 / m0), np.max(np.abs(m1 - m0) / m0), r, J,
                                 np.max(np.abs(h2 - h0) ** 2 / m0), np.max(np.abs(m2 - m0) / m0)))
    meta = np.array(meta)
    print(f"{len(calls)} refine calls; spread Hz min/median/max {meta[:, 0].min():.2f}/{np.median(meta[:, 0]):.2f}/"
          f"{meta[:, 0].max():.2f}; var/p_sig median {np.median(meta[:, 1]):.3g}, least {meta[:, 2].min():.3g}")
    for t in tols:
        s = np.array(stats[t])
        print(f"tol {t:g}: |dh|^2/mse max {s[:, 0].max():.2e} p99 {np.quantile(s[:, 0], .99):.2e}; "
              f"|dmse|/mse max {s[:, 1].max():.2e}; rank mean {s[:, 2].mean():.1f} max {s[:, 2].max():.0f} of J "
              f"mean {s[:, 3].mean():.1f} max {s[:, 3].max():.0f}")
        print(f"   reduced-rank GP: |dh|^2/mse max {s[:, 4].max():.2e} p99 {np.quantile(s[:, 4], .99):.2e}; "
              f"|dmse|/mse max {s[:, 5].max():.2e}")


if __name__ == "__main__":
    main()
