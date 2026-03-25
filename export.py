import copy, os, re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from caldav import DAVClient
from icalendar import Calendar

D = Path('site')

def g(k, d=''):
    v = os.getenv(k, d).strip()
    if not v:
        raise RuntimeError('missing env: ' + k)
    return v

def b(k, d=False):
    v = os.getenv(k, '').strip().lower()
    return d if not v else v in {'1', 'true', 'yes', 'y', 'on'}

def pick(client, name):
    p = client.get_principal()
    cs = p.get_calendars()
    if not cs:
        raise RuntimeError('no calendars found')
    if name:
        w = name.casefold()
        for c in cs:
            names = []
            if getattr(c, 'name', None):
                names.append(str(c.name))
            f = getattr(c, 'get_display_name', None)
            if callable(f):
                try:
                    names.append(str(f()))
                except Exception:
                    pass
            if any(x.casefold() == w for x in names):
                return c
        raise RuntimeError('calendar not found')
    if len(cs) == 1:
        return cs[0]
    raise RuntimeError('set CALDAV_CALENDAR_NAME')

def main():
    token = g('ICS_TOKEN')
    if not re.fullmatch(r'[A-Za-z0-9._-]{24,200}', token):
        raise RuntimeError('bad ICS_TOKEN')

    name = os.getenv('CALDAV_CALENDAR_NAME', '').strip() or None
    back = int(os.getenv('LOOKBACK_DAYS', '30'))
    ahead = int(os.getenv('LOOKAHEAD_DAYS', '180'))
    title_mode = os.getenv('EVENT_TITLE_MODE', 'original').strip().lower()
    default_title = os.getenv('DEFAULT_EVENT_TITLE', 'Busy').strip() or 'Busy'
    keep_loc = b('INCLUDE_LOCATION', False)
    keep_desc = b('INCLUDE_DESCRIPTION', False)

    D.mkdir(parents=True, exist_ok=True)
    start = datetime.now(timezone.utc) - timedelta(days=back)
    end = datetime.now(timezone.utc) + timedelta(days=ahead)

    out = Calendar()
    out.add('prodid', '-//calendar-bridge//EN')
    out.add('version', '2.0')
    out.add('calscale', 'GREGORIAN')

    with DAVClient(
        url=g('CALDAV_URL'),
        username=g('CALDAV_USERNAME'),
        password=g('CALDAV_PASSWORD')
    ) as client:
        cal = pick(client, name)
        seen = set()

        for r in client.get_events(cal, start=start, end=end):
            raw = r.get_data()
            if not raw:
                continue

            parsed = Calendar.from_ical(raw)
            for c in parsed.subcomponents:
                n = getattr(c, 'name', '')

                if n == 'VTIMEZONE':
                    tzid = str(c.get('TZID', ''))
                    if tzid and tzid in seen:
                        continue
                    if tzid:
                        seen.add(tzid)
                    out.add_component(copy.deepcopy(c))
                    continue

                if n != 'VEVENT':
                    continue

                x = copy.deepcopy(c)

                for k in ('ATTENDEE', 'ORGANIZER', 'URL', 'CONFERENCE'):
                    if k in x:
                        del x[k]

                if not keep_loc and 'LOCATION' in x:
                    del x['LOCATION']
                if not keep_desc and 'DESCRIPTION' in x:
                    del x['DESCRIPTION']

                x.subcomponents = [
                    s for s in x.subcomponents
                    if getattr(s, 'name', None) != 'VALARM'
                ]

                if title_mode == 'busy':
                    x['SUMMARY'] = default_title
                elif title_mode == 'original' and 'SUMMARY' not in x:
                    x['SUMMARY'] = default_title

                out.add_component(x)

    (D / (token + '.ics')).write_bytes(out.to_ical())
    (D / 'index.html').write_text(
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="robots" content="noindex,nofollow,noarchive">'
        '<title>calendar-bridge</title></head><body>OK</body></html>',
        encoding='utf-8'
    )
    (D / 'robots.txt').write_text('User-agent: *\nDisallow: /\n', encoding='utf-8')
    (D / '.nojekyll').write_text('', encoding='utf-8')

if __name__ == '__main__':
    main()
