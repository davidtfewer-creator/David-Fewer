"""
earnings_calendar_sync.py — Friday earnings-calendar sync (IBKR -> Google Calendar).

Pulls upcoming earnings dates for the book (and watch names) from IBKR TWS —
the same interface Scripts 1 and 2 already use — and upserts them into Google
Calendar as all-day events, each carrying the book's standing action for that
name. When an MU report falls inside the horizon it ALSO places the adopted
pause window (report week +/- one week, the P3 rule operated manually) as a
banner event, so the one calendar rule the book has is on the calendar.

--------------------------------------------------------------------- setup
One-time, on the trading machine:

  1. Python packages:
       pip install ib_insync google-api-python-client google-auth-httplib2 google-auth-oauthlib

  2. Google OAuth client (five minutes, once):
       - console.cloud.google.com -> New project (e.g. "BC Calendar")
       - APIs & Services -> Library -> enable "Google Calendar API"
       - APIs & Services -> OAuth consent screen -> External -> add your own
         gmail as a test user
       - Credentials -> Create credentials -> OAuth client ID -> Desktop app
         -> download JSON -> save it next to this script as credentials.json
       The FIRST run opens a browser for consent and caches token.json beside
       the script; every later run is silent.

  3. TWS (or IB Gateway) running and logged in, API enabled
     (Configure -> API -> Settings -> Enable ActiveX and Socket Clients),
     same as for Script 1. Set HOST/PORT/CLIENT_ID below to match.

  4. Schedule it for Fridays (Windows Task Scheduler):
       Program:  pythonw
       Args:     C:\\path\\to\\earnings_calendar_sync.py
       Trigger:  Weekly, Friday, 08:05
     (or cron: 5 8 * * 5)

Flags: --dry-run (print, write nothing), --days N (horizon, default 16),
       --calendar ID (default 'primary'), --dump (save each ticker's raw
       calendar XML beside the script — use this on first run if a date looks
       wrong and send me the XML).

Notes: the TWS fundamentals calendar is Refinitiv-fed; the XML layout has
varied across TWS versions, so the parser hunts for earnings-flavoured dates
generically and takes the nearest FUTURE one per name. Any name TWS returns
nothing for is reported in the run summary rather than silently skipped —
those weeks, check the IR page. Events are keyed with a private extended
property, so re-runs update in place and never duplicate.
"""
import argparse
import datetime as dt
import os
import re
import sys
import xml.etree.ElementTree as ET

HOST, PORT, CLIENT_ID = '127.0.0.1', 7496, 27   # 7497 for paper TWS
HERE = os.path.dirname(os.path.abspath(__file__))

# name -> (in scope, report timing, standing book action for the event body)
BOOK = {
    'TSM':  ('book', 'pre-market',
             'No pause — trade through (earnings map, Aug 2026). Pre-market reporter: '
             'the 9:00 rule sees the print before orders go in.'),
    'VRT':  ('book', 'pre-market',
             'No pause — trade through. Report-adjacent entries measured BETTER than '
             'ordinary entries (+2.4-2.5% vs +1.4%, zero stops).'),
    'VST':  ('book', 'pre-market',
             'No pause — trade through. (A tempting P2 pause cell was a textbook '
             'inverted-halves mirage — do not act on it.)'),
    'RKLB': ('watch', 'after close',
             'REMOVED from the book 2 Sep 2026 (SpaceX linkage, binary launch risk); '
             'tracked only while the discretionary position remains open.'),
    'MU':   ('book', 'after close',
             'PAUSE ACTIVE (adopted P3 rule): no NEW MU bids from the Monday of the '
             'week before the report to the Sunday of the week after. Exits, targets '
             'and stops run unchanged; MU capital pools to the other names. A separate '
             'banner event marks the window.'),
    'GM':   ('book', 'pre-market', 'No pause — trade through (earnings map, Aug 2026).'),
    'VLO':  ('book', 'pre-market', 'No pause — trade through (earnings map, Aug 2026).'),
    'CF':   ('book', 'after close', 'No pause — trade through (earnings map, Aug 2026).'),
    'MRVL': ('book', 'after close',
             'No pause — trade through. Post-report weeks are MRVL\'s BEST trades '
             '(+3.7% avg, zero stops); the 9:00 rule handles adverse gaps.'),
    'NVDA': ('watch', 'after close',
             'Not in the book. Bellwether print for the AI complex — NO defensive '
             'action: AI-six entries after NVDA reports measured better than average '
             '(+2.10% vs +1.67%).'),
    'AVGO': ('book', 'after close',
             'IN THE BOOK from 2 Sep 2026 (replaced RKLB). Earnings map measured '
             'week-of model entries adverse (the MU profile) — consider keeping '
             'AVGO bids off report week until a tested pause rule exists.'),
}

DATE_PAT = re.compile(r'(20\d{2})[-/]?(\d{2})[-/]?(\d{2})')
EARNINGS_HINT = re.compile(r'earn|eps|result|announce', re.IGNORECASE)


