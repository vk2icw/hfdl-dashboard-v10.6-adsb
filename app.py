from __future__ import annotations
import asyncio, json, os, re, sqlite3, time, base64, secrets, mimetypes
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import csv, io, urllib.request, urllib.parse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Body, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response, FileResponse
import uvicorn

DB=os.getenv('DATABASE_PATH','/data/hfdl.sqlite3'); UDP=int(os.getenv('UDP_PORT','5557')); WEB=int(os.getenv('WEB_PORT','8090')); UDP_BIND=os.getenv('UDP_BIND_IP','0.0.0.0').strip() or '0.0.0.0'; WEB_BIND=os.getenv('WEB_BIND_IP','0.0.0.0').strip() or '0.0.0.0'; AUTH_USER=os.getenv('DASHBOARD_USERNAME','').strip(); AUTH_PASS=os.getenv('DASHBOARD_PASSWORD','').strip()
clients:set[WebSocket]=set(); counters={'total':0,'invalid':0,'last':None}
AIRPLANES_LIVE_ENABLED=os.getenv('AIRPLANES_LIVE_ENABLED','yes').strip().lower() not in {'0','no','false','off'}
AIRPLANES_LIVE_CACHE_SECONDS=max(15,int(os.getenv('AIRPLANES_LIVE_CACHE_SECONDS','60')))
airplanes_live_cache:dict[str,tuple[float,dict[str,Any]]]={}
airplanes_live_last_request=0.0
airplanes_live_lock=asyncio.Lock()
PLANESPOTTERS_PHOTO_ENABLED=os.getenv('PLANESPOTTERS_PHOTO_ENABLED','yes').strip().lower() not in {'0','no','false','off'}
PLANESPOTTERS_PHOTO_CACHE_SECONDS=max(300,int(os.getenv('PLANESPOTTERS_PHOTO_CACHE_SECONDS','21600')))
planespotters_photo_cache:dict[str,tuple[float,dict[str,Any]]]={}
planespotters_photo_last_request=0.0
planespotters_photo_lock=asyncio.Lock()
ADSB_LOL_ENABLED=os.getenv('ADSB_LOL_ENABLED','yes').strip().lower() not in {'0','no','false','off'}
ADSB_LOL_CACHE_SECONDS=max(15,int(os.getenv('ADSB_LOL_CACHE_SECONDS','60')))
adsb_lol_cache:dict[str,tuple[float,dict[str,Any]]]={}
adsb_lol_last_request=0.0
adsb_lol_lock=asyncio.Lock()

def db():
    Path(DB).parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB,check_same_thread=False); c.row_factory=sqlite3.Row; return c

