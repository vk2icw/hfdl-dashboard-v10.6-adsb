from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')

def rep(old,new):
    global s
    if old not in s:
        raise SystemExit('Expected app.py block not found:\n'+old[:300])
    s=s.replace(old,new,1)

# Airport-Data official thumbnail API state and conservative cache.
rep(
"PLANESPOTTERS_PHOTO_ENABLED=os.getenv('PLANESPOTTERS_PHOTO_ENABLED','yes').strip().lower() not in {'0','no','false','off'}\n",
"AIRPORT_DATA_PHOTO_ENABLED=os.getenv('AIRPORT_DATA_PHOTO_ENABLED','yes').strip().lower() not in {'0','no','false','off'}\nAIRPORT_DATA_PHOTO_CACHE_SECONDS=max(300,int(os.getenv('AIRPORT_DATA_PHOTO_CACHE_SECONDS','21600')))\nairport_data_photo_cache:dict[str,tuple[float,dict[str,Any]]]={}\nairport_data_photo_last_request=0.0\nairport_data_photo_lock=asyncio.Lock()\nPLANESPOTTERS_PHOTO_ENABLED=os.getenv('PLANESPOTTERS_PHOTO_ENABLED','yes').strip().lower() not in {'0','no','false','off'}\n"
)

# Server-side Airport-Data lookup. The public API returns thumbnail, photo page and photographer.
anchor="async def fetch_planespotters_photo(icao_code:str,refresh:bool=False)->dict[str,Any]:\n"
if anchor not in s:
    raise SystemExit('Planespotters fetch anchor not found')
airport_data_fetch=r'''async def fetch_airport_data_photo(icao_code:str,refresh:bool=False)->dict[str,Any]:
    global airport_data_photo_last_request
    code=icao(icao_code)
    if not code:
        return {'ok':False,'reason':'invalid_icao','error':'A valid six-character ICAO hex address is required.'}
    code=code.upper()
    now=time.time()
    cached=airport_data_photo_cache.get(code)
    if cached and not refresh and now-cached[0] < AIRPORT_DATA_PHOTO_CACHE_SECONDS:
        result=dict(cached[1]); result['cached']=True; return result
    if not AIRPORT_DATA_PHOTO_ENABLED:
        return {'ok':False,'reason':'disabled','error':'Airport-Data automatic photo lookup is disabled.'}

    async with airport_data_photo_lock:
        now=time.time()
        cached=airport_data_photo_cache.get(code)
        if cached and not refresh and now-cached[0] < AIRPORT_DATA_PHOTO_CACHE_SECONDS:
            result=dict(cached[1]); result['cached']=True; return result

        wait=max(0.0,1.05-(now-airport_data_photo_last_request))
        if wait:
            await asyncio.sleep(wait)

        endpoint=f'https://airport-data.com/api/ac_thumb.json?m={urllib.parse.quote(code)}&n=1'
        try:
            def do_request():
                req=urllib.request.Request(
                    endpoint,
                    headers={
                        'User-Agent':'HFDL-Operations-Dashboard/10.6 (local non-commercial aircraft photo lookup)',
                        'Accept':'application/json',
                        'Accept-Encoding':'identity'
                    }
                )
                with urllib.request.urlopen(req,timeout=12) as response:
                    return json.loads(response.read().decode('utf-8','replace'))
            payload=await asyncio.to_thread(do_request)
            airport_data_photo_last_request=time.time()
        except urllib.error.HTTPError as exc:
            airport_data_photo_last_request=time.time()
            if exc.code==404:
                return {'ok':False,'reason':'not_found','error':'No Airport-Data photograph is available for this ICAO address.'}
            if exc.code==429:
                return {'ok':False,'reason':'rate_limited','error':'Airport-Data photo lookup is temporarily rate limited.'}
            return {'ok':False,'reason':'http_error','error':f'Airport-Data returned HTTP {exc.code}.'}
        except (TimeoutError,urllib.error.URLError):
            airport_data_photo_last_request=time.time()
            return {'ok':False,'reason':'unavailable','error':'Airport-Data is currently unavailable.'}
        except Exception:
            airport_data_photo_last_request=time.time()
            return {'ok':False,'reason':'unavailable','error':'Airport-Data photo lookup could not be reached.'}

        items=payload.get('data') if isinstance(payload,dict) else None
        if payload.get('status') != 200 or not isinstance(items,list) or not items:
            result={'ok':False,'reason':'not_found','error':'No Airport-Data photograph is available for this ICAO address.'}
            airport_data_photo_cache[code]=(time.time(),result)
            return result
        item=next((x for x in items if isinstance(x,dict)),None)
        if not item:
            return {'ok':False,'reason':'not_found','error':'No usable Airport-Data photograph was returned.'}

        thumbnail_url=safe_external_https_url(item.get('image'),{'airport-data.com'})
        link=safe_external_https_url(item.get('link'),{'airport-data.com'})
        if not thumbnail_url or not link:
            return {'ok':False,'reason':'invalid_response','error':'Airport-Data returned an incomplete photo record.'}

        result={
            'ok':True,
            'cached':False,
            'icao':code,
            'provider':'Airport-Data.com',
            'photo':{
                'thumbnail_url':thumbnail_url,
                'link':link,
                'photographer':str(item.get('photographer') or '').strip() or None
            },
            'notice':'Thumbnail and attribution are supplied by Airport-Data.com. Click through to the original photograph.'
        }
        airport_data_photo_cache[code]=(time.time(),result)
        return result

'''
s=s.replace(anchor,airport_data_fetch+anchor,1)

