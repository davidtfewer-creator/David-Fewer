"""
disc_vol_gate.py — the dislocation screen's flag rule, re-measured (10 Sep 2026).

WHY: ops/dislocation_scan.py was written to formalise the VRT episode of
9 Sep (-8.2% in a session on no company news: a -9.6% close against its
3-session high with an 11.5% range day) and it does not flag VRT. Two
separate reasons, both in the flag rule:

  1. The tested proxy's dip test is "close >= 3% below the 10-day mean".
     VRT had been running, so after an 8% fall it still sat only 1.3% below
     its 10dma. The scanner therefore added an OR branch -- "close >= 5%
     below the 3-session high" -- which is NOT part of the tested proxy and
     had never been measured.
  2. The vol test is "5-day MEAN true range >= 1.3x the 60-day median".
     VRT's own norm is a 4.84% daily range, so an 11.5% day averaged with
     the four ordinary ones before it scores 1.20x -- under the gate. The
     measure dilutes the event with the sessions that preceded it.

Both changes are measured here on the harness that validated the original
(disc_structure.run/stats: buy next open, GTC target at +T, time-stop at the
open after N sessions), nine names, daily workbook data, both halves at the
standard 2025-05-23 split. Nothing is adopted that does not clear both.

  V0  baseline (tested proxy)      dip: 10dma         vol: 5-day mean
  V1  scanner as written           dip: 10dma OR 3sh  vol: 5-day mean
  V2  event-day vol only           dip: 10dma         vol: signal day
  V3  scanner dip + event-day vol  dip: 10dma OR 3sh  vol: signal day
  V4  the VRT shape alone          dip: 3sh only      vol: signal day
  V5  the VRT shape, 5-day vol     dip: 3sh only      vol: 5-day mean

Usage: python disc_vol_gate.py <workbook.xlsx>
"""
import json
import statistics
import sys

import disc_structure as base

OUT = 'disc_vol_gate.json'
SPLIT = base.SPLIT
DIP_MA, DIP_3SH, VOLX = 0.97, 0.95, 1.3
TGT, CAP = 0.05, 10                      # the adopted bracket


def flagged(C, tr, i, use_ma, use_3sh, vol):
    """Does the flag rule fire on session i? Shared by the backtest and the
    last-session check so the two can never diverge."""
    dip_ma = C[i] < DIP_MA * statistics.fmean(C[i - 9:i + 1])
    dip_3sh = C[i] <= DIP_3SH * max(C[i - 3:i])
    if not ((use_ma and dip_ma) or (use_3sh and dip_3sh)):
        return False
    med60 = statistics.median(tr[i - 59:i + 1])
    v = tr[i] if vol == 'day' else statistics.fmean(tr[i - 4:i + 1])
    return med60 > 0 and v >= VOLX * med60


def make_signals(**kw):
    """Signal-day indices under one flag rule. Same window conventions as
    disc_structure.signals: 65-session warm-up, entry on i+1."""
    def f(dts, O, H, L, C):
        n = len(C)
        tr = [(H[i] - L[i]) / C[i] for i in range(n)]
        return [i for i in range(65, n - 1) if flagged(C, tr, i, **kw)]
    return f


VARIANTS = {
    'V0 baseline 10dma  / 5d vol': dict(use_ma=True, use_3sh=False, vol='mean5'),
    'V1 scanner  +3sh   / 5d vol': dict(use_ma=True, use_3sh=True, vol='mean5'),
    'V2          10dma  / day vol': dict(use_ma=True, use_3sh=False, vol='day'),
    'V3 scanner  +3sh   / day vol': dict(use_ma=True, use_3sh=True, vol='day'),
    'V4 3sh only        / day vol': dict(use_ma=False, use_3sh=True, vol='day'),
    'V5 3sh only        / 5d vol': dict(use_ma=False, use_3sh=True, vol='mean5'),
}
BASE = 'V0 baseline 10dma  / 5d vol'


