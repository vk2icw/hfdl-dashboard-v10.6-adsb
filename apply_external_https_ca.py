from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')

old = "from __future__ import annotations\nimport asyncio, json, os, re, sqlite3, time, base64, secrets, mimetypes\n"
new = "from __future__ import annotations\nimport asyncio, json, os, re, sqlite3, time, base64, secrets, mimetypes, ssl\nimport certifi\n"
if old not in s:
    raise SystemExit('app.py import anchor not found')
s = s.replace(old, new, 1)

anchor = "import csv, io, urllib.request, urllib.parse\n"
if anchor not in s:
    raise SystemExit('urllib import anchor not found')
setup = anchor + "EXTERNAL_HTTPS_CONTEXT=ssl.create_default_context(cafile=certifi.where())\nurllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=EXTERNAL_HTTPS_CONTEXT)))\n"
s = s.replace(anchor, setup, 1)

# Preserve useful network diagnostics instead of hiding all SSL/URL failures behind a generic message.
s = s.replace(
    "except (TimeoutError,urllib.error.URLError):\n            airport_data_photo_last_request=time.time()\n            return {'ok':False,'reason':'unavailable','error':'Airport-Data is currently unavailable.'}",
    "except (TimeoutError,urllib.error.URLError) as exc:\n            airport_data_photo_last_request=time.time()\n            detail=str(getattr(exc,'reason',exc))[:240]\n            return {'ok':False,'reason':'unavailable','error':f'Airport-Data HTTPS failed: {detail}'}"
)
s = s.replace(
    "except Exception:\n            airport_data_photo_last_request=time.time()\n            return {'ok':False,'reason':'unavailable','error':'Airport-Data photo lookup could not be reached.'}",
    "except Exception as exc:\n            airport_data_photo_last_request=time.time()\n            return {'ok':False,'reason':'unavailable','error':f'Airport-Data lookup failed: {str(exc)[:240]}'}"
)

p.write_text(s, encoding='utf-8')
compile(s, 'app.py', 'exec')
print('Applied certifi-backed HTTPS context and external-service diagnostics.')
