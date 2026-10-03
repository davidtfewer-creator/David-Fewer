"""
frozen_sleeve_diag.py — how much is the book giving up while both sleeves of a
name are occupied? (user proposal, 3 Oct 2026)

The user's observation: a sleeve holds one position at a time, so when both
sleeves of a name are in the market the name is frozen out until one sells.
A violently-moving name can offer several round trips inside that window and
the book takes none of them. He has been taking them by hand in the
discretionary log.

This is the DIAGNOSTIC half only — it sizes the forgone opportunity before
any intervention is designed, which is the order every adopted finding in
this book was reached in. It asks three questions:

  1. How much of the book's life is spent with a name frozen?
  2. On those days the model still COMPUTES a bid. How often would that bid
     have been touched?
  3. What would those entries have been worth, on the model's own exit rule?

Source: the workbook's own Model sheets, which carry the deployed parameters
and compute the bid, the target and the hold flags for every session whether
or not the sleeve can act. Nothing is re-fitted and no parameter is searched;
this reads what the book already believes.

FILL CONVENTION. The 5-minute archive is still lost (HANDOVER 3.28d), so
same-day round trips cannot be verified. Every number here uses the
conservative rule -- a position opened on day i can exit no earlier than
day i+1 -- which is a hard lower bound, not an estimate. The sheet's own
convention is reported alongside for scale, and is known to read high
(3.5: 508% vs 158% on RKLB).

Usage: python frozen_sleeve_diag.py <workbook.xlsx>
"""
import datetime as dt
import json
import statistics
import sys

import openpyxl

OUT = 'frozen_sleeve_diag.json'
SPLIT = dt.date(2025, 5, 23)
HDR = 7                      # Model sheet header row; data starts at HDR+1
STOP_DAYS = 50
COL = dict(date=1, O=2, H=3, L=4, C=5,                    # A..E
           bayes_bid=24, bayes_hold=31,                   # X, AE
           ou_hold=38, ou_bid=39)                         # AL, AM


def d_of(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)):
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
    return None


def read_model(wb, name):
    ws = wb[f'Model {name}']
    prem = dict(bayes=ws.cell(row=2, column=10).value,     # J2
                ou=ws.cell(row=3, column=8).value)         # H3
    rows = []
    for r in range(HDR + 1, ws.max_row + 1):
        d = d_of(ws.cell(row=r, column=COL['date']).value)
        o = ws.cell(row=r, column=COL['O']).value
        if d is None or not isinstance(o, (int, float)):
            continue
        rows.append(dict(
            date=d, O=o,
            H=ws.cell(row=r, column=COL['H']).value,
            L=ws.cell(row=r, column=COL['L']).value,
            C=ws.cell(row=r, column=COL['C']).value,
            bid=dict(bayes=ws.cell(row=r, column=COL['bayes_bid']).value,
                     ou=ws.cell(row=r, column=COL['ou_bid']).value),
            hold=dict(bayes=ws.cell(row=r, column=COL['bayes_hold']).value,
                      ou=ws.cell(row=r, column=COL['ou_hold']).value)))
    return rows, prem


def trade_from(rows, i, bid, prem, same_day):
    """The model's own round trip, opened at `bid` on row i: exit at the first
    high that reaches bid + prevC*prem, else the open after STOP_DAYS."""
    target = bid + rows[i - 1]['C'] * prem
    j0 = i if same_day else i + 1
    for j in range(j0, len(rows)):
        if (rows[j]['date'] - rows[i]['date']).days > STOP_DAYS:
            return dict(ret=rows[j]['O'] / bid - 1, hold=j - i, stop=True)
        if rows[j]['H'] >= target:
            return dict(ret=target / bid - 1, hold=j - i, stop=False)
    return None                                            # window incomplete


def analyse(rows, prem, same_day=False):
    n = len(rows)
    frozen = [bool(r['hold']['bayes']) and bool(r['hold']['ou']) for r in rows]
    spells, cur = [], None
    for i, f in enumerate(frozen):
        if f and cur is None:
            cur = i
        elif not f and cur is not None:
            spells.append((cur, i - 1))
            cur = None
    if cur is not None:
        spells.append((cur, n - 1))

    missed = []
    for i in range(1, n):
        if not frozen[i]:
            continue
        for s in ('bayes', 'ou'):
            bid = rows[i]['bid'][s]
            if not isinstance(bid, (int, float)) or bid <= 0:
                continue
            if rows[i]['L'] <= bid:                        # the bid was touched
                t = trade_from(rows, i, bid, prem[s], same_day)
                if t:
                    missed.append(dict(t, date=rows[i]['date'], sleeve=s, bid=bid))
    return frozen, spells, missed


