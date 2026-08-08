from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')

def rep(old,new):
    global s
    if old not in s:
        raise SystemExit('Expected app.py block not found:\n'+old[:200])
    s=s.replace(old,new,1)

rep("clients:set[WebSocket]=set(); counters={'total':0,'invalid':0,'last':None}\n",
"clients:set[WebSocket]=set(); counters={'total':0,'invalid':0,'last':None}\nAIRCRAFT_DISPLAY_SECONDS=180\nMESSAGE_MAX_AGE_SECONDS=120\n")

rep("for name,kind in [('frame_type','TEXT'),('src_gs','TEXT'),('dst_gs','TEXT'),('assigned_ac_id','TEXT'),('freq_skew','REAL'),('slot','TEXT')]:",
"for name,kind in [('frame_type','TEXT'),('src_gs','TEXT'),('dst_gs','TEXT'),('assigned_ac_id','TEXT'),('freq_skew','REAL'),('slot','TEXT'),('source_time','TEXT'),('received_time','TEXT'),('source_epoch','REAL'),('received_epoch','REAL'),('source_delay_seconds','REAL'),('display_eligible','INTEGER')]:")

rep("        c.commit()\n\ndef norm(k):",
"        aircraft_existing={r[1] for r in c.execute('PRAGMA table_info(aircraft)')}\n        for name,kind in [('source_time','TEXT'),('received_time','TEXT')]:\n            if name not in aircraft_existing:\n                c.execute(f'ALTER TABLE aircraft ADD COLUMN {name} {kind}')\n        c.commit()\n\ndef norm(k):")

rep("def parse(d):\n    now=datetime.now(timezone.utc)\n",
"def parse_time_value(v):\n    if v in (None,''): return None\n    try:\n        text=str(v).strip().replace('Z','+00:00')\n        dt=datetime.fromisoformat(text)\n        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)\n        return dt.astimezone(timezone.utc)\n    except Exception:\n        return None\n\ndef parse(d):\n    now=datetime.now(timezone.utc)\n    received_dt=parse_time_value(pathv(d,'received_at','received_time')) or now\n    source_dt=parse_time_value(pathv(d,'source_generated_at','source_message_time','transmission_time','message_time'))\n    source_delay=(received_dt-source_dt).total_seconds() if source_dt else None\n    display_eligible=not(source_delay is not None and source_delay>MESSAGE_MAX_AGE_SECONDS)\n")

old="return {'ts':now.isoformat(),'epoch':now.timestamp(),'freq':f,'signal':sig,'noise':noise,'snr':snr,'freq_skew':skew,'slot':str(slot)[:12] if slot is not None else None,'bitrate':int(bitrate) if bitrate else None,'direction':str(direction)[:40] if direction else None,'frame_type':frame,'msgtype':str(typ)[:120],'icao':ac_icao,'callsign':cs,'assigned_ac_id':str(assigned)[:24] if assigned is not None else None,'lat':lat,'lon':lon,'alt':alt,'src_gs':src_gs,'dst_gs':dst_gs,'gs':gs,'raw':d}"
new="return {'ts':received_dt.isoformat(),'epoch':received_dt.timestamp(),'source_time':source_dt.isoformat() if source_dt else None,'received_time':received_dt.isoformat(),'source_epoch':source_dt.timestamp() if source_dt else None,'received_epoch':received_dt.timestamp(),'source_delay_seconds':source_delay,'display_eligible':1 if display_eligible else 0,'freq':f,'signal':sig,'noise':noise,'snr':snr,'freq_skew':skew,'slot':str(slot)[:12] if slot is not None else None,'bitrate':int(bitrate) if bitrate else None,'direction':str(direction)[:40] if direction else None,'frame_type':frame,'msgtype':str(typ)[:120],'icao':ac_icao,'callsign':cs,'assigned_ac_id':str(assigned)[:24] if assigned is not None else None,'lat':lat,'lon':lon,'alt':alt,'src_gs':src_gs,'dst_gs':dst_gs,'gs':gs,'raw':d}"
rep(old,new)

