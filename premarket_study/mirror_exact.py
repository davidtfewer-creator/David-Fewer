"""Exact line-by-line replica of ladder_engine._tranche for the Bayes sleeve, recording the
per-day state needed to map onto sheet columns. Guaranteed == engine (same code path)."""
from engine import Params, run_model


def mirror_exact(dates, O, H, L, C, p, m=(1.0, 1.3, 1.7), w=(0.80, 0.15, 0.05)):
    f = run_model(dates, O, H, L, C, p, collect=True).frames
    Lvl, Slp, W, G = f['Lvl'], f['Slp'], f['W'], f['G']
    N = len(C); k, pc, prem, comm, rate, stop = p.k, p.peak_cap, p.premium, p.comm, p.interest, p.stop_days
    pot0 = p.capital * p.bayes_pct
    fund = pot0; shares = 0.0; cost_px = 0.0; filled = set(); incyc = False; bd = None
    anchor_px = 0.0; budgets = None
    REC = {key: [None]*N for key in
           ('fresh', 'f0', 'pr', 'B', 'fills', 'fund', 'sh', 'anc', 'bd', 'tgt', 'sale', 'exit', 'nb', 'eq')}
    for i in range(N):
        if i > 0:
            fund += fund * rate * (dates[i]-dates[i-1]).days / 365.0
        REC['f0'][i] = fund
        REC['fresh'][i] = (not incyc)
        rp = None
        fills = [0, 0, 0]; sale = None; did_exit = 0
        if i >= 1:
            fair = Lvl[i-1] + Slp[i-1]; sig = W[i-1]; peak = G[i-1]*(1-pc)
            rp = [min(fair - mm*k*sig, O[i], peak) for mm in m]
            if not incyc:
                budgets = [fund*ww for ww in w]; filled = set(); anchor_px = 0.0
            for j, price in enumerate(rp):
                if j in filled or price is None or price <= 0:
                    continue
                bj = budgets[j]
                if L[i] <= price and fund >= bj - 1e-9 and bj > 0:
                    sh = bj/(price+comm); shares += sh; cost_px += sh*price; fund -= bj
                    anchor_px = max(anchor_px, price); filled.add(j); fills[j] = 1
                    if not incyc:
                        incyc = True; bd = dates[i]
            if incyc and shares > 0:
                target = anchor_px + C[i-1]*prem
                held = (dates[i]-bd).days >= stop
                sell = target if H[i] >= target else (O[i] if held else None)
                if sell is not None:
                    fund += shares*(sell-comm); sale = sell; did_exit = 1
                    shares = 0.0; cost_px = 0.0; filled = set(); incyc = False; bd = None
        REC['pr'][i] = rp; REC['B'][i] = list(budgets) if budgets else None
        REC['fills'][i] = fills; REC['fund'][i] = fund; REC['sh'][i] = shares
        REC['anc'][i] = anchor_px; REC['bd'][i] = bd; REC['sale'][i] = sale
        REC['exit'][i] = did_exit; REC['nb'][i] = sum(fills)
        REC['eq'][i] = fund + shares*C[i]
    REC['buys'] = sum(sum(x) for x in REC['fills'] if x)
    REC['terminal_fund'] = fund
    return REC


if __name__ == '__main__':
    import json
    from ladder_engine import run_ladder
    from multi_stock import params_for
    import verify_all_ladder as V
    pj = json.load(open('params_all.json')); q = V.srcdo['Query']
    print('exact-mirror vs engine (all ten):')
    allok = True
    for s in V.STOCKS:
        i = V.STOCKS.index(s); dts, O, H, L, Cc = [], [], [], [], []
        for row in q.iter_rows(min_row=2, values_only=True):
            d = V.to_date(row[0]); o = row[1+4*i]
            if d is None or not isinstance(o, (int, float)) or o <= 0: continue
            dts.append(d); O.append(o); H.append(row[2+4*i]); L.append(row[3+4*i]); Cc.append(row[4+4*i])
        p = params_for(s, pj)
        R = mirror_exact(dts, O, H, L, Cc, p)
        r = run_ladder(dts, O, H, L, Cc, p, [p.k, 1.3*p.k, 1.7*p.k], [p.ou_buf_k], 'first', [0.80, 0.15, 0.05], None)
        ok = abs(R['terminal_fund']-r['bayes_fund'][-1]) < 1e-4 and R['buys'] == r['bayes_trades']
        allok = allok and ok
        print(f'  {s:6s} mirror fund={R["terminal_fund"]:.2f} buys={R["buys"]}  '
              f'engine fund={r["bayes_fund"][-1]:.2f} buys={r["bayes_trades"]}  {"OK" if ok else "X"}')
    print('ALL OK' if allok else 'MISMATCH')
