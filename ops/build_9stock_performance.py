"""
build_9stock_performance.py — companion performance workbook (user, 4 Sep 2026).

Creates 9stock_performance.xlsx: a SEPARATE workbook that reads the live
trading workbook (a mirror that must never be modified) by external links and
compares realised P&L against a planned-return band.

Contents:
  Performance sheet
    - assumptions: starting capital (match the trading book's Performance!C4),
      MIN planned return (default 66%/yr — the plan without pooling credit)
      and MAX planned return (default 88.5%/yr — the pooled full-sample
      ceiling reference). All editable.
    - Table 1: weekly + cumulative P&L (as recorded — blotter plus closed
      discretionary trades, Active Trading cols P and R) against the
      cumulative MIN/MAX plan lines, with variance columns.
    - Table 2: the same EXCLUDING the discretionary log (weekly P&L minus the
      disc log's closed Net P&L for that week ending), cumulative, variances.
    - two charts: cumulative actual vs the plan band, all trading and
      model-only.
  Feed sheet
    - direct external references to the source ('[1]Active Trading'!O42:O93,
      P42:P93, R42:R93 and the disc log AD42:AD241 / AE42:AE241). Direct cell
      references are the ONE link type Excel refreshes from a CLOSED source —
      SUMIFS/INDIRECT against closed workbooks return errors, which is why the
      raw columns are mirrored here and everything else computes locally.

The external-link plumbing (xl/externalLinks/*, workbook externalReferences,
content types) is injected into the saved zip because openpyxl does not
manage external workbooks; the link cache is seeded with the source's own
Excel-cached values so the file shows real numbers even before the first
refresh. The link target is the source's bare filename, so the pair works in
ANY folder as long as the two files sit together. If the live file is ever
renamed: Data -> Edit Links -> Change Source.

Usage:
    python build_9stock_performance.py <source_trading_book.xlsx> <out.xlsx>
The source is opened READ-ONLY (cached values only); it is never written.
"""
import datetime as dt
import os
import re
import shutil
import sys
import zipfile

import openpyxl
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

NAVY, GOLD, TEAL, GREY = 'FF182644', 'FFC6A04A', 'FF176E78', 'FF5F5F5F'
EPOCH = dt.date(1899, 12, 30)
WK_ROWS = range(42, 94)          # weekly log rows in Active Trading
DISC_ROWS = range(42, 242)       # discretionary log rows
NROWS = len(WK_ROWS)             # 52


def serial(v):
    if isinstance(v, dt.datetime):
        v = v.date()
    return (v - EPOCH).days


def read_cache(src_path):
    """Cached values of every mirrored source cell, for the link cache."""
    wb = openpyxl.load_workbook(src_path, data_only=True)
    at = wb['Active Trading']
    cache = {}
    for col in ('O', 'P', 'R'):
        for r in WK_ROWS:
            cache[f'{col}{r}'] = at[f'{col}{r}'].value
    for col in ('AD', 'AE'):
        for r in DISC_ROWS:
            cache[f'{col}{r}'] = at[f'{col}{r}'].value
    return cache


