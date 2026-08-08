from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')

old = ".aircraft-photo{width:100%;height:250px;object-fit:cover;border-radius:10px;border:1px solid var(--border);background:#0b1020}"
new = ".aircraft-photo{display:block;width:auto;height:auto;max-width:100%;max-height:320px;object-fit:contain;margin:0 auto;border-radius:10px;border:1px solid var(--border);background:#0b1020;cursor:zoom-in}"

if old not in s:
    raise SystemExit('Expected aircraft photo CSS was not found; a prior patch may have changed the renderer.')

s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
compile(s, 'app.py', 'exec')
print('Applied aircraft photo display quality rules successfully.')