def init_db():
    with db() as c:
        c.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, ts TEXT, epoch REAL, freq REAL, signal REAL, noise REAL, snr REAL, bitrate INTEGER, direction TEXT, msgtype TEXT, icao TEXT, callsign TEXT, lat REAL, lon REAL, alt REAL, gs TEXT, raw TEXT);
        CREATE INDEX IF NOT EXISTS idx_msg_epoch ON messages(epoch DESC);
        CREATE TABLE IF NOT EXISTS aircraft(icao TEXT PRIMARY KEY,callsign TEXT,lat REAL,lon REAL,alt REAL,freq REAL,msgtype TEXT,last_seen TEXT,last_epoch REAL);
        CREATE TABLE IF NOT EXISTS aircraft_metadata(icao TEXT PRIMARY KEY,registration TEXT,aircraft_type TEXT,operator TEXT,country TEXT,photo_url TEXT,photo_credit TEXT,metadata_source TEXT,updated_at TEXT);
        CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT,match_type TEXT NOT NULL,pattern TEXT NOT NULL,event_type TEXT NOT NULL DEFAULT 'any',enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS alert_hits(id INTEGER PRIMARY KEY AUTOINCREMENT,alert_id INTEGER,message_id INTEGER,ts TEXT,icao TEXT,callsign TEXT,msgtype TEXT,details TEXT);''')
        meta_existing={r[1] for r in c.execute('PRAGMA table_info(aircraft_metadata)')}
        for name,kind in [('photo_url','TEXT'),('photo_credit','TEXT'),('photo_link','TEXT'),('photo_checked_at','TEXT'),('metadata_source','TEXT')]:
            if name not in meta_existing:
                c.execute(f'ALTER TABLE aircraft_metadata ADD COLUMN {name} {kind}')
        defaults={
            'metadata_mode':'local',
            'metadata_url':'',
            'photo_mode':'local_first',
            'overwrite_manual':'no',
            'photo_lookup':'manual'
        }
        for key,value in defaults.items():
            c.execute('INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)',(key,value))
        existing={r[1] for r in c.execute('PRAGMA table_info(messages)')}
        for name,kind in [('frame_type','TEXT'),('src_gs','TEXT'),('dst_gs','TEXT'),('assigned_ac_id','TEXT'),('freq_skew','REAL'),('slot','TEXT')]:
            if name not in existing:
                c.execute(f'ALTER TABLE messages ADD COLUMN {name} {kind}')
        c.commit()

def norm(k): return re.sub(r'[^a-z0-9]','',str(k).lower())
def findv(obj,names):
    wanted={norm(x) for x in names}
    if isinstance(obj,dict):
        for k,v in obj.items():
            if norm(k) in wanted and v not in (None,'',[],{}): return v
        for v in obj.values():
            r=findv(v,names)
            if r not in (None,'',[],{}): return r
    elif isinstance(obj,list):
        for v in obj:
            r=findv(v,names)
            if r not in (None,'',[],{}): return r
    return None

def pathv(obj,*paths):
    for path in paths:
        cur=obj; ok=True
        for part in path.split('.'):
            if not isinstance(cur,dict): ok=False; break
            match=next((k for k in cur if norm(k)==norm(part)),None)
            if match is None: ok=False; break
            cur=cur[match]
        if ok and cur not in (None,'',[],{}): return cur
    return None

def find_with_path(obj,names,path=()):
    wanted={norm(x) for x in names}; out=[]
    if isinstance(obj,dict):
        for k,v in obj.items():
            np=path+(str(k),)
            if norm(k) in wanted and v not in (None,'',[],{}): out.append((np,v))
            out.extend(find_with_path(v,names,np))
    elif isinstance(obj,list):
        for i,v in enumerate(obj): out.extend(find_with_path(v,names,path+(str(i),)))
    return out

def choose_protocol_value(d,names):
    candidates=find_with_path(d,names)
    def score(item):
        path='.'.join(item[0]).lower(); points=0
        if 'lpdu' in path or 'spdu' in path: points+=100
        if 'acars' in path or 'arinc' in path: points+=70
        if 'hfdl' in path: points+=40
        if path.startswith('app.') or '.app.' in path: points-=200
        return points
    return max(candidates,key=score)[1] if candidates else None

def scalar(v):
    if isinstance(v,dict):
        for key in ('name','value','id','code','description'):
            x=pathv(v,key)
            if x not in (None,'',[],{}): return x
        return None
    return v

def num(v):
    if v is None or isinstance(v,bool): return None
    if isinstance(v,(int,float)): return float(v)
    m=re.search(r'-?\d+(?:\.\d+)?',str(v)); return float(m.group()) if m else None

def icao(v):
    if v is None:return None
    if isinstance(v,int):return f'{v:06X}'
    m=re.search(r'\b[0-9A-F]{6}\b',str(v).upper().replace('0X','')); return m.group() if m else None

def parse(d):
    now=datetime.now(timezone.utc)
    f=num(pathv(d,'freq','frequency','frequency_khz','freq_khz') or findv(d,{'frequency','freq','frequency_khz','freq_khz'}))
    if f and f>1_000_000:f/=1000
    sig=num(pathv(d,'sig_level','signal_level','signal_dbfs') or findv(d,{'sig_level','signal_dbfs','signal_level','signal'}))
    noise=num(pathv(d,'noise_level','noise_dbfs') or findv(d,{'noise_level','noise_dbfs','noise'}))
    snr=num(pathv(d,'snr','snr_db') or findv(d,{'snr','snr_db','signal_to_noise'}))
    if snr is None and sig is not None and noise is not None:snr=sig-noise
    skew=num(pathv(d,'freq_skew','frequency_skew','freq_error') or findv(d,{'freq_skew','frequency_skew','freq_error'}))
    slot=scalar(pathv(d,'slot','hfdl.slot'))
    lat=num(choose_protocol_value(d,{'latitude','lat'})); lon=num(choose_protocol_value(d,{'longitude','lon','lng'})); alt=num(choose_protocol_value(d,{'altitude_ft','altitude','alt','flight_level'}))
    if lat is not None and not -90<=lat<=90:lat=None
    if lon is not None and not -180<=lon<=180:lon=None
    lpdu=pathv(d,'hfdl.lpdu','lpdu'); spdu=pathv(d,'hfdl.spdu','spdu')
    frame='LPDU' if lpdu is not None else ('SPDU' if spdu is not None else None)
    typ=scalar(pathv(d,'hfdl.lpdu.type','lpdu.type','hfdl.spdu.type','spdu.type'))
    if typ is None: typ=scalar(choose_protocol_value(d,{'message_type','msg_type','lpdu_type','spdu_type','label','event'}))
    if typ is None: typ='HFDL message'
    src_type=scalar(pathv(d,'hfdl.lpdu.src.type','lpdu.src.type','hfdl.spdu.src.type','spdu.src.type'))
    dst_type=scalar(pathv(d,'hfdl.lpdu.dst.type','lpdu.dst.type','hfdl.spdu.dst.type','spdu.dst.type'))
    src_id=scalar(pathv(d,'hfdl.lpdu.src.id','lpdu.src.id','hfdl.spdu.src.id','spdu.src.id'))
    dst_id=scalar(pathv(d,'hfdl.lpdu.dst.id','lpdu.dst.id','hfdl.spdu.dst.id','spdu.dst.id'))
    direction=scalar(pathv(d,'direction','dir'))
    st=(str(src_type).lower() if src_type is not None else '')
    dt=(str(dst_type).lower() if dst_type is not None else '')
    if not direction:
        if 'ground' in st or st in ('gs','ground_station'): direction='Uplink'
        elif 'aircraft' in st or st in ('ac','aircraft_station'): direction='Downlink'
        elif 'ground' in dt: direction='Downlink'
        elif 'aircraft' in dt: direction='Uplink'
    src_gs=str(src_id) if src_id is not None and ('ground' in st or st=='gs') else None
    dst_gs=str(dst_id) if dst_id is not None and ('ground' in dt or dt=='gs') else None
    gs=src_gs or dst_gs
    ac_icao=icao(scalar(choose_protocol_value(d,{'icao','icao_address','aircraft_address','hex'})))
    cs=scalar(choose_protocol_value(d,{'callsign','flight','flight_id','registration','tail'})); cs=str(cs).strip().upper()[:24] if cs else None
    assigned=scalar(pathv(d,'hfdl.lpdu.assigned_ac_id','lpdu.assigned_ac_id','hfdl.lpdu.assigned_aircraft_id','lpdu.assigned_aircraft_id'))
    if assigned is None:
        vals=find_with_path(d,{'assigned_ac_id','assigned_aircraft_id'})
        assigned=scalar(vals[0][1]) if vals else None
    bitrate=num(pathv(d,'bit_rate','bitrate','bps','data_rate') or findv(d,{'bit_rate','bitrate','bps','data_rate'}))
    return {'ts':now.isoformat(),'epoch':now.timestamp(),'freq':f,'signal':sig,'noise':noise,'snr':snr,'freq_skew':skew,'slot':str(slot)[:12] if slot is not None else None,'bitrate':int(bitrate) if bitrate else None,'direction':str(direction)[:40] if direction else None,'frame_type':frame,'msgtype':str(typ)[:120],'icao':ac_icao,'callsign':cs,'assigned_ac_id':str(assigned)[:24] if assigned is not None else None,'lat':lat,'lon':lon,'alt':alt,'src_gs':src_gs,'dst_gs':dst_gs,'gs':gs,'raw':d}

def classify_event(m):
    text=str(m.get('msgtype') or '').lower()
    if 'logon' in text:return 'logon'
    if 'logoff' in text:return 'logoff'
    if m.get('lat') is not None and m.get('lon') is not None:return 'position'
    return 'any'

def evaluate_alerts(c,m,message_id):
    hits=[]; event=classify_event(m)
    rows=c.execute('SELECT * FROM alerts WHERE enabled=1').fetchall()
    for row in rows:
        value=str(m.get(row['match_type']) or '')
        if not value:continue
        if row['pattern'].upper() not in value.upper():continue
        if row['event_type'] not in ('any',event):continue
        details=f"{row['match_type']} {value} matched {row['pattern']} ({event})"
        cur=c.execute('INSERT INTO alert_hits(alert_id,message_id,ts,icao,callsign,msgtype,details) VALUES(?,?,?,?,?,?,?)',(row['id'],message_id,m['ts'],m.get('icao'),m.get('callsign'),m.get('msgtype'),details))
        hits.append({'id':cur.lastrowid,'alert_id':row['id'],'message_id':message_id,'ts':m['ts'],'icao':m.get('icao'),'callsign':m.get('callsign'),'msgtype':m.get('msgtype'),'details':details})
    return hits

def save(m):
    with db() as c:
        sql='INSERT INTO messages(ts,epoch,freq,signal,noise,snr,bitrate,direction,msgtype,icao,callsign,lat,lon,alt,gs,raw,frame_type,src_gs,dst_gs,assigned_ac_id,freq_skew,slot) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
        vals=(m['ts'],m['epoch'],m['freq'],m['signal'],m['noise'],m['snr'],m['bitrate'],m['direction'],m['msgtype'],m['icao'],m['callsign'],m['lat'],m['lon'],m['alt'],m['gs'],json.dumps(m['raw'],separators=(',',':')),m['frame_type'],m['src_gs'],m['dst_gs'],m['assigned_ac_id'],m['freq_skew'],m['slot'])
        cur=c.execute(sql,vals); m['id']=cur.lastrowid
        if m['icao']:
            c.execute('''INSERT INTO aircraft VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(icao) DO UPDATE SET callsign=COALESCE(excluded.callsign,aircraft.callsign),lat=COALESCE(excluded.lat,aircraft.lat),lon=COALESCE(excluded.lon,aircraft.lon),alt=COALESCE(excluded.alt,aircraft.alt),freq=COALESCE(excluded.freq,aircraft.freq),msgtype=excluded.msgtype,last_seen=excluded.last_seen,last_epoch=excluded.last_epoch''',(m['icao'],m['callsign'],m['lat'],m['lon'],m['alt'],m['freq'],m['msgtype'],m['ts'],m['epoch']))
        hits=evaluate_alerts(c,m,m['id'])
        c.commit()
        return hits

async def broadcast(m,hits=None):
    dead=[]
    for ws in list(clients):
        try:
            await ws.send_json({'event':'message','data':{k:v for k,v in m.items() if k!='raw'}})
            for hit in hits or []:await ws.send_json({'event':'alert','data':hit})
        except:dead.append(ws)
    for ws in dead:clients.discard(ws)

class Proto(asyncio.DatagramProtocol):
    def datagram_received(self,data,addr):
        counters['total']+=1;counters['last']=time.time()
        try:
            d=json.loads(data.decode()); m=parse(d); hits=save(m); asyncio.create_task(broadcast(m,hits))
        except Exception:counters['invalid']+=1

@asynccontextmanager
async def life(app):
    init_db(); loop=asyncio.get_running_loop(); t,_=await loop.create_datagram_endpoint(Proto,local_addr=(UDP_BIND,UDP))
    try:yield
    finally:t.close()

app=FastAPI(lifespan=life)


@app.middleware("http")
async def dashboard_no_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

def auth_ok(value):
    if not AUTH_USER and not AUTH_PASS:return True
    if not value or not value.lower().startswith('basic '):return False
    try:
        decoded=base64.b64decode(value.split(' ',1)[1]).decode('utf-8')
        user,password=decoded.split(':',1)
        return secrets.compare_digest(user,AUTH_USER) and secrets.compare_digest(password,AUTH_PASS)
    except Exception:return False

@app.middleware('http')
async def require_auth(request:Request,call_next):
    if auth_ok(request.headers.get('authorization')):
        return await call_next(request)
    return Response(status_code=401,headers={'WWW-Authenticate':'Basic realm="HFDL Dashboard"'},content='Authentication required')


HTML=r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HFDL Operations Dashboard v10.6 ADSB.lol Correlation</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root{
  --bg:#0b1020;--panel:#151c30;--panel2:#1b2540;--border:#2b3758;
  --text:#edf3ff;--muted:#9ba9c7;--accent:#78a9ff;--good:#9ee6cf;
  --warn:#ffd58a;--bad:#ff7d86;--up:#8eb8ff;--down:#9ee6cf;
  --row:38px;--pad:12px;--font:13px
}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
body.compact{--row:30px;--pad:8px;--font:12px}
button,input,select{font:inherit}
.topbar{
  position:sticky;top:0;z-index:1000;background:rgba(11,16,32,.97);
  border-bottom:1px solid var(--border);backdrop-filter:blur(12px)
}
.brandrow{height:58px;display:flex;align-items:center;justify-content:space-between;padding:0 18px;gap:14px}
.brand{display:flex;align-items:center;gap:12px;min-width:0}
.brand h1{font-size:18px;margin:0;white-space:nowrap}
.brand small{color:var(--muted)}
.status{display:flex;align-items:center;color:var(--muted);font-size:12px;white-space:nowrap}
.dot{width:10px;height:10px;border-radius:50%;background:var(--bad);margin-right:7px;box-shadow:0 0 10px currentColor}
.dot.on{background:var(--good);color:var(--good)}
.dot.warn{background:var(--warn);color:var(--warn)}
.menu-toggle{display:none}
.nav{display:flex;gap:4px;padding:0 14px 8px;overflow-x:auto}
.nav button{
  color:var(--muted);background:transparent;border:1px solid transparent;border-radius:9px;
  padding:8px 12px;white-space:nowrap;cursor:pointer
}
.nav button:hover{color:var(--text);background:var(--panel2)}
.nav button.active{color:var(--text);background:var(--panel2);border-color:var(--border)}
.silence{display:none;margin:14px 18px 0;padding:10px 12px;border:1px solid #79612e;background:#2b2415;color:var(--warn);border-radius:10px}
.silence.on{display:block}
main{padding:16px 18px 28px;max-width:1800px;margin:auto}
.view{display:none}.view.active{display:block}
.grid{display:grid;gap:14px}.grid.two{grid-template-columns:1.35fr .65fr}.grid.equal{grid-template-columns:1fr 1fr}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:15px;overflow:hidden;min-width:0}
.panelhead{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 14px;border-bottom:1px solid var(--border)}
.panelhead h2{margin:0;font-size:15px}.panelhead small{color:var(--muted)}
.panelbody{padding:14px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.metric{background:var(--panel);border:1px solid var(--border);border-radius:13px;padding:13px}
.metric span{display:block;color:var(--muted);font-size:12px}.metric b{display:block;font-size:23px;margin-top:4px}
#overview-map{height:380px}#map{height:calc(100vh - 155px);min-height:480px}
.maplayout{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:14px}
.maplist{max-height:calc(100vh - 155px);overflow:auto}
.toolbar{display:flex;flex-wrap:wrap;gap:7px;padding:10px;border-bottom:1px solid var(--border)}
.toolbar input,.toolbar select,.settings input,.settings select{
  background:var(--panel2);color:var(--text);border:1px solid var(--border);
  border-radius:8px;padding:8px 9px;min-width:120px
}
button.action{background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:8px 10px;cursor:pointer}
button.action:hover{border-color:var(--accent)}
.tablewrap{overflow:auto;max-height:calc(100vh - 235px)}
table{width:100%;border-collapse:collapse;font-size:var(--font)}
th,td{height:var(--row);padding:0 var(--pad);border-bottom:1px solid var(--border);text-align:left;white-space:nowrap}
th{position:sticky;top:0;background:#1c2540;color:var(--muted);z-index:3}
tr.legacy{opacity:.45}tr.uplink{border-left:3px solid var(--up)}tr.downlink{border-left:3px solid var(--down)}
.typecell{max-width:260px;overflow:hidden;text-overflow:ellipsis}
.cardlist{display:grid;gap:8px;padding:12px}
.cardrow{display:grid;grid-template-columns:80px 1fr auto;gap:10px;align-items:center;padding:10px;border:1px solid var(--border);border-radius:10px;background:rgba(255,255,255,.015)}
.muted{color:var(--muted)}
.barrow{display:grid;grid-template-columns:90px 1fr 60px;gap:10px;align-items:center;margin:11px 0}
.track{height:10px;border-radius:99px;background:#0d1426;overflow:hidden}.fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--good))}
.settings{display:grid;grid-template-columns:repeat(2,minmax(220px,1fr));gap:12px;max-width:900px}
.setting{border:1px solid var(--border);border-radius:12px;background:var(--panel);padding:14px}
.setting label{display:block;font-weight:600;margin-bottom:6px}.setting p{color:var(--muted);font-size:12px;margin:5px 0 10px}
.marker{width:15px;height:15px;border-radius:50%;background:var(--accent);border:2px solid white;box-shadow:0 0 12px var(--accent)}
.modal{display:none;position:fixed;inset:0;background:#000b;z-index:3000;padding:5vh 5vw}.modal.on{display:block}
.modalbox{height:90vh;background:#111a2e;border:1px solid var(--border);border-radius:14px;padding:16px;overflow:auto}
.modalhead{display:flex;justify-content:space-between;align-items:center}.modal pre{white-space:pre-wrap;word-break:break-word;color:#cfe1ff;font:12px ui-monospace,monospace}
.empty{padding:24px;color:var(--muted);text-align:center}.alert-hit{border-left:3px solid var(--warn);background:rgba(255,213,138,.06)}
.badge{display:inline-block;border:1px solid var(--border);border-radius:999px;padding:3px 7px;font-size:11px;color:var(--muted)}
.filebox{border:1px dashed var(--border);border-radius:12px;padding:14px}.filebox input{max-width:100%}

.aircraft-photo{width:100%;height:250px;object-fit:cover;border-radius:10px;border:1px solid var(--border);background:#0b1020}
.photo-placeholder{min-height:110px;display:flex;align-items:center;justify-content:center;border-radius:10px;border:1px dashed var(--border);color:var(--muted);background:#0b1020}
.photo-credit{font-size:12px;color:var(--muted);margin-top:7px}
.external-lookup-card{margin-top:18px;padding:18px;border:1px solid var(--border);border-radius:12px;background:linear-gradient(180deg,rgba(31,42,70,.92),rgba(18,26,45,.92))}
.external-lookup-card h3{margin:0 0 6px;font-size:18px}
.external-lookup-card p{margin:0 0 14px;color:var(--muted)}
.external-lookup-grid{display:grid;grid-template-columns:120px minmax(0,1fr);gap:10px 14px;margin-bottom:16px}
.external-lookup-grid b{color:var(--muted);font-weight:600}
.external-lookup-grid span{overflow-wrap:anywhere}
.external-lookup-actions{display:flex;gap:8px;flex-wrap:wrap}
.external-lookup-actions .primary{padding:11px 16px;font-weight:700}
.external-live-card{margin-top:14px;padding:16px;border:1px solid var(--border);border-radius:12px;background:rgba(12,20,35,.58)}
.external-live-head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.external-live-head h3{margin:0;font-size:17px}
.external-live-grid{display:grid;grid-template-columns:150px minmax(0,1fr);gap:8px 14px;margin-top:14px}
.external-live-grid b{color:var(--muted);font-weight:600}
.external-source-badge{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;border:1px solid var(--border);font-size:12px;font-weight:700;text-transform:uppercase}
.external-warning{margin-top:12px;padding:10px 12px;border-radius:9px;background:rgba(255,186,73,.10);border:1px solid rgba(255,186,73,.28)}
.detailhero{display:grid;grid-template-columns:1.2fr .8fr;gap:14px;margin-bottom:14px}
.detailidentity{padding:18px}.detailidentity h2{font-size:28px;margin:0 0 5px}.chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}
.chip{border:1px solid var(--border);background:var(--panel2);border-radius:999px;padding:5px 9px;color:var(--muted);font-size:12px}
#detail-map{height:420px}.detailgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.timeline{padding:12px;display:grid;gap:8px;max-height:430px;overflow:auto}
.event{border-left:3px solid var(--accent);padding:9px 10px;background:rgba(255,255,255,.018);border-radius:8px}
.eventtime{color:var(--muted);font-size:11px}.clickable{cursor:pointer}.clickable:hover{background:rgba(120,169,255,.08)}
@media(max-width:1050px){.detailhero,.detailgrid{grid-template-columns:1fr}}

@media(max-width:1050px){
  .grid.two,.grid.equal,.maplayout{grid-template-columns:1fr}
  .metrics{grid-template-columns:repeat(2,1fr)}
  #map{height:65vh}.maplist{max-height:320px}
}
@media(max-width:720px){
  .brandrow{height:auto;min-height:58px}.brand small{display:none}
  .menu-toggle{display:inline-block}
  .nav{display:none;flex-direction:column;padding:8px 14px 12px}.nav.open{display:flex}
  .nav button{text-align:left}
  main{padding:12px}.metrics{grid-template-columns:1fr 1fr}.settings{grid-template-columns:1fr}
}
</style>
</head>
<body>
<header class="topbar">
  <div class="brandrow">
    <div class="brand">
      <button class="action menu-toggle" onclick="toggleMenu()">☰</button>
      <div><h1>HFDL Operations Dashboard <small>v10.6 ADSB.lol Correlation</small></h1></div>
    </div>
    <div class="status"><span id="dot" class="dot"></span><span id="state">Connecting</span>&nbsp;·&nbsp;UDP 5557</div>
  </div>
  <nav id="nav" class="nav">
    <button data-view="overview" class="active">Overview</button>
    <button data-view="mapview">Map</button>
    <button data-view="messages">Messages</button>
    <button data-view="aircraft">Aircraft</button>
    <button data-view="aircraft-detail" id="aircraft-detail-tab" style="display:none">Aircraft Detail</button>
    <button data-view="stations">Stations</button>
    <button data-view="alerts">Alerts</button>
    <button data-view="analytics">Analytics</button>
    <button data-view="settings">Settings</button>
    <button data-view="about">About</button>
  </nav>
</header>

<div id="silence" class="silence">No HFDL datagrams have arrived recently. Check dumphfdl, the network and UDP port 5557.</div>

<main>
<section id="view-overview" class="view active">
  <div class="metrics">
    <div class="metric"><span>Messages · 6 h</span><b id="mc">—</b></div>
    <div class="metric"><span>Aircraft · 6 h</span><b id="ac">—</b></div>
    <div class="metric"><span>Average SNR</span><b id="snr">—</b></div>
    <div class="metric"><span>Datagrams</span><b id="dg">—</b></div>
  </div>
  <div class="grid two" style="margin-top:14px">
    <section class="panel">
      <div class="panelhead"><div><h2>Position overview</h2><small>Recent valid positions</small></div><button class="action" onclick="showView('mapview')">Open full map</button></div>
      <div id="overview-map"></div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Latest messages</h2><small>Most recent decoded traffic</small></div><button class="action" onclick="showView('messages')">View all</button></div>
      <div class="tablewrap" style="max-height:380px"><table><thead><tr><th>Time</th><th>Dir</th><th>Aircraft</th><th>Type</th></tr></thead><tbody id="overview-msgs"></tbody></table></div>
    </section>
  </div>
</section>

<section id="view-mapview" class="view">
  <div class="maplayout">
    <section class="panel">
      <div class="panelhead"><div><h2>Aircraft map</h2><small>HFDL position reports</small></div><div><button class="action" onclick="fitMap()">Fit aircraft</button> <button class="action" onclick="toggleMapFullscreen()">Full screen</button></div></div>
      <div id="map"></div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Aircraft on map</h2><small>Click to centre</small></div></div>
      <div id="map-aircraft" class="cardlist maplist"></div>
    </section>
  </div>
</section>

<section id="view-messages" class="view">
  <section class="panel">
    <div class="panelhead"><div><h2>Live messages</h2><small>Filter, inspect and export</small></div><div><button class="action" onclick="exportData('csv')">CSV</button> <button class="action" onclick="exportData('json')">JSON</button></div></div>
    <div class="toolbar">
      <input id="qicao" placeholder="ICAO">
      <input id="qcall" placeholder="Callsign">
      <select id="qdir"><option value="">All directions</option><option>Uplink</option><option>Downlink</option></select>
      <select id="qframe"><option value="">All frames</option><option>LPDU</option><option>SPDU</option></select>
      <input id="qtype" placeholder="Message type">
      <button class="action" onclick="refresh()">Apply</button>
      <button class="action" onclick="clearFilters()">Clear</button>
    </div>
    <div class="tablewrap"><table><thead><tr><th>Time</th><th>Freq</th><th>Dir</th><th>Frame / Type</th><th>GS</th><th>ICAO</th><th>Callsign</th><th>AC ID</th><th>Signal</th><th>SNR</th><th>Raw</th></tr></thead><tbody id="msgs"></tbody></table></div>
  </section>
</section>

<section id="view-aircraft" class="view">
  <section class="panel">
    <div class="panelhead"><div><h2>Recent aircraft</h2><small>Seen during the last six hours</small></div></div>
    <div class="tablewrap"><table><thead><tr><th>ICAO</th><th>Callsign</th><th>Registration</th><th>Type</th><th>Operator</th><th>Country</th><th>Altitude</th><th>Frequency</th><th>Last message</th><th>Last seen</th><th>Actions</th></tr></thead><tbody id="air"></tbody></table></div>
  </section>
</section>


<section id="view-aircraft-detail" class="view">
  <div class="detailhero">
    <section class="panel">
      <div class="detailidentity">
        <button class="action" onclick="showView('aircraft')">← Back to aircraft</button>
        <h2 id="detail-title" style="margin-top:14px">Aircraft</h2>
        <div id="detail-subtitle" class="muted">Select an aircraft from the Aircraft page.</div>
        <div id="detail-chips" class="chips"></div>
      </div>
      <div id="detail-metrics" class="metrics" style="padding:0 14px 14px"></div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Aircraft photograph</h2><small>Local image, direct URL, or authorised Planespotters thumbnail</small></div><button class="action" onclick="loadPlanespottersPhoto(true)">Refresh photo</button></div>
      <div class="panelbody">
        <div id="detail-photo" class="photo-placeholder">No aircraft photograph available.</div>
        <div id="detail-photo-credit" class="photo-credit"></div>
        <div id="planespotters-photo-status" class="muted" style="margin-top:8px;font-size:12px">Automatic photo lookup has not run.</div>
        <div style="margin-top:12px">
          <input id="aircraft-photo-file" type="file" accept="image/jpeg,image/png,image/webp">
          <button class="action" onclick="uploadAircraftPhoto()">Upload local photo</button>
        </div>
        <div style="margin-top:14px">
          <input id="aircraft-photo-url" style="width:min(100%,520px)" placeholder="Direct image URL: https://example.org/aircraft.jpg"><br><br>
          <input id="aircraft-photo-credit-input" style="width:min(100%,360px)" placeholder="Photographer or source credit">
          <input id="aircraft-photo-link-input" style="width:min(100%,360px)" placeholder="Source webpage URL"><br><br>
          <button class="action" onclick="saveAircraftPhotoUrl()">Save internet photo URL</button>
        </div>
        <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
          <button class="action" onclick="openAdsbLolGlobe()">Open on ADSB.lol</button>
          <button class="action" onclick="loadAdsbLol(true)">Refresh ADSB.lol</button>
          <button class="action" onclick="openAirplanesLiveGlobe()">Open on Airplanes.live</button>
          <button class="action" onclick="loadAirplanesLive(true)">Refresh Airplanes.live</button>
          <button class="action" onclick="openPlanespotters()">Open on Planespotters</button>
          <button class="action" onclick="searchAircraftGoogle()">Search Google</button>
        </div>
        <div class="external-live-card">
          <div class="external-live-head">
            <h3>ADSB.lol correlation</h3>
            <span id="lol-source" class="external-source-badge">Not loaded</span>
          </div>
          <div id="lol-status" class="muted" style="margin-top:7px">Free external ADS-B data is loaded only for the selected aircraft.</div>
          <div class="external-live-grid">
            <b>Position</b><span id="lol-position">—</span>
            <b>Position age</b><span id="lol-position-age">—</span>
            <b>Altitude</b><span id="lol-altitude">—</span>
            <b>Ground speed</b><span id="lol-speed">—</span>
            <b>Track / heading</b><span id="lol-track">—</span>
            <b>Vertical rate</b><span id="lol-vertical-rate">—</span>
            <b>Squawk</b><span id="lol-squawk">—</span>
            <b>Emergency</b><span id="lol-emergency">—</span>
            <b>Callsign</b><span id="lol-flight">—</span>
            <b>Registration / type</b><span id="lol-identity">—</span>
            <b>Last message age</b><span id="lol-seen">—</span>
            <b>Integrity</b><span id="lol-integrity">—</span>
          </div>
          <div id="lol-warning" class="external-warning" style="display:none"></div>
        </div>
        <div class="external-live-card">
          <div class="external-live-head">
            <h3>Airplanes.live correlation</h3>
            <span id="al-source" class="external-source-badge">Not loaded</span>
          </div>
          <div id="al-status" class="muted" style="margin-top:7px">External data is loaded only when this aircraft detail page is opened or refreshed.</div>
          <div class="external-live-grid">
            <b>Position</b><span id="al-position">—</span>
            <b>Position age</b><span id="al-position-age">—</span>
            <b>Altitude</b><span id="al-altitude">—</span>
            <b>Ground speed</b><span id="al-speed">—</span>
            <b>Track / heading</b><span id="al-track">—</span>
            <b>Squawk</b><span id="al-squawk">—</span>
            <b>Emergency</b><span id="al-emergency">—</span>
            <b>Callsign</b><span id="al-flight">—</span>
            <b>Registration / type</b><span id="al-identity">—</span>
            <b>Last message age</b><span id="al-seen">—</span>
          </div>
          <div id="al-warning" class="external-warning" style="display:none"></div>
        </div>
        <div class="external-lookup-card">
          <h3>External aircraft record</h3>
          <p>Open the complete record and available photographs in a new browser tab.</p>
          <div class="external-lookup-grid">
            <b>Registration</b><span id="external-registration">—</span>
            <b>ICAO</b><span id="external-icao">—</span>
            <b>Aircraft type</b><span id="external-type">—</span>
            <b>Operator</b><span id="external-operator">—</span>
          </div>
          <div class="external-lookup-actions">
            <button class="action primary" onclick="openPlanespotters()">Open complete record and photographs</button>
            <button class="action" onclick="searchAircraftGoogle()">Search Google</button>
          </div>
        </div>
      </div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Last known data</h2><small>Latest associated HFDL record</small></div></div>
      <div id="detail-latest" class="panelbody"></div>
      <div class="panelbody" style="padding-top:0;color:var(--muted);font-size:12px">Aircraft identity, metadata and positions are informational only and may be inaccurate or outdated.</div>
    </section>
  </div>
  <div class="detailgrid">
    <section class="panel">
      <div class="panelhead"><div><h2>Track history</h2><small>Position reports from the selected period</small></div><div><select id="detail-hours" onchange="reloadAircraftDetail()"><option value="6">6 h</option><option value="24" selected>24 h</option><option value="72">3 days</option><option value="168">7 days</option></select></div></div>
      <div id="detail-map"></div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Operational timeline</h2><small>Logon, logoff and position-related events</small></div></div>
      <div id="detail-events" class="timeline"></div>
    </section>
  </div>
  <section class="panel" style="margin-top:14px">
    <div class="panelhead"><div><h2>Aircraft message history</h2><small>Messages associated with this ICAO address</small></div><button class="action" onclick="exportAircraftMessages()">Export JSON</button></div>
    <div class="tablewrap"><table><thead><tr><th>Time</th><th>Direction</th><th>Frame / Type</th><th>GS</th><th>Callsign</th><th>AC ID</th><th>Frequency</th><th>SNR</th><th>Raw</th></tr></thead><tbody id="detail-messages"></tbody></table></div>
  </section>
</section>

<section id="view-stations" class="view">
  <div class="grid equal">
    <section class="panel"><div class="panelhead"><div><h2>Ground-station activity</h2><small>Last six hours</small></div></div><div id="gslist" class="cardlist"></div></section>
    <section class="panel"><div class="panelhead"><div><h2>Station summary</h2><small>Uplink and downlink totals</small></div></div><div id="gssummary" class="panelbody"></div></section>
  </div>
</section>


<section id="view-alerts" class="view">
  <div class="grid equal">
    <section class="panel">
      <div class="panelhead"><div><h2>Alert rules</h2><small>Watch ICAO addresses or callsigns</small></div><button class="action" onclick="requestNotifications()">Enable browser notifications</button></div>
      <div class="panelbody">
        <div class="toolbar" style="border:0;padding:0 0 12px">
          <select id="alert-match"><option value="icao">ICAO</option><option value="callsign">Callsign</option></select>
          <input id="alert-pattern" placeholder="Pattern, e.g. 76CD77 or SIA">
          <select id="alert-event"><option value="any">Any message</option><option value="logon">Logon</option><option value="logoff">Logoff</option><option value="position">Position report</option></select>
          <button class="action" onclick="createAlert()">Add alert</button>
        </div>
        <div id="alert-rules" class="cardlist"></div>
      </div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Recent alert hits</h2><small>Newest matches first</small></div><button class="action" onclick="loadAlerts()">Refresh</button></div>
      <div id="alert-hits" class="cardlist"></div>
    </section>
  </div>
</section>

<section id="view-analytics" class="view">
  <div class="panel" style="margin-bottom:14px">
    <div class="panelhead">
      <div><h2>Receiver analytics</h2><small>Reception rate, SNR and interruption history</small></div>
      <select id="analytics-hours" onchange="loadAnalytics()">
        <option value="6">6 hours</option>
        <option value="24" selected>24 hours</option>
        <option value="72">3 days</option>
        <option value="168">7 days</option>
      </select>
    </div>
    <div class="panelbody">
      <canvas id="rate-chart" style="max-height:300px"></canvas>
    </div>
  </div>
  <div class="grid equal">
    <section class="panel">
      <div class="panelhead"><div><h2>SNR trend</h2><small>Average signal-to-noise ratio by interval</small></div></div>
      <div class="panelbody"><canvas id="snr-chart" style="max-height:280px"></canvas></div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Frequency performance</h2><small>Count, average SNR and strongest signal</small></div></div>
      <div class="tablewrap" style="max-height:330px"><table><thead><tr><th>Frequency</th><th>Messages</th><th>Avg SNR</th><th>Strongest</th></tr></thead><tbody id="frequency-performance"></tbody></table></div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Most-heard aircraft</h2><small>By received message count</small></div></div>
      <div id="top-aircraft" class="cardlist"></div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Reception gaps</h2><small>Longest zero-message periods</small></div></div>
      <div id="gap-list" class="cardlist"></div>
    </section>
  </div>
</section>

<section id="view-settings" class="view">
  <section class="panel">
    <div class="panelhead"><div><h2>Display settings</h2><small>Stored in this browser</small></div></div>
    <div class="panelbody settings">
      <div class="setting"><label for="density">Display density</label><p>Compact mode reduces table height and padding.</p><select id="density"><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></div>
      <div class="setting"><label for="rowlimit">Message row limit</label><p>Controls how many recent rows the message page loads.</p><select id="rowlimit"><option>100</option><option selected>250</option><option>500</option><option>1000</option></select></div>
      <div class="setting"><label for="silentmins">Silence warning</label><p>Warn when no datagram is received for this many minutes.</p><select id="silentmins"><option value="1">1 minute</option><option value="3" selected>3 minutes</option><option value="5">5 minutes</option><option value="10">10 minutes</option></select></div>
      <div class="setting"><label for="hidelegacy">Legacy records</label><p>Hide old rows parsed before the improved v2 parser.</p><select id="hidelegacy"><option value="no">Show dimmed</option><option value="yes">Hide</option></select></div>
      <div class="setting"><label for="metadata-mode">Aircraft metadata source</label><p>Choose local import, internet download, a combined fallback mode, or disable enrichment.</p>
        <select id="metadata-mode">
          <option value="local">Local file only</option>
          <option value="internet">Internet download only</option>
          <option value="internet_first">Internet first, then local data</option>
          <option value="local_first">Local data first, then internet</option>
          <option value="disabled">Disabled</option>
        </select>
        <select id="overwrite-manual"><option value="no">Preserve existing values</option><option value="yes">Overwrite existing values</option></select>
        <button class="action" onclick="saveEnrichmentSettings()">Save source settings</button>
      </div>
      <div class="setting"><label>Import metadata from a local file</label><p>Accepts the dashboard CSV format and the original OpenSky aircraftDatabase.csv without renaming columns.</p><div class="filebox"><input id="metadata-file" type="file" accept=".csv,text/csv"><br><br><button class="action" onclick="importMetadata()">Import local CSV</button></div><p id="metadata-status">No file imported.</p></div>
      <div class="setting"><label for="metadata-url">Download metadata from the internet</label><p>OpenSky's original CSV is supported directly, including the native <code>icao24</code>, <code>model</code>, <code>typecode</code>, <code>operator</code>, <code>operatorcallsign</code> and <code>owner</code> columns.</p><input id="metadata-url" style="width:min(100%,720px)" placeholder="https://opensky-network.org/datasets/metadata/aircraftDatabase.csv"><br><br><button class="action" onclick="useOpenSkyUrl()">Use OpenSky URL</button> <button class="action" onclick="downloadMetadata()">Download and import CSV</button><p id="metadata-download-status"></p></div>
      <div class="setting"><label for="photo-mode">Aircraft photo source</label><p>Local photos are stored in the dashboard data folder. Internet photos use the photo_url field from metadata.</p>
        <select id="photo-mode">
          <option value="local_first">Local photo first, then internet URL</option>
          <option value="internet_first">Internet URL first, then local photo</option>
          <option value="local">Local photos only</option>
          <option value="internet">Internet URLs only</option>
          <option value="disabled">Disabled</option>
        </select>
        <select id="photo-lookup">
          <option value="manual">Allow manually entered direct image URLs</option>
          <option value="disabled">Disable internet photo URLs</option>
        </select>
        <button class="action" onclick="saveEnrichmentSettings()">Save photo setting</button>
        <p>Automatic server-side photo lookup is disabled because the provider rejected automated requests. Aircraft Detail now includes a browser link that opens the matching Planespotters page directly by ICAO hex, plus a Google search fallback.</p>
      </div>
      <div class="setting"><label>Password protection</label><p>Set DASHBOARD_USERNAME and DASHBOARD_PASSWORD in compose.yaml, then rebuild. Leave both blank to disable authentication.</p><span class="badge">HTTP Basic authentication</span></div>
      <div class="setting"><label>Restore defaults</label><p>Reset browser display preferences.</p><button class="action" onclick="resetSettings()">Reset settings</button></div>
      <div class="setting"><label>Database backup</label><p>Download a consistent SQLite backup of messages and aircraft history.</p><button class="action" onclick="downloadBackup()">Download backup</button></div>
      <div class="setting"><label>Database status</label><p id="db-status">Loading database information…</p><button class="action" onclick="loadDatabaseStatus()">Refresh status</button></div>
      <div class="setting"><label>Remove legacy records</label><p>Delete only old pre-v2 rows whose type is shown as dumphfdl.</p><button class="action" onclick="purgeLegacy()">Purge legacy rows</button></div>
      <div class="setting"><label for="retention-days">Delete old history</label><p>Delete messages older than the selected number of days. Back up first.</p><select id="retention-days"><option value="7">7 days</option><option value="30" selected>30 days</option><option value="90">90 days</option><option value="365">1 year</option></select> <button class="action" onclick="purgeOlder()">Delete older records</button></div>
    </div>
  </section>
</section>

<section id="view-about" class="view">
  <div class="grid two">
    <section class="panel">
      <div class="panelhead"><div><h2>HFDL Operations Dashboard v9</h2><small>Publication Edition</small></div></div>
      <div class="panelbody">
        <h3 style="margin-top:0">Developed by Louis LeMerle, VK2ICW</h3>
        <p>Concept, design and project direction by Louis LeMerle, VK2ICW.</p>
        <p>Copyright © 2026 Louis LeMerle. Licensed under the MIT License.</p>
        <div class="notice" style="margin-top:16px">
          <b>Operational notice</b>
          <p style="margin-bottom:0">Experimental HFDL reception, analysis and aircraft-data visualisation software. Not for navigation, air traffic control, flight safety, emergency operations or other safety-critical use.</p>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:16px">
          <a class="action" href="/legal/LICENSE" target="_blank">Licence</a>
          <a class="action" href="/legal/DISCLAIMER" target="_blank">Disclaimer</a>
          <a class="action" href="/legal/PRIVACY" target="_blank">Privacy</a>
          <a class="action" href="/legal/SECURITY" target="_blank">Security</a>
          <a class="action" href="/legal/THIRD_PARTY_NOTICES" target="_blank">Third-party notices</a>
          <a class="action" href="/legal/CHANGELOG" target="_blank">Changelog</a>
        </div>
      </div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Important information</h2><small>Read before public or operational use</small></div></div>
      <div class="panelbody cardlist">
        <div class="cardrow"><b>Data quality</b><span class="muted">Decoded information may be incomplete, delayed, duplicated, misdecoded or associated with the wrong aircraft.</span><span>Informational only</span></div>
        <div class="cardrow"><b>Position age</b><span class="muted">A plotted position may be older than the aircraft's latest non-position HFDL message.</span><span>Verify independently</span></div>
        <div class="cardrow"><b>Lawful use</b><span class="muted">Users are responsible for reception, storage, use and disclosure laws in their jurisdiction.</span><span>User responsibility</span></div>
        <div class="cardrow"><b>Security</b><span class="muted">Password protection is not a replacement for firewalling, HTTPS and operating-system controls.</span><span>Do not expose directly</span></div>
        <div class="cardrow"><b>External services</b><span class="muted">Map tiles, metadata downloads, browser links and external images are governed by their providers.</span><span>Separate services</span></div>
      </div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Data and service acknowledgements</h2><small>Independent third-party projects and services</small></div></div>
      <div class="panelbody">
        <p><b>OpenSky Network:</b> optional aircraft metadata import. The downloadable database is offered as-is, may be out of date and is not endorsed or certified for this application.</p>
        <p><b>OpenStreetMap contributors:</b> map data. Attribution remains visible on each map.</p>
        <p><b>ADSB.lol:</b> optional on-demand free external aircraft correlation by ICAO hex, cached briefly and displayed separately from receiver-decoded HFDL data.</p><p><b>Airplanes.live:</b> optional on-demand aircraft correlation by ICAO hex, cached locally for a short period and displayed separately from receiver-decoded HFDL data.</p><p><b>Planespotters.net:</b> optional automatic thumbnail lookup through the public Photo API. The supplied photographer attribution is displayed and the image links to the original Planespotters photograph page. Full-resolution photographs are not copied or stored by the dashboard.</p>
        <p><b>Leaflet and Chart.js:</b> browser mapping and charting libraries.</p>
        <p><b>FastAPI and Uvicorn:</b> local web application and server components.</p>
        <p style="margin-bottom:0">HFDL Operations Dashboard is not affiliated with, sponsored by or endorsed by these independent projects or services.</p>
      </div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Privacy summary</h2><small>Local-first operation</small></div></div>
      <div class="panelbody">
        <p>Received messages, aircraft history, alerts, settings and imported metadata are stored in the local SQLite database.</p>
        <p>The application does not intentionally transmit the received-message database to the developer.</p>
        <p>Internet requests may occur for map tiles, hosted JavaScript libraries, metadata downloads, external images, on-demand ADSB.lol and Airplanes.live aircraft lookups, on-demand Planespotters thumbnail lookups and user-opened aircraft websites. Those services may receive normal browser or network information under their own policies.</p>
        <p style="margin-bottom:0">See the full Privacy and Security documents before exposing the dashboard beyond a trusted local network.</p>
      </div>
    </section>
  </div>
  <div class="panel" style="margin-top:14px">
    <div class="panelbody" style="text-align:center;color:var(--muted)">
      HFDL Operations Dashboard v9 · Developed by Louis LeMerle, VK2ICW · Copyright © 2026 Louis LeMerle
    </div>
  </div>
</section>

</main>

<div id="rawmodal" class="modal" onclick="if(event.target===this)this.classList.remove('on')">
  <div class="modalbox"><div class="modalhead"><h2>Raw dumphfdl JSON</h2><button class="action" onclick="rawmodal.classList.remove('on')">Close</button></div><pre id="rawjson"></pre></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script>
const settings={
 density:localStorage.getItem('hfdl-density')||'comfortable',
 rowlimit:localStorage.getItem('hfdl-rowlimit')||'250',
 silentmins:localStorage.getItem('hfdl-silentmins')||'3',
 hidelegacy:localStorage.getItem('hfdl-hidelegacy')||'no'
};
let latestAircraft=[], latestMessages=[], latestHealth={}, latestStats={}, latestStations=[];
let map, overviewMap, detailMap, detailTrack, detailMarker, rateChart, snrChart;const markers=new Map(),overviewMarkers=new Map();let selectedAircraft=null,selectedAircraftData=null;

function initMaps(){
 map=L.map('map').setView([-25.5,134],4);
 overviewMap=L.map('overview-map',{zoomControl:false}).setView([-25.5,134],3);
 detailMap=L.map('detail-map').setView([-25.5,134],3);
 [map,overviewMap,detailMap].forEach(m=>L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap'}).addTo(m));
}
function markerIcon(){return L.divIcon({className:'',html:'<div class="marker"></div>',iconSize:[16,16],iconAnchor:[8,8]})}
function fmtFreq(v){return v==null?'—':Number(v).toFixed(1)+' kHz'}
function fmtDb(v,suffix=' dB'){return v==null?'—':Number(v).toFixed(1)+suffix}
function age(e){if(!e)return'—';let x=Math.max(0,Date.now()/1000-e);return x<60?Math.round(x)+'s ago':x<3600?Math.floor(x/60)+'m ago':Math.floor(x/3600)+'h ago'}
function gsText(m){return m.src_gs?('GS '+m.src_gs+' →'):m.dst_gs?('→ GS '+m.dst_gs):(m.gs||'—')}
function isLegacy(m){return !m.direction&&String(m.msgtype||'').toLowerCase()==='dumphfdl'}

function showView(name){
 document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
 document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===name));
 document.getElementById('view-'+name).classList.add('active');
 localStorage.setItem('hfdl-view',name);if(name==='analytics')setTimeout(loadAnalytics,100);if(name==='settings'){setTimeout(loadDatabaseStatus,100);setTimeout(loadMetadataStatus,120)};if(name==='alerts')setTimeout(loadAlerts,100);
 document.getElementById('nav').classList.remove('open');
 setTimeout(()=>{if(name==='mapview')map.invalidateSize();if(name==='overview')overviewMap.invalidateSize();if(name==='aircraft-detail')detailMap.invalidateSize()},80);
}
function toggleMenu(){document.getElementById('nav').classList.toggle('open')}
document.querySelectorAll('.nav button').forEach(b=>b.onclick=()=>showView(b.dataset.view));

function query(){
 let p=new URLSearchParams({limit:settings.rowlimit});
 [['icao','qicao'],['callsign','qcall'],['direction','qdir'],['frame_type','qframe'],['msgtype','qtype']].forEach(([k,id])=>{let e=document.getElementById(id);if(e&&e.value.trim())p.set(k,e.value.trim())});
 return p
}
function messageRow(m){
 if(settings.hidelegacy==='yes'&&isLegacy(m))return'';
 let cls=(isLegacy(m)?'legacy ':'')+(m.direction==='Uplink'?'uplink':m.direction==='Downlink'?'downlink':'');
 return `<tr class="${cls}"><td>${new Date(m.ts).toLocaleTimeString()}</td><td>${fmtFreq(m.freq)}</td><td>${m.direction||'—'}</td><td class="typecell" title="${[m.frame_type,m.msgtype].filter(Boolean).join(' · ')}">${[m.frame_type,m.msgtype].filter(Boolean).join(' · ')||'HFDL'}</td><td>${gsText(m)}</td><td>${m.icao||'—'}</td><td>${m.callsign||'—'}</td><td>${m.assigned_ac_id||'—'}</td><td>${fmtDb(m.signal,' dBFS')}</td><td>${fmtDb(m.snr)}</td><td><button class="action" onclick="rawMsg(${m.id})">JSON</button></td></tr>`
}
function renderMessages(){
 document.getElementById('msgs').innerHTML=latestMessages.map(messageRow).join('');
 document.getElementById('overview-msgs').innerHTML=latestMessages.slice(0,8).map(m=>`<tr><td>${new Date(m.ts).toLocaleTimeString()}</td><td>${m.direction||'—'}</td><td>${m.callsign||m.icao||'—'}</td><td class="typecell">${[m.frame_type,m.msgtype].filter(Boolean).join(' · ')||'HFDL'}</td></tr>`).join('')
}
function updateMapMarkers(targetMap,targetMarkers,small=false){
 const alive=new Set();
 latestAircraft.forEach(a=>{
  if(a.lat==null||a.lon==null)return;alive.add(a.icao);
  let mk=targetMarkers.get(a.icao);
  if(!mk){mk=L.marker([a.lat,a.lon],{icon:markerIcon()}).addTo(targetMap);targetMarkers.set(a.icao,mk)}else mk.setLatLng([a.lat,a.lon]);
  mk.bindPopup(`<b>${a.callsign||a.icao}</b><br>ICAO ${a.icao}<br>${fmtFreq(a.freq)}<br>${age(a.last_epoch)}`)
 });
 for(const[k,v]of targetMarkers)if(!alive.has(k)){v.remove();targetMarkers.delete(k)}
}
function centreAircraft(icao){
 let a=latestAircraft.find(x=>x.icao===icao);if(!a||a.lat==null)return;
 showView('mapview');setTimeout(()=>{map.setView([a.lat,a.lon],7);markers.get(icao)?.openPopup()},100)
}
function renderAircraft(){
 document.getElementById('air').innerHTML=latestAircraft.map(a=>`<tr class="clickable" onclick="openAircraftDetail('${a.icao}')"><td><b>${a.icao}</b></td><td>${a.callsign||'—'}</td><td>${a.registration||'—'}</td><td>${a.aircraft_type||'—'}</td><td>${a.operator||'—'}</td><td>${a.country||'—'}</td><td>${a.alt==null?'—':Math.round(a.alt).toLocaleString()+' ft'}</td><td>${fmtFreq(a.freq)}</td><td>${a.msgtype||'—'}</td><td>${age(a.last_epoch)}</td><td><button class="action" onclick="event.stopPropagation();openAircraftDetail('${a.icao}')">Details</button> ${a.lat==null?'':`<button class="action" onclick="event.stopPropagation();centreAircraft('${a.icao}')">Map</button>`}</td></tr>`).join('');
 let positioned=latestAircraft.filter(a=>a.lat!=null&&a.lon!=null);
 document.getElementById('map-aircraft').innerHTML=positioned.length?positioned.map(a=>`<div class="cardrow" onclick="centreAircraft('${a.icao}')" style="cursor:pointer"><b>${a.callsign||a.icao}</b><span class="muted">${a.icao} · ${fmtFreq(a.freq)}</span><span>${age(a.last_epoch)}</span></div>`).join(''):'<div class="empty">No recent position reports.</div>';
 updateMapMarkers(map,markers);updateMapMarkers(overviewMap,overviewMarkers,true)
}
function renderStations(){
 document.getElementById('gslist').innerHTML=latestStations.length?latestStations.map(g=>`<div class="cardrow"><b>GS ${g.gs}</b><span class="muted">${g.uplink} uplink · ${g.downlink} downlink</span><span>${age(g.last_epoch)}</span></div>`).join(''):'<div class="empty">No ground-station records.</div>';
 let up=latestStations.reduce((n,g)=>n+g.uplink,0),down=latestStations.reduce((n,g)=>n+g.downlink,0);
 document.getElementById('gssummary').innerHTML=`<div class="metrics"><div class="metric"><span>Active stations</span><b>${latestStations.length}</b></div><div class="metric"><span>Uplink frames</span><b>${up}</b></div><div class="metric"><span>Downlink frames</span><b>${down}</b></div><div class="metric"><span>Total GS frames</span><b>${up+down}</b></div></div>`
}
function renderAnalytics(){
 let entries=Object.entries(latestStats.freqs||{}),mx=Math.max(1,...entries.map(x=>x[1]));
 document.getElementById('bars').innerHTML=entries.length?entries.map(([k,v])=>`<div class="barrow"><span>${k} kHz</span><div class="track"><div class="fill" style="width:${100*v/mx}%"></div></div><span>${v}</span></div>`).join(''):'<div class="empty">No frequency data.</div>';
 document.getElementById('healthcards').innerHTML=`<div class="cardrow"><b>Status</b><span class="muted">UDP receiver</span><span>${latestHealth.status||'—'}</span></div><div class="cardrow"><b>Datagrams</b><span class="muted">Since container start</span><span>${latestHealth.total??'—'}</span></div><div class="cardrow"><b>Invalid</b><span class="muted">Rejected JSON packets</span><span>${latestHealth.invalid??'—'}</span></div><div class="cardrow"><b>Last input</b><span class="muted">Most recent datagram</span><span>${age(latestHealth.last)}</span></div>`
}
function renderStatus(){
 document.getElementById('mc').textContent=(latestStats.total??0).toLocaleString();
 document.getElementById('ac').textContent=latestStats.aircraft??0;
 document.getElementById('snr').textContent=latestStats.avg_snr==null?'—':latestStats.avg_snr+' dB';
 document.getElementById('dg').textContent=latestHealth.total??0;
 let silent=!latestHealth.last||Date.now()/1000-latestHealth.last>Number(settings.silentmins)*60;
 document.getElementById('silence').classList.toggle('on',silent);
 document.getElementById('dot').className='dot '+(silent?'warn':'on');
 document.getElementById('state').textContent=silent?'Feed silent':'Live'
}
async function refresh(){
 let qp=query();
 try{
  [latestStats,latestAircraft,latestMessages,latestHealth,latestStations]=await Promise.all([
   fetch('/api/stats').then(r=>r.json()),fetch('/api/aircraft').then(r=>r.json()),
   fetch('/api/messages?'+qp).then(r=>r.json()),fetch('/health').then(r=>r.json()),
   fetch('/api/ground-stations').then(r=>r.json())
  ]);
  renderStatus();renderMessages();renderAircraft();renderStations()
 }catch(e){document.getElementById('state').textContent='Data error'}
}
async function rawMsg(id){let d=await fetch('/api/messages/'+id+'/raw').then(r=>r.json());document.getElementById('rawjson').textContent=JSON.stringify(d,null,2);document.getElementById('rawmodal').classList.add('on')}
function fitMap(){let a=[...markers.values()];if(a.length)map.fitBounds(L.featureGroup(a).getBounds().pad(.2))}
function toggleMapFullscreen(){let p=document.getElementById('map').parentElement;if(!document.fullscreenElement)p.requestFullscreen();else document.exitFullscreen()}
function clearFilters(){['qicao','qcall','qtype'].forEach(id=>document.getElementById(id).value='');document.getElementById('qdir').value='';document.getElementById('qframe').value='';refresh()}
function exportData(fmt){let p=query();p.set('format',fmt);location.href='/api/export?'+p}
function applySettings(){
 document.body.classList.toggle('compact',settings.density==='compact');
 ['density','rowlimit','silentmins','hidelegacy'].forEach(id=>document.getElementById(id).value=settings[id]);
 renderMessages();renderStatus()
}
function saveSettings(){
 ['density','rowlimit','silentmins','hidelegacy'].forEach(id=>{settings[id]=document.getElementById(id).value;localStorage.setItem('hfdl-'+id,settings[id])});
 applySettings();refresh()
}
['density','rowlimit','silentmins','hidelegacy'].forEach(id=>document.getElementById(id).addEventListener('change',saveSettings));
function resetSettings(){['density','rowlimit','silentmins','hidelegacy','view'].forEach(k=>localStorage.removeItem('hfdl-'+k));location.reload()}

async function openAircraftDetail(icao){
 selectedAircraft=icao;
 document.getElementById('aircraft-detail-tab').style.display='inline-block';
 showView('aircraft-detail');
 await reloadAircraftDetail()
}
async function reloadAircraftDetail(){
 if(!selectedAircraft)return;
 let hours=document.getElementById('detail-hours').value;
 try{
  selectedAircraftData=await fetch(`/api/aircraft/${selectedAircraft}/detail?hours=${hours}&limit=1500`).then(r=>r.json());
  await loadAdsbLol(false);
  await loadAirplanesLive(false);
  renderAircraftDetail();
  await loadPlanespottersPhoto(false)
 }catch(e){
  document.getElementById('detail-subtitle').textContent='Could not load aircraft detail.'
 }
}
function renderAircraftDetail(){
 let d=selectedAircraftData,a=d.aircraft||{},st=d.stats||{};
 document.getElementById('detail-title').textContent=(a.callsign?`${a.callsign} · `:'')+(a.icao||selectedAircraft);
 document.getElementById('detail-subtitle').textContent=`Last seen ${a.last_epoch?age(a.last_epoch):'—'} · ${a.msgtype||'No recent message type'}`;
 let chips=[];
 (d.callsigns||[]).forEach(x=>chips.push(`<span class="chip">Callsign ${x}</span>`));
 (d.assigned_ids||[]).forEach(x=>chips.push(`<span class="chip">AC ID ${x}</span>`));
 (d.stations||[]).forEach(x=>chips.push(`<span class="chip">GS ${x}</span>`));if(a.registration)chips.push(`<span class="chip">Registration ${a.registration}</span>`);if(a.aircraft_type)chips.push(`<span class="chip">${a.aircraft_type}</span>`);if(a.operator)chips.push(`<span class="chip">${a.operator}</span>`);if(a.country)chips.push(`<span class="chip">${a.country}</span>`);
 document.getElementById('detail-chips').innerHTML=chips.join('')||'<span class="chip">No associations yet</span>';
 document.getElementById('detail-metrics').innerHTML=`
  <div class="metric"><span>Messages</span><b>${st.message_count??0}</b></div>
  <div class="metric"><span>Positions</span><b>${st.position_count??0}</b></div>
  <div class="metric"><span>Average SNR</span><b>${st.average_snr==null?'—':st.average_snr+' dB'}</b></div>
  <div class="metric"><span>Strongest signal</span><b>${st.strongest_signal==null?'—':st.strongest_signal+' dBFS'}</b></div>`;
 document.getElementById('detail-latest').innerHTML=`
  <div class="cardrow"><b>ICAO</b><span class="muted">Aircraft address</span><span>${a.icao||selectedAircraft}</span></div>
  <div class="cardrow"><b>Callsign</b><span class="muted">Most recent</span><span>${a.callsign||'—'}</span></div>
  <div class="cardrow"><b>Registration</b><span class="muted">Imported metadata</span><span>${a.registration||'—'}</span></div>
  <div class="cardrow"><b>Aircraft type</b><span class="muted">Imported metadata</span><span>${a.aircraft_type||'—'}</span></div>
  <div class="cardrow"><b>Operator</b><span class="muted">Imported metadata</span><span>${a.operator||'—'}</span></div>
  <div class="cardrow"><b>Frequency</b><span class="muted">Last channel</span><span>${fmtFreq(a.freq)}</span></div>
  <div class="cardrow"><b>Altitude</b><span class="muted">Last reported</span><span>${a.alt==null?'—':Math.round(a.alt).toLocaleString()+' ft'}</span></div>
  <div class="cardrow"><b>Position</b><span class="muted">Last valid coordinates</span><span>${a.lat==null?'—':Number(a.lat).toFixed(3)+', '+Number(a.lon).toFixed(3)}</span></div>`;
 let photo=document.getElementById('detail-photo'),credit=document.getElementById('detail-photo-credit');
 if(a.photo_src){
   photo.className='';
   photo.innerHTML=`<img class="aircraft-photo" src="${a.photo_src}" alt="Aircraft ${a.registration||a.icao}" onerror="this.parentElement.className='photo-placeholder';this.parentElement.textContent='Photograph could not be loaded.'">`;
   let creditText=a.photo_credit?`Photo: ${a.photo_credit}`:`Photo source: ${a.photo_source||'configured source'}`;
   credit.innerHTML=a.photo_link?`${creditText} · <a href="${a.photo_link}" target="_blank" rel="noopener">View source</a>`:creditText;
 }else{
   photo.className='photo-placeholder';photo.textContent='No aircraft photograph available.';credit.textContent='';
 }
 document.getElementById('aircraft-photo-url').value=a.photo_url||'';
 document.getElementById('aircraft-photo-credit-input').value=a.photo_credit||'';
 document.getElementById('aircraft-photo-link-input').value=a.photo_link||'';
 document.getElementById('external-registration').textContent=a.registration||'—';
 document.getElementById('external-icao').textContent=a.icao||selectedAircraft||'—';
 document.getElementById('external-type').textContent=a.aircraft_type||'—';
 document.getElementById('external-operator').textContent=a.operator||'—';
 let points=(d.track||[]).map(p=>[p.lat,p.lon]);
 if(detailTrack){detailTrack.remove();detailTrack=null}
 if(detailMarker){detailMarker.remove();detailMarker=null}
 if(points.length){
  detailTrack=L.polyline(points,{weight:3,opacity:.8}).addTo(detailMap);
  let last=d.track[d.track.length-1];
  detailMarker=L.marker([last.lat,last.lon],{icon:markerIcon()}).addTo(detailMap).bindPopup(`<b>${a.callsign||a.icao}</b><br>${new Date(last.ts).toLocaleString()}`);
  detailMap.fitBounds(detailTrack.getBounds().pad(.18))
 }else detailMap.setView([-25.5,134],3);
 let events=d.events||[];
 document.getElementById('detail-events').innerHTML=events.length?events.map(e=>`<div class="event"><div><b>${[e.frame_type,e.msgtype].filter(Boolean).join(' · ')}</b></div><div>${e.direction||'—'} · ${gsText(e)} · ${e.callsign||e.icao||'—'}</div><div class="eventtime">${new Date(e.ts).toLocaleString()} · ${fmtFreq(e.freq)} · ${fmtDb(e.snr)}</div></div>`).join(''):'<div class="empty">No logon, logoff or position events in this period.</div>';
 document.getElementById('detail-messages').innerHTML=(d.messages||[]).map(m=>`<tr class="${m.direction==='Uplink'?'uplink':m.direction==='Downlink'?'downlink':''}"><td>${new Date(m.ts).toLocaleString()}</td><td>${m.direction||'—'}</td><td>${[m.frame_type,m.msgtype].filter(Boolean).join(' · ')||'HFDL'}</td><td>${gsText(m)}</td><td>${m.callsign||'—'}</td><td>${m.assigned_ac_id||'—'}</td><td>${fmtFreq(m.freq)}</td><td>${fmtDb(m.snr)}</td><td><button class="action" onclick="rawMsg(${m.id})">JSON</button></td></tr>`).join('')
}
function exportAircraftMessages(){
 if(!selectedAircraftData)return;
 let blob=new Blob([JSON.stringify(selectedAircraftData,null,2)],{type:'application/json'});
 let url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download=`hfdl-aircraft-${selectedAircraft}.json`;a.click();URL.revokeObjectURL(url)
}

async function loadAnalytics(){
 let hours=document.getElementById('analytics-hours').value;
 let data=await fetch('/api/analytics?hours='+hours).then(r=>r.json());
 let labels=data.series.map(p=>new Date(p.epoch*1000).toLocaleString([],hours<=24?{hour:'2-digit',minute:'2-digit'}:{month:'short',day:'numeric',hour:'2-digit'}));
 let counts=data.series.map(p=>p.count);
 let snrs=data.series.map(p=>p.avg_snr);
 if(rateChart)rateChart.destroy();
 rateChart=new Chart(document.getElementById('rate-chart'),{
  type:'line',
  data:{labels,datasets:[{label:'Messages per interval',data:counts,borderColor:'#78a9ff',backgroundColor:'rgba(120,169,255,.14)',fill:true,tension:.22,pointRadius:0}]},
  options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#9ba9c7'}}},scales:{x:{ticks:{color:'#9ba9c7',maxTicksLimit:12},grid:{color:'rgba(43,55,88,.45)'}},y:{beginAtZero:true,ticks:{color:'#9ba9c7'},grid:{color:'rgba(43,55,88,.45)'}}}}
 });
 if(snrChart)snrChart.destroy();
 snrChart=new Chart(document.getElementById('snr-chart'),{
  type:'line',
  data:{labels,datasets:[{label:'Average SNR (dB)',data:snrs,borderColor:'#9ee6cf',backgroundColor:'rgba(158,230,207,.10)',fill:true,tension:.22,pointRadius:0,spanGaps:true}]},
  options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#9ba9c7'}}},scales:{x:{ticks:{color:'#9ba9c7',maxTicksLimit:10},grid:{color:'rgba(43,55,88,.45)'}},y:{ticks:{color:'#9ba9c7'},grid:{color:'rgba(43,55,88,.45)'}}}}
 });
 document.getElementById('frequency-performance').innerHTML=(data.frequency_stats||[]).map(f=>`<tr><td>${f.frequency} kHz</td><td>${f.count}</td><td>${f.avg_snr==null?'—':f.avg_snr+' dB'}</td><td>${f.strongest_signal==null?'—':f.strongest_signal+' dBFS'}</td></tr>`).join('')||'<tr><td colspan="4">No frequency records.</td></tr>';
 document.getElementById('top-aircraft').innerHTML=(data.top_aircraft||[]).map((a,i)=>`<div class="cardrow clickable" onclick="openAircraftDetailFromName('${String(a.aircraft).replaceAll("'","")}')"><b>${i+1}</b><span>${a.aircraft}</span><span>${a.count}</span></div>`).join('')||'<div class="empty">No aircraft records.</div>';
 document.getElementById('gap-list').innerHTML=(data.gaps||[]).map(g=>`<div class="cardrow"><b>${Math.round(g.seconds/60)} min</b><span class="muted">${new Date(g.start*1000).toLocaleString()}</span><span>${new Date(g.end*1000).toLocaleTimeString()}</span></div>`).join('')||'<div class="empty">No reception gaps in this period.</div>'
}
function openAircraftDetailFromName(value){
 let match=latestAircraft.find(a=>a.icao===value||a.callsign===value);
 if(match)openAircraftDetail(match.icao)
}
function humanBytes(bytes){
 if(bytes==null)return'—';let units=['B','KB','MB','GB'],i=0,n=Number(bytes);
 while(n>=1024&&i<units.length-1){n/=1024;i++}
 return n.toFixed(i?1:0)+' '+units[i]
}
async function loadDatabaseStatus(){
 let d=await fetch('/api/database').then(r=>r.json());
 document.getElementById('db-status').innerHTML=`${humanBytes(d.size_bytes)} · ${Number(d.messages).toLocaleString()} messages · ${Number(d.aircraft).toLocaleString()} aircraft · ${Number(d.legacy_messages).toLocaleString()} legacy rows`;
}
function downloadBackup(){location.href='/api/database/backup'}
async function purgeLegacy(){
 if(!confirm('Delete all legacy dumphfdl rows? Download a backup first.'))return;
 let r=await fetch('/api/database/purge-legacy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true})});
 let d=await r.json();alert(d.ok?`Deleted ${d.deleted} legacy rows.`:(d.error||'Operation failed'));await refresh();await loadDatabaseStatus()
}
async function purgeOlder(){
 let days=Number(document.getElementById('retention-days').value);
 if(!confirm(`Delete messages older than ${days} days? Download a backup first.`))return;
 let r=await fetch('/api/database/purge-older',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({days,confirm:true})});
 let d=await r.json();alert(d.ok?`Deleted ${d.deleted} old messages.`:(d.error||'Operation failed'));await refresh();await loadDatabaseStatus()
}

async function loadAlerts(){
 let d=await fetch('/api/alerts').then(r=>r.json());
 document.getElementById('alert-rules').innerHTML=(d.rules||[]).map(r=>`<div class="cardrow"><b>${r.match_type.toUpperCase()}</b><span>${r.pattern} · ${r.event_type}</span><button class="action" onclick="deleteAlert(${r.id})">Delete</button></div>`).join('')||'<div class="empty">No alert rules.</div>';
 document.getElementById('alert-hits').innerHTML=(d.hits||[]).map(h=>`<div class="cardrow alert-hit"><b>${h.callsign||h.icao||'Match'}</b><span>${h.msgtype||h.details}</span><span>${new Date(h.ts).toLocaleString()}</span></div>`).join('')||'<div class="empty">No alert hits.</div>'
}
async function createAlert(){
 let match_type=document.getElementById('alert-match').value,pattern=document.getElementById('alert-pattern').value.trim(),event_type=document.getElementById('alert-event').value;
 if(!pattern){alert('Enter an ICAO address or callsign pattern.');return}
 let r=await fetch('/api/alerts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({match_type,pattern,event_type})});let d=await r.json();
 if(!d.ok){alert(d.error||'Could not create alert');return}document.getElementById('alert-pattern').value='';loadAlerts()
}
async function deleteAlert(id){if(!confirm('Delete this alert rule?'))return;await fetch('/api/alerts/'+id,{method:'DELETE'});loadAlerts()}
async function requestNotifications(){if(!('Notification'in window)){alert('Browser notifications are not supported.');return}let p=await Notification.requestPermission();alert('Notification permission: '+p)}
function showAlert(hit){
 let title='HFDL alert: '+(hit.callsign||hit.icao||'aircraft');
 let body=hit.details||hit.msgtype||'Alert matched';
 if('Notification'in window&&Notification.permission==='granted')new Notification(title,{body});
 loadAlerts()
}

async function loadEnrichmentSettings(){
 let d=await fetch('/api/enrichment/settings').then(r=>r.json());
 if(document.getElementById('metadata-mode'))document.getElementById('metadata-mode').value=d.metadata_mode||'local';
 if(document.getElementById('metadata-url'))document.getElementById('metadata-url').value=d.metadata_url||'';
 if(document.getElementById('photo-mode'))document.getElementById('photo-mode').value=d.photo_mode||'local_first';
 if(document.getElementById('overwrite-manual'))document.getElementById('overwrite-manual').value=d.overwrite_manual||'no';
 if(document.getElementById('photo-lookup'))document.getElementById('photo-lookup').value=d.photo_lookup||'manual';
}
async function saveEnrichmentSettings(){
 let payload={
  metadata_mode:document.getElementById('metadata-mode').value,
  metadata_url:document.getElementById('metadata-url').value.trim(),
  photo_mode:document.getElementById('photo-mode').value,
  overwrite_manual:document.getElementById('overwrite-manual').value,
  photo_lookup:document.getElementById('photo-lookup').value
 };
 let r=await fetch('/api/enrichment/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 let d=await r.json();alert(d.ok?'Aircraft enrichment settings saved.':(d.error||'Could not save settings.'));
}
function useOpenSkyUrl(){
 document.getElementById('metadata-url').value='https://opensky-network.org/datasets/metadata/aircraftDatabase.csv';
}
async function downloadMetadata(){
 let url=document.getElementById('metadata-url').value.trim();
 if(!url){alert('Enter a direct CSV URL first.');return}
 document.getElementById('metadata-download-status').textContent='Downloading and importing; a large OpenSky file may take several minutes…';
 let r=await fetch('/api/metadata/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
 let d=await r.json();
 document.getElementById('metadata-download-status').textContent=d.ok?`${d.source||'Internet CSV'}: imported ${d.imported} rows; skipped ${d.skipped}.`:(d.error||'Download failed.');
 await loadMetadataStatus();await refresh()
}



function secondsLabel(value){
 if(value==null||Number.isNaN(Number(value)))return'—';
 let s=Math.max(0,Number(value));
 if(s<60)return`${Math.round(s)} sec`;
 if(s<3600)return`${Math.round(s/60)} min`;
 return`${(s/3600).toFixed(1)} hr`;
}
function fmtExternalAltitude(a){
 if(a==null)return'—';
 if(String(a).toLowerCase()==='ground')return'Ground';
 return`${Math.round(Number(a)).toLocaleString()} ft`;
}

function resetAdsbLol(message='Not loaded',badge='Not loaded',warning=''){
 document.getElementById('lol-source').textContent=badge;
 document.getElementById('lol-status').textContent=message;
 for(let id of ['lol-position','lol-position-age','lol-altitude','lol-speed','lol-track',
                 'lol-vertical-rate','lol-squawk','lol-emergency','lol-flight',
                 'lol-identity','lol-seen','lol-integrity']){
  document.getElementById(id).textContent='—';
 }
 let box=document.getElementById('lol-warning');
 if(warning){
  box.textContent=warning;
  box.style.display='block';
 }else{
  box.textContent='';
  box.style.display='none';
 }
}
function formatVerticalRate(a){
 let value=a.geom_rate;
 let label='geometric';
 if(value==null){value=a.baro_rate;label='barometric'}
 if(value==null)return'—';
 let n=Number(value);
 return`${n>0?'+':''}${Math.round(n).toLocaleString()} ft/min ${label}`;
}
async function loadAdsbLol(force=false){
 if(!selectedAircraft){resetAdsbLol('Select an aircraft first.');return}
 resetAdsbLol('Loading free ADSB.lol correlation data…','Loading');
 try{
  let url=`/api/external/adsb-lol/${encodeURIComponent(selectedAircraft)}${force?'?refresh=true':''}`;
  let response=await fetch(url);
  let data=await response.json();
  if(!response.ok||!data.ok){
   let reason=String(data.reason||'unknown');
   let badge={
    not_found:'No current record',
    invalid_icao:'Invalid ICAO',
    disabled:'Disabled',
    rate_limited:'Rate limited',
    timeout:'API timeout',
    unavailable:'API unavailable'
   }[reason]||'API error';
   let warning='';
   if(reason==='not_found'){
    warning='The aircraft may be outside current ADS-B/MLAT coverage or its recent external record may have expired.';
   }else if(reason==='rate_limited'){
    warning='Wait briefly before refreshing again.';
   }else if(reason==='timeout'||reason==='unavailable'){
    warning='The external service is unavailable; local HFDL reception and stored data are unaffected.';
   }
   resetAdsbLol(data.error||'No ADSB.lol data is available.',badge,warning);
   return;
  }

  let a=data.aircraft||{};
  let source=String(a.type||'unknown').replaceAll('_',' ');
  document.getElementById('lol-source').textContent=source;
  document.getElementById('lol-status').textContent=
    `${data.cached?'Cached':'Fresh'} ADSB.lol result · API age ${secondsLabel(data.api_age_seconds)}`;

  let lat=a.lat,lon=a.lon;
  document.getElementById('lol-position').textContent=
    (lat==null||lon==null)?'—':`${Number(lat).toFixed(5)}, ${Number(lon).toFixed(5)}`;
  document.getElementById('lol-position-age').textContent=secondsLabel(a.seen_pos);
  document.getElementById('lol-altitude').textContent=
    `${fmtExternalAltitude(a.alt_baro)}${a.alt_geom==null?'':` · geometric ${fmtExternalAltitude(a.alt_geom)}`}`;
  document.getElementById('lol-speed').textContent=
    a.gs==null?'—':`${Number(a.gs).toFixed(1)} kt`;

  let track=a.track==null?'—':`${Number(a.track).toFixed(1)}° track`;
  let heading=a.true_heading!=null?`${Number(a.true_heading).toFixed(1)}° true heading`:
              (a.mag_heading!=null?`${Number(a.mag_heading).toFixed(1)}° magnetic heading`:'');
  document.getElementById('lol-track').textContent=heading?`${track} · ${heading}`:track;
  document.getElementById('lol-vertical-rate').textContent=formatVerticalRate(a);
  document.getElementById('lol-squawk').textContent=a.squawk||'—';
  document.getElementById('lol-emergency').textContent=a.emergency||'none';
  document.getElementById('lol-flight').textContent=(a.flight||'').trim()||'—';
  document.getElementById('lol-identity').textContent=[a.r,a.t].filter(Boolean).join(' · ')||'—';
  document.getElementById('lol-seen').textContent=secondsLabel(a.seen);

  let integrity=[];
  if(a.nic!=null)integrity.push(`NIC ${a.nic}`);
  if(a.nac_p!=null)integrity.push(`NACp ${a.nac_p}`);
  if(a.sil!=null)integrity.push(`SIL ${a.sil}`);
  if(a.version!=null)integrity.push(`ADS-B v${a.version}`);
  document.getElementById('lol-integrity').textContent=integrity.join(' · ')||'—';

  let emergency=String(a.emergency||'none').toLowerCase();
  let squawk=String(a.squawk||'');
  let critical=['general','minfuel','nordo','unlawful','downed'].includes(emergency)||
               ['7500','7600','7700'].includes(squawk);
  let warning=document.getElementById('lol-warning');
  if(critical){
   warning.style.display='block';
   warning.textContent=`External alert indication: emergency=${emergency}, squawk=${squawk||'unknown'}. Verify independently; this dashboard is not an operational safety system.`;
  }else{
   warning.style.display='none';
  }
 }catch(error){
  resetAdsbLol(
    'ADSB.lol could not be reached.',
    'API unavailable',
    'The external service is unavailable; local HFDL reception and stored data are unaffected.'
  );
 }
}
function openAdsbLolGlobe(){
 if(!selectedAircraft){alert('Select an aircraft first.');return}
 let code=String(selectedAircraft).trim().toLowerCase();
 window.open(`https://adsb.lol/?icao=${encodeURIComponent(code)}`,'_blank','noopener,noreferrer');
}

function resetAirplanesLive(message='Not loaded',badge='Not loaded',warning=''){
 document.getElementById('al-source').textContent=badge;
 document.getElementById('al-status').textContent=message;
 for(let id of ['al-position','al-position-age','al-altitude','al-speed','al-track','al-squawk','al-emergency','al-flight','al-identity','al-seen']){
  document.getElementById(id).textContent='—';
 }
 let box=document.getElementById('al-warning');
 if(warning){
  box.textContent=warning;
  box.style.display='block';
 }else{
  box.textContent='';
  box.style.display='none';
 }
}
async function loadAirplanesLive(force=false){
 if(!selectedAircraft){resetAirplanesLive('Select an aircraft first.');return}
 resetAirplanesLive('Loading external correlation data…');
 try{
  let url=`/api/external/airplanes-live/${encodeURIComponent(selectedAircraft)}${force?'?refresh=true':''}`;
  let response=await fetch(url);
  let data=await response.json();
  if(!response.ok||!data.ok){
   let reason=String(data.reason||'unknown');
   if(reason==='not_found'){
    resetAirplanesLive(
      data.error||'No current external record is available for this aircraft.',
      'No current record',
      'The HFDL aircraft may be outside current ADS-B, MLAT or ADS-C coverage, or its external record may have expired.'
    );
   }else if(reason==='invalid_icao'){
    resetAirplanesLive(data.error||'Invalid ICAO address.','Invalid ICAO');
   }else if(reason==='disabled'){
    resetAirplanesLive(data.error||'Integration disabled.','Disabled');
   }else if(reason==='rate_limited'){
    resetAirplanesLive(
      data.error||'Airplanes.live rate limit reached.',
      'Rate limited',
      'Wait briefly, then press Refresh external data.'
    );
   }else if(reason==='timeout'){
    resetAirplanesLive(
      data.error||'Airplanes.live timed out.',
      'API timeout',
      'The external service did not respond in time. Your locally decoded HFDL data is unaffected.'
    );
   }else{
    resetAirplanesLive(
      data.error||'Airplanes.live is currently unavailable.',
      'API unavailable',
      'The external service could not be reached. Your locally decoded HFDL data is unaffected.'
    );
   }
   return;
  }
  let a=data.aircraft||{};
  let source=String(a.type||'unknown').replaceAll('_',' ');
  document.getElementById('al-source').textContent=source;
  document.getElementById('al-status').textContent=
    `${data.cached?'Cached':'Fresh'} Airplanes.live result · API age ${secondsLabel(data.api_age_seconds)}`;
  let lat=a.lat,lon=a.lon;
  if((lat==null||lon==null)&&a.lastPosition){lat=a.lastPosition.lat;lon=a.lastPosition.lon}
  document.getElementById('al-position').textContent=
    (lat==null||lon==null)?'—':`${Number(lat).toFixed(5)}, ${Number(lon).toFixed(5)}`;
  let posAge=a.seen_pos;
  if((posAge==null||posAge==='')&&a.lastPosition)posAge=a.lastPosition.seen_pos;
  document.getElementById('al-position-age').textContent=secondsLabel(posAge);
  document.getElementById('al-altitude').textContent=
    `${fmtExternalAltitude(a.alt_baro)}${a.alt_geom==null?'':` · geometric ${fmtExternalAltitude(a.alt_geom)}`}`;
  document.getElementById('al-speed').textContent=
    a.gs==null?'—':`${Number(a.gs).toFixed(1)} kt`;
  let track=a.track==null?'—':`${Number(a.track).toFixed(1)}° track`;
  let heading=a.true_heading!=null?`${Number(a.true_heading).toFixed(1)}° true heading`:
              (a.mag_heading!=null?`${Number(a.mag_heading).toFixed(1)}° magnetic heading`:'');
  document.getElementById('al-track').textContent=heading?`${track} · ${heading}`:track;
  document.getElementById('al-squawk').textContent=a.squawk||'—';
  document.getElementById('al-emergency').textContent=a.emergency||'none';
  document.getElementById('al-flight').textContent=(a.flight||'').trim()||'—';
  document.getElementById('al-identity').textContent=
    [a.r,a.t].filter(Boolean).join(' · ')||'—';
  document.getElementById('al-seen').textContent=secondsLabel(a.seen);
  let emergency=String(a.emergency||'none').toLowerCase();
  let critical=['general','minfuel','nordo','unlawful','downed'].includes(emergency)||
               ['7500','7600','7700'].includes(String(a.squawk||''));
  let warning=document.getElementById('al-warning');
  if(critical){
   warning.style.display='block';
   warning.textContent=`External alert indication: emergency=${emergency}, squawk=${a.squawk||'unknown'}. Verify independently; this dashboard is not an operational safety system.`;
  }else{
   warning.style.display='none';
  }
 }catch(error){
  resetAirplanesLive('Airplanes.live could not be reached.');
 }
}
function openAirplanesLiveGlobe(){
 if(!selectedAircraft){alert('Select an aircraft first.');return}
 let code=String(selectedAircraft).trim().toLowerCase();
 window.open(`https://globe.airplanes.live/?icao=${encodeURIComponent(code)}`,'_blank','noopener,noreferrer');
}


async function loadPlanespottersPhoto(force=false){
 if(!selectedAircraft)return;
 let a=selectedAircraftData?.aircraft||{};
 let status=document.getElementById('planespotters-photo-status');

 // A manually configured or locally uploaded photograph always takes priority.
 if(a.photo_src&&!force){
  status.textContent='Using your configured photograph. Automatic Planespotters lookup was not substituted.';
  return;
 }

 status.textContent='Looking for an authorised Planespotters thumbnail…';
 try{
  let url=`/api/external/planespotters-photo/${encodeURIComponent(selectedAircraft)}${force?'?refresh=true':''}`;
  let response=await fetch(url);
  let data=await response.json();

  if(!response.ok||!data.ok){
   let message=data.error||'No Planespotters photograph is currently available.';
   status.textContent=message;
   if(force&&a.photo_src)renderAircraftDetail();
   return;
  }

  let photo=data.photo||{};
  if(!photo.thumbnail_url){
   status.textContent='Planespotters returned no usable thumbnail.';
   return;
  }

  let holder=document.getElementById('detail-photo');
  let credit=document.getElementById('detail-photo-credit');
  holder.className='';
  holder.innerHTML=`<a href="${photo.link}" target="_blank" rel="noopener noreferrer">
    <img class="aircraft-photo" src="${photo.thumbnail_url}"
      alt="Aircraft ${a.registration||a.icao||selectedAircraft}"
      referrerpolicy="no-referrer-when-downgrade"
      onerror="this.parentElement.parentElement.className='photo-placeholder';this.parentElement.parentElement.textContent='Planespotters thumbnail could not be loaded.'">
  </a>`;
  let photographer=photo.photographer||'Unknown photographer';
  credit.innerHTML=`© ${photographer} · Photo supplied by
    <a href="${photo.link}" target="_blank" rel="noopener noreferrer">Planespotters.net</a>
    · <a href="${photo.link}" target="_blank" rel="noopener noreferrer">Open original photograph</a>`;
  status.textContent=`${data.cached?'Cached':'Fresh'} Planespotters Photo API result. Click the thumbnail to open the original page.`;
 }catch(error){
  status.textContent='Planespotters Photo API could not be reached. Your HFDL data is unaffected.';
 }
}

function openPlanespotters(){
 if(!selectedAircraft){alert('Select an aircraft first.');return}
 let code=String(selectedAircraft).trim().toUpperCase();
 window.open(`https://www.planespotters.net/hex/${encodeURIComponent(code)}`,'_blank','noopener,noreferrer');
}
function searchAircraftGoogle(){
 if(!selectedAircraft){alert('Select an aircraft first.');return}
 let aircraft=latestAircraft.find(a=>a.icao===selectedAircraft);
 let registration=aircraft?.registration||'';
 let query=registration?`${registration} aircraft ${selectedAircraft}`:`aircraft ICAO ${selectedAircraft}`;
 window.open(`https://www.google.com/search?q=${encodeURIComponent(query)}`,'_blank','noopener,noreferrer');
}
async function saveAircraftPhotoUrl(){
 if(!selectedAircraft){alert('Select an aircraft first.');return}
 let photo_url=document.getElementById('aircraft-photo-url').value.trim();
 let photo_credit=document.getElementById('aircraft-photo-credit-input').value.trim();
 let photo_link=document.getElementById('aircraft-photo-link-input').value.trim();
 if(!photo_url){alert('Enter a direct HTTP or HTTPS image URL.');return}
 let r=await fetch(`/api/photos/url/${encodeURIComponent(selectedAircraft)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({photo_url,photo_credit,photo_link})});
 let d=await r.json();
 if(!d.ok){alert(d.error||'Could not save the photo URL.');return}
 await reloadAircraftDetail()
}
async function uploadAircraftPhoto(){
 if(!selectedAircraft){alert('Select an aircraft first.');return}
 let input=document.getElementById('aircraft-photo-file');
 if(!input.files.length){alert('Choose a JPEG, PNG or WebP image first.');return}
 let file=input.files[0];
 let url=`/api/photos/upload?icao_code=${encodeURIComponent(selectedAircraft)}&filename=${encodeURIComponent(file.name)}`;
 let r=await fetch(url,{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream'},body:file});
 let d=await r.json();
 if(!d.ok){alert(d.error||'Photo upload failed.');return}
 input.value='';await reloadAircraftDetail()
}
async function importMetadata(){
 let input=document.getElementById('metadata-file');if(!input.files.length){alert('Choose a CSV file first.');return}
 let text=await input.files[0].text();let r=await fetch('/api/metadata/import',{method:'POST',headers:{'Content-Type':'text/plain'},body:text});let d=await r.json();
 document.getElementById('metadata-status').textContent=d.ok?`Imported ${d.imported} rows; skipped ${d.skipped}.`:(d.error||'Import failed');await refresh()
}
async function loadMetadataStatus(){let d=await fetch('/api/metadata/status').then(r=>r.json());let el=document.getElementById('metadata-status');if(el)el.textContent=`${d.count} aircraft metadata records loaded.`}
function ws(){
 let w=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`);
 w.onopen=()=>w.send('ready');w.onmessage=e=>{let p=JSON.parse(e.data);if(p.event==='message')setTimeout(refresh,180);if(p.event==='alert')showAlert(p.data)};
 w.onclose=()=>{document.getElementById('dot').className='dot';document.getElementById('state').textContent='Reconnecting';setTimeout(ws,2000)}
}
['qicao','qcall','qtype'].forEach(id=>document.getElementById(id).addEventListener('keydown',e=>{if(e.key==='Enter')refresh()}));
initMaps();applySettings();showView(localStorage.getItem('hfdl-view')||'overview');refresh();loadMetadataStatus();loadEnrichmentSettings();ws();setInterval(refresh,30000);
</script>
</body></html>'''

