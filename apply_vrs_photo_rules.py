from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')

def rep(old,new):
    global s
    if old not in s:
        raise SystemExit('Expected app.py block not found:\n'+old[:240])
    s=s.replace(old,new,1)

rep(
"def get_settings():\n    with db() as c:\n        return {r['key']:r['value'] for r in c.execute('SELECT key,value FROM app_settings')}\n",
"def local_photo_path(code:str,registration:str|None=None):\n    folder=Path(DB).parent/'aircraft_photos'\n    names=[]\n    clean_code=str(code or '').strip().upper()\n    if clean_code:\n        names.append(clean_code)\n    clean_reg=re.sub(r'[^A-Z0-9-]','',str(registration or '').strip().upper())\n    if clean_reg and clean_reg not in names:\n        names.append(clean_reg)\n    for name in names:\n        for suffix in ('.jpg','.jpeg','.png','.webp','.gif','.bmp'):\n            path=folder/(name+suffix)\n            if path.exists():\n                return path,name\n    return None,None\n\ndef get_settings():\n    with db() as c:\n        return {r['key']:r['value'] for r in c.execute('SELECT key,value FROM app_settings')}\n"
)

rep(
"    folder=Path(DB).parent/'aircraft_photos'\n    has_local=any((folder/(code+s)).exists() for s in ('.jpg','.jpeg','.png','.webp'))\n    remote=aircraft_data.get('photo_url')\n",
"    local_path,local_key=local_photo_path(code,aircraft_data.get('registration'))\n    has_local=local_path is not None\n    remote=aircraft_data.get('photo_url')\n"
)

rep(
"    aircraft_data['photo_src']=photo_src\n    aircraft_data['photo_source']=photo_source\n",
"    aircraft_data['photo_src']=photo_src\n    aircraft_data['photo_source']=photo_source\n    aircraft_data['local_photo_key']=local_key\n"
)

rep(
"@app.get('/api/photos/{icao_code}')\ndef local_photo(icao_code:str):\n    code=icao(icao_code)\n    folder=Path(DB).parent/'aircraft_photos'\n    for suffix in ('.jpg','.jpeg','.png','.webp'):\n        path=folder/(str(code)+suffix)\n        if path.exists():\n            return FileResponse(path,media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')\n    return Response(status_code=404)\n",
"@app.get('/api/photos/{icao_code}')\ndef local_photo(icao_code:str):\n    code=icao(icao_code)\n    if not code:\n        return Response(status_code=404)\n    with db() as c:\n        row=c.execute('SELECT registration FROM aircraft_metadata WHERE icao=?',(code,)).fetchone()\n    registration=row['registration'] if row else None\n    path,_=local_photo_path(code,registration)\n    if path:\n        return FileResponse(path,media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')\n    return Response(status_code=404)\n"
)

rep(
"<div class=\"setting\"><label for=\"photo-mode\">Aircraft photo source</label><p>Local photos are stored in the dashboard data folder. Internet photos use the photo_url field from metadata.</p>",
"<div class=\"setting\"><label for=\"photo-mode\">Aircraft photo source</label><p>Local-first, VRS-style lookup. The dashboard checks the aircraft_photos folder by ICAO hex first, then registration. Internet photo URLs and Planespotters remain fallbacks.</p>"
)

rep(
"<option value=\"local_first\">Local photo first, then internet URL</option>",
"<option value=\"local_first\">Local folder first (ICAO, then registration), then internet URL</option>"
)

rep(
"<p>Automatic server-side photo lookup is disabled because the provider rejected automated requests. Aircraft Detail now includes a browser link that opens the matching Planespotters page directly by ICAO hex, plus a Google search fallback.</p>",
"<p>Recommended: keep your own aircraft photographs locally. Name files by ICAO hex (preferred) or registration, for example 7C6B0F.jpg or VH-VFP.jpg. Planespotters lookup remains an optional fallback when no configured photo is available.</p>"
)

p.write_text(s,encoding='utf-8')
print('Applied VRS-style local aircraft photo rules to app.py')
