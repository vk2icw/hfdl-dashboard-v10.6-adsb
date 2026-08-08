from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')

start = s.find("@app.get('/api/external/airport-data-photo/{icao_code}')")
end = s.find("@app.get('/api/external/planespotters-photo/{icao_code}')", start)
if start < 0 or end < 0:
    raise SystemExit('Airport-Data route block not found')

route = r'''@app.get('/api/external/airport-data-photo/{icao_code}')
async def airport_data_photo(icao_code:str,refresh:bool=False):
    code=icao(icao_code)
    if not code:
        return JSONResponse({'ok':False,'reason':'invalid_icao','error':'A valid six-character ICAO hex address is required.'},status_code=400)

    # Prefer registration because Airport-Data's photo catalogue is strongly registration-oriented.
    registration=None
    with db() as c:
        row=c.execute('SELECT registration FROM aircraft_metadata WHERE icao=?',(code,)).fetchone()
    if row and row['registration']:
        registration=str(row['registration']).strip().upper()

    async def by_registration(reg:str):
        try:
            endpoint='https://airport-data.com/api/ac_thumb.json?r='+urllib.parse.quote(reg)+'&n=2'
            def do_request():
                req=urllib.request.Request(endpoint,headers={
                    'User-Agent':'HFDL-Operations-Dashboard/10.6 (local non-commercial aircraft photo lookup)',
                    'Accept':'application/json','Accept-Encoding':'identity'
                })
                with urllib.request.urlopen(req,timeout=12) as response:
                    return json.loads(response.read().decode('utf-8','replace'))
            payload=await asyncio.to_thread(do_request)
            items=payload.get('data') if isinstance(payload,dict) else None
            if payload.get('status')!=200 or not isinstance(items,list) or not items:
                return {'ok':False,'reason':'not_found','error':'No Airport-Data photograph is available for this registration.'}
            for item in items:
                if not isinstance(item,dict):
                    continue
                thumbnail_url=safe_external_https_url(item.get('image'),{'airport-data.com'})
                link=safe_external_https_url(item.get('link'),{'airport-data.com'})
                if not thumbnail_url or not link:
                    continue
                # Some Airport-Data responses include registration / Mode-S metadata. Reject an explicit mismatch.
                returned_reg=str(item.get('registration') or item.get('reg') or '').strip().upper()
                if returned_reg and returned_reg!=reg:
                    continue
                returned_mode_s=str(item.get('mode_s') or item.get('modes') or item.get('icao') or '').strip().upper().replace('0X','')
                if returned_mode_s and re.fullmatch(r'[0-9A-F]{6}',returned_mode_s) and returned_mode_s!=code:
                    continue
                return {
                    'ok':True,'cached':False,'icao':code,'provider':'Airport-Data.com',
                    'lookup':'registration','registration':reg,
                    'photo':{
                        'thumbnail_url':thumbnail_url,
                        'link':link,
                        'photographer':str(item.get('photographer') or '').strip() or None
                    },
                    'notice':'Airport-Data photo matched by registration.'
                }
            return {'ok':False,'reason':'invalid_response','error':'Airport-Data returned no photo matching this registration.'}
        except urllib.error.HTTPError as exc:
            if exc.code==429:
                return {'ok':False,'reason':'rate_limited','error':'Airport-Data photo lookup is temporarily rate limited.'}
            if exc.code==404:
                return {'ok':False,'reason':'not_found','error':'No Airport-Data photograph is available for this registration.'}
            return {'ok':False,'reason':'http_error','error':f'Airport-Data returned HTTP {exc.code}.'}
        except (TimeoutError,urllib.error.URLError):
            return {'ok':False,'reason':'unavailable','error':'Airport-Data is currently unavailable.'}
        except Exception:
            return {'ok':False,'reason':'unavailable','error':'Airport-Data registration lookup could not be completed.'}

    result=None
    if registration:
        result=await by_registration(registration)
        if result.get('ok'):
            return JSONResponse(result,status_code=200)

    # Registration is unavailable or did not yield a valid matching image: fall back to Mode-S/ICAO.
    mode_result=await fetch_airport_data_photo(code,refresh=refresh)
    if mode_result.get('ok'):
        mode_result['lookup']='mode_s'
        mode_result['registration']=registration
        return JSONResponse(mode_result,status_code=200)

    # Preserve the most useful error. A registration miss followed by a Mode-S miss is still a clean not-found.
    result=mode_result if mode_result else result
    status={
        'invalid_icao':400,
        'not_found':404,
        'rate_limited':429,
        'disabled':503,
        'unavailable':503,
        'http_error':502,
        'invalid_response':502
    }.get((result or {}).get('reason'),502)
    return JSONResponse(result or {'ok':False,'reason':'not_found','error':'No Airport-Data photograph is available.'},status_code=status)

'''

s = s[:start] + route + s[end:]

s = s.replace(
    "window.airportDataPhotoStatus='Airport-Data: no usable photo for the Mode-S lookup';",
    "window.airportDataPhotoStatus='Airport-Data: no usable photo by registration or Mode-S';"
)

p.write_text(s,encoding='utf-8')
compile(s,'app.py','exec')
print('Applied Airport-Data registration-first lookup with Mode-S fallback.')
