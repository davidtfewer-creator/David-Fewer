"""
Guard against the failure that broke the weekly sheet's buy levels.

Two things had to line up for that bug: a formula that fails wholesale on some Excel versions
(MAXIFS, which needs 2019 or 365), and an IFERROR feeding a column that carries its previous value
forward, so one silent #NAME? froze the all-time-high for the entire sample.

This checks both: any function that needs a specific Excel version, and any IFERROR sitting on a
formula that references its own column one row up. Run it on every workbook before sending one.

    python3 xlsx_compat_check.py file.xlsx [file2.xlsx ...]
"""
import collections, re, sys
import openpyxl

VERSIONED = {'MAXIFS': '2019+', 'MINIFS': '2019+', 'IFS': '2019+', 'SWITCH': '2019+',
             'TEXTJOIN': '2019+', 'CONCAT': '2019+', 'XLOOKUP': '365', 'FILTER': '365',
             'SORT': '365', 'UNIQUE': '365', 'SEQUENCE': '365', 'LET': '365',
             'LAMBDA': '365', 'XMATCH': '365', 'TEXTSPLIT': '365', 'IFNA': '2013+',
             'AGGREGATE': '2010+'}
PAT = re.compile(r'(?<![A-Z0-9_.])(' + '|'.join(VERSIONED) + r')\s*\(')


def check(path):
    wb = openpyxl.load_workbook(path)
    vers = collections.Counter(); first = {}; carriers = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if not isinstance(v, str) or not v.startswith('='): continue
                for m in PAT.findall(v.upper()):
                    vers[m] += 1; first.setdefault(m, f'{ws.title}!{c.coordinate}')
                if 'IFERROR' in v.upper() and c.row > 1 and re.search(
                        rf'(?<![A-Z${{]}}]){c.column_letter}{c.row-1}(?![0-9])', v):
                    carriers.append(f'{ws.title}!{c.coordinate}')
    print(f'{path}')
    if vers:
        for m, n in vers.items():
            print(f'  VERSION RISK  {m} ({VERSIONED[m]}): {n} cells, first {first[m]}')
    else:
        print('  version-dependent functions: none')
    if carriers:
        print(f'  SILENT-FAILURE RISK  IFERROR on a self-carrying column: '
              f'{len(carriers)} cells, first {carriers[0]}')
    else:
        print('  IFERROR on a self-carrying column: none')
    return not vers and not carriers


if __name__ == '__main__':
    ok = all([check(p) for p in sys.argv[1:]])
    sys.exit(0 if ok else 1)
