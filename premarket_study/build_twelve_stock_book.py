"""
Add RTX, DE and NVDA to the live nine-name workbook -> the twelve-name book.

Follows build_nine_stock_book.py: EXTENDS the uploaded live file in place, so the
trade log, fees, notes, overrides and every user-entered cell survive. Roster per
HANDOVER §3.70 (PARR dropped, §3.64/§3.69); the three new names carry the
train-half fitted vectors exactly as simulated (rho +0.36 / +0.38 / +0.41).

LAYOUT. Nine->twelve needs 3 more funds rows and 6 more order rows, and the
nine-stock build used the last of the slack. So blocks move, and this is the
whole of the layout change (user's call, 16 Oct):

  Query           RTX AL:AO, DE AP:AS, NVDA AT:AW. Pure append — no existing
                  column moves, so Script 1 only has to fetch three more tickers.
  Feed/Model      three new sheet pairs copied from the TSM pair and repointed.
  Dashboard       rows 13-15. Nothing below row 12, so nothing moves.
  Allocation      names 11-22, TOTAL 21->24, machine block 25-42 -> 28-51,
                  summary 43-46 -> 52-55, notes +9. No script anchors here
                  (IBKR_AvailFunds is B5 and does not move).
  Active Trading  funds 7-18, orders title/header 17/18 -> 20/21, orders
                  19-36 -> 22-45, and THE WHOLE LOG REGION (rows 40-1041,
                  columns A-AG: main log, weekly rollup, discretionary log)
                  SHIFTS DOWN NINE ROWS to 49-1050.
  Performance     its weekly rows read 'Active Trading'!$O42.. — repointed +9.

  IBKR_Orders     'Active Trading'!$A$18:$J$36  ->  $A$21:$J$45
  IBKR_LogAnchor  'Active Trading'!$A$41        ->  $A$50
  IBKR_AvailFunds / IBKR_BuyFee / IBKR_SellFee  unchanged.

Script 2 is unaffected IF it addresses the blotter through those two names. If
it hardcodes row 41 or 42 it MUST be updated, or it will write into the orders
block. The before/after map is printed at the end and saved to the JSON.

Usage: python3 build_twelve_stock_book.py [--src <xlsx>] [--out <xlsx>]
"""
import copy as pycopy
import datetime
import json
import re
import sys

import openpyxl
from openpyxl.formula.translate import Translator
from openpyxl.utils import get_column_letter as cl

from fresh_opt_cands import daily_from_5min

SRC = ('/root/.claude/uploads/3d41d7f9-ef99-5f28-8175-d0fe4e3b909a/'
       '071a87e9-TradingExcel_9stock_avgo.xlsx')
OUT = '/home/user/David-Fewer/TradingExcel_12stock_live.xlsx'
MAP = 'premarket_study/twelve_stock_cellmap.json'

OLD = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'GM', 'VLO', 'CF', 'MRVL']
NEW = ['RTX', 'DE', 'NVDA']
ALL = OLD + NEW
N = len(ALL)
W12 = 1.0 / 12.0

# --- Active Trading geometry -------------------------------------------------
AT_FUND0, AT_ORD_TITLE, AT_ORD_HDR, AT_ORD0 = 7, 17, 18, 19     # old
AT_LOG0_OLD, AT_LOG_LAST_OLD = 40, 1041
NF_FUND0 = 7                                                     # new
NF_ORD_TITLE, NF_ORD_HDR, NF_ORD0 = 20, 21, 22
AT_SHIFT = 9                                                     # log moves +9
AT_LOG0_NEW = AT_LOG0_OLD + AT_SHIFT                             # 49

# --- Allocation geometry -----------------------------------------------------
AL_N0 = 11
AL_TOT_OLD, AL_TOT_NEW = 21, 24
AL_MACH_TITLE_OLD, AL_MACH_HDR_OLD, AL_MACH0_OLD = 23, 24, 25
AL_MACH_TITLE_NEW, AL_MACH_HDR_NEW, AL_MACH0_NEW = 26, 27, 28
AL_SUM_OLD, AL_SUM_NEW = (43, 46), (52, 55)
AL_NOTE_OLD0, AL_NOTE_SHIFT = 48, 9


