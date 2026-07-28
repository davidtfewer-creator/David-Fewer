"""Validate the Python engine against the workbook's cached Model NVDA results."""
import csv
from datetime import date
from engine import Params, run_model

TARGETS = dict(annual_return=1.5020325756392054, total_buys=186,
               stop_loss_exits=0, terminal_fund=7_520_461.832403965)


def load(path):
    dates, O, H, L, C = [], [], [], [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            dates.append(date.fromisoformat(row['date']))
            O.append(float(row['open'])); H.append(float(row['high']))
            L.append(float(row['low']));  C.append(float(row['close']))
    return dates, O, H, L, C


if __name__ == '__main__':
    dates, O, H, L, C = load('nvda_ohlc.csv')
    print(f'Loaded {len(dates)} rows: {dates[0]} -> {dates[-1]}')
    res = run_model(dates, O, H, L, C, Params())
    print('\n=== ENGINE vs WORKBOOK ===')
    rows = [
        ('Terminal fund', res.terminal_fund, TARGETS['terminal_fund']),
        ('Annual return', res.annual_return, TARGETS['annual_return']),
        ('Total buys',    res.total_buys,    TARGETS['total_buys']),
        ('Stop-loss exits', res.stop_loss_exits, TARGETS['stop_loss_exits']),
    ]
    ok = True
    for name, got, want in rows:
        if isinstance(want, float):
            match = abs(got - want) < 1e-6 * max(1, abs(want))
            print(f'  {name:18s} engine={got:>18.6f}  workbook={want:>18.6f}  {"OK" if match else "MISMATCH"}')
        else:
            match = got == want
            print(f'  {name:18s} engine={got:>18}  workbook={want:>18}  {"OK" if match else "MISMATCH"}')
        ok = ok and match
    print(f'  (Bayes buys={res.bayes_buys}, OU buys={res.ou_buys})')
    print('\nRESULT:', 'VALIDATED — reproduces workbook' if ok else 'DOES NOT MATCH — engine needs fixing')
