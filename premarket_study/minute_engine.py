"""
Minute-verified fill model for NVDA: for ANY candidate bid/target, decide from the minute bars
whether a same-day exit was actually achievable (first minute the bid fills, then whether the
target is reached at/after that minute). Lets us re-optimise against REALITY instead of the
optimistic or pessimistic bound.

Days outside the minute window fall back to the at-open rule (provably legitimate only).
"""
import openpyxl, datetime, collections, pickle, os
import numpy as np

MIN = '/root/.claude/uploads/2d71f10a-e19f-51b2-8457-2cd547c34dff/b0d1e498-Nvidia_Minute_Data__Day_Trading_Model_.xlsx'
CACHE = '/home/user/David-Fewer/premarket_study/nvda_minute_index.pkl'


def build_index():
    """date -> (lows[np], suffix_max_high[np]).  Cached to disk (xlsx parse is slow)."""
    if os.path.exists(CACHE):
        with open(CACHE, 'rb') as f:
            return pickle.load(f)
    wb = openpyxl.load_workbook(MIN, read_only=True, data_only=True)
    ws = wb['NVDA Minute Data']
    by = collections.defaultdict(list)
    first = True
    for row in ws.iter_rows(values_only=True):
        if first:
            first = False; continue
        lt, o, h, l = row[1], row[2], row[3], row[4]
        if lt is None or o is None:
            continue
        by[lt.date()].append((lt, h, l))
    wb.close()
    idx = {}
    for d, rows in by.items():
        rows.sort(key=lambda x: x[0])
        highs = np.array([r[1] for r in rows], dtype=float)
        lows = np.array([r[2] for r in rows], dtype=float)
        # suffix max of highs: suffix[i] = max(highs[i:])
        suffix = np.maximum.accumulate(highs[::-1])[::-1]
        idx[d] = (lows, suffix)
    with open(CACHE, 'wb') as f:
        pickle.dump(idx, f)
    return idx


def make_checker(dates, O):
    """Return f(i, bid, target) -> True if a same-day exit was really achievable on day i."""
    idx = build_index()
    def check(i, bid, target):
        d = dates[i]
        ent = idx.get(d)
        if ent is None:                       # no minute data: allow only provable at-open case
            return bid >= O[i] - 1e-9
        lows, suffix = ent
        hit = lows <= bid + 1e-9
        if not hit.any():
            return False                       # never filled intraday
        j = int(np.argmax(hit))                # first filling minute
        return bool(suffix[j] >= target - 1e-9)
    return check, idx


if __name__ == '__main__':
    from stop_sweep import load_book
    from engine import run_model
    data, params, cached = load_book()
    dts, O, H, L, C = data['NVDA']
    chk, idx = make_checker(dts, O)
    covered = sum(1 for d in dts if d in idx)
    print(f'minute index: {len(idx)} sessions; daily sample {len(dts)} days, '
          f'{covered} covered ({covered/len(dts)*100:.0f}%)\n')

    p = params['NVDA']
    modes = [('optimistic (published)', True),
             ('at-open floor', 'at_open'),
             ('MINUTE-VERIFIED (truth)', chk),
             ('pessimistic floor', False)]
    print(f'{"mode":26s}{"ann":>8s}{"buys":>7s}{"stops":>7s}{"maxDD":>8s}{"Sharpe":>8s}')
    print('-' * 64)
    for name, m in modes:
        r = run_model(dts, O, H, L, C, p, same_day_exit=m)
        print(f'{name:26s}{r.annual_return*100:>7.0f}%{r.total_buys:>7d}{r.stop_loss_exits:>7d}'
              f'{r.max_drawdown*100:>7.0f}%{r.sharpe:>8.2f}')
