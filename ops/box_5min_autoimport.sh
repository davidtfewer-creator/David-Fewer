#!/usr/bin/env bash
# Import every un-imported Box text extraction in the tool-results directory,
# taking each file's TICKER from its own first line ("VRT 5min") rather than
# from the order the Box calls were made in. Call order is not a safe key when
# several get_file_content calls run concurrently, and a mis-mapped ticker is a
# silent data corruption, not an error.
set -u
DIR="${1:?tool-results dir}"
OUT=/home/user/David-Fewer/premarket_study/data_5min
mkdir -p "$OUT"
for f in "$DIR"/mcp-Box-get_file_content-*.txt; do
  [ -e "$f" ] || continue
  t=$(head -1 "$f" | awk '{print $1}')
  case "$t" in ''|*[!A-Z]*) echo "SKIP $(basename "$f"): first line is not a ticker"; continue;; esac
  if [ -s "$OUT/${t}_5min.xlsx" ]; then echo "have $t"; continue; fi
  python3 /home/user/David-Fewer/ops/box_5min_import.py "$f" "$t" 2>&1 | tail -2
done
