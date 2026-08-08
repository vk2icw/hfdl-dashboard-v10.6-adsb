from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')

def rep(old,new):
    global s
    if old not in s:
        raise SystemExit('Expected app.py block not found:\n'+old[:300])
    s=s.replace(old,new,1)

# Prevent the shorter identity card stretching to the height of the photo/tools card.
rep(
    ".detailhero{display:grid;grid-template-columns:1.2fr .8fr;gap:14px;margin-bottom:14px}",
    ".detailhero{display:grid;grid-template-columns:1.2fr .8fr;gap:14px;margin-bottom:14px;align-items:start}"
)

# Make aircraft-detail photo inputs follow the dashboard dark theme instead of browser-white controls.
rep(
    ".photo-credit{font-size:12px;color:var(--muted);margin-top:7px}",
    ".photo-credit{font-size:12px;color:var(--muted);margin-top:7px}"
    "#aircraft-photo-url,#aircraft-photo-credit-input,#aircraft-photo-link-input{width:100%;background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:9px 10px;outline:none}"
    "#aircraft-photo-url:focus,#aircraft-photo-credit-input:focus,#aircraft-photo-link-input:focus{border-color:var(--accent)}"
    "#aircraft-photo-file{max-width:100%;color:var(--muted)}"
    "#aircraft-photo-file::file-selector-button{background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:7px 9px;margin-right:8px;cursor:pointer}"
)

# Provider-neutral status id: this status represents the full photo chain, not Planespotters alone.
s=s.replace('planespotters-photo-status','aircraft-photo-status')

# Label the mixed external-service controls and expose Airport-Data directly.
rep(
    '<div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">\n          <button class="action" onclick="openAdsbLolGlobe()">Open on ADSB.lol</button>',
    '<div style="margin-top:14px"><div class="muted" style="font-size:12px;margin-bottom:7px">External aircraft services</div><div style="display:flex;gap:8px;flex-wrap:wrap">\n          <button class="action" onclick="openAirportData()">Open on Airport-Data</button>\n          <button class="action" onclick="openAdsbLolGlobe()">Open on ADSB.lol</button>'
)
rep(
    '          <button class="action" onclick="searchAircraftGoogle()">Search Google</button>\n        </div>\n        <div class="external-live-card">',
    '          <button class="action" onclick="searchAircraftGoogle()">Search Google</button>\n        </div></div>\n        <div class="external-live-card">'
)

# Keep track of why Airport-Data fell through, so Planespotters does not erase the diagnostic.
rep(
    "async function loadAircraftPhoto(force=false){\n if(!selectedAircraft)return;",
    "async function loadAircraftPhoto(force=false){\n if(!selectedAircraft)return;\n window.airportDataPhotoStatus='';"
)
rep(
    " status.textContent='No Airport-Data image found; trying Planespotters…';\n await loadPlanespottersPhoto(force);",
    " window.airportDataPhotoStatus='Airport-Data: no usable photo for the Mode-S lookup';\n status.textContent=window.airportDataPhotoStatus+' · checking Planespotters…';\n await loadPlanespottersPhoto(force);"
)
rep(
    " }catch(error){\n  // Fall through to Planespotters.\n }",
    " }catch(error){\n  window.airportDataPhotoStatus='Airport-Data lookup error';\n }"
)
rep(
    " status.textContent='Looking for an authorised Planespotters thumbnail…';",
    " status.textContent=(window.airportDataPhotoStatus?window.airportDataPhotoStatus+' · ':'')+'Checking Planespotters…';"
)
rep(
    "   let message=data.error||'No Planespotters photograph is currently available.';\n   status.textContent=message;",
    "   let message=data.error||'No Planespotters photograph is currently available.';\n   status.textContent=window.airportDataPhotoStatus?(window.airportDataPhotoStatus+' · Planespotters: '+message):message;"
)

# Airport-Data registration fallback. The public API supports registration lookup, and this is useful
# when a Mode-S lookup is missing or stale even though the aircraft profile has photographs.
route_anchor="@app.get('/api/external/airport-data-photo/{icao_code}')\nasync def airport_data_photo(icao_code:str,refresh:bool=False):\n    result=await fetch_airport_data_photo(icao_code,refresh=refresh)\n"
if route_anchor not in s:
    raise SystemExit('Airport-Data route anchor not found')
replacement="""@app.get('/api/external/airport-data-photo/{icao_code}')
async def airport_data_photo(icao_code:str,refresh:bool=False):
    result=await fetch_airport_data_photo(icao_code,refresh=refresh)
    # If Mode-S did not return a photo, retry via the current registration from our metadata.
    # Airport-Data documents registration as a supported thumbnail lookup key.
    if not result.get('ok') and result.get('reason') in {'not_found','invalid_response'}:
        code=icao(icao_code)
        registration=None
        if code:
            with db() as c:
                row=c.execute('SELECT registration FROM aircraft_metadata WHERE icao=?',(code,)).fetchone()
            registration=(str(row['registration']).strip().upper() if row and row['registration'] else None)
        if registration:
            try:
                endpoint='https://airport-data.com/api/ac_thumb.json?r='+urllib.parse.quote(registration)+'&n=2'
                def do_registration_request():
                    req=urllib.request.Request(endpoint,headers={
                        'User-Agent':'HFDL-Operations-Dashboard/10.6 (local non-commercial aircraft photo lookup)',
                        'Accept':'application/json','Accept-Encoding':'identity'
                    })
                    with urllib.request.urlopen(req,timeout=12) as response:
                        return json.loads(response.read().decode('utf-8','replace'))
                payload=await asyncio.to_thread(do_registration_request)
                items=payload.get('data') if isinstance(payload,dict) else None
                if payload.get('status')==200 and isinstance(items,list) and items:
                    item=next((x for x in items if isinstance(x,dict)),None)
                    if item:
                        thumbnail_url=safe_external_https_url(item.get('image'),{'airport-data.com'})
                        link=safe_external_https_url(item.get('link'),{'airport-data.com'})
                        if thumbnail_url and link:
                            result={
                                'ok':True,'cached':False,'icao':code,'provider':'Airport-Data.com',
                                'lookup':'registration','registration':registration,
                                'photo':{'thumbnail_url':thumbnail_url,'link':link,'photographer':str(item.get('photographer') or '').strip() or None},
                                'notice':'Airport-Data photo found by registration fallback.'
                            }
            except Exception:
                pass
"""
s=s.replace(route_anchor,replacement,1)

# Add a direct Airport-Data profile action for verification/troubleshooting.
anchor="function openPlanespotters(){\n"
if anchor not in s:
    raise SystemExit('Open Planespotters JavaScript anchor not found')
fn="""function openAirportData(){
 if(!selectedAircraft){alert('Select an aircraft first.');return}
 let aircraft=latestAircraft.find(a=>a.icao===selectedAircraft);
 let registration=aircraft?.registration||selectedAircraftData?.aircraft?.registration||'';
 let target=registration?`https://airport-data.com/aircraft/${encodeURIComponent(registration)}.html`:`https://airport-data.com/aircraft/search/`;
 window.open(target,'_blank','noopener,noreferrer');
}
"""
s=s.replace(anchor,fn+anchor,1)

# Clarify the page title/version wording slightly while retaining the correlation feature name.
s=s.replace('v10.6 ADSB.lol Correlation','v10.6 · ADS-B + HFDL',2)

p.write_text(s,encoding='utf-8')
compile(s,'app.py','exec')
print('Applied aircraft detail layout, photo diagnostics and Airport-Data registration fallback.')