@app.get('/',response_class=HTMLResponse)
def root():return HTML
@app.get('/health')
def health():return {'status':'ok','udp_bind_ip':UDP_BIND,'udp_port':UDP,'web_bind_ip':WEB_BIND,'web_port':WEB,'total':counters['total'],'invalid':counters['invalid'],'last':counters['last']}
@app.get('/api/messages')
def messages(limit:int=Query(100,ge=1,le=1000),icao_filter:str|None=Query(None,alias='icao'),callsign:str|None=None,direction:str|None=None,frame_type:str|None=None,msgtype:str|None=None):
    sql='SELECT id,ts,epoch,freq,signal,noise,snr,bitrate,direction,msgtype,icao,callsign,lat,lon,alt,gs,frame_type,src_gs,dst_gs,assigned_ac_id,freq_skew,slot FROM messages'
    clauses=[]; params=[]
    for column,value in [('icao',icao_filter),('callsign',callsign),('direction',direction),('frame_type',frame_type),('msgtype',msgtype)]:
        if value:
            clauses.append(f'UPPER(COALESCE({column},"")) LIKE UPPER(?)'); params.append('%'+value+'%')
    if clauses: sql+=' WHERE '+' AND '.join(clauses)
    sql+=' ORDER BY epoch DESC LIMIT ?'; params.append(limit)
    with db() as c:return [dict(r) for r in c.execute(sql,params)]