rep("sql='INSERT INTO messages(ts,epoch,freq,signal,noise,snr,bitrate,direction,msgtype,icao,callsign,lat,lon,alt,gs,raw,frame_type,src_gs,dst_gs,assigned_ac_id,freq_skew,slot) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'",
"sql='INSERT INTO messages(ts,epoch,freq,signal,noise,snr,bitrate,direction,msgtype,icao,callsign,lat,lon,alt,gs,raw,frame_type,src_gs,dst_gs,assigned_ac_id,freq_skew,slot,source_time,received_time,source_epoch,received_epoch,source_delay_seconds,display_eligible) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'")
rep("vals=(m['ts'],m['epoch'],m['freq'],m['signal'],m['noise'],m['snr'],m['bitrate'],m['direction'],m['msgtype'],m['icao'],m['callsign'],m['lat'],m['lon'],m['alt'],m['gs'],json.dumps(m['raw'],separators=(',',':')),m['frame_type'],m['src_gs'],m['dst_gs'],m['assigned_ac_id'],m['freq_skew'],m['slot'])",
"vals=(m['ts'],m['epoch'],m['freq'],m['signal'],m['noise'],m['snr'],m['bitrate'],m['direction'],m['msgtype'],m['icao'],m['callsign'],m['lat'],m['lon'],m['alt'],m['gs'],json.dumps(m['raw'],separators=(',',':')),m['frame_type'],m['src_gs'],m['dst_gs'],m['assigned_ac_id'],m['freq_skew'],m['slot'],m['source_time'],m['received_time'],m['source_epoch'],m['received_epoch'],m['source_delay_seconds'],m['display_eligible'])")
rep("        if m['icao']:\n            c.execute('''INSERT INTO aircraft VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(icao) DO UPDATE SET callsign=COALESCE(excluded.callsign,aircraft.callsign),lat=COALESCE(excluded.lat,aircraft.lat),lon=COALESCE(excluded.lon,aircraft.lon),alt=COALESCE(excluded.alt,aircraft.alt),freq=COALESCE(excluded.freq,aircraft.freq),msgtype=excluded.msgtype,last_seen=excluded.last_seen,last_epoch=excluded.last_epoch''',(m['icao'],m['callsign'],m['lat'],m['lon'],m['alt'],m['freq'],m['msgtype'],m['ts'],m['epoch']))",
"        if m['icao'] and m['display_eligible']:\n            c.execute('''INSERT INTO aircraft(icao,callsign,lat,lon,alt,freq,msgtype,last_seen,last_epoch,source_time,received_time) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(icao) DO UPDATE SET callsign=COALESCE(excluded.callsign,aircraft.callsign),lat=COALESCE(excluded.lat,aircraft.lat),lon=COALESCE(excluded.lon,aircraft.lon),alt=COALESCE(excluded.alt,aircraft.alt),freq=COALESCE(excluded.freq,aircraft.freq),msgtype=excluded.msgtype,last_seen=excluded.last_seen,last_epoch=excluded.last_epoch,source_time=excluded.source_time,received_time=excluded.received_time''',(m['icao'],m['callsign'],m['lat'],m['lon'],m['alt'],m['freq'],m['msgtype'],m['ts'],m['epoch'],m['source_time'],m['received_time']))")

rep("    cutoff=time.time()-21600\n    with db() as c:return [dict(r) for r in c.execute('SELECT a.*,m.registration,m.aircraft_type,m.operator,m.country,m.photo_url,m.photo_credit,m.photo_link,m.photo_checked_at,m.metadata_source FROM aircraft a LEFT JOIN aircraft_metadata m ON m.icao=a.icao WHERE a.last_epoch>=? ORDER BY a.last_epoch DESC',(cutoff,))]",
"    cutoff=time.time()-AIRCRAFT_DISPLAY_SECONDS\n    with db() as c:return [dict(r) for r in c.execute('SELECT a.*,m.registration,m.aircraft_type,m.operator,m.country,m.photo_url,m.photo_credit,m.photo_link,m.photo_checked_at,m.metadata_source FROM aircraft a LEFT JOIN aircraft_metadata m ON m.icao=a.icao WHERE a.last_epoch>=? ORDER BY a.last_epoch DESC',(cutoff,))]")

rep('<div class="panelhead"><div><h2>Recent aircraft</h2><small>Seen during the last six hours</small></div></div>',
'<div class="panelhead"><div><h2>Recent aircraft</h2><small>Live display: maximum 3 minutes · source age limit 2 minutes</small></div></div>')
rep('<th>Last message</th><th>Last seen</th><th>Actions</th>',
'<th>Source time</th><th>Received time</th><th>Last message</th><th>Last seen</th><th>Actions</th>')

old_render="<td>${fmtFreq(a.freq)}</td><td>${a.msgtype||'—'}</td><td>${age(a.last_epoch)}</td><td><button class=\"action\""
new_render="<td>${fmtFreq(a.freq)}</td><td>${a.source_time?new Date(a.source_time).toLocaleTimeString():'—'}</td><td>${a.received_time?new Date(a.received_time).toLocaleTimeString():'—'}</td><td>${a.msgtype||'—'}</td><td>${age(a.last_epoch)}</td><td><button class=\"action\""
rep(old_render,new_render)

rep("mk.bindPopup(`<b>${a.callsign||a.icao}</b><br>ICAO ${a.icao}<br>${fmtFreq(a.freq)}<br>${age(a.last_epoch)}`)",
"mk.bindPopup(`<b>${a.callsign||a.icao}</b><br>ICAO ${a.icao}<br>${fmtFreq(a.freq)}<br>Source: ${a.source_time?new Date(a.source_time).toLocaleTimeString():'—'}<br>Received: ${a.received_time?new Date(a.received_time).toLocaleTimeString():'—'}<br>${age(a.last_epoch)}`)")

# Include timestamps in message API output so both can be inspected outside the aircraft list.
rep("SELECT id,ts,epoch,freq,signal,noise,snr,bitrate,direction,msgtype,icao,callsign,lat,lon,alt,gs,frame_type,src_gs,dst_gs,assigned_ac_id,freq_skew,slot FROM messages",
"SELECT id,ts,epoch,source_time,received_time,source_delay_seconds,display_eligible,freq,signal,noise,snr,bitrate,direction,msgtype,icao,callsign,lat,lon,alt,gs,frame_type,src_gs,dst_gs,assigned_ac_id,freq_skew,slot FROM messages")

p.write_text(s,encoding='utf-8')
compile(s,'app.py','exec')
print('Applied timestamp and aircraft freshness rules successfully.')
