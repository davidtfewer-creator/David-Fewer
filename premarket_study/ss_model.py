"""
Schwartz-Smith two-factor model as a trading sleeve.

The book's two engines approximate a decomposition without ever writing it down: the Kalman
local-linear-trend filter tracks the permanent level and the OU sleeve fades the transient
deviation. Schwartz-Smith states that decomposition directly and estimates both jointly:

    log S_t = chi_t + xi_t
    d(chi)  = -kappa*chi dt + sig_chi dW1        short-term, mean-reverting to zero
    d(xi)   =  mu dt      + sig_xi  dW2          long-term equilibrium, a random walk with drift
    corr(dW1, dW2) = rho

In discrete time this is a linear Gaussian state-space model, so one Kalman filter estimates both
factors and their joint uncertainty. The parameters are fitted by maximum likelihood on the PRICE
series -- not on trading returns -- which is the honest way round: the filter is estimated as a
model of the price, then the trading rule is laid on top.

The entry then mirrors the existing sleeves exactly:

    fair_t   = exp(xi_t + mu + phi*chi_t)        one-step-ahead forecast, phi = exp(-kappa)
    bid_t    = min(fair_t - k*sigma_t, O_t, ATH*(1-cap))
    target_t = bid_t + prem*C_{t-1}

so the only thing that differs from the Bayes and OU sleeves is where the fair value and its
uncertainty come from. Everything downstream -- fills, premium exit, carry, stop, commission,
interest -- is shared, which is what makes the three directly comparable and blendable.
"""
import numpy as np
from scipy.optimize import minimize


def ss_filter(y, th, dt=1.0):
    """Kalman filter for the two-factor model. y = log prices.

    Returns the one-step-ahead forecast of log price, its standard deviation, and the
    log-likelihood. State is [chi, xi]."""
    kappa, s_chi, s_xi, mu, rho, s_v = th
    phi = np.exp(-kappa*dt)
    # transition
    F = np.array([[phi, 0.0], [0.0, 1.0]])
    c = np.array([0.0, mu*dt])
    # process covariance
    v_chi = s_chi**2*(1-np.exp(-2*kappa*dt))/(2*kappa) if kappa > 1e-8 else s_chi**2*dt
    v_xi = s_xi**2*dt
    cov = rho*s_chi*s_xi*(1-np.exp(-kappa*dt))/kappa if kappa > 1e-8 else rho*s_chi*s_xi*dt
    Q = np.array([[v_chi, cov], [cov, v_xi]])
    H = np.array([1.0, 1.0])
    R = s_v**2

    n = len(y)
    x = np.array([0.0, y[0]])
    P = np.array([[v_chi*4, 0.0], [0.0, v_xi*4]])
    fc = np.full(n, np.nan); sd = np.full(n, np.nan)
    ll = 0.0
    for t in range(n):
        xp = F @ x + c
        Pp = F @ P @ F.T + Q
        f = H @ xp                      # forecast of log price
        s = H @ Pp @ H + R
        if s <= 0 or not np.isfinite(s): return fc, sd, -1e12
        fc[t] = f; sd[t] = np.sqrt(s)
        e = y[t] - f
        ll += -0.5*(np.log(2*np.pi*s) + e*e/s)
        K = (Pp @ H)/s
        x = xp + K*e
        P = Pp - np.outer(K, H @ Pp)
    return fc, sd, ll


BOUNDS = [(0.005, 0.60),     # kappa: reversion speed per day (half-life 1.2 .. 140 days)
          (0.005, 0.30),     # sigma_chi
          (0.002, 0.15),     # sigma_xi
          (-0.01, 0.01),     # mu (daily drift of the equilibrium)
          (-0.95, 0.95),     # rho
          (1e-4, 0.05)]      # measurement noise
X0 = [0.05, 0.05, 0.02, 0.0005, -0.3, 0.005]


def fit_ss(logp, seeds=3):
    """Maximum likelihood on the price series alone."""
    best = None
    rng = np.random.default_rng(7)
    for j in range(seeds):
        x0 = X0 if j == 0 else [lo + (hi-lo)*u for (lo, hi), u
                                in zip(BOUNDS, rng.random(len(BOUNDS)))]
        r = minimize(lambda th: -ss_filter(logp, th)[2], x0, bounds=BOUNDS,
                     method='L-BFGS-B', options=dict(maxiter=300))
        if best is None or r.fun < best.fun: best = r
    return list(best.x), -best.fun


def ss_signal(C, th):
    """Fair value and its standard deviation in PRICE units, one step ahead."""
    y = np.log(np.asarray(C, dtype=float))
    fc, sd, _ = ss_filter(y, th)
    fair = np.exp(fc + 0.5*sd**2)          # lognormal mean
    sig = fair*np.sqrt(np.expm1(sd**2))    # lognormal standard deviation
    return fair, sig
