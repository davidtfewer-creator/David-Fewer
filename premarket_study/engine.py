"""
Faithful Python replica of the 'Model NVDA' sheet (Hybrid Bayesian / OU model).

Row-by-row reproduction of the Excel recursion so we can experiment with signal
substitutions (pre-market VWAP vs previous close) off-workbook. Validated against
the workbook's cached results before any experiment is trusted.

Column map (Excel 'Model NVDA' -> here):
  B Open, C High, D Low, E Close, F Range=High-Low, G ATH=running max(High)
  Bayesian Kalman local-linear-trend: H..W
  Tranche 1 (Bayes) accounting: Y..AE, buy price X
  Tranche 2 (OU) accounting: AF..AL, buy price AM
  OU machinery: AX mean, AY AR(1), AZ sigma, BA forecast
"""
from dataclasses import dataclass, field
from datetime import date
import math


@dataclass
class Params:
    lam: float = 0.604475      # observation-noise scale on daily range
    phi_L: float = 0.320751    # level process-noise scale
    psi: float = 0.007398      # slope process-noise scale
    k: float = 1.140966        # Bayes bid buffer (sigmas below fair value)
    premium: float = 0.017306  # Bayes take-profit premium (x prev close)
    peak_cap: float = 0.019635 # Bayes bid cap below running peak
    comm: float = 0.005        # commission $/share
    capital: float = 1_000_000
    interest: float = 0.0314   # IBKR interest pa on idle cash
    stop_days: int = 50        # calendar-day stop-loss
    bayes_pct: float = 0.5     # capital split to the Bayes tranche
    ou_W: int = 51             # OU lookback window
    ou_buf_k: float = 0.907335 # OU bid buffer (sigmas below forecast)
    ou_prem: float = 0.024772  # OU take-profit premium (x prev close)
    ou_cap: float = 0.056198   # OU bid cap below running peak
    years: float = 2.2         # annualisation horizon (matches workbook)


@dataclass
class Result:
    terminal_fund: float
    profit: float
    annual_return: float
    total_buys: int
    bayes_buys: int
    ou_buys: int
    stop_loss_exits: int
    fundY_final: float
    fundAF_final: float
    sharpe: float = 0.0          # annualised, on combined-book daily equity returns
    max_drawdown: float = 0.0    # peak-to-trough on combined-book equity
    frames: dict = field(default_factory=dict)  # optional per-row arrays for inspection


