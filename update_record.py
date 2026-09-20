#!/usr/bin/env python3
"""Refresh the public live record from the broker. Runs in CI, on a schedule.

Reads live_record.json, which is the committed record of every basket published and every fill.
Asks the broker what those positions are worth now. Writes live_record_public.json, which is what
the website reads.

It never invents a basket and never edits history. The only thing it changes is the mark.

Credentials come from the environment, never from a file in this repository:
    ALPACA_KEY, ALPACA_SECRET, and optionally ALPACA_BASE.
"""
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
BOOK = ROOT / 'live_record.json'
OUT = ROOT / 'live_record_public.json'
BASE = os.environ.get('ALPACA_BASE', 'https://paper-api.alpaca.markets/v2')
KEY = os.environ.get('ALPACA_KEY')
SECRET = os.environ.get('ALPACA_SECRET')
MODE = 'paper' if 'paper-api' in BASE else 'live'


def api(url):
    req = Request(url, headers={'APCA-API-KEY-ID': KEY, 'APCA-API-SECRET-KEY': SECRET})
    try:
        with urlopen(req, timeout=40) as r:
            return json.loads(r.read())
    except HTTPError as e:
        print('broker error %d: %s' % (e.code, e.read().decode()[:200]), file=sys.stderr)
        return None


def collect_fills(book):
    """Record fills for any basket whose orders have executed.

    Only ever writes fills that are missing. An entry that already has them is left alone, and a
    fill for a ticker that was not in the published basket is refused, exactly as the manual path
    does. This is bookkeeping after the fact, not a decision.
    """
    changed = False
    for e in book.get('entries', []):
        if e.get('fills') or not e.get('orders'):
            continue
        ids = {o['order_id'] for o in e['orders']}
        got = api(BASE + '/orders?status=closed&limit=500&direction=asc') or []
        done = [o for o in got if o['id'] in ids and o['status'] == 'filled']
        if not done:
            print('  %s: orders placed, nothing filled yet' % e['signal_date'])
            continue
        fills = []
        for o in done:
            if o['symbol'] not in e['tickers']:
                print('  refusing %s: not in the published basket' % o['symbol'], file=sys.stderr)
                return changed
            fills.append({'ticker': o['symbol'], 'shares': float(o['filled_qty']),
                          'price': float(o['filled_avg_price']), 'commission': 0.0,
                          'date': o['filled_at'][:10]})
        e['fills'] = fills
        e['not_filled'] = sorted(set(e['tickers']) - {f['ticker'] for f in fills})
        e['cash_invested'] = round(sum(f['shares'] * f['price'] for f in fills), 2)
        changed = True
        print('  %s: recorded %d fills, %.2f invested'
              % (e['signal_date'], len(fills), e['cash_invested']))
    return changed


def main():
    if not BOOK.exists():
        sys.exit('No live_record.json in this repository.')
    book = json.loads(BOOK.read_text(encoding='utf-8'))
    if KEY and SECRET and collect_fills(book):
        BOOK.write_text(json.dumps(book, indent=1), encoding='utf-8')
        print('live_record.json updated with new fills')
    entries = book.get('entries', [])
    traded = [e for e in entries if e.get('fills')]

    position = None
    as_of = None
    if traded and KEY and SECRET:
        current = traded[-1]
        held = api(BASE + '/positions') or []
        by_symbol = {p['symbol']: p for p in held}
        names, invested, value = [], 0.0, 0.0
        for f in current['fills']:
            p = by_symbol.get(f['ticker'])
            now = float(p['current_price']) if p else None
            invested += f['shares'] * f['price']
            if now:
                value += f['shares'] * now
            names.append({'ticker': f['ticker'], 'shares': f['shares'], 'entry': f['price'],
                          'now': now,
                          'change': round(now / f['price'] - 1, 6) if now else None})
        acct = api(BASE + '/account') or {}
        position = {'signal_date': current['signal_date'], 'invested': round(invested, 2),
                    'value': round(value, 2),
                    'change': round(value / invested - 1, 6) if invested else None,
                    'equity': float(acct['equity']) if acct.get('equity') else None,
                    'names': names}
        clock = api(BASE + '/clock') or {}
        as_of = (clock.get('timestamp') or '')[:19]

    modes = {e.get('mode') for e in entries if e.get('mode')}
    mode = 'paper' if modes == {'paper'} else ('live' if modes == {'live'}
                                               else ('mixed' if modes else 'none'))
    pub = {
        'model': book.get('model', 'Nova Sharpe'),
        'started': book.get('started'),
        'mode': mode,
        'broker': next((e.get('broker') for e in reversed(entries) if e.get('broker')), None),
        'as_of': as_of,
        'refreshed_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'entries': [{'signal_date': e['signal_date'], 'published_at': e['published_at'],
                     'mode': e.get('mode'), 'tickers': e['tickers'], 'sha256': e['sha256'],
                     'note': e.get('note', ''), 'weight_each': e['weight_each'],
                     'traded': bool(e.get('fills')), 'not_filled': e.get('not_filled', []),
                     'fills': [{'ticker': f['ticker'], 'price': f['price'], 'date': f['date']}
                               for f in e.get('fills', [])]}
                    for e in entries],
        'position': position,
        'disclosure': ('Every basket above was published and hash stamped before it was traded, at '
                       'the open of the session that followed. This record is short and proves very '
                       'little on its own yet.'),
    }
    OUT.write_text(json.dumps(pub, separators=(',', ':')), encoding='utf-8')
    leak = [s for s in (KEY or 'x', SECRET or 'y') if s and s in OUT.read_text(encoding='utf-8')]
    if leak:
        sys.exit('Refusing to publish: a credential ended up in the output.')
    print('wrote %s, mode %s, %d entries, position %s'
          % (OUT.name, mode, len(entries), 'marked' if position else 'none'))


if __name__ == '__main__':
    main()
