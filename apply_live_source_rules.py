from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')


def rep(old: str, new: str) -> None:
    global s
    if old not in s:
        raise SystemExit('Expected app.py block not found:\n' + old[:300])
    s = s.replace(old, new, 1)


# Keep the last genuine frequency internally, but timestamp it separately so an
# old HFDL channel cannot masquerade as a current ADS-B frequency.
rep(
    "for name,kind in [('source_time','TEXT'),('received_time','TEXT'),('heading','REAL')]:",
    "for name,kind in [('source_time','TEXT'),('received_time','TEXT'),('heading','REAL'),('freq_epoch','REAL')]:",
)

rep(
    "c.execute('''INSERT INTO aircraft(icao,callsign,lat,lon,alt,freq,msgtype,last_seen,last_epoch,source_time,received_time,heading) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(icao) DO UPDATE SET callsign=COALESCE(excluded.callsign,aircraft.callsign),lat=COALESCE(excluded.lat,aircraft.lat),lon=COALESCE(excluded.lon,aircraft.lon),alt=COALESCE(excluded.alt,aircraft.alt),freq=COALESCE(excluded.freq,aircraft.freq),msgtype=excluded.msgtype,last_seen=excluded.last_seen,last_epoch=excluded.last_epoch,source_time=excluded.source_time,received_time=excluded.received_time,heading=COALESCE(excluded.heading,aircraft.heading)''',(m['icao'],m['callsign'],m['lat'],m['lon'],m['alt'],m['freq'],m['msgtype'],m['ts'],m['epoch'],m['source_time'],m['received_time'],m['heading']))",
    "c.execute('''INSERT INTO aircraft(icao,callsign,lat,lon,alt,freq,msgtype,last_seen,last_epoch,source_time,received_time,heading,freq_epoch) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(icao) DO UPDATE SET callsign=COALESCE(excluded.callsign,aircraft.callsign),lat=COALESCE(excluded.lat,aircraft.lat),lon=COALESCE(excluded.lon,aircraft.lon),alt=COALESCE(excluded.alt,aircraft.alt),freq=COALESCE(excluded.freq,aircraft.freq),msgtype=excluded.msgtype,last_seen=excluded.last_seen,last_epoch=excluded.last_epoch,source_time=excluded.source_time,received_time=excluded.received_time,heading=COALESCE(excluded.heading,aircraft.heading),freq_epoch=CASE WHEN excluded.freq IS NOT NULL THEN excluded.freq_epoch ELSE aircraft.freq_epoch END''',(m['icao'],m['callsign'],m['lat'],m['lon'],m['alt'],m['freq'],m['msgtype'],m['ts'],m['epoch'],m['source_time'],m['received_time'],m['heading'],m['epoch'] if m['freq'] is not None else None))",
)

old_aircraft = """@app.get('/api/aircraft')
def aircraft():
    cutoff=time.time()-AIRCRAFT_DISPLAY_SECONDS
    with db() as c:return [dict(r) for r in c.execute('SELECT a.*,m.registration,m.aircraft_type,m.operator,m.country,m.photo_url,m.photo_credit,m.photo_link,m.photo_checked_at,m.metadata_source FROM aircraft a LEFT JOIN aircraft_metadata m ON m.icao=a.icao WHERE a.last_epoch>=? ORDER BY a.last_epoch DESC',(cutoff,))]"""
new_aircraft = """@app.get('/api/aircraft')
def aircraft():
    now=time.time(); cutoff=now-AIRCRAFT_DISPLAY_SECONDS
    with db() as c:
        rows=[dict(r) for r in c.execute('SELECT a.*,m.registration,m.aircraft_type,m.operator,m.country,m.photo_url,m.photo_credit,m.photo_link,m.photo_checked_at,m.metadata_source FROM aircraft a LEFT JOIN aircraft_metadata m ON m.icao=a.icao WHERE a.last_epoch>=? ORDER BY a.last_epoch DESC',(cutoff,))]
    for row in rows:
        # Frequency is a live HFDL/channel observation, not an aircraft property.
        # Existing databases have NULL freq_epoch, so stale historic values vanish immediately.
        if row.get('freq_epoch') is None or now-float(row['freq_epoch'])>AIRCRAFT_DISPLAY_SECONDS:
            row['freq']=None
    return rows"""
rep(old_aircraft, new_aircraft)

# Expose the ADS-B-specific counters that the dual connector UI already reads.
rep(
    "def health():return {'status':'ok','udp_bind_ip':UDP_BIND,'udp_port':UDP,'web_bind_ip':WEB_BIND,'web_port':WEB,'total':counters['total'],'invalid':counters['invalid'],'last':counters['last']}",
    "def health():return {'status':'ok','udp_bind_ip':UDP_BIND,'udp_port':UDP,'web_bind_ip':WEB_BIND,'web_port':WEB,'total':counters['total'],'invalid':counters['invalid'],'last':counters['last'],'adsb_total':counters.get('adsb_total',0),'adsb_last':counters.get('adsb_last')}",
)

# A clearer map symbol size: 30 px on the main/detail map and 24 px on overview.
rep(
    ".aircraft-marker{width:24px;height:24px;",
    ".aircraft-marker{width:30px;height:30px;",
)
rep(
    ".aircraft-marker.small{width:19px;height:19px}",
    ".aircraft-marker.small{width:24px;height:24px}",
)
rep(
    "const size=small?19:24,source=aircraftSource(a)",
    "const size=small?24:30,source=aircraftSource(a)",
)

# With SBS traffic flowing, keep the status green for up to 30 seconds between frames.
rep(
    "if(adsbAge!=null&&adsbAge<15){adsbDot.className='dot on';adsbState.textContent='ADS-B active'}",
    "if(adsbAge!=null&&adsbAge<30){adsbDot.className='dot on';adsbState.textContent='ADS-B active'}",
)

p.write_text(s, encoding='utf-8')
compile(s, 'app.py', 'exec')
print('Applied live source/frequency expiry, ADS-B health and aircraft size rules successfully.')
