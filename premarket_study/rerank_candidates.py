"""
Re-rank the candidate names on an estimated verified basis.

No intraday data exists for the candidates, so their fills cannot be verified directly. Instead:
  1. On the ten book names (which ARE verified) measure, per name,
         phi   = fraction of all trades that are same-day round trips   (daily data alone)
         rho   = verified fill rate                                     (intraday)
         R     = retention = (1+verified ann)/(1+optimistic ann)
  2. Regress R on the fictitious fraction  f = phi*(1-rho)  -> a calibration curve.
  3. For each candidate compute phi from daily bars, assume the book mean rho, and apply the
     calibration to estimate its verified return. Report the at-open floor as a hard lower bound.

Estimates are labelled as such: the honest output is a RANKING plus a bracket, not a point
forecast.
"""
import statistics, datetime
from stop_sweep import load_book
from engine import run_model
from five_min import make_checker as fm
from minute_engine import make_checker as nv
import newcands, newfeed
from engine import Params

book_data, book_params, _ = load_book()
BOOK = list(book_data)


def same_day_fraction(dts, O, H, L, C, p):
    r = run_model(dts, O, H, L, C, p, collect=True)
    tot = sd = 0
    for tk in ('t1', 't2'):
        t = r.frames[tk]
        for i in range(len(C)):
            if t['Z'][i] == 1:
                tot += 1
                if t['AD'][i] == 1: sd += 1
    return (sd/tot if tot else 0), r


# ---------- 1. calibration from the verified book ----------
print('=== CALIBRATION on the ten verified names ===')
print(f'{"name":6s}{"same-day phi":>13s}{"fill rho":>10s}{"fictitious f":>14s}{"retention":>11s}')
print('-'*54)
pts = []
for s in BOOK:
    dts, O, H, L, C = book_data[s]; p = book_params[s]
    chk = nv(dts, O)[0] if s == 'NVDA' else fm(s, dts, O)[0]
    phi, r = same_day_fraction(dts, O, H, L, C, p)
    real = fake = 0
    for tk, bids in (('t1', r.frames['X']), ('t2', r.frames['AM'])):
        t = r.frames[tk]
        for i in range(len(C)):
            if t['Z'][i] == 1 and t['AD'][i] == 1 and bids[i] is not None:
                if chk(i, bids[i], t['AB'][i]): real += 1
                else: fake += 1
    rho = real/(real+fake) if real+fake else 0
    ro = run_model(dts, O, H, L, C, p, same_day_exit=True).annual_return
    rv = run_model(dts, O, H, L, C, p, same_day_exit=chk).annual_return
    R = (1+rv)/(1+ro)
    f = phi*(1-rho)
    pts.append((f, R))
    print(f'{s:6s}{phi*100:>12.0f}%{rho*100:>9.0f}%{f*100:>13.0f}%{R:>11.3f}')

# least squares R = a + b*f
n = len(pts); mf = statistics.mean(x[0] for x in pts); mR = statistics.mean(x[1] for x in pts)
b = sum((x[0]-mf)*(x[1]-mR) for x in pts)/sum((x[0]-mf)**2 for x in pts)
a = mR - b*mf
MEAN_RHO = 0.57
print(f'\ncalibration: retention = {a:.3f} {b:+.3f} * fictitious_fraction   (mean rho = {MEAN_RHO:.2f})')


# ---------- 2. candidates ----------
def report(title, names, loader):
    print(f'\n=== {title} ===')
    print(f'{"name":6s}{"optimistic":>12s}{"same-day":>10s}{"est. verified":>15s}'
          f'{"at-open floor":>15s}{"trades/yr":>11s}')
    print('-'*69)
    rows = []
    for s in names:
        dts, O, H, L, C, p = loader(s)
        phi, r = same_day_fraction(dts, O, H, L, C, p)
        ro = run_model(dts, O, H, L, C, p, same_day_exit=True)
        ra = run_model(dts, O, H, L, C, p, same_day_exit='at_open').annual_return
        f = phi*(1-MEAN_RHO)
        R = max(min(a + b*f, 1.0), 0.02)
        est = (1+ro.annual_return)*R - 1
        yrs = (dts[-1]-dts[0]).days/365.25
        rows.append((s, ro.annual_return, phi, est, ra, ro.total_buys/yrs))
    for s, o, phi, est, ra, tr in sorted(rows, key=lambda x: -x[3]):
        print(f'{s:6s}{o*100:>11.0f}%{phi*100:>9.0f}%{est*100:>14.0f}%{ra*100:>14.0f}%{tr:>11.0f}')
    return rows


def cand_loader(s):
    dts, O, H, L, C, p, _ = newcands.load(s)
    return dts, O, H, L, C, p

CANDS = ['CCL', 'MU', 'CVNA', 'LLY']
report('CANDIDATE NAMES (CCL / MU / CVNA / LLY)', CANDS, cand_loader)

# diversifier set: fitted params live in the earlier study; refit is out of scope here, so we
# use each name's own optimised params from the diversifier run where available.
print('\nNote: diversifier set (OXY, DVN, FSLR, MRNA ...) was fitted with freshly optimised')
print('parameters that did not survive walk-forward; a verified re-rank of that set requires')
print('intraday data and is deferred.')
