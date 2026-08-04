"""
Is the Monday anchor advantage real, and is the weekend gap the reason?

The claim: two non-trading days let information accumulate, so the Friday close -> Monday open
transition is a bigger repricing than any weekday-to-weekday transition. The weekly entry rule
prices off the previous week's high/low/close and is CLAMPED at this week's open

    buy = min( mean(m*(prevH+prevL)/2, prevC*w) + log10(prevRange)*g , thisOpen )

so a wide Monday down-gap lowers the entry and improves the fill. That is a mechanism, and a
mechanism makes predictions beyond "Monday scored best in this sample":

  A  the gap should scale with NON-TRADING DAYS, not with the label "Monday". Holiday Tuesdays
     follow a 3-day break and should behave like Mondays. This separates the mechanism from the
     calendar name and is entirely model-free.
  B  the advantage should appear on OTHER STOCKS. Nine names beyond NVDA are independent samples;
     a sample fluke in NVDA has no reason to repeat in them.
  C  it should hold in each sub-period of the NVDA sample, not just on aggregate.
  D  the causal channel should be visible: under a Monday anchor the open clamp should bind more
     often and fills should concentrate on day 1 of the week.

Week grouping is done by shifting dates back `anchor` days and taking the ISO week, so a holiday
does not silently merge two weeks together -- the naive "split when weekday == anchor" rule does,
which distorts exactly the Monday-holiday weeks this test is about.
"""
import datetime, statistics, math, collections
from stop_sweep import load_book
from weekly_mr import P, verify_same_day

data, _params, _cached = load_book()
COMM = 0.005
INTEREST = 0.0314
NAMES = list(data)
DAY = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']


# ----------------------------------------------------------------- week grouping
def group_weeks(dts, anchor):
    """Weeks starting on `anchor` weekday, robust to holidays."""
    wk, cur, key = [], [], None
    for i, d in enumerate(dts):
        k = (d - datetime.timedelta(days=anchor)).isocalendar()[:2]
        if key is None: key = k
        if k != key:
            if cur: wk.append(cur)
            cur = []; key = k
        cur.append(i)
    if cur: wk.append(cur)
    return [w for w in wk if len(w) >= 2]


def wstats(idxs, O, H, L, C):
    return dict(o=O[idxs[0]], h=max(H[i] for i in idxs), l=min(L[i] for i in idxs),
                c=C[idxs[-1]], idxs=idxs)


# ----------------------------------------------------------------- the tranche
def tranche(WS, series, w0, w1, p=P, capital=1.0, verify=None, track=None):
    """One tranche over weeks [w0,w1]. verify=None -> same-day exits disallowed (conservative)."""
    dts, O, H, L, C = series
    fund, shares, holding = capital, 0.0, False
    buy = tgt = None; trades = 0
    if w0 >= len(WS): return capital, 0
    ath = max(H[i] for i in WS[w0]['idxs'])
    for wi in range(w0 + 1, min(w1, len(WS) - 1) + 1):
        prev, cwk = WS[wi - 1], WS[wi]
        ath = max(ath, prev['h'])
        if not holding:
            fund += fund * INTEREST * (dts[cwk['idxs'][-1]] - dts[prev['idxs'][-1]]).days / 365.0
        rng = prev['h'] - prev['l']
        if rng <= 0: continue
        raw = statistics.mean([p['m']*(prev['h']+prev['l'])/2, prev['c']*p['w']]) \
            + math.log10(rng)*p['g']
        Lp = min(raw, cwk['o'])
        if not holding:
            buy = min(Lp, ath*(1 - p['cap'])); tgt = buy + prev['c']*p['prem']
            if track is not None:
                track['weeks'] += 1
                track['clamped'] += (cwk['o'] < raw)
        idxs = cwk['idxs']
        if not holding:
            bd = next((k for k, i in enumerate(idxs) if L[i] <= buy), None)
            if bd is None: continue
            if track is not None:
                track['fills'] += 1; track['fillday'][bd + 1] += 1
                track['fill_clamped'] += (cwk['o'] < raw)
            shares = fund/(buy + COMM); fund = 0.0; holding = True
            for k in range(bd, len(idxs)):
                i = idxs[k]
                if H[i] >= tgt:
                    if k == bd:
                        if verify is None: continue
                        if verify(i, buy, tgt) is False: continue
                    fund = shares*(tgt - COMM); shares = 0.0; holding = False; trades += 1; break
        else:
            for i in idxs:
                if H[i] >= tgt:
                    fund = shares*(tgt - COMM); shares = 0.0; holding = False; trades += 1; break
    last = WS[min(w1, len(WS) - 1)]['idxs'][-1]
    return fund + (shares*C[last] if holding else 0.0), trades


