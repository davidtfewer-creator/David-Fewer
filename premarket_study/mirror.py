"""
A read-only mirror of the trading workbook, so the model can be looked at while Python writes it.

The problem is narrow: Excel opens an .xlsx with a share mode that permits other readers but not
other writers, so while the master is open in Excel any openpyxl save to it fails with
PermissionError. Reads are fine. It is only the write that collides.

So the mirror does not need to be clever. It needs to be a different file that nothing writes to.

    model/TradingExcel_5stock_live.xlsx      <- Python owns this. Nobody opens it in Excel, ever.
    view/model_view_20260805_1432.xlsx       <- what you open. A snapshot. Python never re-opens it.

Two facts about this particular workbook make a plain byte copy the right answer:

  It has no Power Query connections -- the Query sheet is an ordinary sheet that the IBKR script
  writes into via the IBKR_QueryAnchor name -- so opening a copy will not prompt for a refresh or
  reach for an external data source.

  openpyxl wipes every cached formula result when it saves (the values become <v/>) but it also
  writes fullCalcOnLoad="1" into the workbook, so Excel recalculates everything the moment the
  file is opened. The snapshot therefore displays correct numbers even though the bytes on disk
  contain none.

The second point has a consequence that matters more than the mirror does, and it is the reason
publish() warns about it: after any openpyxl save, the MASTER also holds no cached values. Anything
that reads the master back with data_only=True gets None until Excel has opened and saved it. If
the pipeline writes prices with openpyxl and then expects to read computed order levels back out,
it cannot work -- there is nothing to read. Use the Excel-driven path below for that, where Excel
does the calculating and the cached values are real.

------------------------------------------------------------------------------------------------
Recipe

  Every script that writes the master:

      from mirror import assert_writable, save_atomic, publish

      assert_writable(MASTER)          # fail fast and clearly if a human has it open
      ...                              # do the work
      save_atomic(wb, MASTER)          # write to a temp file, then rename over the master
      publish(MASTER, VIEW_DIR)        # drop a fresh snapshot for the human to open

  If the pipeline drives Excel over COM (xlwings or pywin32), use publish_via_excel instead. It
  asks Excel for the copy, so the snapshot keeps its cached values and needs no recalculation on
  open -- and it is a single call that never touches the master's own file handle.
"""
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime

STAMP = '%Y%m%d_%H%M%S'


def lock_path(path):
    """Excel's lock file: ~$ prefixed onto the workbook name, in the same directory."""
    d, n = os.path.split(os.path.abspath(path))
    return os.path.join(d, '~$' + n)


def is_open_in_excel(path):
    """True if the file looks locked. Two independent tests, because neither is sufficient alone.

    The ~$ lock file is what Excel leaves behind and is the reliable signal on a network share;
    opening for append is the definitive test on Windows, where Excel's share mode denies writers.
    On Linux there is no mandatory locking, so only the lock file test can fire -- which is why
    both are used and either is enough to refuse.
    """
    if os.path.exists(lock_path(path)):
        return True
    if os.path.exists(path):
        try:
            with open(path, 'r+b'):
                pass
        except PermissionError:
            return True
        except OSError:
            return True
    return False


def assert_writable(path):
    if is_open_in_excel(path):
        raise RuntimeError(
            f'{os.path.basename(path)} is open in Excel (lock file '
            f'{os.path.basename(lock_path(path))}). Close it, or open the snapshot in the view '
            f'folder instead -- the master is not meant to be opened by hand.')


def save_atomic(wb, path):
    """Save into the same directory, then rename over the target.

    A direct wb.save() onto a path Excel holds can leave a half-written workbook behind. Writing
    beside it and renaming means the master is either the old file or the new one, never a
    fragment; and the rename is what fails if the file is locked, before anything is destroyed.
    """
    d = os.path.dirname(os.path.abspath(path)) or '.'
    fd, tmp = tempfile.mkstemp(suffix='.xlsx', dir=d)
    os.close(fd)
    try:
        wb.save(tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return path


def publish(master, view_dir, keep=10, latest_name=None, quiet=False):
    """Copy the master into view_dir under a timestamped name; prune to the newest `keep`.

    Also refreshes a stable filename so a shortcut can point at one place. That copy is
    best-effort: if the human has it open, Excel holds it and the rename fails, which is reported
    and ignored. The timestamped snapshot always succeeds, so there is always a current file to
    open, and the master's own update is never at risk either way.
    """
    os.makedirs(view_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(master))[0]
    # the stamp is per-second, so two runs inside the same second would collide and the second
    # would silently overwrite the first; suffix until the name is free
    stem = os.path.join(view_dir, f'{base}_view_{datetime.now().strftime(STAMP)}')
    stamped, n = f'{stem}.xlsx', 1
    while os.path.exists(stamped):
        stamped, n = f'{stem}_{n}.xlsx', n + 1
    shutil.copy2(master, stamped)

    stable = os.path.join(view_dir, latest_name or f'{base}_view_latest.xlsx')
    stable_ok, tmp = True, None
    try:
        fd, tmp = tempfile.mkstemp(suffix='.xlsx', dir=view_dir)
        os.close(fd)
        shutil.copy2(master, tmp)
        os.replace(tmp, stable)
    except OSError:
        stable_ok = False
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

    # prune, newest first
    olds = sorted((f for f in os.listdir(view_dir)
                   if f.startswith(f'{base}_view_2') and f.endswith('.xlsx')), reverse=True)
    for f in olds[keep:]:
        try:
            os.remove(os.path.join(view_dir, f))
        except OSError:
            pass

    if not quiet:
        print(f'snapshot  {stamped}')
        print(f'stable    {stable}' if stable_ok else
              f'stable    SKIPPED -- {os.path.basename(stable)} is open; it still shows older '
              f'data. The snapshot above is current.')
    return stamped, stable_ok


def publish_via_excel(master, mirror):
    """Windows only. Ask Excel for the copy, so cached values survive and no recalc is needed.

    Use this when Excel is already the calculation engine -- an xlwings or pywin32 pipeline. Excel
    recalculates, saves the master, then SaveCopyAs writes a fully-valued duplicate without
    changing the master's own path or leaving it dirty. Untested outside Windows; it will raise on
    any platform without the COM stack.
    """
    import win32com.client                                   # noqa: F401  (Windows only)
    xl = win32com.client.DispatchEx('Excel.Application')
    xl.Visible = False
    xl.DisplayAlerts = False
    try:
        wb = xl.Workbooks.Open(os.path.abspath(master))
        xl.CalculateFullRebuild()
        wb.Save()
        wb.SaveCopyAs(os.path.abspath(mirror))
        wb.Close(SaveChanges=False)
    finally:
        xl.Quit()
    return mirror


if __name__ == '__main__':
    master = sys.argv[1] if len(sys.argv) > 1 else (
        '/home/user/David-Fewer/TradingExcel_5stock_live_freesleeves.xlsx')
    view = sys.argv[2] if len(sys.argv) > 2 else '/home/user/David-Fewer/view'
    print(f'master   {master}')
    print(f'locked   {is_open_in_excel(master)}')
    t0 = time.time()
    publish(master, view)
    print(f'took     {time.time()-t0:.2f}s  ({os.path.getsize(master)/1e6:.1f} MB)')
    print('DONE')