def stats(tr):
    if not tr:
        return None
    r = [t['ret'] for t in tr]
    h = [max(t['hold'], 1) for t in tr]
    return dict(n=len(tr), avg=statistics.fmean(r), med=statistics.median(r),
                worst=min(r), stops=sum(t['stop'] for t in tr),
                med_hold=statistics.median(h),
                wk=statistics.fmean(a / b * 7 for a, b in zip(r, h)))


def main():
    wb = openpyxl.load_workbook(sys.argv[1], data_only=True)
    names = sorted(s[6:] for s in wb.sheetnames if s.startswith('Model '))
    print(f'nine-name book, deployed parameters from the workbook\'s Model sheets')
    print('conservative fills: a position opened on day i cannot exit before i+1\n')

    print(f'{"":6s}{"sessions":>9s}{"frozen":>8s}{"%":>7s}{"spells":>8s}'
          f'{"med":>6s}{"max":>6s}  | bid touched while frozen')
    res, allmissed = {}, []
    for nm in names:
        rows, prem = read_model(wb, nm)
        frozen, spells, missed = analyse(rows, prem)
        lens = [b - a + 1 for a, b in spells]
        s = stats(missed)
        allmissed += [dict(m, name=nm) for m in missed]
        res[nm] = dict(sessions=len(rows), frozen=sum(frozen), spells=len(spells),
                       med_spell=statistics.median(lens) if lens else 0,
                       max_spell=max(lens) if lens else 0, missed=s)
        tail = (f'{s["n"]:>3d} entries, avg {s["avg"]*100:>+6.2f}%' if s
                else '  0 entries')
        print(f'{nm:6s}{len(rows):>9d}{sum(frozen):>8d}{sum(frozen)/len(rows)*100:>6.1f}%'
              f'{len(spells):>8d}{res[nm]["med_spell"]:>6.0f}{res[nm]["max_spell"]:>6d}'
              f'  | {tail}')

    tot_s = sum(r['sessions'] for r in res.values())
    tot_f = sum(r['frozen'] for r in res.values())
    yrs = 2.45                       # the sample spans Apr 2024 - Oct 2026
    print(f'\nbook: {tot_f} of {tot_s} name-sessions frozen ({tot_f/tot_s*100:.1f}%), '
          f'{tot_f/len(names)/yrs:.0f} frozen sessions per name-year')

    print('\nTHE FORGONE ENTRIES (model bid touched while both sleeves occupied)')
    for tag, sel in (('all', lambda t: True),
                     ('train half', lambda t: t['date'] < SPLIT),
                     ('tested half', lambda t: t['date'] >= SPLIT),
                     ('Bayes bid', lambda t: t['sleeve'] == 'bayes'),
                     ('OU bid', lambda t: t['sleeve'] == 'ou')):
        s = stats([t for t in allmissed if sel(t)])
        if s:
            print(f'  {tag:12s} n={s["n"]:4d}  avg {s["avg"]*100:+6.2f}%  med {s["med"]*100:+6.2f}%'
                  f'  worst {s["worst"]*100:+7.1f}%  stops {s["stops"]:3d}'
                  f'  med hold {s["med_hold"]:>3.0f}d  {s["wk"]*100:+6.2f}%/wk')

    print('\n  per name:')
    for nm in names:
        s = res[nm]['missed']
        if s:
            print(f'    {nm:6s} n={s["n"]:4d}  avg {s["avg"]*100:+6.2f}%  worst {s["worst"]*100:+7.1f}%'
                  f'  stops {s["stops"]:3d}  med hold {s["med_hold"]:>3.0f}d')

    with open(OUT, 'w') as f:
        json.dump(dict(per_name=res, n_missed=len(allmissed),
                       missed=[dict(m, date=str(m['date'])) for m in allmissed]),
                  f, indent=1, default=str)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