def argval(flag, default):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def to_date(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, (int, float)):
        return datetime.date(1899, 12, 30) + datetime.timedelta(days=int(v))
    return None


SHEETQ = r"(?:'[^']+'|\b[A-Za-z_][A-Za-z0-9_ ]*)!"


def shift_local_abs(f, lo, delta):
    """Bump UNQUALIFIED absolute row refs ($C$42) at or below `lo` by `delta`.
    Sheet-qualified references are masked out first so another sheet's rows are
    never moved by this sheet's shift."""
    if not isinstance(f, str) or not f.startswith('='):
        return f
    holes = []

    def mask(m):
        holes.append(m.group(0))
        return f'\x00{len(holes)-1}\x00'

    # mask "Sheet!" prefixes together with the ref that follows them
    masked = re.sub(SHEETQ + r"\$?[A-Z]{1,2}\$?\d+(?::\$?[A-Z]{1,2}\$?\d+)?", mask, f)
    masked = re.sub(SHEETQ + r"\$?[A-Z]{1,2}:\$?[A-Z]{1,2}", mask, masked)

    def bump(m):
        row = int(m.group(2))
        return f'{m.group(1)}${row + delta}' if row >= lo else m.group(0)

    masked = re.sub(r"(\$[A-Z]{1,2})\$(\d+)", bump, masked)
    return re.sub(r'\x00(\d+)\x00', lambda m: holes[int(m.group(1))], masked)


def retarget(f, mapping):
    """Rewrite references INTO another sheet: mapping is {sheet: {old: new}}."""
    if not isinstance(f, str) or not f.startswith('='):
        return f
    for sheet, rows in mapping.items():
        q = f"'{sheet}'!" if ' ' in sheet else f'{sheet}!'
        for old, new in sorted(rows.items(), key=lambda kv: -kv[0]):
            f = re.sub(re.escape(q) + r"(\$[A-Z]{1,2})\$" + str(old) + r"(?!\d)",
                       lambda m, n=new: f'{q}{m.group(1)}${n}', f)
    return f


def snap(ws, row, cols):
    return {c: (ws.cell(row, c).value, ws.cell(row, c)._style) for c in cols}


def put(ws, row, tmpl, src_row, subs=(), xform=None):
    for c, (v, st) in tmpl.items():
        if isinstance(v, str) and v.startswith('='):
            v = Translator(v, origin=f'{cl(c)}{src_row}') \
                .translate_formula(f'{cl(c)}{row}')
            for a, b in subs:
                v = v.replace(a, b)
            if xform:
                v = xform(v)
        cell = ws.cell(row, c)
        cell.value = v
        cell._style = pycopy.copy(st)