def run_variant(data, kw, tgt=TGT, cap=CAP):
    """disc_structure.run with the signal rule swapped."""
    orig = base.signals
    base.signals = make_signals(**kw)
    try:
        return base.run(data, tgt, cap)
    finally:
        base.signals = orig


def today_flags(data, kw):
    """Which names the rule fires on for the LAST completed session -- the
    scan's own use, where there is no next open to trade yet."""
    out = []
    for nm, (dts, O, H, L, C) in data.items():
        tr = [(H[i] - L[i]) / C[i] for i in range(len(C))]
        if flagged(C, tr, len(C) - 1, **kw):
            out.append(nm)
    return sorted(out)


def standalone(data, tgt=TGT, cap=CAP):
    """Every signal-eligible session scored as one trade, with its dip and vol
    state attached. No non-overlap rule, so populations nest strictly and any
    two cells are directly comparable -- the crowded (tradeable) version above
    lets a loose rule's early signal displace a tight rule's later one, which
    confounds exactly the comparison this decomposition is for."""
    rows = []
    for nm, (dts, O, H, L, C) in data.items():
        n = len(C)
        tr = [(H[k] - L[k]) / C[k] for k in range(n)]
        for i in range(65, n - 1):
            med60 = statistics.median(tr[i - 59:i + 1])
            if med60 <= 0:
                continue
            px = O[i + 1]
            target = px * (1 + tgt)
            ej = ep = None
            for j in range(i + 1, min(i + 1 + cap, n)):
                if H[j] >= target:
                    ej, ep = j, target
                    break
            if ej is None:
                j = min(i + 1 + cap, n - 1)
                ej, ep = j, O[j]
            rows.append(dict(
                name=nm, entry=base.d_of(dts[i + 1]), ret=ep / px - 1, hit=ep == target,
                hold=max((base.d_of(dts[ej]) - base.d_of(dts[i + 1])).days, 1),
                mae=min(L[k] for k in range(i + 1, ej + 1)) / px - 1,
                d3=C[i] / max(C[i - 3:i]) - 1,
                dma=C[i] / statistics.fmean(C[i - 9:i + 1]) - 1,
                vday=tr[i] / med60, v5=statistics.fmean(tr[i - 4:i + 1]) / med60))
    return rows


# the decomposition the scanner's grades are quoted from: the two dip tests
# against the two vol measures, every cell on both halves
CELLS = [
    ('A  tested proxy: 10dma<=-3%, week hot',
     lambda t: t['dma'] <= -0.03 and t['v5'] >= VOLX),
    ('B  alternative:  3sh<=-5%,  week hot',
     lambda t: t['d3'] <= -0.05 and t['v5'] >= VOLX),
    ('   A OR B  (the scanner as first written)',
     lambda t: (t['dma'] <= -0.03 or t['d3'] <= -0.05) and t['v5'] >= VOLX),
    ('   A AND B (both dip tests agree)  = STRONG',
     lambda t: t['dma'] <= -0.03 and t['d3'] <= -0.05 and t['v5'] >= VOLX),
    ('   B not A (dip off a running high) = FLAG',
     lambda t: t['d3'] <= -0.05 and t['dma'] > -0.03 and t['v5'] >= VOLX),
    ('   A not B (the grinding slide)    = SLIDE',
     lambda t: t['dma'] <= -0.03 and t['d3'] > -0.05 and t['v5'] >= VOLX),
    ('C  violent day, calm week          = DAYVOL',
     lambda t: t['d3'] <= -0.05 and t['vday'] >= VOLX and t['v5'] < VOLX),
    ('     ... of those, deep (3sh<=-8%)',
     lambda t: t['d3'] <= -0.08 and t['vday'] >= VOLX and t['v5'] < VOLX),
    ('D  no vol gate at all: 3sh<=-5%',
     lambda t: t['d3'] <= -0.05),
    ('E  no screen at all: every session',
     lambda t: True),
]


