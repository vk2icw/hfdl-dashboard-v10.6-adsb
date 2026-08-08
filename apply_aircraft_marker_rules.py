from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')


def rep(old: str, new: str) -> None:
    global s
    if old not in s:
        raise SystemExit('Expected app.py block not found:\n' + old[:260])
    s = s.replace(old, new, 1)


# Persist ADS-B track/heading. HFDL records normally leave this null.
rep(
    "('display_eligible','INTEGER')]:",
    "('display_eligible','INTEGER'),('heading','REAL')]:",
)
rep(
    "for name,kind in [('source_time','TEXT'),('received_time','TEXT')]:",
    "for name,kind in [('source_time','TEXT'),('received_time','TEXT'),('heading','REAL')]:",
)
rep(
    "    bitrate=num(pathv(d,'bit_rate','bitrate','bps','data_rate') or findv(d,{'bit_rate','bitrate','bps','data_rate'}))\n",
    "    bitrate=num(pathv(d,'bit_rate','bitrate','bps','data_rate') or findv(d,{'bit_rate','bitrate','bps','data_rate'}))\n"
    "    heading=num(pathv(d,'heading','track_deg','track','course') or findv(d,{'heading','track_deg','track','course'}))\n"
    "    if heading is not None: heading=heading%360\n",
)
rep(
    "'bitrate':int(bitrate) if bitrate else None,'direction'",
    "'bitrate':int(bitrate) if bitrate else None,'heading':heading,'direction'",
)
rep(
    "sql='INSERT INTO messages(ts,epoch,freq,signal,noise,snr,bitrate,direction,msgtype,icao,callsign,lat,lon,alt,gs,raw,frame_type,src_gs,dst_gs,assigned_ac_id,freq_skew,slot,source_time,received_time,source_epoch,received_epoch,source_delay_seconds,display_eligible) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'",
    "sql='INSERT INTO messages(ts,epoch,freq,signal,noise,snr,bitrate,direction,msgtype,icao,callsign,lat,lon,alt,gs,raw,frame_type,src_gs,dst_gs,assigned_ac_id,freq_skew,slot,source_time,received_time,source_epoch,received_epoch,source_delay_seconds,display_eligible,heading) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'",
)
rep(
    "m['source_delay_seconds'],m['display_eligible'])",
    "m['source_delay_seconds'],m['display_eligible'],m['heading'])",
)
rep(
    "c.execute('''INSERT INTO aircraft(icao,callsign,lat,lon,alt,freq,msgtype,last_seen,last_epoch,source_time,received_time) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(icao) DO UPDATE SET callsign=COALESCE(excluded.callsign,aircraft.callsign),lat=COALESCE(excluded.lat,aircraft.lat),lon=COALESCE(excluded.lon,aircraft.lon),alt=COALESCE(excluded.alt,aircraft.alt),freq=COALESCE(excluded.freq,aircraft.freq),msgtype=excluded.msgtype,last_seen=excluded.last_seen,last_epoch=excluded.last_epoch,source_time=excluded.source_time,received_time=excluded.received_time''',(m['icao'],m['callsign'],m['lat'],m['lon'],m['alt'],m['freq'],m['msgtype'],m['ts'],m['epoch'],m['source_time'],m['received_time']))",
    "c.execute('''INSERT INTO aircraft(icao,callsign,lat,lon,alt,freq,msgtype,last_seen,last_epoch,source_time,received_time,heading) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(icao) DO UPDATE SET callsign=COALESCE(excluded.callsign,aircraft.callsign),lat=COALESCE(excluded.lat,aircraft.lat),lon=COALESCE(excluded.lon,aircraft.lon),alt=COALESCE(excluded.alt,aircraft.alt),freq=COALESCE(excluded.freq,aircraft.freq),msgtype=excluded.msgtype,last_seen=excluded.last_seen,last_epoch=excluded.last_epoch,source_time=excluded.source_time,received_time=excluded.received_time,heading=COALESCE(excluded.heading,aircraft.heading)''',(m['icao'],m['callsign'],m['lat'],m['lon'],m['alt'],m['freq'],m['msgtype'],m['ts'],m['epoch'],m['source_time'],m['received_time'],m['heading']))",
)