@app.get('/api/messages/{message_id}/raw')
def message_raw(message_id:int):
    with db() as c:
        r=c.execute('SELECT raw FROM messages WHERE id=?',(message_id,)).fetchone()
    if not r:return {'error':'not found'}
    return json.loads(r['raw'])

@app.get('/api/aircraft')
def aircraft():
    cutoff=time.time()-21600
    with db() as c:return [dict(r) for r in c.execute('SELECT a.*,m.registration,m.aircraft_type,m.operator,m.country,m.photo_url,m.photo_credit,m.photo_link,m.photo_checked_at,m.metadata_source FROM aircraft a LEFT JOIN aircraft_metadata m ON m.icao=a.icao WHERE a.last_epoch>=? ORDER BY a.last_epoch DESC',(cutoff,))]
@app.get('/api/stats')
def stats():
    cutoff=time.time()-21600
    with db() as c:rows=c.execute('SELECT freq,icao,snr FROM messages WHERE epoch>=?',(cutoff,)).fetchall()
    freqs=Counter(f'{r["freq"]:.1f}' for r in rows if r['freq'] is not None); snrs=[r['snr'] for r in rows if r['snr'] is not None]
    return {'total':len(rows),'aircraft':len({r['icao'] for r in rows if r['icao']}),'avg_snr':round(sum(snrs)/len(snrs),1) if snrs else None,'freqs':dict(freqs.most_common())}

