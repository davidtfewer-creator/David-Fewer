"""
Measure the TRUE same-day fill rate for NVDA using minute data.

For every day the daily-bar model recorded a same-day round trip (bought and sold at target on
the same session), check the intraday sequence:
    1. find the first minute whose LOW <= bid            -> the actual fill minute
    2. look ONLY at minutes at/after that fill           -> was the target ever reached?
If yes, the same-day exit is real. If no, the daily-bar backtest booked a trade that could not
have happened (the peak preceded the dip).

Splits results by at-open fills (provably legitimate) vs intraday-dip fills (the ambiguous ones),
so we learn the true rate for the class that actually matters.
"""
import openpyxl, datetime, collections
from stop_sweep import load_book
from engine import run_model

MIN = '/root/.claude/uploads/2d71f10a-e19f-51b2-8457-2cd547c34dff/b0d1e498-Nvidia_Minute_Data__Day_Trading_Model_.xlsx'


def load_minutes():
    """date -> list of (minute_index, open, high, low, close) in session order."""
    wb = openpyxl.load_workbook(MIN, read_only=True, data_only=True)
    ws = wb['NVDA Minute Data']
    by = collections.defaultdict(list)
    first = True
    for row in ws.iter_rows(values_only=True):
        if first:
            first = False
            continue
        lt, o, h, l, c = row[1], row[2], row[3], row[4], row[5]
        if lt is None or o is None:
            continue
        d = lt.date() if isinstance(lt, datetime.datetime) else None
        if d is None:
            continue
        by[d].append((lt, o, h, l, c))
    for d in by:
        by[d].sort(key=lambda x: x[0])
    wb.close()
    return by


def verify(minutes, bid, target, at_open):
    """Return 'real' / 'fake' / 'nofill' for one same-day round trip."""
    fill = None
    for i, (t, o, h, l, c) in enumerate(minutes):
        if at_open and i == 0:
            fill = i           # capped at the open: filled in the opening minute
            break
        if l <= bid + 1e-9:
            fill = i
            break
    if fill is None:
        return 'nofill'
    for (t, o, h, l, c) in minutes[fill:]:
        if h >= target - 1e-9:
            return 'real'
    return 'fake'


if __name__ == '__main__':
    print('loading minute data...', flush=True)
    mins = load_minutes()
    ds = sorted(mins)
    print(f'  {len(mins)} sessions, {ds[0]} .. {ds[-1]}', flush=True)

    data, params, cached = load_book()
    dts, O, H, L, C = data['NVDA']
    r = run_model(dts, O, H, L, C, params['NVDA'], collect=True)
    X, AM = r.frames['X'], r.frames['AM']

    print('\n=== NVDA same-day round trips verified against minute data ===', flush=True)
    grand = collections.Counter()
    for tkey, tname, bids in (('t1', 'Bayes', X), ('t2', 'OU', AM)):
        t = r.frames[tkey]
        cnt = collections.Counter()
        for i in range(len(C)):
            if t['Z'][i] != 1 or t['AD'][i] != 1:      # same-day round trips only
                continue
            d = dts[i]
            if d not in mins:                          # outside the minute-data window
                cnt['no_data'] += 1
                continue
            bid = bids[i]; tgt = t['AB'][i]
            if bid is None:
                cnt['no_data'] += 1
                continue
            at_open = bid >= O[i] - 1e-9
            v = verify(mins[d], bid, tgt, at_open)
            cnt[v] += 1
            cnt['open_' + v if at_open else 'dip_' + v] += 1
        checked = cnt['real'] + cnt['fake']
        rate = cnt['real'] / checked * 100 if checked else 0
        dip_ch = cnt['dip_real'] + cnt['dip_fake']
        dip_rate = cnt['dip_real'] / dip_ch * 100 if dip_ch else 0
        op_ch = cnt['open_real'] + cnt['open_fake']
        op_rate = cnt['open_real'] / op_ch * 100 if op_ch else 0
        print(f'\n{tname} tranche:', flush=True)
        print(f'  same-day trades checked : {checked}   (skipped {cnt["no_data"]} outside minute window, '
              f'{cnt["nofill"]} no intraday fill)', flush=True)
        print(f'  REAL (target hit after fill) : {cnt["real"]}  = {rate:.0f}%', flush=True)
        print(f'  FAKE (peak preceded the dip) : {cnt["fake"]}  = {100-rate:.0f}%', flush=True)
        print(f'    at-open fills : {cnt["open_real"]}/{op_ch} real = {op_rate:.0f}%  (expect ~100%)', flush=True)
        print(f'    dip fills     : {cnt["dip_real"]}/{dip_ch} real = {dip_rate:.0f}%  <-- the ambiguous class', flush=True)
        grand['real'] += cnt['real']; grand['fake'] += cnt['fake']
        grand['dip_real'] += cnt['dip_real']; grand['dip_fake'] += cnt['dip_fake']

    tot = grand['real'] + grand['fake']
    dtot = grand['dip_real'] + grand['dip_fake']
    print(f'\n=== HEADLINE ===', flush=True)
    print(f'Overall same-day trades that are REAL: {grand["real"]}/{tot} = {grand["real"]/tot*100:.0f}%', flush=True)
    print(f'Of the AMBIGUOUS (dip-filled) ones   : {grand["dip_real"]}/{dtot} = {grand["dip_real"]/dtot*100:.0f}%', flush=True)
    print('DONE', flush=True)