# Replace the generic glowing dot with a lightweight top-down aircraft SVG.
rep(
    ".marker{width:15px;height:15px;border-radius:50%;background:var(--accent);border:2px solid white;box-shadow:0 0 12px var(--accent)}",
    ".aircraft-div-icon{background:transparent!important;border:0!important}"
    ".aircraft-marker{width:24px;height:24px;display:flex;align-items:center;justify-content:center;transform-origin:50% 50%;filter:drop-shadow(0 0 4px rgba(0,0,0,.8));transition:transform .25s linear,filter .15s ease}"
    ".aircraft-marker svg{width:100%;height:100%;fill:currentColor;stroke:#fff;stroke-width:1.1;stroke-linejoin:round}"
    ".aircraft-marker.aircraft-adsb{color:#4da3ff}"
    ".aircraft-marker.aircraft-hfdl{color:#4fd1a5}"
    ".aircraft-marker.selected{filter:drop-shadow(0 0 3px #fff) drop-shadow(0 0 9px currentColor);transform-origin:50% 50%}"
    ".aircraft-marker.small{width:19px;height:19px}",
)
rep(
    "function markerIcon(){return L.divIcon({className:'',html:'<div class=\"marker\"></div>',iconSize:[16,16],iconAnchor:[8,8]})}",
    "function aircraftSource(a){return String(a?.msgtype||'').toUpperCase().startsWith('ADSB SBS')?'adsb':'hfdl'}\n"
    "function markerIcon(a,small=false,selected=false){\n"
    " const value=Number(a?.heading),hasHeading=Number.isFinite(value),heading=hasHeading?((value%360)+360)%360:0;\n"
    " const size=small?19:24,source=aircraftSource(a),classes=['aircraft-marker','aircraft-'+source,small?'small':'',selected?'selected':''].filter(Boolean).join(' ');\n"
    " const title=hasHeading?('Track '+Math.round(heading)+'°'):'Heading unavailable';\n"
    " const svg='<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M12 1.3l2.5 7.1 7.4 3.1v2.2l-7.2-1.2-1.1 6.4 3 2.2v1.6L12 21.2 7.4 22.7v-1.6l3-2.2-1.1-6.4-7.2 1.2v-2.2l7.4-3.1z\"/></svg>';\n"
    " return L.divIcon({className:'aircraft-div-icon',html:`<div class=\"${classes}\" style=\"transform:rotate(${heading}deg)\" title=\"${title}\">${svg}</div>`,iconSize:[size,size],iconAnchor:[size/2,size/2]})\n"
    "}",
)
rep(
    "if(!mk){mk=L.marker([a.lat,a.lon],{icon:markerIcon()}).addTo(targetMap);targetMarkers.set(a.icao,mk)}else mk.setLatLng([a.lat,a.lon]);",
    "if(!mk){mk=L.marker([a.lat,a.lon],{icon:markerIcon(a,small,a.icao===selectedAircraft)}).addTo(targetMap);targetMarkers.set(a.icao,mk)}else{mk.setLatLng([a.lat,a.lon]);mk.setIcon(markerIcon(a,small,a.icao===selectedAircraft))}",
)
rep(
    "mk.bindPopup(`<b>${a.callsign||a.icao}</b><br>ICAO ${a.icao}<br>${fmtFreq(a.freq)}<br>Source: ${a.source_time?new Date(a.source_time).toLocaleTimeString():'—'}<br>Received: ${a.received_time?new Date(a.received_time).toLocaleTimeString():'—'}<br>${age(a.last_epoch)}`)",
    "mk.bindPopup(`<b>${a.callsign||a.icao}</b><br>ICAO ${a.icao}<br>${aircraftSource(a).toUpperCase()} · ${a.heading==null?'Heading unavailable':'Track '+Math.round(Number(a.heading))+'°'}<br>${fmtFreq(a.freq)}<br>Source: ${a.source_time?new Date(a.source_time).toLocaleTimeString():'—'}<br>Received: ${a.received_time?new Date(a.received_time).toLocaleTimeString():'—'}<br>${age(a.last_epoch)}`)",
)
rep(
    "function centreAircraft(icao){\n let a=latestAircraft.find(x=>x.icao===icao);if(!a||a.lat==null)return;\n showView('mapview');setTimeout(()=>{map.setView([a.lat,a.lon],7);markers.get(icao)?.openPopup()},100)\n}",
    "function centreAircraft(icao){\n let a=latestAircraft.find(x=>x.icao===icao);if(!a||a.lat==null)return;\n selectedAircraft=icao;updateMapMarkers(map,markers,false);updateMapMarkers(overviewMap,overviewMarkers,true);\n showView('mapview');setTimeout(()=>{map.setView([a.lat,a.lon],7);markers.get(icao)?.openPopup()},100)\n}",
)
rep(
    "detailMarker=L.marker([last.lat,last.lon],{icon:markerIcon()}).addTo(detailMap).bindPopup(`<b>${a.callsign||a.icao}</b><br>${new Date(last.ts).toLocaleString()}`);",
    "detailMarker=L.marker([last.lat,last.lon],{icon:markerIcon(a,false,true)}).addTo(detailMap).bindPopup(`<b>${a.callsign||a.icao}</b><br>${a.heading==null?'Heading unavailable':'Track '+Math.round(Number(a.heading))+'°'}<br>${new Date(last.ts).toLocaleString()}`);",
)

# Make the browser connection indicator reflect the actual WebSocket state.
rep(
    " w.onopen=()=>w.send('ready');w.onmessage=e=>{let p=JSON.parse(e.data);if(p.event==='message')setTimeout(refresh,180);if(p.event==='alert')showAlert(p.data)};",
    " w.onopen=()=>{document.getElementById('dot').className='dot good';document.getElementById('state').textContent='Connected';w.send('ready')};w.onmessage=e=>{let p=JSON.parse(e.data);if(p.event==='message')setTimeout(refresh,180);if(p.event==='alert')showAlert(p.data)};",
)

p.write_text(s, encoding='utf-8')
compile(s, 'app.py', 'exec')
print('Applied aircraft SVG marker and heading rules successfully.')
