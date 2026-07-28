"""
Verify the Dashboard's live bid plumbing equals the validated engine, by computing
the engine's NEXT-day (post-last-data) bids and matching the workbook's cached
Dashboard BUY levels. If these match, adding MIN(...,open,...) is correct by
construction (MIN semantics), so no LibreOffice recalc of the huge model is needed.
"""
import math
from engine import Params, run_model
from validate_nvda import load

# workbook cached Dashboard values (uncapped: no open entered)
CACHED = {
    'NVDA': (193.37579927422755, 190.12851428392474),
}

def nextday_bids(dates, O, H, L, C, p):
    r = run_model(dates, O, H, L, C, p, collect=True)
    f = r.frames; i = len(C) - 1
    fair = f['Lvl'][i] + f['Slp'][i]
    ath  = f['G'][i]; sig = f['W'][i]
    bayes = min(fair - p.k * sig, ath * (1 - p.peak_cap))           # uncapped (no open)
    # next-day OU stats over the last W closes (indices i-W+1 .. i), matching Dashboard
    W = p.ou_W
    win = C[i - W + 1:i + 1]
    mean = sum(win) / W
    y = C[i - W + 2:i + 1]; x = C[i - W + 1:i]
    n = len(x); mx = sum(x)/n; my = sum(y)/n
    num = sum((x[j]-mx)*(y[j]-my) for j in range(n)); den = sum((x[j]-mx)**2 for j in range(n))
    ar = min(max(num/den if den else 0.0, 0.0), 0.99)
    sg = math.sqrt(sum((v-mean)**2 for v in win)/W)
    fcst = mean + ar*(C[i] - mean)
    ou = min(fcst - p.ou_buf_k * sg, ath * (1 - p.ou_cap))          # uncapped
    return bayes, ou

if __name__ == '__main__':
    dates, O, H, L, C = load('nvda_ohlc.csv')
    b, o = nextday_bids(dates, O, H, L, C, Params())
    cb, co = CACHED['NVDA']
    print(f'NVDA next-day Bayes BUY: engine={b:.4f}  workbook Dashboard={cb:.4f}  '
          f'diff={b-cb:+.4f}  {"OK" if abs(b-cb)<0.01 else "MISMATCH"}')
    print(f'NVDA next-day OU    BUY: engine={o:.4f}  workbook Dashboard={co:.4f}  '
          f'diff={o-co:+.4f}  {"OK" if abs(o-co)<0.01 else "MISMATCH"}')