def main():
    src, out = argval('--src', SRC), argval('--out', OUT)
    wb = openpyxl.load_workbook(src)
    cfg = json.load(open('deployed_book12.json'))
    rep = {'src': src, 'out': out, 'roster': ALL, 'moves': {}}

    # =================================================================== Query
    q = wb['Query']
    dates = {}
    for r in range(2, q.max_row + 1):
        d = to_date(q.cell(r, 1).value)
        if d:
            dates[d] = r
    qcols = {}
    for i, nm in enumerate(NEW):
        c0 = 38 + 4 * i                                    # AL, AP, AT
        qcols[nm] = (cl(c0), cl(c0 + 3))
        for j, sfx in enumerate(('_O', '_H', '_L', '_C')):
            q.cell(1, c0 + j).value = f'{nm}{sfx}'
        dts, O, H, L, C = daily_from_5min(nm)
        n = 0
        for k, d in enumerate(dts):
            r = dates.get(d)
            if r is None:
                continue
            for j, ser in enumerate((O, H, L, C)):
                q.cell(r, c0 + j).value = ser[k]
            n += 1
        print(f'Query: {nm:5s} {qcols[nm][0]}:{qcols[nm][1]}  {n} rows, '
              f'last {dts[-1]}')
        rep.setdefault('query', {})[nm] = dict(cols=list(qcols[nm]), rows=n,
                                               last=str(dts[-1]))

    # ============================================================ Feed / Model
    for nm in NEW:
        fs = wb.copy_worksheet(wb['Feed TSM'])
        fs.title = f'Feed {nm}'
        c0 = 38 + 4 * NEW.index(nm)
        letters = [cl(c0 + j) for j in range(4)]
        fs.cell(1, 1).value = '=Query!A1'
        for j in range(4):
            fs.cell(1, 2 + j).value = f'=Query!{letters[j]}1'
        fs.cell(1, 7).value = (f'Daily OHLC for {nm}. Loaded from the Query sheet; '
                               f'the Model sheet reads columns A:E.')
        for r in range(2, fs.max_row + 1):
            fs.cell(r, 1).value = '=INDEX(Query!$A:$A,ROW())'
            for j in range(4):
                Lc = letters[j]
                fs.cell(r, 2 + j).value = f'=INDEX(Query!${Lc}:${Lc},ROW())'

        m = wb.copy_worksheet(wb['Model TSM'])
        m.title = f'Model {nm}'
        for row in m.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and 'Feed TSM' in cell.value:
                    cell.value = cell.value.replace('Feed TSM', f'Feed {nm}')
        p = cfg['params'][nm]
        m['A1'] = (f'{nm} Daily Bayesian – 2 Tranches, 50-Day Stop-Loss  '
                   f'(live Feed | auto-extends)')
        m['B2'], m['D2'], m['F2'] = p['lam'], p['phi_L'], p['psi']
        m['H2'], m['J2'], m['L2'] = p['k'], p['premium'], p['peak_cap']
        m['V2'] = 0.5
        m['B3'], m['D3'] = int(round(p['ou_W'])), p['ou_buf_k']
        m['H3'], m['J3'] = p['ou_prem'], p['ou_cap']
        print(f'Feed/Model {nm}: params written '
              f'(prem {p["premium"]*100:.2f}%, ou_prem {p["ou_prem"]*100:.2f}%)')

    # ============================================================== Dashboard
    db = wb['Dashboard']
    db_t = snap(db, 4, range(1, 18))
    for i, nm in enumerate(NEW):
        r = 13 + i
        put(db, r, db_t, 4,
            subs=[("'Feed TSM'", f"'Feed {nm}'"), ("'Model TSM'", f"'Model {nm}'")])
        db.cell(r, 1).value = nm
    db['A1'] = 'HYBRID DASHBOARD — daily pre-open levels (12 daily names)'
    print('Dashboard: rows 13-15 added (nothing below row 12, so nothing moved)')
    rep['moves']['Dashboard'] = 'rows 13-15 appended; no existing row moved'

    # ============================================================= Allocation
    al = wb['Allocation']
    name_t = snap(al, AL_N0, range(1, 29))
    tot_row = snap(al, AL_TOT_OLD, range(1, 29))
    mach_title = snap(al, AL_MACH_TITLE_OLD, range(1, 8))
    mach_hdr = snap(al, AL_MACH_HDR_OLD, range(1, 8))
    mach_t = {j: snap(al, AL_MACH0_OLD + j, range(1, 8)) for j in (0, 1)}
    summ = [snap(al, r, range(1, 3)) for r in range(AL_SUM_OLD[0], AL_SUM_OLD[1] + 1)]
    notes = [(al.cell(r, 1).value, al.cell(r, 1)._style, al.cell(r, 2).value,
              al.cell(r, 2)._style) for r in range(AL_NOTE_OLD0, al.max_row + 1)]

    for r in range(AL_N0, al.max_row + 1):                 # clear below header
        for c in range(1, 29):
            al.cell(r, c).value = None

    at_rowmap = {}                                          # old AT row -> new
    for j in range(18):
        at_rowmap[AT_ORD0 + j] = NF_ORD0 + j
    for i, nm in enumerate(ALL):
        r = AL_N0 + i
        put(al, r, name_t, AL_N0,
            subs=[("'Feed TSM'", f"'Feed {nm}'")],
            xform=lambda f: f.replace('$11:$H$19', '$11:$H$22')
                             .replace('$11:$J$19', '$11:$J$22')
                             .replace('$11:$F$19', '$11:$F$22')
                             .replace('$X$11:$X$18', '$X$11:$X$22')
                             .replace('$Z$11:$Z$18', '$Z$11:$Z$22')
                             .replace('$D$25', f'$D${AL_MACH0_NEW}')
                             .replace('$D$26', f'$D${AL_MACH0_NEW+1}'))
        al.cell(r, 1).value = nm
        al.cell(r, 2).value = 1
        al.cell(r, 5).value = W12                           # cap 1/12
        al.cell(r, 17).value = 0.5                          # Q: Bayes share
        # the U/V/W columns read this name's own two sleeve rows
        for c in (21, 22, 23):
            v = al.cell(r, c).value
            if isinstance(v, str):
                al.cell(r, c).value = (v.replace('$D$25', f'$D${AL_MACH0_NEW+2*i}')
                                        .replace('$D$26', f'$D${AL_MACH0_NEW+2*i+1}'))
    al['B8'] = W12
    put(al, AL_TOT_NEW, tot_row, AL_TOT_OLD, xform=lambda f: f.replace('19)', '22)'))
    al.cell(AL_TOT_NEW, 1).value = 'TOTAL'

    put(al, AL_MACH_TITLE_NEW, mach_title, AL_MACH_TITLE_OLD)
    put(al, AL_MACH_HDR_NEW, mach_hdr, AL_MACH_HDR_OLD)
    lo, hi = AL_MACH0_NEW, AL_MACH0_NEW + 2 * N - 1
    for j in range(2 * N):
        r = lo + j
        i, tr = j // 2, ('Bayes' if j % 2 == 0 else 'OU')
        share = f'$R${AL_N0+i}' if tr == 'Bayes' else f'(1-$R${AL_N0+i})'
        for c, (v, st) in mach_t[j % 2].items():
            al.cell(r, c)._style = pycopy.copy(st)
        al.cell(r, 1).value = ALL[i]
        al.cell(r, 2).value = tr
        al.cell(r, 3).value = (f'=IF(SUM($F${lo}:$F${hi})=0,0,'
                               f'$B$5*F{r}/SUM($F${lo}:$F${hi}))')
        al.cell(r, 4).value = (f"=IF('Active Trading'!$C${NF_ORD0+j}=\"HOLDING\",1,0)")
        al.cell(r, 5).value = f'=$K${AL_N0+i}*{share}'
        al.cell(r, 6).value = f'=E{r}*(1-D{r})'
    sum_f = [f'=COUNT(D{lo}:D{hi})-SUM(D{lo}:D{hi})',
             f'=IF(B{AL_SUM_NEW[0]+1}=0,0,$B$5/B{AL_SUM_NEW[0]+1})',
             f'=IF(ABS(SUM(C{lo}:C{hi})-$B$5)<0.01,"OK","MISMATCH")']
    gate = '=' + '+'.join(f'G{lo+2*i}' for i in range(N))
    al.cell(AL_SUM_NEW[0], 1).value = summ[0][1][0]
    al.cell(AL_SUM_NEW[0], 1)._style = pycopy.copy(summ[0][1][1])
    al.cell(AL_SUM_NEW[0], 7).value = gate
    for k in range(3):
        r = AL_SUM_NEW[0] + 1 + k
        al.cell(r, 1).value = summ[k + 1][1][0]
        al.cell(r, 1)._style = pycopy.copy(summ[k + 1][1][1])
        al.cell(r, 2).value = sum_f[k]
        al.cell(r, 2)._style = pycopy.copy(summ[k + 1][2][1])
    for k, (a, sa, b, sb) in enumerate(notes):
        r = AL_NOTE_OLD0 + AL_NOTE_SHIFT + k
        al.cell(r, 1).value = a
        al.cell(r, 1)._style = pycopy.copy(sa)
        if isinstance(b, str) and b.startswith('='):
            b = shift_local_abs(b, AL_MACH0_OLD, 3)
            b = b.replace(f'$C${AL_MACH0_OLD+3}:$C$40', f'$C${lo}:$C${hi}')
            b = b.replace('$S$11:$S$18', '$S$11:$S$22').replace('$AB$11:$AB$18',
                                                                '$AB$11:$AB$22')
            b = retarget(b, {'Active Trading': {**at_rowmap,
                                                **{r0: r0 + AT_SHIFT for r0 in
                                                   range(AT_LOG0_OLD, AT_LOG_LAST_OLD + 1)}}})
        al.cell(r, 2).value = b
        al.cell(r, 2)._style = pycopy.copy(sb)
    al['A1'] = ('PORTFOLIO ALLOCATION  —  twelve daily names, equal weighted. '
                'RTX, DE and NVDA admitted October 2026.')
    al['A2'] = ('Edit only the blue cells. Twelve daily names, equal weighted: the '
                'floor (B8) and the cap (E11:E22) are both 1/12, which pins each '
                'name to 8.33%.')
    print(f'Allocation: names 11-22, TOTAL {AL_TOT_NEW}, machine {lo}-{hi}, '
          f'summary {AL_SUM_NEW[0]}-{AL_SUM_NEW[1]}')
    rep['moves']['Allocation'] = (f'names 11-19->11-22, TOTAL 21->24, machine '
                                  f'25-42->{lo}-{hi}, summary 43-46->'
                                  f'{AL_SUM_NEW[0]}-{AL_SUM_NEW[1]}, notes +9')
    # ========================================================= Active Trading
    at = wb['Active Trading']
    LOGC = range(1, 34)
    fund_t = snap(at, AT_FUND0, range(1, 13))
    ord_title = snap(at, AT_ORD_TITLE, range(1, 19))
    ord_hdr = snap(at, AT_ORD_HDR, range(1, 19))
    ord_t = {t: snap(at, AT_ORD0 + t, range(1, 19)) for t in (0, 1)}
    log = {r: {c: (at.cell(r, c).value, at.cell(r, c)._style) for c in LOGC}
           for r in range(AT_LOG0_OLD, AT_LOG_LAST_OLD + 1)}
    log_live = sum(1 for r in log if r > AT_LOG0_OLD + 1
                   and log[r][2][0] not in (None, ''))

    # merged section titles that move: unmerge now, re-apply at the new rows
    MERGE_MOVE = {f'A{AT_ORD_TITLE}:I{AT_ORD_TITLE}': f'A{NF_ORD_TITLE}:I{NF_ORD_TITLE}',
                  f'A{AT_LOG0_OLD}:M{AT_LOG0_OLD}':
                      f'A{AT_LOG0_OLD + AT_SHIFT}:M{AT_LOG0_OLD + AT_SHIFT}'}
    for mr in list(MERGE_MOVE):
        if mr in {str(x) for x in at.merged_cells.ranges}:
            at.unmerge_cells(mr)

    for r in range(AT_FUND0, AT_ORD_TITLE):          # funds rows: keep L:N gates
        for c in range(1, 13):
            at.cell(r, c).value = None
    for r in range(AT_ORD_TITLE, AT_LOG_LAST_OLD + 1):
        for c in LOGC:
            at.cell(r, c).value = None

    LOGFIX = [('$42:', '$51:'), ('$1031', '$1040')]

    def logrange(f):
        for a, b in (('$B$42:$B$1031', '$B$51:$B$1040'),):
            f = f.replace(a, b)
        return re.sub(r'(\$[A-Z]{1,2})\$42:(\$[A-Z]{1,2})\$1031',
                      lambda m: f'{m.group(1)}$51:{m.group(2)}$1040', f)

    for i, nm in enumerate(ALL):                     # ---- STOCK FUNDS 7-18
        put(at, AT_FUND0 + i, fund_t, AT_FUND0, xform=lambda f: logrange(f)
            .replace('$R$11:$R$19', '$R$11:$R$22')
            .replace('$A$11:$A$19', '$A$11:$A$22'))
        at.cell(AT_FUND0 + i, 1).value = nm

    put(at, NF_ORD_TITLE, ord_title, AT_ORD_TITLE)   # ---- ORDERS 20/21/22-45
    put(at, NF_ORD_HDR, ord_hdr, AT_ORD_HDR)
    for j in range(2 * N):
        r, i, t = NF_ORD0 + j, j // 2, j % 2
        nm, drow = ALL[i], 4 + i

        qclose = cl(5 + 4 * i)          # this name's CLOSE column in Query

        def fix(f, nm=nm, drow=drow, qc=qclose):
            f = logrange(f)
            # column N's 200dma is per-name: repoint TSM's close col to this name's
            f = f.replace('Query!$E:$E', f'Query!${qc}:${qc}')
            for Lc in 'BAL':
                f = f.replace(f'Dashboard!${Lc}$4:${Lc}$12',
                              f'Dashboard!${Lc}$4:${Lc}$15')
            for Lc in 'CDEF':                        # single-cell Dashboard refs
                f = re.sub(r'Dashboard!' + Lc + r'4(?![0-9])',
                           f'Dashboard!{Lc}{drow}', f)
            f = f.replace('Allocation!$C$25:$C$42',
                          f'Allocation!$C${AL_MACH0_NEW}:$C${AL_MACH0_NEW + 2*N - 1}')
            f = f.replace('ROW()-18', f'ROW()-{NF_ORD0 - 1}')
            return f.replace("'Model TSM'", f"'Model {nm}'")

        put(at, r, ord_t[t], AT_ORD0 + t, xform=fix)
        at.cell(r, 1).value = nm
        at.cell(r, 2).value = 'Bayes' if t == 0 else 'OU'

    for r in sorted(log):                            # ---- LOG REGION +9
        dst = r + AT_SHIFT
        for c, (v, st) in log[r].items():
            if isinstance(v, str) and v.startswith('='):
                v = Translator(v, origin=f'{cl(c)}{r}').translate_formula(f'{cl(c)}{dst}')
                v = shift_local_abs(v, AT_LOG0_OLD, AT_SHIFT)
            cell = at.cell(dst, c)
            cell.value = v
            cell._style = pycopy.copy(st)

    for _, dstm in MERGE_MOVE.items():
        at.merge_cells(dstm)

    at['A1'] = ('ACTIVE TRADING BLOTTER  —  twelve daily names  (TSM · VRT · VST · '
                'AVGO · MU · GM · VLO · CF · MRVL · RTX · DE · NVDA)')
    print(f'Active Trading: funds 7-18, orders {NF_ORD0}-{NF_ORD0+2*N-1}, '
          f'log {AT_LOG0_OLD}-{AT_LOG_LAST_OLD} -> {AT_LOG0_NEW}-'
          f'{AT_LOG_LAST_OLD+AT_SHIFT} ({log_live} live rows carried)')
    rep['moves']['Active Trading'] = (
        f'funds 7-15->7-18, orders 19-36->{NF_ORD0}-{NF_ORD0+2*N-1}, '
        f'log region 40-1041->{AT_LOG0_NEW}-{AT_LOG_LAST_OLD+AT_SHIFT} (+9), '
        f'{log_live} populated log rows carried')

    # ============================================================ Performance
    pf = wb['Performance']
    atmap = {'Active Trading': {r: r + AT_SHIFT
                                for r in range(AT_LOG0_OLD, AT_LOG_LAST_OLD + 1)}}
    npf = 0
    for row in pf.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith('='):
                nv = retarget(cell.value, atmap)
                if nv != cell.value:
                    cell.value = nv
                    npf += 1
    print(f'Performance: {npf} formulas repointed to the moved log')
    rep['moves']['Performance'] = f'{npf} formulas repointed +9'

    # ========================================================= defined names
    dn = wb.defined_names
    dn['IBKR_Orders'].value = (f"'Active Trading'!$A${NF_ORD_HDR}:$J$"
                               f"{NF_ORD0 + 2*N - 1}")
    dn['IBKR_LogAnchor'].value = f"'Active Trading'!$A${AT_LOG0_NEW + 1}"
    rep['defined_names'] = {'IBKR_Orders': ["'Active Trading'!$A$18:$J$36",
                                            dn['IBKR_Orders'].value],
                            'IBKR_LogAnchor': ["'Active Trading'!$A$41",
                                               dn['IBKR_LogAnchor'].value],
                            'IBKR_AvailFunds': ['unchanged', dn['IBKR_AvailFunds'].value],
                            'IBKR_BuyFee': ['unchanged', dn['IBKR_BuyFee'].value],
                            'IBKR_SellFee': ['unchanged', dn['IBKR_SellFee'].value]}
    for k, v in rep['defined_names'].items():
        print(f'  {k:18s} {v[0]:30s} -> {v[1]}')

    # ================================================================== Notes
    nt = wb['Notes']
    nt['B3'] = ('Twelve daily names: TSM, VRT, VST, AVGO, MU, GM, VLO, CF, MRVL '
                '+ RTX, DE, NVDA (admitted October 2026). PARR was assessed in the '
                'same round and declined: unfittable (rho -0.49) and, capped at '
                '$400k for liquidity, it contributed 2.1% on a fixed-size sleeve.')
    nt['B4'] = ('RTX, DE and NVDA carry train-half fitted vectors (train->test rank '
                'correlation +0.36, +0.38, +0.41). The nine keep their live '
                'vectors. Bayes share 0.50 on all twelve (split mode B9=2 reads '
                'Q11:Q22). Backtest: 72.0% full, 20.9% max drawdown, 637 fills/yr.')
    nt['B5'] = ('Allocation is equal weight: floor (B8) and cap (E11:E22) both 1/12 '
                '(8.33%). Enter the CASH available this morning in Allocation!B5. '
                'Overlay is the pre-market rule on all twelve; NO breadth gate.')

    wb.save(out)
    json.dump(rep, open(MAP.split('/')[-1], 'w'), indent=1)
    print(f'\nwritten {out}')
    verify(out, log_live)


