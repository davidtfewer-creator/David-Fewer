"""
Python 'formula mirror' of the laddered Bayes tranche, written so each variable is computed
EXACTLY as the Excel cell formula will be (same references, same order). If this reproduces
ladder_engine's Bayes tranche, the recursion is correct and can be translated to worksheet
formulas cell-for-cell. Config C: depths [1,1.3,1.7]xk, weights [.8,.15,.05], first-rung TP.
"""
from engine import Params, run_model
from ladder_engine import run_ladder
from validate_nvda import load


def mirror(dates, O, H, L, C, p, m=(1.0, 1.3, 1.7), w=(0.80, 0.15, 0.05)):
    f = run_model(dates, O, H, L, C, p, collect=True).frames
    Lvl, Slp, W, G = f['Lvl'], f['Slp'], f['W'], f['G']
    N = len(C); k, pc, prem, comm, rate, stop = p.k, p.peak_cap, p.premium, p.comm, p.interest, p.stop_days
    m1, m2, m3 = m; w1, w2, w3 = w
    # per-day state arrays (like sheet columns)
    FUND = [0.0]*N; SH = [0.0]*N; F1 = [0]*N; F2 = [0]*N; F3 = [0]*N
    B1 = [0.0]*N; B2 = [0.0]*N; B3 = [0.0]*N; ANC = [0.0]*N; BD = [None]*N
    NB = [0]*N; EQ = [0.0]*N
    FUND[0] = p.capital * p.bayes_pct; EQ[0] = FUND[0]
    for i in range(1, N):
        fair = Lvl[i-1] + Slp[i-1]; sig = W[i-1]; peak = G[i-1]*(1-pc)
        pr1 = min(fair - m1*k*sig, O[i], peak)
        pr2 = min(fair - m2*k*sig, O[i], peak)
        pr3 = min(fair - m3*k*sig, O[i], peak)
        fresh = SH[i-1] <= 0
        days = (dates[i]-dates[i-1]).days
        f0 = FUND[i-1] * (1 + rate*days/365.0)
        b1 = f0*w1 if fresh else B1[i-1]
        b2 = f0*w2 if fresh else B2[i-1]
        b3 = f0*w3 if fresh else B3[i-1]
        pf1 = 0 if fresh else F1[i-1]; pf2 = 0 if fresh else F2[i-1]; pf3 = 0 if fresh else F3[i-1]
        avail = f0                                            # sequential fund-availability guard
        fill1 = 1 if (pf1 == 0 and L[i] <= pr1 and avail >= b1 - 1e-9) else 0
        avail -= fill1 * b1
        fill2 = 1 if (pf2 == 0 and L[i] <= pr2 and avail >= b2 - 1e-9) else 0
        avail -= fill2 * b2
        fill3 = 1 if (pf3 == 0 and L[i] <= pr3 and avail >= b3 - 1e-9) else 0
        dsh = fill1*b1/(pr1+comm) + fill2*b2/(pr2+comm) + fill3*b3/(pr3+comm)
        dcash = fill1*b1 + fill2*b2 + fill3*b3
        sh_mid = (0.0 if fresh else SH[i-1]) + dsh
        fund_mid = f0 - dcash
        f1m = max(pf1, fill1); f2m = max(pf2, fill2); f3m = max(pf3, fill3)
        anc = max(0.0 if fresh else ANC[i-1], fill1*pr1, fill2*pr2, fill3*pr3)
        tgt = anc + C[i-1]*prem
        bd = (dates[i] if dsh > 0 else None) if fresh else (BD[i-1] if SH[i-1] > 0 else None)
        dh = (dates[i]-bd).days if (sh_mid > 0 and bd is not None) else -1
        stop_hit = dh >= stop
        exit_ = 1 if (sh_mid > 0 and (H[i] >= tgt or stop_hit)) else 0
        if exit_:
            sale = O[i] if (stop_hit and H[i] < tgt) else tgt
            FUND[i] = fund_mid + sh_mid*(sale - comm); SH[i] = 0.0
            F1[i] = F2[i] = F3[i] = 0; ANC[i] = 0.0; BD[i] = None
        else:
            FUND[i] = fund_mid; SH[i] = sh_mid
            F1[i], F2[i], F3[i] = f1m, f2m, f3m; ANC[i] = anc; BD[i] = bd
        B1[i], B2[i], B3[i] = b1, b2, b3
        NB[i] = fill1+fill2+fill3
        EQ[i] = FUND[i] + SH[i]*C[i]
    return dict(FUND=FUND, SH=SH, EQ=EQ, buys=sum(NB))


if __name__ == '__main__':
    dates, O, H, L, C = load('nvda_ohlc.csv'); p = Params()
    mir = mirror(dates, O, H, L, C, p)
    r = run_ladder(dates, O, H, L, C, p, [p.k, 1.3*p.k, 1.7*p.k], [p.ou_buf_k],
                   'first', [0.80, 0.15, 0.05], None)
    eng_fund = r['bayes_fund']; eng_eq = r['eqB']; eng_buys = r['bayes_trades']
    N = len(C)
    dfund = max(abs(mir['FUND'][i]-eng_fund[i]) for i in range(N))
    deq = max(abs(mir['EQ'][i]-eng_eq[i]) for i in range(N))
    print('MIRROR vs ENGINE (Bayes tranche, NVDA, config C):')
    print(f'  terminal fund: mirror={mir["FUND"][-1]:.2f}  engine={eng_fund[-1]:.2f}')
    print(f'  max |Δfund| over all days: {dfund:.6f}')
    print(f'  max |Δequity| over all days: {deq:.6f}')
    print(f'  Bayes buys: mirror={mir["buys"]}  engine={eng_buys}')
    ok = dfund < 1e-6 and deq < 1e-6 and mir['buys'] == eng_buys
    print('  RESULT:', 'MIRROR MATCHES ENGINE — recursion verified' if ok else 'MISMATCH')