def book(name, anchor, w0=1, w1=None, n=3, stag=1, verify=None, track=None):
    series = data[name]
    dts = series[0]
    WS = [wstats(w, *series[1:]) for w in group_weeks(dts, anchor)]
    if w1 is None: w1 = len(WS) - 1
    tot = 0.0; tr = 0
    for t in range(n):
        f, k = tranche(WS, series, w0 + t*stag, w1, verify=verify, track=track, capital=1.0/n)
        tot += f; tr += k
    yrs = (dts[WS[min(w1, len(WS)-1)]['idxs'][-1]] - dts[WS[w0]['idxs'][0]]).days/365.25
    return (tot)**(1/yrs) - 1, tr, len(WS)


# ----------------------------------------------------------------- A. the mechanism
def gap_table():
    print('=== A. OVERNIGHT REPRICING vs NON-TRADING DAYS (model-free, all 10 names) ===')
    by_day = collections.defaultdict(list)
    by_gapdays = collections.defaultdict(list)
    dip_day = collections.defaultdict(list)
    for nm in NAMES:
        dts, O, H, L, C = data[nm]
        for i in range(1, len(dts)):
            g = O[i]/C[i-1] - 1
            nd = (dts[i] - dts[i-1]).days
            by_day[dts[i].weekday()].append(g)
            by_gapdays[min(nd, 4)].append(g)
            dip_day[dts[i].weekday()].append(L[i]/O[i] - 1)
    print(f'{"weekday":10s}{"n":>7s}{"mean |gap|":>12s}{"mean gap":>11s}{"P(gap<-1%)":>12s}'
          f'{"mean dip O->L":>15s}')
    for w in range(5):
        g = by_day[w]; d = dip_day[w]
        print(f'{DAY[w]:10s}{len(g):>7d}{statistics.mean(abs(x) for x in g)*100:>11.2f}%'
              f'{statistics.mean(g)*100:>10.2f}%'
              f'{sum(1 for x in g if x < -0.01)/len(g)*100:>11.1f}%'
              f'{statistics.mean(d)*100:>14.2f}%')
    print(f'\n{"calendar days since prior session":36s}{"n":>7s}{"mean |gap|":>12s}{"P(gap<-1%)":>12s}')
    lbl = {1: '1  (normal overnight)', 3: '3  (weekend)', 4: '4+ (holiday weekend)'}
    for nd in (1, 3, 4):
        g = by_gapdays.get(nd, [])
        if not g: continue
        print(f'{lbl[nd]:36s}{len(g):>7d}{statistics.mean(abs(x) for x in g)*100:>11.2f}%'
              f'{sum(1 for x in g if x < -0.01)/len(g)*100:>11.1f}%')
    # Monday label vs weekend mechanism: Tuesdays that follow a 3+ day break
    hol, norm_tue = [], []
    for nm in NAMES:
        dts, O, H, L, C = data[nm]
        for i in range(1, len(dts)):
            if dts[i].weekday() != 1: continue
            g = abs(O[i]/C[i-1] - 1)
            (hol if (dts[i]-dts[i-1]).days >= 3 else norm_tue).append(g)
    print(f'\nTuesday after a normal 1-day gap : {statistics.mean(norm_tue)*100:.2f}%  '
          f'(n={len(norm_tue)})')
    print(f'Tuesday after a 3+ day break     : {statistics.mean(hol)*100:.2f}%  (n={len(hol)})'
          '   <- same label, different break length')