def verify(path, log_live):
    print('\n================ VERIFICATION ================')
    wb = openpyxl.load_workbook(path)
    ok = True

    def chk(label, cond, detail=''):
        nonlocal ok
        ok = ok and cond
        print(f'  [{"PASS" if cond else "FAIL"}] {label}' + (f'  {detail}' if detail else ''))

    for nm in NEW:
        chk(f'Feed/Model {nm} exist', f'Feed {nm}' in wb.sheetnames
            and f'Model {nm}' in wb.sheetnames)
    q = wb['Query']
    chk('Query header AL=RTX_O', q['AL1'].value == 'RTX_O', str(q['AL1'].value))
    chk('Query header AT=NVDA_O', q['AT1'].value == 'NVDA_O', str(q['AT1'].value))
    chk('Query AK (MRVL_C) untouched', q['AK1'].value == 'MRVL_C', str(q['AK1'].value))

    al = wb['Allocation']
    chk('Allocation names 11-22', [al.cell(11 + i, 1).value for i in range(N)] == ALL)
    chk('Allocation machine block 28-51',
        [al.cell(AL_MACH0_NEW + j, 1).value for j in range(2 * N)]
        == [s for s in ALL for _ in (0, 1)])
    chk('Allocation cap = 1/12', abs(al['E11'].value - W12) < 1e-12)

    at = wb['Active Trading']
    chk('AT funds rows 7-18', [at.cell(7 + i, 1).value for i in range(N)] == ALL)
    chk('AT order rows 22-45',
        [at.cell(NF_ORD0 + j, 1).value for j in range(2 * N)]
        == [s for s in ALL for _ in (0, 1)])
    chk('AT log header at row 50', at.cell(AT_LOG0_NEW + 1, 1).value == '#',
        repr(at.cell(AT_LOG0_NEW + 1, 1).value))
    live = sum(1 for r in range(AT_LOG0_NEW + 2, at.max_row + 1)
               if at.cell(r, 2).value not in (None, ''))
    chk('AT log rows carried', live == log_live, f'{live} vs {log_live}')
    # row 41 is now inside the expanded orders block, not blank
    j41 = 41 - NF_ORD0
    chk('AT row 41 is now an order row', at.cell(41, 1).value == ALL[j41 // 2]
        and at.cell(41, 2).value == ('Bayes' if j41 % 2 == 0 else 'OU'),
        f'{at.cell(41,1).value} {at.cell(41,2).value}')

    dn = wb.defined_names
    chk('IBKR_Orders', dn['IBKR_Orders'].value
        == f"'Active Trading'!$A${NF_ORD_HDR}:$J${NF_ORD0+2*N-1}",
        dn['IBKR_Orders'].value)
    chk('IBKR_LogAnchor', dn['IBKR_LogAnchor'].value
        == f"'Active Trading'!$A${AT_LOG0_NEW+1}", dn['IBKR_LogAnchor'].value)
    chk('IBKR_AvailFunds unmoved', dn['IBKR_AvailFunds'].value == 'Allocation!$B$5')

    # ---- the 200dma column must point at each name's OWN Query close column
    bad200 = []
    for j in range(2 * N):
        want = cl(5 + 4 * (j // 2))
        v = str(at.cell(NF_ORD0 + j, 14).value or '')
        if f'Query!${want}:${want}' not in v:
            bad200.append(f'{ALL[j//2]} r{NF_ORD0+j} wants {want}')
    chk('200dma column per-name', not bad200, '; '.join(bad200[:4]))

    # ---- the one that matters: every live trade record intact, moved +9
    srcwb = openpyxl.load_workbook(SRC)
    sat = srcwb['Active Trading']
    diffs, cmp_rows = [], 0
    for r in range(AT_LOG0_OLD + 2, AT_LOG_LAST_OLD + 1):
        if sat.cell(r, 2).value in (None, '') and sat.cell(r, 21).value in (None, ''):
            continue
        cmp_rows += 1
        for c in list(range(1, 13)) + list(range(20, 34)):
            a, b = sat.cell(r, c).value, at.cell(r + AT_SHIFT, c).value
            if isinstance(a, str) and a.startswith('='):
                continue                      # formulas are re-pointed by design
            if isinstance(a, float) and isinstance(b, float):
                # openpyxl re-serialises floats; accept last-ULP drift, not change
                if a == b or abs(a - b) <= 1e-9 * max(1.0, abs(a)):
                    continue
            if a != b:
                diffs.append(f'r{r}->{r+AT_SHIFT} {cl(c)}: {a!r} != {b!r}')
    chk(f'log data intact ({cmp_rows} records compared)', not diffs,
        '; '.join(diffs[:4]))

    stale = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, str) and v.startswith('='):
                    if 'Allocation!$C$25:$C$42' in v or 'Dashboard!$B$4:$B$12' in v:
                        stale.append(f'{ws.title}!{c.coordinate}')
    chk('no stale 9-name ranges', not stale, ', '.join(stale[:5]))
    print('================ ' + ('ALL PASS' if ok else 'FAILURES ABOVE')
          + ' ================')


if __name__ == '__main__':
    main()