def build(src_name, out_path, start_cap):
    wb = openpyxl.Workbook()
    pf = wb.active
    pf.title = 'Performance'
    fd = wb.create_sheet('Feed')
    hdr_fill = PatternFill(fill_type='solid', start_color=NAVY, end_color=NAVY)
    hdr_font = Font(bold=True, color='FFFFFFFF')

    # ---------------- Feed: direct external references only
    fd['A1'], fd['B1'], fd['C1'] = 'Week ending', 'Weekly P&L', 'Cumulative'
    fd['E1'], fd['F1'] = 'Disc net P&L', 'Disc week ending'
    for c in ('A1', 'B1', 'C1', 'E1', 'F1'):
        fd[c].font = Font(bold=True, color=NAVY)
    for i, r_src in enumerate(WK_ROWS):
        r = 2 + i
        fd.cell(row=r, column=1, value=f"='[1]Active Trading'!O{r_src}").number_format = 'dd/mm/yyyy'
        fd.cell(row=r, column=2, value=f"='[1]Active Trading'!P{r_src}")
        fd.cell(row=r, column=3, value=f"='[1]Active Trading'!R{r_src}")
    for i, r_src in enumerate(DISC_ROWS):
        r = 2 + i
        fd.cell(row=r, column=5, value=f"='[1]Active Trading'!AD{r_src}")
        f = fd.cell(row=r, column=6, value=f"='[1]Active Trading'!AE{r_src}")
        f.number_format = 'dd/mm/yyyy'
    fd['H2'] = ('Direct external references to the trading workbook (same folder). '
                'Do not edit; everything downstream computes on the Performance sheet.')
    fd['H2'].font = Font(italic=True, size=9, color=GREY)

    # ---------------- Performance sheet
    t = pf.cell(row=1, column=1, value='BAYESIAN CAPITAL — 9-STOCK BOOK vs PLAN BAND')
    t.font = Font(bold=True, size=13, color=NAVY)
    pf.cell(row=2, column=1, value=(
        f'Feeds from {src_name} in the same folder (never modified). Actual = weekly '
        'realised P&L as recorded (blotter + closed discretionary trades); the second '
        'table strips the discretionary log. Enable link updates when Excel asks.')
    ).font = Font(italic=True, color=GREY)

    pf.cell(row=4, column=2, value='Starting capital').font = Font(bold=True)
    c = pf.cell(row=4, column=3, value=start_cap)
    c.number_format = '$#,##0'
    pf.cell(row=4, column=4, value='keep equal to the trading workbook, Performance!C4'
            ).font = Font(italic=True, size=9, color=GREY)
    pf.cell(row=5, column=2, value='MIN planned return (p.a.)').font = Font(bold=True)
    pf.cell(row=5, column=3, value=0.66).number_format = '0.0%'
    pf.cell(row=5, column=4, value='plan without the pooling credit — the cautious floor'
            ).font = Font(italic=True, size=9, color=GREY)
    pf.cell(row=6, column=2, value='MAX planned return (p.a.)').font = Font(bold=True)
    pf.cell(row=6, column=3, value=0.885).number_format = '0.0%'
    pf.cell(row=6, column=4, value='pooled full-sample measurement — the ceiling reference; '
            'the central 74–75% plan lives in the trading workbook'
            ).font = Font(italic=True, size=9, color=GREY)
    pf.cell(row=7, column=2, value='Weekly rate MIN / MAX').font = Font(bold=True)
    pf.cell(row=7, column=3, value='=(1+$C$5)^(1/52)-1').number_format = '0.000%'
    pf.cell(row=7, column=4, value='=(1+$C$6)^(1/52)-1').number_format = '0.000%'

    heads = ['Week #', 'Week ending', 'Weekly P&L', 'Cumulative P&L',
             'Cum plan MIN', 'Cum plan MAX', 'vs MIN', 'vs MAX', '',
             'Weekly P&L excl disc', 'Cumulative excl disc',
             'excl disc vs MIN', 'excl disc vs MAX']
    for j, h in enumerate(heads, start=1):
        if not h:
            continue
        cell = pf.cell(row=10, column=j, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
    widths = [7, 12, 13, 14, 14, 14, 12, 12, 2, 15, 15, 13, 13]
    for j, w in enumerate(widths, start=1):
        pf.column_dimensions[get_column_letter(j)].width = w

    for i in range(NROWS):
        r, rf = 11 + i, 2 + i
        pf.cell(row=r, column=1, value=f'=IF($B{r}="","",ROW()-10)')
        b = pf.cell(row=r, column=2,
                    value=f'=IF(OR(Feed!A{rf}="",Feed!A{rf}=0),"",Feed!A{rf})')
        b.number_format = 'dd/mm/yyyy'
        # actual columns blank for weeks that have not started yet
        pf.cell(row=r, column=3,
                value=f'=IF(OR($B{r}="",$B{r}>TODAY()+6),"",N(Feed!B{rf}))')
        pf.cell(row=r, column=4, value=f'=IF($C{r}="","",N(Feed!C{rf}))')
        pf.cell(row=r, column=5, value=f'=IF($B{r}="","",$C$4*((1+$C$7)^$A{r}-1))')
        pf.cell(row=r, column=6, value=f'=IF($B{r}="","",$C$4*((1+$D$7)^$A{r}-1))')
        pf.cell(row=r, column=7, value=f'=IF(OR($D{r}="",$E{r}=""),"",$D{r}-$E{r})')
        pf.cell(row=r, column=8, value=f'=IF(OR($D{r}="",$F{r}=""),"",$D{r}-$F{r})')
        pf.cell(row=r, column=10,
                value=(f'=IF($C{r}="","",$C{r}'
                       f'-SUMIFS(Feed!$E$2:$E$201,Feed!$F$2:$F$201,$B{r}))'))
        pf.cell(row=r, column=11, value=f'=IF($J{r}="","",SUM($J$11:$J{r}))')
        pf.cell(row=r, column=12, value=f'=IF(OR($K{r}="",$E{r}=""),"",$K{r}-$E{r})')
        pf.cell(row=r, column=13, value=f'=IF(OR($K{r}="",$F{r}=""),"",$K{r}-$F{r})')
        for j in (3, 4, 5, 6, 7, 8, 10, 11, 12, 13):
            pf.cell(row=r, column=j).number_format = '$#,##0'

    last = 10 + NROWS

    def mk_chart(title, val_col):
        ch = LineChart()
        ch.title = title
        ch.style = 2
        ch.height, ch.width = 9, 16
        cats = Reference(pf, min_col=2, min_row=11, max_row=last)
        for col, rgb, wd, dash in ((val_col, TEAL[2:], 28000, None),
                                   (5, GREY[2:], 16000, 'dash'),
                                   (6, GOLD[2:], 16000, 'dash')):
            ref = Reference(pf, min_col=col, min_row=10, max_row=last)
            ch.add_data(ref, titles_from_data=True)
            s = ch.series[-1]
            s.graphicalProperties.line.solidFill = rgb
            s.graphicalProperties.line.width = wd
            if dash:
                s.graphicalProperties.line.dashStyle = dash
        ch.set_categories(cats)
        ch.y_axis.numFmt = '$#,##0'
        return ch

    pf.add_chart(mk_chart('Cumulative P&L vs plan band — all trading', 4), f'A{last + 3}')
    pf.add_chart(mk_chart('Cumulative P&L vs plan band — excluding discretionary', 11),
                 f'J{last + 3}')

    wb.calculation.fullCalcOnLoad = True
    wb.save(out_path)


# ---------------- external-link injection (openpyxl does not manage these)
CT_EL = ('application/vnd.openxmlformats-officedocument.spreadsheetml.'
         'externalLink+xml')
NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
NS_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL_EL = f'{NS_R}/externalLink'
REL_ELPATH = f'{NS_R}/externalLinkPath'


def cached_xml(cache):
    """<sheetData> rows for the link cache, from the source's Excel-cached values."""
    by_row = {}
    for ref, v in cache.items():
        if v is None:
            continue
        m = re.match(r'([A-Z]+)(\d+)', ref)
        by_row.setdefault(int(m.group(2)), []).append((ref, v))
    rows = []
    for rn in sorted(by_row):
        cells = []
        for ref, v in sorted(by_row[rn]):
            if isinstance(v, (dt.datetime, dt.date)):
                cells.append(f'<cell r="{ref}"><v>{serial(v)}</v></cell>')
            elif isinstance(v, (int, float)):
                cells.append(f'<cell r="{ref}"><v>{v!r}</v></cell>')
            else:                                   # strings ("", OPEN, ...)
                s = str(v).replace('&', '&amp;').replace('<', '&lt;')
                cells.append(f'<cell r="{ref}" t="str"><v>{s}</v></cell>')
        rows.append(f'<row r="{rn}">{"".join(cells)}</row>')
    return ''.join(rows)


def inject_links(path, src_name, cache):
    tmp = path + '.tmp'
    zin = zipfile.ZipFile(path)
    zout = zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED)
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == '[Content_Types].xml':
            data = data.replace(
                b'</Types>',
                f'<Override PartName="/xl/externalLinks/externalLink1.xml" '
                f'ContentType="{CT_EL}"/></Types>'.encode())
        elif item.filename == 'xl/workbook.xml':
            data = data.replace(
                b'</sheets>',
                b'</sheets><externalReferences><externalReference '
                b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/'
                b'2006/relationships" r:id="rIdEL1"/></externalReferences>')
        elif item.filename == 'xl/_rels/workbook.xml.rels':
            data = data.replace(
                b'</Relationships>',
                f'<Relationship Id="rIdEL1" Type="{REL_EL}" '
                f'Target="externalLinks/externalLink1.xml"/></Relationships>'.encode())
        zout.writestr(item, data)
    zout.writestr(
        'xl/externalLinks/externalLink1.xml',
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<externalLink xmlns="{NS_MAIN}" xmlns:r="{NS_R}">'
        f'<externalBook r:id="rId1">'
        f'<sheetNames><sheetName val="Active Trading"/></sheetNames>'
        f'<sheetDataSet><sheetData sheetId="0">{cached_xml(cache)}</sheetData>'
        f'</sheetDataSet></externalBook></externalLink>')
    zout.writestr(
        'xl/externalLinks/_rels/externalLink1.xml.rels',
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        f'relationships"><Relationship Id="rId1" Type="{REL_ELPATH}" '
        f'Target="{src_name}" TargetMode="External"/></Relationships>')
    zout.close()
    zin.close()
    shutil.move(tmp, path)


