"""
Build a scaffold Excel workbook that hosts the Power Query replica of the Apps Script feed.
Uses plain cells + workbook DEFINED NAMES (Config, Tickers) rather than Excel Tables, which
avoids the openpyxl-vs-Excel table "repair" prompt. No API key is written anywhere.
"""
import openpyxl
from openpyxl.styles import Font
from openpyxl.workbook.defined_name import DefinedName

OUT = '/home/user/David-Fewer/Hybrid10_Feed_PowerQuery.xlsx'
TICKERS = ['NVDA','TSM','TSLA','VRT','VST','AVGO','PLTR','RKLB','SOFI','SPOT']
HDR = Font(name='Arial', size=10, bold=True)
TITLE = Font(name='Arial', size=11, bold=True)
MONO = Font(name='Consolas', size=9)

wb = openpyxl.Workbook()

# ---- Config sheet (range named "Config") ----
cfg = wb.active; cfg.title = 'Config'
cfg['A1'] = 'Setting'; cfg['B1'] = 'Value'
cfg['A2'] = 'ApiKey'                               # B2 left empty (user pastes key)
cfg['A3'] = 'StartDate'; cfg['B3'] = '2024-04-01'
cfg['A1'].font = HDR; cfg['B1'].font = HDR
cfg['D2'] = 'paste your Massive API key in B2 (kept out of the query code)'
cfg['D3'] = 'feed start date yyyy-mm-dd (matches the script)'
cfg.column_dimensions['A'].width = 12
cfg.column_dimensions['B'].width = 26
cfg.column_dimensions['D'].width = 58

# ---- Tickers sheet (range named "Tickers") ----
tk = wb.create_sheet('Tickers')
tk['A1'] = 'Ticker'; tk['A1'].font = HDR
for i, t in enumerate(TICKERS, start=2):
    tk.cell(i, 1, t)
tk.column_dimensions['A'].width = 12

# ---- workbook-scoped defined names the query reads ----
wb.defined_names.add(DefinedName('Config',  attr_text="Config!$A$1:$B$3"))
wb.defined_names.add(DefinedName('Tickers', attr_text=f"Tickers!$A$1:$A${1+len(TICKERS)}"))

# ---- Data sheet: header only (query load target) ----
data = wb.create_sheet('Data')
hdr = ['Date']
for t in TICKERS:
    hdr += [f'{t}_O', f'{t}_H', f'{t}_L', f'{t}_C']
for j, h in enumerate(hdr, start=1):
    data.cell(1, j, h).font = HDR
data['A3'] = ('Load the Hybrid10Feed query here (Close & Load To > Table > =Data!$A$1); '
              'it overwrites this header with the live feed.')
data.column_dimensions['A'].width = 12

# ---- ReadMe sheet: steps + M code ----
rm = wb.create_sheet('ReadMe')
rm.column_dimensions['A'].width = 120
lines = [
    ('Hybrid10 Feed - Power Query replica of the Google Apps Script', True),
    ('', False),
    ('WHAT THIS DOES', True),
    ('Pulls daily OHLC for the ten tickers from the Massive aggregates API (same endpoint the', False),
    ('Apps Script used) and builds Date | <TK>_O/_H/_L/_C, keeping only dates common to all ten.', False),
    ('', False),
    ('SECURITY', True),
    ('The key is NOT stored in the query - paste it into Config!B2. Rotate the key you shared in', False),
    ('chat, since it was exposed.', False),
    ('', False),
    ('ONE-TIME SETUP', True),
    ('1. Config!B2: paste your Massive API key.  Config!B3: start date (default 2024-04-01).', False),
    ('2. Data tab: Get Data > Launch Power Query Editor > New Query > Blank Query.', False),
    ('3. Advanced Editor: delete all, paste the M code below, Done. Rename the query Hybrid10Feed.', False),
    ('4. Close & Load To... > Table > Existing worksheet > =Data!$A$1.', False),
    ('5. First refresh: set the api.massive.com credential to Anonymous (the key rides in the URL).', False),
    ('', False),
    ('REFRESH LATER: Data > Refresh All. Date is emitted as text dd/MM/yyyy (as the script did).', False),
    ('', False),
    ('==================  M CODE (paste into Advanced Editor)  ==================', True),
]
r = 1
for text, bold in lines:
    if text:
        c = rm.cell(r, 1, text)
        c.font = TITLE if bold else Font(name='Arial', size=10)
    r += 1
with open('/home/user/David-Fewer/premarket_study/HybridFeed.m') as f:
    for code_line in f.read().splitlines():
        if code_line != '':
            rm.cell(r, 1, code_line).font = MONO
        r += 1

wb.save(OUT)
print('saved', OUT)
print('defined names:', list(wb.defined_names))
print('sheets:', wb.sheetnames)