@app.get('/api/ground-stations')
def ground_stations():
    cutoff=time.time()-21600
    with db() as c:
        rows=c.execute('SELECT COALESCE(src_gs,dst_gs,gs) AS station,direction,MAX(epoch) AS last_epoch,COUNT(*) AS n FROM messages WHERE epoch>=? AND COALESCE(src_gs,dst_gs,gs) IS NOT NULL GROUP BY station,direction',(cutoff,)).fetchall()
    stations={}
    for r in rows:
        key=str(r['station']); item=stations.setdefault(key,{'gs':key,'uplink':0,'downlink':0,'last_epoch':0})
        if r['direction']=='Uplink': item['uplink']+=r['n']
        elif r['direction']=='Downlink': item['downlink']+=r['n']
        item['last_epoch']=max(item['last_epoch'],r['last_epoch'] or 0)
    return sorted(stations.values(),key=lambda x:x['last_epoch'],reverse=True)

@app.get('/api/export')
def export_messages(format:str='csv',limit:int=Query(1000,ge=1,le=10000),icao_filter:str|None=Query(None,alias='icao'),callsign:str|None=None,direction:str|None=None,frame_type:str|None=None,msgtype:str|None=None):
    sql='SELECT id,ts,freq,direction,frame_type,msgtype,src_gs,dst_gs,icao,callsign,assigned_ac_id,signal,noise,snr,lat,lon,alt FROM messages'
    clauses=[]; params=[]
    for column,value in [('icao',icao_filter),('callsign',callsign),('direction',direction),('frame_type',frame_type),('msgtype',msgtype)]:
        if value:
            clauses.append(f'UPPER(COALESCE({column},"")) LIKE UPPER(?)'); params.append('%'+value+'%')
    if clauses: sql+=' WHERE '+' AND '.join(clauses)
    sql+=' ORDER BY epoch DESC LIMIT ?'; params.append(limit)
    with db() as c: rows=[dict(r) for r in c.execute(sql,params)]
    if format.lower()=='json': return JSONResponse(rows,headers={'Content-Disposition':'attachment; filename=hfdl-messages.json'})
    out=io.StringIO(); fields=list(rows[0].keys()) if rows else ['id','ts','freq','direction','frame_type','msgtype','src_gs','dst_gs','icao','callsign','assigned_ac_id','signal','noise','snr','lat','lon','alt']
    writer=csv.DictWriter(out,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=hfdl-messages.csv'})




def normalise_adsb_lol_aircraft(raw:dict[str,Any])->dict[str,Any]:
    allowed={
        'hex','r','t','dbFlags','type','flight','alt_baro','alt_geom','gs','ias','tas','mach',
        'track','track_rate','roll','mag_heading','true_heading','baro_rate','geom_rate',
        'squawk','emergency','category','nav_qnh','nav_altitude_mcp','nav_altitude_fms',
        'nav_heading','nav_modes','lat','lon','nic','rc','seen_pos','version','nic_baro',
        'nac_p','nac_v','sil','sil_type','gva','sda','mlat','tisb','messages','seen','rssi',
        'alert','spi','wd','ws','oat','tat','rr_lat','rr_lon','acas_ra','gpsOkBefore'
    }
    return {k:v for k,v in raw.items() if k in allowed}

async def fetch_adsb_lol(icao_code:str,refresh:bool=False)->dict[str,Any]:
    global adsb_lol_last_request
    code=icao(icao_code)
    if not code:
        return {'ok':False,'reason':'invalid_icao','error':'A valid six-character ICAO hex address is required.'}
    code=code.lower()
    now=time.time()
    cached=adsb_lol_cache.get(code)
    if cached and not refresh and now-cached[0] < ADSB_LOL_CACHE_SECONDS:
        result=dict(cached[1]); result['cached']=True; return result
    if not ADSB_LOL_ENABLED:
        return {'ok':False,'reason':'disabled','error':'ADSB.lol integration is disabled.'}

    async with adsb_lol_lock:
        now=time.time()
        cached=adsb_lol_cache.get(code)
        if cached and not refresh and now-cached[0] < ADSB_LOL_CACHE_SECONDS:
            result=dict(cached[1]); result['cached']=True; return result

        # Be conservative with the free public service.
        wait=max(0.0,1.05-(now-adsb_lol_last_request))
        if wait:
            await asyncio.sleep(wait)

        endpoint=f'https://api.adsb.lol/v2/icao/{urllib.parse.quote(code)}'
        try:
            def do_request():
                req=urllib.request.Request(
                    endpoint,
                    headers={
                        'User-Agent':'HFDL-Operations-Dashboard/10.6 (local non-commercial aircraft correlation)',
                        'Accept':'application/json',
                        'Accept-Encoding':'identity'
                    }
                )
                with urllib.request.urlopen(req,timeout=12) as response:
                    return json.loads(response.read().decode('utf-8','replace'))
            payload=await asyncio.to_thread(do_request)
            adsb_lol_last_request=time.time()
        except urllib.error.HTTPError as exc:
            adsb_lol_last_request=time.time()
            if exc.code==404:
                return {'ok':False,'reason':'not_found','error':'No current ADSB.lol record is available for this ICAO address.'}
            if exc.code==429:
                return {'ok':False,'reason':'rate_limited','error':'ADSB.lol is temporarily rate limited.'}
            return {'ok':False,'reason':'http_error','error':f'ADSB.lol returned HTTP {exc.code}.'}
        except (TimeoutError,urllib.error.URLError) as exc:
            adsb_lol_last_request=time.time()
            reason='timeout' if isinstance(getattr(exc,'reason',None),TimeoutError) else 'unavailable'
            return {
                'ok':False,
                'reason':reason,
                'error':'ADSB.lol did not respond in time.' if reason=='timeout' else 'ADSB.lol is currently unavailable.'
            }
        except Exception:
            adsb_lol_last_request=time.time()
            return {'ok':False,'reason':'unavailable','error':'ADSB.lol could not be reached.'}

        if not isinstance(payload,dict):
            return {'ok':False,'reason':'invalid_response','error':'ADSB.lol returned an invalid response.'}

        aircraft_list=payload.get('ac')
        if not isinstance(aircraft_list,list):
            aircraft_list=payload.get('aircraft')
        if not isinstance(aircraft_list,list):
            aircraft_list=[]

        match=None
        for item in aircraft_list:
            if not isinstance(item,dict):
                continue
            item_hex=str(item.get('hex','')).lstrip('~').lower()
            if item_hex==code:
                match=item
                break
        if match is None and aircraft_list and isinstance(aircraft_list[0],dict):
            match=aircraft_list[0]
        if match is None:
            result={'ok':False,'reason':'not_found','error':'No current ADSB.lol record is available for this ICAO address.'}
            adsb_lol_cache[code]=(time.time(),result)
            return result

        api_now=payload.get('now')
        try:
            api_age=max(0.0,time.time()-float(api_now)/1000.0) if float(api_now)>1e12 else max(0.0,time.time()-float(api_now))
        except (TypeError,ValueError):
            api_age=None

        result={
            'ok':True,
            'cached':False,
            'icao':code.upper(),
            'provider':'ADSB.lol',
            'api_age_seconds':api_age,
            'aircraft':normalise_adsb_lol_aircraft(match),
            'notice':'Free open external data. Informational only; not for navigation or operational safety.'
        }
        adsb_lol_cache[code]=(time.time(),result)
        return result

@app.get('/api/external/adsb-lol/{icao_code}')
async def adsb_lol_aircraft(icao_code:str,refresh:bool=False):
    result=await fetch_adsb_lol(icao_code,refresh=refresh)
    if result.get('ok'):
        status=200
    else:
        status={
            'invalid_icao':400,
            'disabled':503,
            'rate_limited':429,
            'timeout':504,
            'unavailable':503,
            'http_error':502,
            'invalid_response':502,
            'not_found':404
        }.get(result.get('reason'),502)
    return JSONResponse(result,status_code=status)


def normalise_airplanes_live_aircraft(raw:dict[str,Any])->dict[str,Any]:
    allowed={
        'hex','r','t','dbFlags','type','flight','alt_baro','alt_geom','gs','ias','tas','mach',
        'track','track_rate','roll','mag_heading','true_heading','baro_rate','geom_rate',
        'squawk','emergency','category','nav_qnh','nav_altitude_mcp','nav_altitude_fms',
        'nav_heading','nav_modes','lat','lon','nic','rc','seen_pos','version','nic_baro',
        'nac_p','nac_v','sil','sil_type','gva','sda','mlat','tisb','messages','seen','rssi',
        'alert','spi','wd','ws','oat','tat','lastPosition','rr_lat','rr_lon','acas_ra',
        'gpsOkBefore'
    }
    return {k:v for k,v in raw.items() if k in allowed}

async def fetch_airplanes_live(icao_code:str,refresh:bool=False)->dict[str,Any]:
    global airplanes_live_last_request
    code=icao(icao_code)
    if not code:
        return {'ok':False,'reason':'invalid_icao','error':'A valid six-character ICAO hex address is required.'}
    code=code.lower()
    now=time.time()
    cached=airplanes_live_cache.get(code)
    if cached and not refresh and now-cached[0] < AIRPLANES_LIVE_CACHE_SECONDS:
        result=dict(cached[1])
        result['cached']=True
        return result
    if not AIRPLANES_LIVE_ENABLED:
        return {'ok':False,'reason':'disabled','error':'Airplanes.live integration is disabled.'}

    async with airplanes_live_lock:
        now=time.time()
        cached=airplanes_live_cache.get(code)
        if cached and not refresh and now-cached[0] < AIRPLANES_LIVE_CACHE_SECONDS:
            result=dict(cached[1]); result['cached']=True; return result

        wait=max(0.0,1.05-(now-airplanes_live_last_request))
        if wait:
            await asyncio.sleep(wait)

        endpoints=[
            f'https://api.airplanes.live/v2/hex/{urllib.parse.quote(code)}',
            f'https://api.airplanes.live/v2/icao/{urllib.parse.quote(code)}'
        ]
        last_error={'ok':False,'reason':'not_found','error':'No current Airplanes.live record is available for this ICAO address.'}
        payload=None
        for endpoint in endpoints:
            try:
                def do_request():
                    req=urllib.request.Request(
                        endpoint,
                        headers={
                            'User-Agent':'HFDL-Operations-Dashboard/10.4 (+local non-commercial aircraft correlation)',
                            'Accept':'application/json'
                        }
                    )
                    with urllib.request.urlopen(req,timeout=12) as response:
                        return json.loads(response.read().decode('utf-8','replace'))
                payload=await asyncio.to_thread(do_request)
                airplanes_live_last_request=time.time()
                if isinstance(payload,dict) and isinstance(payload.get('aircraft'),list):
                    break
            except urllib.error.HTTPError as exc:
                airplanes_live_last_request=time.time()
                if exc.code == 429:
                    last_error={'ok':False,'reason':'rate_limited','error':'Airplanes.live rate limit reached.'}
                elif exc.code == 404:
                    last_error={'ok':False,'reason':'not_found','error':'No current Airplanes.live record is available for this ICAO address.'}
                else:
                    last_error={'ok':False,'reason':'http_error','error':f'Airplanes.live returned HTTP {exc.code}.'}
                payload=None
            except (TimeoutError, urllib.error.URLError) as exc:
                airplanes_live_last_request=time.time()
                reason='timeout' if isinstance(getattr(exc,'reason',None), TimeoutError) else 'unavailable'
                last_error={'ok':False,'reason':reason,'error':'Airplanes.live could not be reached in time.' if reason=='timeout' else 'Airplanes.live is currently unavailable.'}
                payload=None
            except Exception:
                airplanes_live_last_request=time.time()
                last_error={'ok':False,'reason':'unavailable','error':'Airplanes.live is currently unavailable.'}
                payload=None

        if not isinstance(payload,dict):
            return last_error if isinstance(last_error,dict) else {'ok':False,'reason':'unavailable','error':str(last_error)}

        aircraft_list=payload.get('aircraft') or []
        match=None
        for item in aircraft_list:
            if not isinstance(item,dict):
                continue
            item_hex=str(item.get('hex','')).lstrip('~').lower()
            if item_hex==code:
                match=item
                break
        if match is None and aircraft_list and isinstance(aircraft_list[0],dict):
            match=aircraft_list[0]
        if match is None:
            return {'ok':False,'reason':'not_found','error':'No current Airplanes.live record is available for this ICAO address.'}

        api_now=payload.get('now')
        try:
            api_age=max(0.0,time.time()-float(api_now))
        except (TypeError,ValueError):
            api_age=None

        result={
            'ok':True,
            'cached':False,
            'icao':code.upper(),
            'provider':'Airplanes.live',
            'api_age_seconds':api_age,
            'aircraft':normalise_airplanes_live_aircraft(match),
            'notice':'External non-commercial data; no uptime guarantee. Not for navigation or operational safety.'
        }
        airplanes_live_cache[code]=(time.time(),result)
        return result


def safe_external_https_url(value:Any,allowed_hosts:set[str])->str|None:
    if not isinstance(value,str):
        return None
    try:
        parsed=urllib.parse.urlparse(value.strip())
    except Exception:
        return None
    host=(parsed.hostname or '').lower()
    if parsed.scheme!='https' or not any(host==h or host.endswith('.'+h) for h in allowed_hosts):
        return None
    return value.strip()

async def fetch_planespotters_photo(icao_code:str,refresh:bool=False)->dict[str,Any]:
    global planespotters_photo_last_request
    code=icao(icao_code)
    if not code:
        return {'ok':False,'reason':'invalid_icao','error':'A valid six-character ICAO hex address is required.'}
    code=code.lower()
    now=time.time()
    cached=planespotters_photo_cache.get(code)
    if cached and not refresh and now-cached[0] < PLANESPOTTERS_PHOTO_CACHE_SECONDS:
        result=dict(cached[1]); result['cached']=True; return result
    if not PLANESPOTTERS_PHOTO_ENABLED:
        return {'ok':False,'reason':'disabled','error':'Planespotters automatic photo lookup is disabled.'}

    async with planespotters_photo_lock:
        now=time.time()
        cached=planespotters_photo_cache.get(code)
        if cached and not refresh and now-cached[0] < PLANESPOTTERS_PHOTO_CACHE_SECONDS:
            result=dict(cached[1]); result['cached']=True; return result

        wait=max(0.0,1.05-(now-planespotters_photo_last_request))
        if wait:
            await asyncio.sleep(wait)

        endpoint=f'https://api.planespotters.net/pub/photos/hex/{urllib.parse.quote(code)}'
        try:
            def do_request():
                req=urllib.request.Request(
                    endpoint,
                    headers={
                        'User-Agent':'HFDL-Operations-Dashboard/10.5 (non-commercial local aircraft display)',
                        'Accept':'application/json'
                    }
                )
                with urllib.request.urlopen(req,timeout=12) as response:
                    return json.loads(response.read().decode('utf-8','replace'))
            payload=await asyncio.to_thread(do_request)
            planespotters_photo_last_request=time.time()
        except urllib.error.HTTPError as exc:
            planespotters_photo_last_request=time.time()
            if exc.code==404:
                return {'ok':False,'reason':'not_found','error':'No Planespotters photograph is available for this ICAO address.'}
            if exc.code==429:
                return {'ok':False,'reason':'rate_limited','error':'Planespotters photo lookup is temporarily rate limited.'}
            return {'ok':False,'reason':'http_error','error':f'Planespotters returned HTTP {exc.code}.'}
        except (TimeoutError,urllib.error.URLError):
            planespotters_photo_last_request=time.time()
            return {'ok':False,'reason':'unavailable','error':'Planespotters Photo API is currently unavailable.'}
        except Exception:
            planespotters_photo_last_request=time.time()
            return {'ok':False,'reason':'unavailable','error':'Planespotters Photo API could not be reached.'}

        photos=payload.get('photos') if isinstance(payload,dict) else None
        if not isinstance(photos,list) or not photos:
            result={'ok':False,'reason':'not_found','error':'No Planespotters photograph is available for this ICAO address.'}
            planespotters_photo_cache[code]=(time.time(),result)
            return result

        item=next((p for p in photos if isinstance(p,dict)),None)
        if not item:
            return {'ok':False,'reason':'not_found','error':'No usable Planespotters photograph was returned.'}

        thumbnail=item.get('thumbnail') if isinstance(item.get('thumbnail'),dict) else {}
        thumbnail_url=safe_external_https_url(
            thumbnail.get('src'),
            {'planespotters.net','cdn.planespotters.net'}
        )
        link=safe_external_https_url(item.get('link'),{'planespotters.net'})
        if not link and item.get('id'):
            photo_id=str(item.get('id')).strip()
            if photo_id:
                link=f'https://www.planespotters.net/photo/{urllib.parse.quote(photo_id)}'

        if not thumbnail_url or not link:
            return {'ok':False,'reason':'invalid_response','error':'Planespotters returned an incomplete photo record.'}

        size=thumbnail.get('size') if isinstance(thumbnail.get('size'),dict) else {}
        result={
            'ok':True,
            'cached':False,
            'icao':code.upper(),
            'provider':'Planespotters.net Photo API',
            'photo':{
                'thumbnail_url':thumbnail_url,
                'width':size.get('width'),
                'height':size.get('height'),
                'link':link,
                'photographer':str(item.get('photographer') or '').strip() or None,
                'photo_id':item.get('id')
            },
            'notice':'Thumbnail and attribution are supplied by Planespotters.net. Click through to the original photograph.'
        }
        planespotters_photo_cache[code]=(time.time(),result)
        return result

@app.get('/api/external/planespotters-photo/{icao_code}')
async def planespotters_photo(icao_code:str,refresh:bool=False):
    result=await fetch_planespotters_photo(icao_code,refresh=refresh)
    if result.get('ok'):
        status=200
    else:
        status={
            'invalid_icao':400,
            'disabled':503,
            'rate_limited':429,
            'unavailable':503,
            'http_error':502,
            'invalid_response':502,
            'not_found':404
        }.get(result.get('reason'),502)
    return JSONResponse(result,status_code=status)

@app.get('/api/external/airplanes-live/{icao_code}')
async def airplanes_live_aircraft(icao_code:str,refresh:bool=False):
    result=await fetch_airplanes_live(icao_code,refresh=refresh)
    if result.get('ok'):
        status=200
    else:
        status={
            'invalid_icao':400,
            'disabled':503,
            'rate_limited':429,
            'timeout':504,
            'unavailable':503,
            'http_error':502,
            'not_found':404,
        }.get(result.get('reason'),502)
    return JSONResponse(result,status_code=status)

@app.get('/api/aircraft/{icao_code}/detail')
def aircraft_detail(
    icao_code: str,
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(500, ge=1, le=5000)
):
    code=icao_code.strip().upper()
    cutoff=time.time()-hours*3600
    with db() as c:
        aircraft_row=c.execute(
            'SELECT a.icao,a.callsign,a.lat,a.lon,a.alt,a.freq,a.msgtype,a.last_seen,a.last_epoch,m.registration,m.aircraft_type,m.operator,m.country,m.photo_url,m.photo_credit,m.photo_link,m.photo_checked_at,m.metadata_source FROM aircraft a LEFT JOIN aircraft_metadata m ON m.icao=a.icao WHERE a.icao=?',
            (code,)
        ).fetchone()
        rows=c.execute(
            'SELECT id,ts,epoch,freq,signal,noise,snr,bitrate,direction,msgtype,icao,callsign,lat,lon,alt,gs,frame_type,src_gs,dst_gs,assigned_ac_id,freq_skew,slot FROM messages WHERE icao=? AND epoch>=? ORDER BY epoch DESC LIMIT ?',
            (code,cutoff,limit)
        ).fetchall()
    messages=[dict(r) for r in rows]
    callsigns=sorted({m['callsign'] for m in messages if m['callsign']})
    assigned_ids=sorted({str(m['assigned_ac_id']) for m in messages if m['assigned_ac_id']})
    stations=sorted({str(m['src_gs'] or m['dst_gs'] or m['gs']) for m in messages if (m['src_gs'] or m['dst_gs'] or m['gs'])})
    track=[
        {'lat':m['lat'],'lon':m['lon'],'alt':m['alt'],'epoch':m['epoch'],'ts':m['ts'],'freq':m['freq'],'callsign':m['callsign']}
        for m in reversed(messages) if m['lat'] is not None and m['lon'] is not None
    ]
    event_types=('logon','logoff','position','squitter')
    events=[m for m in messages if any(token in str(m['msgtype'] or '').lower() for token in event_types)][:100]
    snrs=[m['snr'] for m in messages if m['snr'] is not None]
    signals=[m['signal'] for m in messages if m['signal'] is not None]
    aircraft_data=dict(aircraft_row) if aircraft_row else {'icao':code}
    settings=get_settings()
    mode=settings.get('photo_mode','local_first')
    folder=Path(DB).parent/'aircraft_photos'
    has_local=any((folder/(code+s)).exists() for s in ('.jpg','.jpeg','.png','.webp'))
    remote=aircraft_data.get('photo_url')
    photo_src=None
    photo_source=None
    if mode=='local' and has_local:
        photo_src=f'/api/photos/{code}'
        photo_source='local file'
    elif mode=='internet' and remote:
        photo_src=remote
        photo_source='internet URL'
    elif mode=='local_first':
        if has_local:
            photo_src=f'/api/photos/{code}'
            photo_source='local file'
        elif remote:
            photo_src=remote
            photo_source='internet URL'
    elif mode=='internet_first':
        if remote:
            photo_src=remote
            photo_source='internet URL'
        elif has_local:
            photo_src=f'/api/photos/{code}'
            photo_source='local file'
    aircraft_data['photo_src']=photo_src
    aircraft_data['photo_source']=photo_source
    return {
        'aircraft': aircraft_data,
        'messages': messages,
        'events': events,
        'track': track,
        'callsigns': callsigns,
        'assigned_ids': assigned_ids,
        'stations': stations,
        'stats': {
            'message_count': len(messages),
            'position_count': len(track),
            'average_snr': round(sum(snrs)/len(snrs),1) if snrs else None,
            'strongest_signal': round(max(signals),1) if signals else None,
            'first_seen': messages[-1]['ts'] if messages else None,
            'last_seen': messages[0]['ts'] if messages else None
        }
    }




def get_settings():
    with db() as c:
        return {r['key']:r['value'] for r in c.execute('SELECT key,value FROM app_settings')}

def metadata_upsert_rows(csv_text:str, source:str='local', overwrite:bool=False):
    reader=csv.DictReader(io.StringIO(csv_text))
    imported=0; skipped=0
    with db() as c:
        for row in reader:
            lower={norm(k):v for k,v in row.items() if k is not None}
            code=icao(lower.get('icao') or lower.get('icao24') or lower.get('hex') or lower.get('icaoaddress'))
            if not code:
                skipped+=1
                continue
            values={
                'registration':(lower.get('registration') or lower.get('reg') or '').strip().upper() or None,
                'aircraft_type':(lower.get('aircrafttype') or lower.get('model') or lower.get('typecode') or lower.get('type') or '').strip() or None,
                'operator':(lower.get('operator') or lower.get('operatorcallsign') or lower.get('owner') or lower.get('airline') or '').strip() or None,
                'country':(lower.get('country') or '').strip() or None,
                'photo_url':(lower.get('photourl') or lower.get('imageurl') or lower.get('photo') or '').strip() or None,
                'photo_credit':(lower.get('photocredit') or lower.get('credit') or '').strip() or None
            }
            old=c.execute('SELECT * FROM aircraft_metadata WHERE icao=?',(code,)).fetchone()
            if old and not overwrite:
                for key in values:
                    if old[key] not in (None,''):
                        values[key]=old[key]
            c.execute("""INSERT INTO aircraft_metadata
                (icao,registration,aircraft_type,operator,country,photo_url,photo_credit,metadata_source,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(icao) DO UPDATE SET
                  registration=excluded.registration,
                  aircraft_type=excluded.aircraft_type,
                  operator=excluded.operator,
                  country=excluded.country,
                  photo_url=excluded.photo_url,
                  photo_credit=excluded.photo_credit,
                  metadata_source=excluded.metadata_source,
                  updated_at=excluded.updated_at""",
                (code,values['registration'],values['aircraft_type'],values['operator'],values['country'],
                 values['photo_url'],values['photo_credit'],source,datetime.now(timezone.utc).isoformat()))
            imported+=1
        c.commit()
    return imported,skipped


LEGAL_FILES={
    'LICENSE':'LICENSE',
    'DISCLAIMER':'DISCLAIMER.md',
    'PRIVACY':'PRIVACY.md',
    'SECURITY':'SECURITY.md',
    'THIRD_PARTY_NOTICES':'THIRD_PARTY_NOTICES.md',
    'CHANGELOG':'CHANGELOG.md'
}

@app.get('/legal/{name}')
def legal_document(name:str):
    filename=LEGAL_FILES.get(name.upper())
    if not filename:
        return Response(status_code=404)
    path=Path(__file__).with_name(filename)
    if not path.exists():
        return Response(status_code=404)
    return FileResponse(path,media_type='text/plain; charset=utf-8',filename=filename)

@app.get('/api/enrichment/settings')
def enrichment_settings():
    return get_settings()

@app.post('/api/enrichment/settings')
def update_enrichment_settings(payload:dict=Body(...)):
    allowed_modes={'local','internet','internet_first','local_first','disabled'}
    photo_modes={'local','internet','internet_first','local_first','disabled'}
    metadata_mode=str(payload.get('metadata_mode','local'))
    photo_mode=str(payload.get('photo_mode','local_first'))
    overwrite=str(payload.get('overwrite_manual','no'))
    photo_lookup=str(payload.get('photo_lookup','manual'))
    metadata_url=str(payload.get('metadata_url','')).strip()
    if metadata_mode not in allowed_modes or photo_mode not in photo_modes or overwrite not in {'yes','no'} or photo_lookup not in {'manual','disabled'}:
        return JSONResponse({'ok':False,'error':'Invalid enrichment settings'},status_code=400)
    if metadata_url and urllib.parse.urlparse(metadata_url).scheme not in ('http','https'):
        return JSONResponse({'ok':False,'error':'Metadata URL must use HTTP or HTTPS'},status_code=400)
    values={'metadata_mode':metadata_mode,'metadata_url':metadata_url,'photo_mode':photo_mode,'overwrite_manual':overwrite,'photo_lookup':photo_lookup}
    with db() as c:
        for key,value in values.items():
            c.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
        c.commit()
    return {'ok':True,**values}

@app.post('/api/metadata/download')
def metadata_download(payload:dict=Body(...)):
    url=str(payload.get('url','')).strip()
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme not in ('http','https'):
        return JSONResponse({'ok':False,'error':'Only HTTP and HTTPS URLs are accepted'},status_code=400)
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'HFDL-Dashboard/9.0'})
        with urllib.request.urlopen(req,timeout=25) as response:
            raw=response.read(100*1024*1024+1)
        if len(raw)>100*1024*1024:
            return JSONResponse({'ok':False,'error':'CSV exceeds the 100 MB download limit'},status_code=400)
        text=raw.decode('utf-8-sig')
        settings=get_settings()
        imported,skipped=metadata_upsert_rows(text,'internet',settings.get('overwrite_manual')=='yes')
        with db() as c:
            c.execute("INSERT INTO app_settings(key,value) VALUES('metadata_url',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(url,))
            c.commit()
        return {'ok':True,'imported':imported,'skipped':skipped,'source':'OpenSky' if 'opensky-network.org' in url else 'internet CSV'}
    except Exception as exc:
        return JSONResponse({'ok':False,'error':f'Download failed: {exc}'},status_code=400)


@app.post('/api/photos/url/{icao_code}')
def save_photo_url(icao_code:str,payload:dict=Body(...)):
    code=icao(icao_code)
    if not code:
        return JSONResponse({'ok':False,'error':'Invalid ICAO address'},status_code=400)
    settings=get_settings()
    if settings.get('photo_lookup','manual')=='disabled':
        return JSONResponse({'ok':False,'error':'Internet photo URLs are disabled in Settings'},status_code=400)
    photo_url=str(payload.get('photo_url','')).strip()
    photo_credit=str(payload.get('photo_credit','')).strip() or None
    photo_link=str(payload.get('photo_link','')).strip() or None
    parsed=urllib.parse.urlparse(photo_url)
    if parsed.scheme not in ('http','https'):
        return JSONResponse({'ok':False,'error':'Photo URL must use HTTP or HTTPS'},status_code=400)
    if photo_link and urllib.parse.urlparse(photo_link).scheme not in ('http','https'):
        return JSONResponse({'ok':False,'error':'Source link must use HTTP or HTTPS'},status_code=400)
    now=datetime.now(timezone.utc).isoformat()
    with db() as c:
        c.execute("""INSERT INTO aircraft_metadata
            (icao,photo_url,photo_credit,photo_link,photo_checked_at,metadata_source,updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(icao) DO UPDATE SET
              photo_url=excluded.photo_url,
              photo_credit=excluded.photo_credit,
              photo_link=excluded.photo_link,
              photo_checked_at=excluded.photo_checked_at,
              updated_at=excluded.updated_at""",
            (code,photo_url,photo_credit,photo_link,now,'manual internet URL',now))
        c.commit()
    return {'ok':True,'icao':code,'photo_url':photo_url,'photo_credit':photo_credit,'photo_link':photo_link}

@app.post('/api/photos/upload')
async def photo_upload(request:Request,icao_code:str=Query(...),filename:str=Query('aircraft.jpg')):
    code=icao(icao_code)
    if not code:
        return JSONResponse({'ok':False,'error':'Invalid ICAO address'},status_code=400)
    suffix=Path(filename).suffix.lower()
    allowed={'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp'}
    if suffix not in allowed:
        return JSONResponse({'ok':False,'error':'Use a JPEG, PNG or WebP file'},status_code=400)
    content=await request.body()
    if not content or len(content)>10*1024*1024:
        return JSONResponse({'ok':False,'error':'Photo must be between 1 byte and 10 MB'},status_code=400)
    folder=Path(DB).parent/'aircraft_photos'
    folder.mkdir(parents=True,exist_ok=True)
    for old in folder.glob(code+'.*'):
        old.unlink(missing_ok=True)
    target=folder/(code+suffix)
    target.write_bytes(content)
    return {'ok':True,'icao':code,'path':str(target)}

@app.get('/api/photos/{icao_code}')
def local_photo(icao_code:str):
    code=icao(icao_code)
    folder=Path(DB).parent/'aircraft_photos'
    for suffix in ('.jpg','.jpeg','.png','.webp'):
        path=folder/(str(code)+suffix)
        if path.exists():
            return FileResponse(path,media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
    return Response(status_code=404)

@app.get('/api/metadata/status')
def metadata_status():
    with db() as c:count=c.execute('SELECT COUNT(*) FROM aircraft_metadata').fetchone()[0]
    return {'count':count}

@app.post('/api/metadata/import')
def metadata_import(csv_text:str=Body(...,media_type='text/plain')):
    settings=get_settings()
    imported,skipped=metadata_upsert_rows(csv_text,'local',settings.get('overwrite_manual')=='yes')
    return {'ok':True,'imported':imported,'skipped':skipped}

@app.get('/api/alerts')
def list_alerts():
    with db() as c:
        rules=[dict(r) for r in c.execute('SELECT * FROM alerts ORDER BY id DESC')]
        hits=[dict(r) for r in c.execute('SELECT * FROM alert_hits ORDER BY id DESC LIMIT 100')]
    return {'rules':rules,'hits':hits}

@app.post('/api/alerts')
def create_alert(payload:dict=Body(...)):
    match_type=str(payload.get('match_type','')).lower();pattern=str(payload.get('pattern','')).strip().upper();event_type=str(payload.get('event_type','any')).lower()
    if match_type not in ('icao','callsign') or not pattern or event_type not in ('any','logon','logoff','position'):
        return JSONResponse({'ok':False,'error':'Invalid alert rule'},status_code=400)
    with db() as c:
        cur=c.execute('INSERT INTO alerts(match_type,pattern,event_type,enabled,created_at) VALUES(?,?,?,?,?)',(match_type,pattern,event_type,1,datetime.now(timezone.utc).isoformat()));c.commit()
    return {'ok':True,'id':cur.lastrowid}

@app.delete('/api/alerts/{alert_id}')
def delete_alert(alert_id:int):
    with db() as c:c.execute('DELETE FROM alerts WHERE id=?',(alert_id,));c.commit()
    return {'ok':True}

@app.get('/api/analytics')
def analytics(hours:int=Query(24,ge=1,le=720)):
    now=time.time()
    cutoff=now-hours*3600
    bucket_seconds=300 if hours<=24 else (900 if hours<=72 else 3600)
    with db() as c:
        rows=c.execute(
            'SELECT epoch,freq,snr,signal,icao,callsign,direction,msgtype FROM messages WHERE epoch>=? ORDER BY epoch',
            (cutoff,)
        ).fetchall()
    buckets={}
    freq={}
    aircraft={}
    msgtypes={}
    for r in rows:
        bucket=int(r['epoch']//bucket_seconds*bucket_seconds)
        item=buckets.setdefault(bucket,{'epoch':bucket,'count':0,'snr_sum':0.0,'snr_n':0})
        item['count']+=1
        if r['snr'] is not None:
            item['snr_sum']+=r['snr']; item['snr_n']+=1
        if r['freq'] is not None:
            key=f"{r['freq']:.1f}"
            fitem=freq.setdefault(key,{'count':0,'snr_sum':0.0,'snr_n':0,'strongest':None})
            fitem['count']+=1
            if r['snr'] is not None:
                fitem['snr_sum']+=r['snr']; fitem['snr_n']+=1
            if r['signal'] is not None and (fitem['strongest'] is None or r['signal']>fitem['strongest']):
                fitem['strongest']=r['signal']
        ident=r['callsign'] or r['icao']
        if ident:
            aircraft[ident]=aircraft.get(ident,0)+1
        typ=r['msgtype'] or 'Unknown'
        msgtypes[typ]=msgtypes.get(typ,0)+1

    start=int(cutoff//bucket_seconds*bucket_seconds)
    end=int(now//bucket_seconds*bucket_seconds)
    series=[]
    for epoch in range(start,end+1,bucket_seconds):
        item=buckets.get(epoch,{'epoch':epoch,'count':0,'snr_sum':0.0,'snr_n':0})
        series.append({
            'epoch':epoch,
            'count':item['count'],
            'avg_snr':round(item['snr_sum']/item['snr_n'],1) if item['snr_n'] else None
        })

    gaps=[]
    gap_start=None
    for point in series:
        if point['count']==0 and gap_start is None:
            gap_start=point['epoch']
        elif point['count']>0 and gap_start is not None:
            gaps.append({'start':gap_start,'end':point['epoch'],'seconds':point['epoch']-gap_start})
            gap_start=None
    if gap_start is not None:
        gaps.append({'start':gap_start,'end':end+bucket_seconds,'seconds':end+bucket_seconds-gap_start})

    frequency_stats=[]
    for key,value in sorted(freq.items(),key=lambda kv:kv[1]['count'],reverse=True):
        frequency_stats.append({
            'frequency':key,
            'count':value['count'],
            'avg_snr':round(value['snr_sum']/value['snr_n'],1) if value['snr_n'] else None,
            'strongest_signal':round(value['strongest'],1) if value['strongest'] is not None else None
        })

    return {
        'hours':hours,
        'bucket_seconds':bucket_seconds,
        'series':series,
        'frequency_stats':frequency_stats,
        'top_aircraft':[{'aircraft':k,'count':v} for k,v in sorted(aircraft.items(),key=lambda kv:kv[1],reverse=True)[:15]],
        'message_types':[{'type':k,'count':v} for k,v in sorted(msgtypes.items(),key=lambda kv:kv[1],reverse=True)[:15]],
        'gaps':sorted(gaps,key=lambda g:g['seconds'],reverse=True)[:20],
        'total_messages':len(rows)
    }

@app.get('/api/database')
def database_status():
    path=Path(DB)
    with db() as c:
        c.execute('PRAGMA wal_checkpoint(PASSIVE)')
        messages=c.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
        aircraft_count=c.execute('SELECT COUNT(*) FROM aircraft').fetchone()[0]
        oldest=c.execute('SELECT MIN(ts) FROM messages').fetchone()[0]
        newest=c.execute('SELECT MAX(ts) FROM messages').fetchone()[0]
        legacy=c.execute("SELECT COUNT(*) FROM messages WHERE direction IS NULL AND LOWER(COALESCE(msgtype,''))='dumphfdl'").fetchone()[0]
    total_size=0
    for suffix in ('','-wal','-shm'):
        p=Path(str(path)+suffix)
        if p.exists(): total_size+=p.stat().st_size
    return {
        'path':str(path),
        'size_bytes':total_size,
        'messages':messages,
        'aircraft':aircraft_count,
        'legacy_messages':legacy,
        'oldest':oldest,
        'newest':newest
    }

@app.get('/api/database/backup')
def database_backup():
    with db() as c:
        c.execute('PRAGMA wal_checkpoint(FULL)')
    content=Path(DB).read_bytes()
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    return Response(
        content=content,
        media_type='application/vnd.sqlite3',
        headers={'Content-Disposition':f'attachment; filename=hfdl-backup-{stamp}.sqlite3'}
    )

@app.post('/api/database/purge-legacy')
def purge_legacy(confirm:bool=Body(False,embed=True)):
    if not confirm:
        return JSONResponse({'ok':False,'error':'Confirmation required'},status_code=400)
    with db() as c:
        ids=[r[0] for r in c.execute("SELECT id FROM messages WHERE direction IS NULL AND LOWER(COALESCE(msgtype,''))='dumphfdl'")]
        c.execute("DELETE FROM messages WHERE direction IS NULL AND LOWER(COALESCE(msgtype,''))='dumphfdl'")
        c.commit()
    return {'ok':True,'deleted':len(ids)}

@app.post('/api/database/purge-older')
def purge_older(days:int=Body(...,embed=True),confirm:bool=Body(False,embed=True)):
    if not confirm:
        return JSONResponse({'ok':False,'error':'Confirmation required'},status_code=400)
    if days<1 or days>3650:
        return JSONResponse({'ok':False,'error':'Days must be between 1 and 3650'},status_code=400)
    cutoff=time.time()-days*86400
    with db() as c:
        count=c.execute('SELECT COUNT(*) FROM messages WHERE epoch<?',(cutoff,)).fetchone()[0]
        c.execute('DELETE FROM messages WHERE epoch<?',(cutoff,))
        c.execute('DELETE FROM aircraft WHERE last_epoch<?',(cutoff,))
        c.commit()
    return {'ok':True,'deleted':count,'days':days}

@app.websocket('/ws')
async def socket(ws:WebSocket):
    if not auth_ok(ws.headers.get('authorization')):
        await ws.close(code=1008);return
    await ws.accept();clients.add(ws)
    try:
        while True:await ws.receive_text()
    except WebSocketDisconnect:pass
    finally:clients.discard(ws)
if __name__=='__main__':uvicorn.run(app,host=WEB_BIND,port=WEB,log_level=os.getenv('LOG_LEVEL','info'))
