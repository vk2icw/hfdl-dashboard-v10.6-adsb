from pathlib import Path

p = Path('apply_aircraft_database_page.py')
s = p.read_text(encoding='utf-8')
start = "api=r'''\n"
end = "'''\n\nrep(\n\"@app.get('/api/enrichment/settings')"
if start not in s or end not in s:
    raise SystemExit('Expected aircraft database API block markers were not found')
s = s.replace(start, 'api=r"""\n', 1)
s = s.replace(end, '"""\n\nrep(\n\"@app.get(\'/api/enrichment/settings\')', 1)
p.write_text(s, encoding='utf-8')
compile(s, 'apply_aircraft_database_page.py', 'exec')
print('Fixed aircraft database patch quoting successfully.')