def decompose(data):
    rows = standalone(data)
    print('\nSTANDALONE DECOMPOSITION (populations nest; each signal one trade)')
    print(f'{"":44s} |{"full":^36s}     |{"train":^24s} |{"test":^24s}')
    print(f'{"":44s} |{"n":>5s}{"hit":>5s}{"avg":>8s}{"%/wk":>8s}{"hold":>6s}'
          f'{"worst":>8s} |{"n":>5s}{"hit":>5s}{"avg":>8s}{"%/wk":>8s}'
          f' |{"n":>5s}{"hit":>5s}{"avg":>8s}{"%/wk":>8s}')
    out = {}
    for tag, f in CELLS:
        tr = [t for t in rows if f(t)]
        s = base.stats(tr)
        a = base.stats([t for t in tr if t['entry'] < SPLIT])
        b = base.stats([t for t in tr if t['entry'] >= SPLIT])
        print(f'{tag:44s} |{cell(s)}{s["med_hold"]:5.0f}d{s["worst"]*100:+7.1f}%'
              f' |{cell(a)} |{cell(b)}')
        out[tag.strip()] = dict(full=s, train=a, test=b)
    return out


def cell(x):
    return ('             n/a      ' if x is None else
            f'{x["n"]:5d}{x["hit"]*100:4.0f}%{x["avg_ret"]*100:+7.2f}%'
            f'{x["per_week"]*100:+7.2f}%')


def line(tag, s, a, b):
    return (f'{tag:29s} |{cell(s)}{s["med_hold"]:5.0f}d{s["worst"]*100:+7.1f}%'
            f' |{cell(a)} |{cell(b)}')


def main():
    data = base.load_from_workbook(sys.argv[1])
    asof = max(v[0][-1] for v in data.values())
    print(f'universe: {len(data)} names {sorted(data)}, data through {asof}')
    print(f'bracket T={TGT*100:.0f}% / N={CAP} sessions, half-sample split {SPLIT}\n')
    print(f'{"":29s} |{"full":^36s}     |{"train":^24s} |{"test":^24s}')
    print(f'{"":29s} |{"n":>5s}{"hit":>5s}{"avg":>8s}{"%/wk":>8s}{"hold":>6s}'
          f'{"worst":>8s} |{"n":>5s}{"hit":>5s}{"avg":>8s}{"%/wk":>8s}'
          f' |{"n":>5s}{"hit":>5s}{"avg":>8s}{"%/wk":>8s}')
    res = {}
    for tag, kw in VARIANTS.items():
        tr = run_variant(data, kw)
        s = base.stats(tr)
        a = base.stats([t for t in tr if t['entry'] < SPLIT])
        b = base.stats([t for t in tr if t['entry'] >= SPLIT])
        res[tag] = dict(rule=kw, full=s, train=a, test=b,
                        would_flag_today=today_flags(data, kw))
        print(line(tag, s, a, b))

    print(f'\nwhat each rule flags on the last completed session ({asof}):')
    for tag in VARIANTS:
        f = res[tag]['would_flag_today']
        print(f'  {tag:29s} {", ".join(f) if f else "(none)"}')

    # the marginal population: what a looser rule ADDS to the tested proxy
    v0 = {(t['name'], str(t['entry'])) for t in run_variant(data, VARIANTS[BASE])}
    print('\nmarginal populations (trades the rule adds to the tested proxy):')
    for tag in ('V1 scanner  +3sh   / 5d vol', 'V2          10dma  / day vol',
                'V3 scanner  +3sh   / day vol'):
        add = [t for t in run_variant(data, VARIANTS[tag])
               if (t['name'], str(t['entry'])) not in v0]
        if not add:
            print(f'  {tag:29s} adds nothing')
            continue
        s = base.stats(add)
        a = base.stats([t for t in add if t['entry'] < SPLIT])
        b = base.stats([t for t in add if t['entry'] >= SPLIT])
        print(line(f'  +{len(add):d} marginal, {tag[:14]}', s, a, b))
        res[tag]['marginal'] = dict(
            full=s, train=a, test=b,
            trades=[dict(t, entry=str(t['entry'])) for t in add])

    res['decomposition'] = decompose(data)
    with open(OUT, 'w') as f:
        json.dump(res, f, indent=1, default=str)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
