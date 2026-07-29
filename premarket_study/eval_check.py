import formulas
OUT='/home/user/David-Fewer/TradingExcel_s1_laddering_OptionC_backtest.xlsx'
xl = formulas.ExcelModel().loads(OUT).finish()
sol = xl.calculate()
# find the Model NVDA Y5 (annual), AA4 (buys), Y4 (profit), FUND867
import re
def get(cellkey_substr):
    for k,v in sol.items():
        if cellkey_substr in k.upper():
            return k, v
    return None, None
for tgt in ["'MODEL NVDA'!Y5","'MODEL NVDA'!AA4","'MODEL NVDA'!Y4"]:
    for k,v in sol.items():
        if k.upper().endswith(tgt.split('!')[1]) and 'MODEL NVDA' in k.upper():
            try: print(tgt, '=', v.value[0,0])
            except Exception as e: print(tgt, 'val', v)
            break
