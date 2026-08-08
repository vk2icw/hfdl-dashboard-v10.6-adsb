from pathlib import Path

p = Path('apply_aircraft_database_page.py')
s = p.read_text(encoding='utf-8')
old = "    sql='''SELECT m.icao,m.registration,m.aircraft_type,m.operator,m.country,m.photo_url,m.photo_credit,m.photo_link,m.photo_checked_at,m.metadata_source,m.updated_at,a.callsign,a.last_seen,a.last_epoch FROM aircraft_metadata m LEFT JOIN aircraft a ON a.icao=m.icao'''"
new = '    sql="SELECT m.icao,m.registration,m.aircraft_type,m.operator,m.country,m.photo_url,m.photo_credit,m.photo_link,m.photo_checked_at,m.metadata_source,m.updated_at,a.callsign,a.last_seen,a.last_epoch FROM aircraft_metadata m LEFT JOIN aircraft a ON a.icao=m.icao"'
if old not in s:
    raise SystemExit('Expected nested SQL string was not found in apply_aircraft_database_page.py')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
compile(s, 'apply_aircraft_database_page.py', 'exec')
print('Fixed aircraft database patch quoting successfully.')