# ----------------------------------------------------------------- B. cross-name
def cross_name():
    print('\n=== B. ANCHOR BY STOCK (NVDA parameters fixed, same-day exits DISALLOWED) ===')
    print(f'{"stock":8s}' + ''.join(f'{d:>9s}' for d in DAY) + f'{"best":>7s}{"Mon rank":>10s}')
    print('-'*72)
    ranks = []
    for nm in NAMES:
        rs = []
        for a in range(5):
            r, t, nw = book(nm, a)
            rs.append(r)
        order = sorted(range(5), key=lambda k: -rs[k])
        mr = order.index(0) + 1
        ranks.append(mr)
        print(f'{nm:8s}' + ''.join(f'{r*100:>8.0f}%' for r in rs)
              + f'{DAY[order[0]]:>7s}{mr:>10d}')
    print('-'*72)
    wins = sum(1 for r in ranks if r == 1)
    print(f'Monday ranks 1st in {wins}/{len(NAMES)} names; mean rank {statistics.mean(ranks):.2f} '
          f'(2.5 if the anchor were irrelevant, 3.00 expected under the null)')
    return ranks


# ----------------------------------------------------------------- C. sub-periods
def subperiods():
    print('\n=== C. NVDA SUB-PERIODS (minute-verified same-day exits) ===')
    WS0 = group_weeks(data['NVDA'][0], 0)
    N = len(WS0)
    thirds = [(1, N//3), (N//3, 2*N//3), (2*N//3, N-1)]
    print(f'{"block":16s}' + ''.join(f'{d:>9s}' for d in DAY) + f'{"best":>7s}')
    for (a_, b_) in thirds:
        rs = []
        for a in range(5):
            r, t, nw = book('NVDA', a, w0=a_, w1=b_, verify=verify_same_day)
            rs.append(r)
        best = DAY[max(range(5), key=lambda k: rs[k])]
        print(f'{f"weeks {a_}-{b_}":16s}' + ''.join(f'{r*100:>8.0f}%' for r in rs) + f'{best:>7s}')
    rs = []
    for a in range(5):
        r, t, nw = book('NVDA', a, verify=verify_same_day)
        rs.append(r)
    print(f'{"full sample":16s}' + ''.join(f'{r*100:>8.0f}%' for r in rs)
          + f'{DAY[max(range(5), key=lambda k: rs[k])]:>7s}')


# ----------------------------------------------------------------- D. the channel
def channel():
    print('\n=== D. THE CAUSAL CHANNEL: open clamp and fill timing (NVDA, minute-verified) ===')
    print(f'{"anchor":8s}{"weeks priced":>14s}{"clamp binds":>13s}{"fills":>7s}'
          f'{"filled wk clamped":>19s}{"fills on day 1":>16s}')
    for a in range(5):
        tk = dict(weeks=0, clamped=0, fills=0, fill_clamped=0,
                  fillday=collections.defaultdict(int))
        book('NVDA', a, verify=verify_same_day, track=tk)
        f1 = tk['fillday'][1]/max(tk['fills'], 1)*100
        print(f'{DAY[a]:8s}{tk["weeks"]:>14d}{tk["clamped"]/max(tk["weeks"],1)*100:>12.0f}%'
              f'{tk["fills"]:>7d}{tk["fill_clamped"]/max(tk["fills"],1)*100:>18.0f}%'
              f'{f1:>15.0f}%')
    print('(clamp binds = the week opened BELOW the computed level, so the open set the entry)')


if __name__ == '__main__':
    gap_table()
    cross_name()
    subperiods()
    channel()
    print('\nDONE')
