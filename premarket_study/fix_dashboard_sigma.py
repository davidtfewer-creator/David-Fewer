"""
The Dashboard's OU sigma was never moved to the residual definition.

Column AZ on every Model sheet was corrected to the standard deviation of the fitted AR(1)
residuals, and the buffers in D3 were re-scaled to suit -- TSM 0.40 to 0.20, VRT 0.57 to 0.40,
VST 0.24 to 0.65, RKLB 0.22 to 0.25, MU 0.30 to 0.75. The Dashboard, which is the sheet the
morning orders are actually read from, still computes

    OU sig  =  STDEVP( last W closes )

the level dispersion the correction removed. It then multiplies that by the re-scaled buffer. The
two changes compound in the same direction: a sigma several times too large multiplied by a buffer
raised on the assumption it would be small. The OU bid comes out far below the market -- MU's is
636 against a close of 830 -- and simply never fills.

The Model sheets are unaffected; the backtest is correct. This is a display-layer bug, and the
display layer is what gets traded, so it is the more serious of the two places to have it.

The fix replaces column P with the same residual construction the Model sheet's AZ uses, written
against the Feed columns the Dashboard already addresses.
"""
import shutil
import openpyxl

SRC = ('/root/.claude/uploads/2d71f10a-e19f-51b2-8457-2cd547c34dff/'
       'ca376547-TradingExcel_5stock_live.xlsx')
OUT = '/home/user/David-Fewer/TradingExcel_5stock_live_fixed.xlsx'
NAMES = ['TSM', 'VRT', 'VST', 'RKLB', 'MU']


def resid_sigma(row, stock):
    """Residual sigma over the last W closes of Feed <stock>, mirroring Model!AZ."""
    n = f'COUNTIF(\'Feed {stock}\'!$E$2:$E$2000,">0")'
    w = f'M{row}'
    # same offsets the AR(1) slope in column O already uses, so sigma and the coefficient are
    # measured on identical windows
    cur = f"OFFSET('Feed {stock}'!$E$1,{n}-{w}+2,0,{w}-1,1)"    # x_t
    lag = f"OFFSET('Feed {stock}'!$E$1,{n}-{w}+1,0,{w}-1,1)"    # x_{t-1}
    mu, ar = f'N{row}', f'O{row}'
    e = f'(({cur}-{mu})-{ar}*({lag}-{mu}))'
    me = f'((AVERAGE({cur})-{mu})-{ar}*(AVERAGE({lag})-{mu}))'
    return f'=SQRT(SUMPRODUCT(({e}-{me})^2)/({w}-1))'


if __name__ == '__main__':
    shutil.copy(SRC, OUT)
    wb = openpyxl.load_workbook(OUT)
    d = wb['Dashboard']
    d['P3'] = 'OU sig (resid)'
    for i, s in enumerate(NAMES):
        r = 4 + i
        d.cell(r, 16, resid_sigma(r, s))
    n = wb['Notes']
    n['A17'] = 'Dashboard OU sigma'
    n['B17'] = ('Dashboard column P computed STDEVP of the last W closes -- the level sigma the '
                'OU correction removed -- while the Model sheets used residual sigma and the '
                'buffers in D3 had been re-scaled to match. The OU BUY levels on the Dashboard '
                'were therefore far below the market and would not have filled. Column P now '
                'uses the same residual construction as Model!AZ. Backtests were never affected; '
                'only the morning order levels were.')
    wb.save(OUT)
    print('wrote', OUT, flush=True)
    for i, s in enumerate(NAMES):
        print(f'  Dashboard P{4+i} ({s}) rewritten', flush=True)
    print('DONE', flush=True)
