"""
Extend the pre-market-VWAP open-cap study to all ten names, parameters FROZEN.

Two stages:
  1. validate_all() — engine must reproduce each workbook's cached results
     (annual return, buys, stop-loss exits) before any experiment is trusted.
  2. experiment_all() — per stock, frozen params, compare the live open-cap proxy:
     prev-close vs PM-VWAP (both traded against actual OHLC). Oracle (true open)
     shown as the unattainable ceiling. Plus per-quarter win counts.
"""
import csv, json
from datetime import date
from engine import Params, run_model

STOCKS = ['NVDA','TSM','TSLA','VRT','VST','AVGO','PLTR','RKLB','SOFI','SPOT']


def load_stock(s):
    dates, O, H, L, C, PMV = [], [], [], [], [], []
    with open(f'data_{s}.csv') as f:
        for r in csv.DictReader(f):
            dates.append(date.fromisoformat(r['date']))
            O.append(float(r['open'])); H.append(float(r['high']))
            L.append(float(r['low']));  C.append(float(r['close']))
            PMV.append(float(r['pm_vwap']) if r['pm_vwap'] != '' else None)
    return dates, O, H, L, C, PMV


def params_for(s, pjson):
    p = pjson[s]
    return Params(lam=p['lam'], phi_L=p['phi_L'], psi=p['psi'], k=p['k'],
                  premium=p['premium'], peak_cap=p['peak_cap'], comm=p['comm'],
                  capital=p['capital'], interest=p['interest'], stop_days=int(p['stop']),
                  bayes_pct=p['bayes_pct'], ou_W=int(p['ou_W']), ou_buf_k=p['ou_buf_k'],
                  ou_prem=p['ou_prem'], ou_cap=p['ou_cap'])


def prevC(C):
    return [C[0]] + [C[i-1] for i in range(1, len(C))]


def pm_cap(PMV, C):
    """PM-VWAP cap with prev-close fallback where PM VWAP is missing (SPOT)."""
    pc = prevC(C)
    return [PMV[i] if PMV[i] is not None else pc[i] for i in range(len(C))]


def validate_all(pjson):
    print('=== ENGINE VALIDATION (frozen params vs workbook cached results) ===')
    print(f'{"stock":6s}{"annual (eng/wb)":>26s}{"buys":>12s}{"stops":>10s}   ok')
    allok = True
    for s in STOCKS:
        dates, O, H, L, C, _ = load_stock(s)
        p = params_for(s, pjson)
        r = run_model(dates, O, H, L, C, p)
        c = pjson[s]
        ok = (abs(r.annual_return - c['cache_annual']) < 1e-4 and
              r.total_buys == c['cache_buys'] and r.stop_loss_exits == c['cache_stops'])
        allok = allok and ok
        print(f'{s:6s}  {r.annual_return*100:7.2f}% / {c["cache_annual"]*100:7.2f}%   '
              f'{r.total_buys:4d}/{c["cache_buys"]:<4d}  {r.stop_loss_exits:3d}/{c["cache_stops"]:<3d}   '
              f'{"OK" if ok else "MISMATCH"}')
    print('VALIDATION:', 'ALL PASS' if allok else 'FAILURES PRESENT', '\n')
    return allok


def quarters(dates):
    segs, start = [], 0
    for i in range(1, len(dates)):
        if (dates[i].year, (dates[i].month-1)//3) != (dates[i-1].year, (dates[i-1].month-1)//3):
            segs.append((start, i-1)); start = i
    segs.append((start, len(dates)-1))
    return segs


def experiment_all(pjson):
    print('=== EXPERIMENT: PM-VWAP vs prev-close as the live open cap (frozen params) ===')
    print(f'{"stock":6s}{"oracle":>9s}{"prevC":>9s}{"PM-VWAP":>9s}{"Δreturn":>9s}'
          f'{"prevC Sh":>9s}{"PMV Sh":>8s}{"prevC dd":>9s}{"PMV dd":>8s}{"Q wins":>8s}')
    print('-'*95)
    agg = {'ret_prev':0,'ret_pm':0,'sh_prev':0,'sh_pm':0,'dd_prev':0,'dd_pm':0,
           'stock_wins':0,'q_wins':0,'q_tot':0}
    rows = []
    for s in STOCKS:
        dates, O, H, L, C, PMV = load_stock(s)
        p = params_for(s, pjson)
        pc = prevC(C); pmc = pm_cap(PMV, C)
        oracle = run_model(dates, O, H, L, C, p)
        rp = run_model(dates, O, H, L, C, p, open_cap=pc, collect=True)
        rv = run_model(dates, O, H, L, C, p, open_cap=pmc, collect=True)
        # per-quarter return wins
        eqp, eqv = rp.frames['equity'], rv.frames['equity']
        qw = qt = 0
        for lo, hi in quarters(dates):
            if eqp[lo] <= 0 or eqv[lo] <= 0: continue
            qt += 1
            if (eqv[hi]/eqv[lo]) > (eqp[hi]/eqp[lo]): qw += 1
        win = rv.annual_return > rp.annual_return
        agg['ret_prev'] += rp.annual_return; agg['ret_pm'] += rv.annual_return
        agg['sh_prev'] += rp.sharpe; agg['sh_pm'] += rv.sharpe
        agg['dd_prev'] += rp.max_drawdown; agg['dd_pm'] += rv.max_drawdown
        agg['stock_wins'] += win; agg['q_wins'] += qw; agg['q_tot'] += qt
        print(f'{s:6s}{oracle.annual_return*100:8.1f}%{rp.annual_return*100:8.1f}%'
              f'{rv.annual_return*100:8.1f}%{(rv.annual_return-rp.annual_return)*100:+8.1f}'
              f'{rp.sharpe:9.2f}{rv.sharpe:8.2f}{rp.max_drawdown*100:8.1f}%{rv.max_drawdown*100:7.1f}%'
              f'{qw:5d}/{qt:<2d}')
        rows.append((s, win))
    n = len(STOCKS)
    print('-'*95)
    print(f'{"AVG":6s}{"":9s}{agg["ret_prev"]/n*100:8.1f}%{agg["ret_pm"]/n*100:8.1f}%'
          f'{(agg["ret_pm"]-agg["ret_prev"])/n*100:+8.1f}{agg["sh_prev"]/n:9.2f}{agg["sh_pm"]/n:8.2f}'
          f'{agg["dd_prev"]/n*100:8.1f}%{agg["dd_pm"]/n*100:7.1f}%{agg["q_wins"]:5d}/{agg["q_tot"]:<3d}')
    print(f'\nPM-VWAP cap beats prev-close cap on annual return in '
          f'{agg["stock_wins"]}/{n} stocks, and in {agg["q_wins"]}/{agg["q_tot"]} stock-quarters.')
    print(f'Avg Sharpe {agg["sh_prev"]/n:.2f} -> {agg["sh_pm"]/n:.2f}; '
          f'avg maxDD {agg["dd_prev"]/n*100:.1f}% -> {agg["dd_pm"]/n*100:.1f}%.')


if __name__ == '__main__':
    pjson = json.load(open('params_all.json'))
    if validate_all(pjson):
        experiment_all(pjson)
    else:
        print('Engine does not reproduce all workbook results — fix before trusting the experiment.')
