"""
Build the Power Query feed host workbook with XlsxWriter (Excel-clean output; proper XML
prologs, no table-part quirks). Plain cells + workbook defined names Config / Tickers.
No API key written anywhere.
"""
import xlsxwriter

OUT = '/home/user/David-Fewer/Hybrid10_Feed_PowerQuery.xlsx'
TICKERS = ['NVDA','TSM','TSLA','VRT','VST','AVGO','PLTR','RKLB','SOFI','SPOT']

wb = xlsxwriter.Workbook(OUT, {'strings_to_numbers': False})
hdr   = wb.add_format({'bold': True, 'font_name': 'Arial', 'font_size': 10})
title = wb.add_format({'bold': True, 'font_name': 'Arial', 'font_size': 11, 'font_color': '#0B1F3A'})
plain = wb.add_format({'font_name': 'Arial', 'font_size': 10})
mono  = wb.add_format({'font_name': 'Consolas', 'font_size': 9})
txt   = wb.add_format({'num_format': '@'})

# ---- Config ----
cfg = wb.add_worksheet('Config')
cfg.set_column('A:A', 12); cfg.set_column('B:B', 26); cfg.set_column('D:D', 58)
cfg.write('A1', 'Setting', hdr); cfg.write('B1', 'Value', hdr)
cfg.write('A2', 'ApiKey')                       # B2 left blank for the user's key
cfg.write_string('B3', '2024-04-01', txt); cfg.write('A3', 'StartDate')
cfg.write('D2', 'paste your Massive API key in B2 (kept out of the query code)')
cfg.write('D3', 'feed start date yyyy-mm-dd (matches the script)')

# ---- Tickers ----
tk = wb.add_worksheet('Tickers')
tk.set_column('A:A', 12)
tk.write('A1', 'Ticker', hdr)
for i, t in enumerate(TICKERS, start=1):
    tk.write(i, 0, t)

# ---- Data (query load target) ----
data = wb.add_worksheet('Data')
data.set_column('A:A', 12)
cols = ['Date']
for t in TICKERS:
    cols += [f'{t}_O', f'{t}_H', f'{t}_L', f'{t}_C']
for j, h in enumerate(cols):
    data.write(0, j, h, hdr)
data.write('A3', 'Load the Hybrid10Feed query here (Close & Load To > Table > =Data!$A$1); '
                 'it overwrites this header with the live feed.')

# ---- ReadMe ----
rm = wb.add_worksheet('ReadMe')
rm.set_column('A:A', 120)
lines = [
    ('Hybrid10 Feed - Power Query replica of the Google Apps Script', title),
    ('', None),
    ('WHAT THIS DOES', title),
    ('Pulls daily OHLC for the ten tickers from the Massive aggregates API (same endpoint the', plain),
    ('Apps Script used) and builds Date | <TK>_O/_H/_L/_C, keeping only dates common to all ten.', plain),
    ('', None),
    ('SECURITY', title),
    ('The key is NOT stored in the query - paste it into Config!B2. Rotate the key you shared in', plain),
    ('chat, since it was exposed.', plain),
    ('', None),
    ('ONE-TIME SETUP', title),
    ('1. Config!B2: paste your Massive API key.  Config!B3: start date (default 2024-04-01).', plain),
    ('2. Data tab: Get Data > Launch Power Query Editor > New Query > Blank Query.', plain),
    ('3. Advanced Editor: delete all, paste the M code below, Done. Rename the query Hybrid10Feed.', plain),
    ('4. Close & Load To... > Table > Existing worksheet > =Data!$A$1.', plain),
    ('5. First refresh: set the api.massive.com credential to Anonymous (the key rides in the URL).', plain),
    ('', None),
    ('REFRESH LATER: Data > Refresh All. Date is emitted as text dd/MM/yyyy (as the script did).', plain),
    ('', None),
    ('==================  M CODE (paste into Advanced Editor)  ==================', title),
]
r = 0
for text, fmt in lines:
    if text:
        rm.write(r, 0, text, fmt)
    r += 1
with open('/home/user/David-Fewer/premarket_study/HybridFeed.m') as f:
    for code_line in f.read().splitlines():
        if code_line != '':
            rm.write(r, 0, code_line, mono)
        r += 1

# ---- workbook defined names the query reads ----
wb.define_name('FeedConfig',  "=Config!$A$1:$B$3")
wb.define_name('FeedTickers', f"=Tickers!$A$1:$A${1+len(TICKERS)}")

wb.close()
print('saved', OUT)