def main():
    src, out = sys.argv[1], sys.argv[2]
    src_name = os.path.basename(src)
    # strip an upload-hash prefix if the file came through chat
    src_name = re.sub(r'^[0-9a-f]{8}-', '', src_name)
    cache = read_cache(src)
    wbp = openpyxl.load_workbook(src, data_only=True)
    start_cap = wbp['Performance']['C4'].value or 5_000_000
    build(src_name, out, start_cap)
    inject_links(out, src_name, cache)

    # ---- validation: zip integrity, xml well-formedness, openpyxl reload
    import xml.dom.minidom
    z = zipfile.ZipFile(out)
    assert z.testzip() is None
    for part in ('xl/externalLinks/externalLink1.xml',
                 'xl/externalLinks/_rels/externalLink1.xml.rels',
                 'xl/workbook.xml', '[Content_Types].xml'):
        xml.dom.minidom.parseString(z.read(part))
    z.close()
    wb2 = openpyxl.load_workbook(out)
    assert wb2.sheetnames == ['Performance', 'Feed']
    assert wb2['Feed']['A2'].value == "='[1]Active Trading'!O42"
    print(f'built {out} (links -> {src_name}, start capital {start_cap:,.0f}); '
          f'validation passed')


if __name__ == '__main__':
    main()
