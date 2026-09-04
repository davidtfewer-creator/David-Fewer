"""
refresh_performance.py — update 9stock_performance.xlsx from the trading book.

Rebuilds the performance workbook as a fresh VALUES snapshot of the trading
workbook (no external links — displays and computes correctly everywhere,
including Excel on the web / Box, which cannot refresh workbook links), while
PRESERVING everything you typed in the old copy: starting capital, MIN/MAX
plan returns, and every Capital added entry.

Usage (trading machine, any time — after Script 2, or in the Sunday package):

    python refresh_performance.py "TradingExcel_9stock_avgo.xlsx" "9stock_performance.xlsx"

The trading workbook is opened read-only; the performance workbook is
replaced in place. Requires: pip install openpyxl. Keep this file next to
build_9stock_performance.py (it does the actual work).
"""
import sys

import build_9stock_performance as b


def main():
    if len(sys.argv) != 3:
        sys.exit('usage: python refresh_performance.py <trading.xlsx> <9stock_performance.xlsx>')
    sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2]]     # static mode (no --links)
    b.main()


if __name__ == '__main__':
    main()