# Expose a local proxy endpoint for the browser to request Airport-Data metadata.
route_anchor="@app.get('/api/external/planespotters-photo/{icao_code}')\n"
if route_anchor not in s:
    raise SystemExit('Planespotters route anchor not found')
airport_data_route=r'''@app.get('/api/external/airport-data-photo/{icao_code}')
async def airport_data_photo(icao_code:str,refresh:bool=False):
    result=await fetch_airport_data_photo(icao_code,refresh=refresh)
    if result.get('ok'):
        status=200
    else:
        status={
            'invalid_icao':400,
            'not_found':404,
            'rate_limited':429,
            'disabled':503,
            'unavailable':503,
            'http_error':502,
            'invalid_response':502
        }.get(result.get('reason'),502)
    return JSONResponse(result,status_code=status)

'''
s=s.replace(route_anchor,airport_data_route+route_anchor,1)

# Make the aircraft-photo panel provider-neutral and refresh the preferred chain.
rep(
'<div class="panelhead"><div><h2>Aircraft photograph</h2><small>Local image, direct URL, or authorised Planespotters thumbnail</small></div><button class="action" onclick="loadPlanespottersPhoto(true)">Refresh photo</button></div>',
'<div class="panelhead"><div><h2>Aircraft photograph</h2><small>Local image, Airport-Data, or Planespotters fallback</small></div><button class="action" onclick="loadAircraftPhoto(true)">Refresh photo</button></div>'
)
rep(
'<div id="planespotters-photo-status" class="muted" style="margin-top:8px;font-size:12px">Automatic photo lookup has not run.</div>',
'<div id="planespotters-photo-status" class="muted" style="margin-top:8px;font-size:12px">Automatic photo lookup has not run.</div>'
)

# Airport-Data first, then existing Planespotters routine. Local/manual remains highest priority.
js_anchor="async function loadPlanespottersPhoto(force=false){\n"
if js_anchor not in s:
    raise SystemExit('Planespotters JavaScript anchor not found')
load_airport_data_js=r'''async function loadAircraftPhoto(force=false){
 if(!selectedAircraft)return;
 let a=selectedAircraftData?.aircraft||{};
 let status=document.getElementById('planespotters-photo-status');
 if(a.photo_src){
  status.textContent='Using your configured/local photograph. Automatic internet lookup was not substituted.';
  return;
 }
 status.textContent='Looking for an Airport-Data aircraft thumbnail…';
 try{
  let url=`/api/external/airport-data-photo/${encodeURIComponent(selectedAircraft)}${force?'?refresh=true':''}`;
  let response=await fetch(url);
  let data=await response.json();
  if(response.ok&&data.ok&&data.photo?.thumbnail_url){
   let photo=data.photo,holder=document.getElementById('detail-photo'),credit=document.getElementById('detail-photo-credit');
   holder.className='';
   holder.innerHTML=`<a href="${photo.link}" target="_blank" rel="noopener noreferrer"><img class="aircraft-photo" src="${photo.thumbnail_url}" alt="Aircraft ${a.registration||a.icao||selectedAircraft}" referrerpolicy="no-referrer-when-downgrade" onerror="this.parentElement.parentElement.className='photo-placeholder';this.parentElement.parentElement.textContent='Airport-Data thumbnail could not be loaded.'"></a>`;
   let photographer=photo.photographer||'Unknown photographer';
   credit.innerHTML=`© ${photographer} · Photo supplied by <a href="${photo.link}" target="_blank" rel="noopener noreferrer">Airport-Data.com</a> · <a href="${photo.link}" target="_blank" rel="noopener noreferrer">Open original photograph</a>`;
   status.textContent=`${data.cached?'Cached':'Fresh'} Airport-Data result. Click the thumbnail to open the original photo page.`;
   return;
  }
 }catch(error){
  // Fall through to Planespotters.
 }
 status.textContent='No Airport-Data image found; trying Planespotters…';
 await loadPlanespottersPhoto(force);
}

'''
s=s.replace(js_anchor,load_airport_data_js+js_anchor,1)

# Automatic aircraft-detail lookup now follows local/manual -> Airport-Data -> Planespotters.
rep(
"  renderAircraftDetail();\n  await loadPlanespottersPhoto(false)",
"  renderAircraftDetail();\n  await loadAircraftPhoto(false)"
)

# Update explanatory copy where the VRS-style patch describes the fallback order.
old="<p>Recommended: keep your own aircraft photographs locally. Name files by ICAO hex (preferred) or registration, for example 7C6B0F.jpg or VH-VFP.jpg. Planespotters lookup remains an optional fallback when no configured photo is available.</p>"
new="<p>Recommended: keep your own aircraft photographs locally. Name files by ICAO hex (preferred) or registration, for example 7C6B0F.jpg or VH-VFP.jpg. When no configured photo is available, the dashboard checks Airport-Data by ICAO hex first and uses Planespotters as a fallback.</p>"
if old in s:
    s=s.replace(old,new,1)

p.write_text(s,encoding='utf-8')
compile(s,'app.py','exec')
print('Applied Airport-Data aircraft photo lookup with Planespotters fallback.')
