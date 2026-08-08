from pathlib import Path
import re, shutil, subprocess, sys, tempfile

text=Path('app.py').read_text(encoding='utf-8')
blocks=[]
for attrs,body in re.findall(r'<script([^>]*)>(.*?)</script>',text,flags=re.I|re.S):
    if re.search(r'\bsrc\s*=',attrs,re.I):
        continue
    if body.strip():
        blocks.append(body)
if not blocks:
    raise SystemExit('No inline dashboard JavaScript found to validate.')
node=shutil.which('node') or shutil.which('node.exe')
if not node:
    raise SystemExit('Node.js is required for embedded JavaScript validation on the build runner.')
js='\n;\n'.join(blocks)
with tempfile.NamedTemporaryFile('w',suffix='.js',delete=False,encoding='utf-8') as f:
    f.write(js)
    name=f.name
proc=subprocess.run([node,'--check',name],text=True,capture_output=True)
Path(name).unlink(missing_ok=True)
if proc.returncode:
    sys.stderr.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    raise SystemExit('Embedded dashboard JavaScript syntax validation failed.')
print('Embedded dashboard JavaScript syntax is valid.')