def parse_calendar_xml(xml_text, today, horizon):
    """Nearest future earnings-flavoured date in the XML, tolerant of layout.

    Strategy: walk every element; an element (or its ancestors' tags/attrs)
    that smells of earnings contributes any parseable dates it carries.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    hits = []

    def walk(el, earningsy):
        tagblob = el.tag + ' ' + ' '.join(f'{k}={v}' for k, v in el.attrib.items())
        e = earningsy or bool(EARNINGS_HINT.search(tagblob))
        blobs = [v for v in el.attrib.values()]
        if el.text:
            blobs.append(el.text)
        if e:
            for blob in blobs:
                for m in DATE_PAT.finditer(str(blob)):
                    try:
                        d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    except ValueError:
                        continue
                    if today <= d <= today + dt.timedelta(days=horizon):
                        hits.append(d)
        for c in el:
            walk(c, e)

    walk(root, False)
    return min(hits) if hits else None


def fetch_ibkr(tickers, days, dump=False):
    from ib_insync import IB, Stock
    ib = IB()
    ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=20)
    today = dt.date.today()
    out, missing = {}, []
    for t in tickers:
        try:
            c = Stock(t, 'SMART', 'USD')
            ib.qualifyContracts(c)
            xml_text = ib.reqFundamentalData(c, 'CalendarReport')
            if dump and xml_text:
                with open(os.path.join(HERE, f'calendar_{t}.xml'), 'w') as f:
                    f.write(xml_text)
            d = parse_calendar_xml(xml_text, today, days) if xml_text else None
            if d is None and xml_text:
                # fall back: snapshot report sometimes carries the next date
                snap = ib.reqFundamentalData(c, 'ReportSnapshot')
                d = parse_calendar_xml(snap, today, days) if snap else None
            if d is not None:
                out[t] = d
            else:
                missing.append(t)
        except Exception as e:                                    # noqa: BLE001
            print(f'  {t}: IBKR error: {e}', file=sys.stderr)
            missing.append(t)
    ib.disconnect()
    return out, missing


def gcal_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    scopes = ['https://www.googleapis.com/auth/calendar.events']
    tok = os.path.join(HERE, 'token.json')
    creds = Credentials.from_authorized_user_file(tok, scopes) if os.path.exists(tok) else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                os.path.join(HERE, 'credentials.json'), scopes)
            creds = flow.run_local_server(port=0)
        with open(tok, 'w') as f:
            f.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds, cache_discovery=False)


def upsert(svc, cal_id, key, summary, start, end, description, dry):
    """All-day event keyed by a private extended property: update, never duplicate."""
    body = dict(summary=summary, description=description,
                start=dict(date=start.isoformat()),
                end=dict(date=end.isoformat()),
                transparency='transparent',
                extendedProperties=dict(private=dict(bc_key=key)))
    if dry:
        print(f'  [dry-run] {start} {summary}')
        return
    got = svc.events().list(calendarId=cal_id, privateExtendedProperty=f'bc_key={key}',
                            maxResults=2).execute().get('items', [])
    if got:
        ev = got[0]
        if (ev['start'].get('date'), ev['end'].get('date'),
                ev.get('description')) != (body['start']['date'],
                                           body['end']['date'], description):
            svc.events().update(calendarId=cal_id, eventId=ev['id'],
                                body={**ev, **body}).execute()
            print(f'  updated  {start} {summary}')
        else:
            print(f'  ok       {start} {summary}')
    else:
        svc.events().insert(calendarId=cal_id, body=body).execute()
        print(f'  created  {start} {summary}')


def mu_pause_window(report):
    """Adopted P3 rule: Monday of the week BEFORE the report's ISO week to the
    Sunday of the week AFTER."""
    monday = report - dt.timedelta(days=report.weekday())
    return monday - dt.timedelta(days=7), monday + dt.timedelta(days=13)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=16)
    ap.add_argument('--calendar', default='primary')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--dump', action='store_true')
    args = ap.parse_args()

    print(f'fetching earnings dates from IBKR (next {args.days} days)...')
    dates, missing = fetch_ibkr(list(BOOK), args.days, dump=args.dump)
    if not dates:
        print('no upcoming reports found in the horizon.', file=sys.stderr)
    svc = None if args.dry_run else gcal_service()

    for t, d in sorted(dates.items(), key=lambda kv: kv[1]):
        scope, timing, action = BOOK[t]
        summary = f'{t} earnings — {timing}' + ('' if scope == 'book' else ' (watch)')
        desc = (f'{action}\n\nSource: IBKR CalendarReport, synced '
                f'{dt.date.today().isoformat()}. Confirm against IR if acting on it.')
        upsert(svc, args.calendar, f'earn_{t}_{d.isoformat()}', summary,
               d, d + dt.timedelta(days=1), desc, args.dry_run)
        if t == 'MU':
            lo, hi = mu_pause_window(d)
            upsert(svc, args.calendar, f'mu_pause_{d.isoformat()}',
                   'MU PAUSE — no new MU bids (P3 rule)', lo, hi + dt.timedelta(days=1),
                   'Adopted rule: no new MU entries from the week before the report '
                   'to the week after. Exits/targets/stops unchanged; MU capital '
                   'pools to the other names. Turn MU bids back on after this window.',
                   args.dry_run)

    if missing:
        print(f'\nNO DATE from IBKR for: {", ".join(missing)} — check those IR pages '
              f'manually this week (or run with --dump and inspect the XML).')


if __name__ == '__main__':
    main()