def run_model(dates, O, H, L, C, p: Params, ou_sigma='level',
              bayes_signal=None, ou_anchor=None, open_cap=None,
              bayes_gain=0.0, collect=False, same_day_exit=True,
              cc_up=None, cc_down=None) -> Result:
    """
    dates: list[date]; O/H/L/C: list[float]. All length N, aligned.

    Signal-injection hooks (all default to the baseline previous-close behaviour):
      open_cap[i]    -> value used as the O_t cap in BOTH bids (default O[i], the true open)
      ou_anchor[i]   -> 'current price' fed to the OU forecast (default C[i-1], prev close)
      bayes_signal[i]-> reserved for the Bayes leg experiment (extra Kalman obs); unused in baseline

    Pass None to use the baseline; pass a list to override per row.
    """
    N = len(O)
    def oc(i):   # open cap
        return O[i] if open_cap is None else open_cap[i]

    # --- derived series ---
    F = [H[i] - L[i] for i in range(N)]
    G = [0.0] * N
    G[0] = H[0]
    for i in range(1, N):
        G[i] = max(H[i], G[i - 1])

    qL = [(p.phi_L * F[i]) ** 2 for i in range(N)]
    qb = [(p.psi   * F[i]) ** 2 for i in range(N)]
    r  = [(p.lam   * F[i]) ** 2 for i in range(N)]

    # --- Kalman state ---
    Lvl = [0.0] * N; Slp = [0.0] * N
    P11 = [0.0] * N; P12 = [0.0] * N; P22 = [0.0] * N
    W   = [0.0] * N
    Lvl[0] = C[0]; Slp[0] = 0.0
    P11[0] = r[0]; P12[0] = 0.0; P22[0] = r[0]
    W[0] = math.sqrt(P11[0] + 2 * P12[0] + P22[0] + qL[0] + r[0])
    for i in range(1, N):
        Kpred = Lvl[i - 1] + Slp[i - 1]
        P11m = P11[i - 1] + 2 * P12[i - 1] + P22[i - 1] + qL[i]
        P12m = P12[i - 1] + P22[i - 1]
        P22m = P22[i - 1] + qb[i]
        S = P11m + r[i]
        KL = P11m / S
        Kb = P12m / S
        Lvl[i] = Kpred + KL * (C[i] - Kpred)
        Slp[i] = Slp[i - 1] + Kb * (C[i] - Kpred)
        P11[i] = (1 - KL) * P11m
        P12[i] = (1 - KL) * P12m
        P22[i] = P22m - P12m ** 2 / S
        W[i] = math.sqrt(P11[i] + 2 * P12[i] + P22[i] + qL[i] + r[i])

    # --- Bayes bid X (row>=1) ---
    # Bayes fair value = Kalman one-step prediction, optionally nudged toward a fresher
    # morning signal (PM-VWAP or the open): fair' = fair + gain*(signal - fair). The
    # filter's own learning still runs off realised closes; only today's bid is refined.
    X = [None] * N
    for i in range(1, N):
        fair = Lvl[i - 1] + Slp[i - 1]
        if bayes_signal is not None and bayes_signal[i] is not None:
            fair = fair + bayes_gain * (bayes_signal[i] - fair)
        X[i] = min(fair - p.k * W[i - 1], oc(i), G[i - 1] * (1 - p.peak_cap))

    # --- OU machinery + bid AM (row>=W) ---
    OUmean = [None] * N; OUar = [None] * N; OUsig = [None] * N; OUf = [None] * N
    AM = [None] * N
    Wn = p.ou_W
    for i in range(N):
        if i < Wn:
            continue
        win = C[i - Wn:i]                       # last W closes
        OUmean[i] = sum(win) / Wn
        y = C[i - Wn + 1:i]                     # AR(1) regression
        x = C[i - Wn:i - 1]
        n = len(x)
        mx = sum(x) / n; my = sum(y) / n
        num = sum((x[j] - mx) * (y[j] - my) for j in range(n))
        den = sum((x[j] - mx) ** 2 for j in range(n))
        slope = num / den if den != 0 else 0.0
        OUar[i] = min(max(slope, 0.0), 0.99)    # MEDIAN(0, slope, 0.99)
        mean_w = OUmean[i]
        if ou_sigma == 'level':
            # deployed: dispersion of the price LEVEL about the window mean. On a trending name
            # that measures the trend, not the innovation, so the buffer inflates precisely when
            # the stock is running.
            OUsig[i] = math.sqrt(sum((v - mean_w) ** 2 for v in win) / Wn)   # STDEVP
        elif ou_sigma == 'resid':
            # residual of the fitted AR(1): what the reversion model cannot explain
            a = OUar[i]
            e = [win[j] - (mean_w + a * (win[j-1] - mean_w)) for j in range(1, Wn)]
            me = sum(e) / len(e)
            OUsig[i] = math.sqrt(sum((v - me) ** 2 for v in e) / len(e))
        elif ou_sigma == 'detrend':
            # residual about a linear trend through the window, with the mean re-anchored to the
            # fitted value at the window end rather than the arithmetic average
            t = list(range(Wn)); mt = (Wn - 1) / 2.0
            dn = sum((t[j] - mt) ** 2 for j in range(Wn))
            b = sum((t[j] - mt) * (win[j] - mean_w) for j in range(Wn)) / dn if dn else 0.0
            a0 = mean_w - b * mt
            r = [win[j] - (a0 + b * t[j]) for j in range(Wn)]
            OUsig[i] = math.sqrt(sum(v * v for v in r) / Wn)
            OUmean[i] = a0 + b * (Wn - 1); mean_w = OUmean[i]
        else:
            raise ValueError(ou_sigma)
        anchor = C[i - 1] if ou_anchor is None else ou_anchor[i]
        OUf[i] = OUmean[i] + OUar[i] * (anchor - OUmean[i])
        AM[i] = min(OUf[i] - p.ou_buf_k * OUsig[i], oc(i), G[i - 1] * (1 - p.ou_cap))

    # --- month-end flags (AO): 1 if last row or month changes next row ---
    AO = [0] * N
    for i in range(N):
        if i == N - 1 or dates[i].month != dates[i + 1].month:
            AO[i] = 1
    AN = [1] + [(dates[i] - dates[i - 1]).days for i in range(1, N)]

    def run_tranche(buy_price, prem, init_fund, interest_start=1, cc_up=None, cc_down=None):
        # cc_up / cc_down: close-conditional premium. On the fill day the target is the usual
        # bid + prevclose*prem. At that day's CLOSE we observe where the stock finished relative
        # to the fill and amend the resting sell for the following days: multiply the premium by
        # cc_up if it closed above the fill, cc_down if at/below. No lookahead -- the close is
        # known before the amendment takes effect. None/None reproduces the fixed-premium model.
        cc = cc_up is not None and cc_down is not None
        buy_px = None; prem_amt = None; adjusted = True
        # interest_start: first row index that accrues interest. In the workbook the
        # Bayes fund is initialised at row 8 (accrues from row 9 -> i=1) while the OU
        # fund is initialised one row later at row 9 (AR9=0, accrues from row 10 -> i=2).
        Y = [0.0] * N; AA = [0.0] * N; AB = [0.0] * N
        AD = [0] * N; AE = [0] * N; Z = [0] * N
        AC = [None] * N; AV = [None] * N
        AP = [0.0] * N; AQ = [0.0] * N
        Y[0] = init_fund
        for i in range(1, N):
            # interest accrual on idle cash
            basis = (AA[i - 1] * (AC[i - 1] - p.comm)) if AD[i - 1] == 1 else Y[i - 1]
            accrue = (basis * p.interest * AN[i] / 365.0
                      if (AE[i - 1] == 0 and i >= interest_start) else 0.0)
            AP[i] = (0.0 if AQ[i - 1] > 0 else AP[i - 1]) + accrue
            AQ[i] = AP[i] if (AO[i] == 1 and AE[i - 1] == 0) else 0.0
            # fund
            Y[i] = ((AA[i - 1] * (AC[i - 1] - p.comm)) if AD[i - 1] == 1 else Y[i - 1]) + AQ[i]
            bp = buy_price[i]
            # buy flag: not holding & low reached the bid
            Z[i] = 1 if (AE[i - 1] == 0 and bp is not None and L[i] <= bp) else 0
            AA[i] = (Y[i] / (bp + p.comm)) if Z[i] == 1 else (AA[i - 1] if AE[i - 1] == 1 else 0.0)
            if Z[i] == 1:
                buy_px = bp; prem_amt = C[i - 1] * prem
                AB[i] = bp + prem_amt
                adjusted = not cc                      # pending amendment at tonight's close
            elif AE[i - 1] == 1:
                if not adjusted:
                    # first session after the fill: C[i-1] is the fill day's close
                    mult = cc_up if C[i - 1] > buy_px else cc_down
                    AB[i] = buy_px + prem_amt * mult
                    adjusted = True
                else:
                    AB[i] = AB[i - 1]
            else:
                AB[i] = 0.0
            # stop-loss condition
            held = AE[i - 1] == 1 and AV[i - 1] is not None and (dates[i] - AV[i - 1]).days >= p.stop_days
            # sell flag. target exit allowed for positions held from a prior day, and for a
            # position bought today per same_day_exit:
            #   True     -> allow (optimistic; assumes the peak followed the dip)
            #   False    -> forbid (conservative floor)
            #   'at_open'-> allow only if the buy filled AT the open (bp>=O): the open is the
            #               first price, so any later high provably came after the buy -> the
            #               same-day exit is legitimate, not an assumption. Intraday-dip buys
            #               (bp<O) stay forbidden (genuinely ambiguous without minute data).
            #   callable -> ask it (used for minute-data verified fills): f(i, bid, target)
            if same_day_exit == 'at_open':
                sd_ok = (Z[i] == 1 and bp is not None and bp >= O[i] - 1e-9)
            elif callable(same_day_exit):
                sd_ok = (Z[i] == 1 and bp is not None and same_day_exit(i, bp, AB[i]))
            else:
                sd_ok = (Z[i] == 1 and same_day_exit)
            tgt_ok = (AE[i - 1] == 1) or sd_ok
            AD[i] = 1 if ((tgt_ok and H[i] >= AB[i]) or held) else 0
            # actual sale price
            if AD[i] == 1:
                AC[i] = O[i] if (held and H[i] < AB[i]) else AB[i]
            else:
                AC[i] = None
            # hold flag
            if AE[i - 1] == 1:
                AE[i] = 0 if AD[i] == 1 else 1
            else:
                AE[i] = 1 if (Z[i] == 1 and AD[i] == 0) else 0
            # buy date
            AV[i] = dates[i] if Z[i] == 1 else (AV[i - 1] if AE[i - 1] == 1 else None)
        stops = sum(1 for i in range(N) if AD[i] == 1 and AC[i] is not None and AC[i] < AB[i])
        return dict(Y=Y, AA=AA, AB=AB, AC=AC, AD=AD, AE=AE, Z=Z, AV=AV, stops=stops,
                    interest=sum(AQ), AP=AP, AQ=AQ, AO=AO, AN=AN)

    t1 = run_tranche(X,  p.premium, p.capital * p.bayes_pct,        interest_start=1,
                     cc_up=cc_up, cc_down=cc_down)
    t2 = run_tranche(AM, p.ou_prem, p.capital * (1 - p.bayes_pct),  interest_start=2,
                     cc_up=cc_up, cc_down=cc_down)

    fY = t1['Y'][-1]; fAF = t2['Y'][-1]
    terminal = fY + fAF
    profit = terminal - p.capital
    ann = (terminal / p.capital) ** (1 / p.years) - 1
    bayes_buys = sum(t1['Z']); ou_buys = sum(t2['Z'])

    # combined-book equity curve (BC/BD in the sheet): shares*close if holding else fund
    equity = [0.0] * N
    for i in range(N):
        e1 = t1['AA'][i] * C[i] if t1['AE'][i] == 1 else t1['Y'][i]
        e2 = t2['AA'][i] * C[i] if t2['AE'][i] == 1 else t2['Y'][i]
        equity[i] = e1 + e2
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, N) if equity[i - 1] > 0]
    if len(rets) > 1:
        mu = sum(rets) / len(rets)
        var = sum((x - mu) ** 2 for x in rets) / (len(rets) - 1)
        sd = math.sqrt(var)
        sharpe = (mu / sd * math.sqrt(252)) if sd > 0 else 0.0
    else:
        sharpe = 0.0
    peak = -1e30; maxdd = 0.0
    for e in equity:
        peak = max(peak, e)
        if peak > 0:
            maxdd = max(maxdd, (peak - e) / peak)

    frames = {}
    if collect:
        frames = dict(F=F, G=G, W=W, X=X, AM=AM, OUmean=OUmean, OUar=OUar,
                      OUsig=OUsig, OUf=OUf, t1=t1, t2=t2, equity=equity,
                      Lvl=Lvl, Slp=Slp)
    return Result(terminal, profit, ann, bayes_buys + ou_buys, bayes_buys, ou_buys,
                  t1['stops'] + t2['stops'], fY, fAF, sharpe, maxdd, frames)
