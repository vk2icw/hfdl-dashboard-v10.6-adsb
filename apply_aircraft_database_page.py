from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')

def rep(old,new):
    global s
    if old not in s:
        raise SystemExit('Expected app.py block not found:\n'+old[:240])
    s=s.replace(old,new,1)

rep(
'    <button data-view="aircraft">Aircraft</button>\n',
'    <button data-view="aircraft">Aircraft</button>\n    <button data-view="aircraft-db">Aircraft Database</button>\n'
)

rep(
'<section id="view-aircraft-detail" class="view">',
'''<section id="view-aircraft-db" class="view">
  <div class="grid two">
    <section class="panel">
      <div class="panelhead"><div><h2>Aircraft database</h2><small>Local metadata with VRS-style local photo status</small></div><button class="action" onclick="loadAircraftDatabase()">Refresh</button></div>
      <div class="toolbar">
        <input id="adb-search" placeholder="Search ICAO, registration, type, operator or country" style="min-width:320px">
        <button class="action" onclick="loadAircraftDatabase()">Search</button>
        <button class="action" onclick="clearAircraftDatabaseSearch()">Clear</button>
      </div>
      <div class="tablewrap"><table><thead><tr><th>ICAO</th><th>Registration</th><th>Type</th><th>Operator</th><th>Country</th><th>Photo</th><th>Source</th><th>Updated</th><th>Actions</th></tr></thead><tbody id="aircraft-db-rows"></tbody></table></div>
    </section>
    <section class="panel">
      <div class="panelhead"><div><h2>Edit aircraft record</h2><small>Manual values are stored locally</small></div></div>
      <div class="panelbody">
        <input id="adb-icao" placeholder="ICAO hex" maxlength="6" style="width:100%"><br><br>
        <input id="adb-registration" placeholder="Registration" style="width:100%"><br><br>
        <input id="adb-type" placeholder="Aircraft type / model" style="width:100%"><br><br>
        <input id="adb-operator" placeholder="Operator" style="width:100%"><br><br>
        <input id="adb-country" placeholder="Country" style="width:100%"><br><br>
        <input id="adb-photo-url" placeholder="Optional direct photo URL" style="width:100%"><br><br>
        <input id="adb-photo-credit" placeholder="Photo credit" style="width:100%"><br><br>
        <input id="adb-photo-link" placeholder="Photo source page" style="width:100%"><br><br>
        <button class="action" onclick="saveAircraftDatabaseRecord()">Save record</button>
        <button class="action" onclick="clearAircraftDatabaseForm()">Clear form</button>
        <p id="adb-status" class="muted" style="margin-top:12px">Select a row or enter a six-character ICAO hex code.</p>
        <div class="filebox" style="margin-top:14px">
          <b>Local photograph</b>
          <p class="muted">Upload a local image for the ICAO record. The dashboard also recognises manually placed files named by ICAO hex or registration.</p>
          <input id="adb-photo-file" type="file" accept="image/jpeg,image/png,image/webp,image/gif,image/bmp"><br><br>
          <button class="action" onclick="uploadAircraftDatabasePhoto()">Upload local photo</button>
        </div>
      </div>
    </section>
  </div>
</section>

<section id="view-aircraft-detail" class="view">'''
)

rep(
" localStorage.setItem('hfdl-view',name);if(name==='analytics')setTimeout(loadAnalytics,100);if(name==='settings'){setTimeout(loadDatabaseStatus,100);setTimeout(loadMetadataStatus,120)};if(name==='alerts')setTimeout(loadAlerts,100);",
" localStorage.setItem('hfdl-view',name);if(name==='analytics')setTimeout(loadAnalytics,100);if(name==='settings'){setTimeout(loadDatabaseStatus,100);setTimeout(loadMetadataStatus,120)};if(name==='alerts')setTimeout(loadAlerts,100);if(name==='aircraft-db')setTimeout(loadAircraftDatabase,100);"
)

insert_js=r'''
let latestAircraftDatabase=[];
function esc(v){return String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]))}
async function loadAircraftDatabase(){
 let q=document.getElementById('adb-search')?.value.trim()||'';
 let url='/api/aircraft-database?limit=2000'+(q?'&q='+encodeURIComponent(q):'');
 latestAircraftDatabase=await fetch(url).then(r=>r.json());
 let rows=latestAircraftDatabase||[];
 document.getElementById('aircraft-db-rows').innerHTML=rows.length?rows.map(a=>`<tr>
  <td><b>${esc(a.icao)}</b></td><td>${esc(a.registration||'—')}</td><td>${esc(a.aircraft_type||'—')}</td>
  <td>${esc(a.operator||'—')}</td><td>${esc(a.country||'—')}</td><td>${a.has_local_photo?'Local':(a.photo_url?'URL':'—')}</td>
  <td>${esc(a.metadata_source||'—')}</td><td>${a.updated_at?new Date(a.updated_at).toLocaleString():'—'}</td>
  <td><button class="action" onclick="editAircraftDatabaseRecord('${esc(a.icao)}')">Edit</button> <button class="action" onclick="openAircraftDetail('${esc(a.icao)}')">Details</button></td></tr>`).join(''):'<tr><td colspan="9">No matching aircraft metadata records.</td></tr>';
}
function editAircraftDatabaseRecord(code){
 let a=latestAircraftDatabase.find(x=>x.icao===code);if(!a)return;
 document.getElementById('adb-icao').value=a.icao||'';
 document.getElementById('adb-registration').value=a.registration||'';
 document.getElementById('adb-type').value=a.aircraft_type||'';
 document.getElementById('adb-operator').value=a.operator||'';
 document.getElementById('adb-country').value=a.country||'';
 document.getElementById('adb-photo-url').value=a.photo_url||'';
 document.getElementById('adb-photo-credit').value=a.photo_credit||'';
 document.getElementById('adb-photo-link').value=a.photo_link||'';
 document.getElementById('adb-status').textContent=a.has_local_photo?`Local photo found using ${a.local_photo_key}.`:'No local photo found yet.';
}
function clearAircraftDatabaseForm(){['adb-icao','adb-registration','adb-type','adb-operator','adb-country','adb-photo-url','adb-photo-credit','adb-photo-link'].forEach(id=>document.getElementById(id).value='');document.getElementById('adb-photo-file').value='';document.getElementById('adb-status').textContent='Form cleared.'}
function clearAircraftDatabaseSearch(){document.getElementById('adb-search').value='';loadAircraftDatabase()}
async function saveAircraftDatabaseRecord(){
 let code=document.getElementById('adb-icao').value.trim().toUpperCase();
 if(!/^[0-9A-F]{6}$/.test(code)){alert('Enter a valid six-character ICAO hex address.');return}
 let payload={registration:document.getElementById('adb-registration').value.trim(),aircraft_type:document.getElementById('adb-type').value.trim(),operator:document.getElementById('adb-operator').value.trim(),country:document.getElementById('adb-country').value.trim(),photo_url:document.getElementById('adb-photo-url').value.trim(),photo_credit:document.getElementById('adb-photo-credit').value.trim(),photo_link:document.getElementById('adb-photo-link').value.trim()};
 let r=await fetch('/api/aircraft-database/'+encodeURIComponent(code),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});let d=await r.json();
 document.getElementById('adb-status').textContent=d.ok?'Aircraft record saved.':(d.error||'Could not save aircraft record.');if(d.ok)await loadAircraftDatabase()
}
async function uploadAircraftDatabasePhoto(){
 let code=document.getElementById('adb-icao').value.trim().toUpperCase(),input=document.getElementById('adb-photo-file');
 if(!/^[0-9A-F]{6}$/.test(code)){alert('Enter a valid ICAO hex first.');return}if(!input.files.length){alert('Choose an image first.');return}
 let file=input.files[0],url=`/api/photos/upload?icao_code=${encodeURIComponent(code)}&filename=${encodeURIComponent(file.name)}`;
 let r=await fetch(url,{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream'},body:file});let d=await r.json();
 document.getElementById('adb-status').textContent=d.ok?'Local aircraft photo saved.':(d.error||'Photo upload failed.');if(d.ok){input.value='';await loadAircraftDatabase()}
}
'''

rep(
"async function loadEnrichmentSettings(){",
insert_js+"\nasync function loadEnrichmentSettings(){"
)

api=r'''
@app.get('/api/aircraft-database')
def aircraft_database(q:str|None=None,limit:int=Query(1000,ge=1,le=5000)):
    sql='''SELECT m.icao,m.registration,m.aircraft_type,m.operator,m.country,m.photo_url,m.photo_credit,m.photo_link,m.photo_checked_at,m.metadata_source,m.updated_at,a.callsign,a.last_seen,a.last_epoch FROM aircraft_metadata m LEFT JOIN aircraft a ON a.icao=m.icao'''
    params=[]
    if q:
        sql+=' WHERE UPPER(COALESCE(m.icao,\'\')||\' \'||COALESCE(m.registration,\'\')||\' \'||COALESCE(m.aircraft_type,\'\')||\' \'||COALESCE(m.operator,\'\')||\' \'||COALESCE(m.country,\'\')) LIKE UPPER(?)'
        params.append('%'+q+'%')
    sql+=' ORDER BY COALESCE(a.last_epoch,0) DESC, m.registration, m.icao LIMIT ?'
    params.append(limit)
    with db() as c:
        rows=[dict(r) for r in c.execute(sql,params)]
    for item in rows:
        path,key=local_photo_path(item['icao'],item.get('registration'))
        item['has_local_photo']=path is not None
        item['local_photo_key']=key
    return rows

@app.post('/api/aircraft-database/{icao_code}')
def aircraft_database_update(icao_code:str,payload:dict=Body(...)):
    code=icao(icao_code)
    if not code:
        return JSONResponse({'ok':False,'error':'Invalid ICAO address'},status_code=400)
    def clean(name,upper=False):
        value=str(payload.get(name,'')).strip()
        return (value.upper() if upper else value) or None
    photo_url=clean('photo_url'); photo_link=clean('photo_link')
    for value,label in ((photo_url,'Photo URL'),(photo_link,'Photo source URL')):
        if value and urllib.parse.urlparse(value).scheme not in ('http','https'):
            return JSONResponse({'ok':False,'error':f'{label} must use HTTP or HTTPS'},status_code=400)
    now=datetime.now(timezone.utc).isoformat()
    with db() as c:
        c.execute('''INSERT INTO aircraft_metadata(icao,registration,aircraft_type,operator,country,photo_url,photo_credit,photo_link,metadata_source,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(icao) DO UPDATE SET registration=excluded.registration,aircraft_type=excluded.aircraft_type,operator=excluded.operator,country=excluded.country,photo_url=excluded.photo_url,photo_credit=excluded.photo_credit,photo_link=excluded.photo_link,metadata_source=excluded.metadata_source,updated_at=excluded.updated_at''',
          (code,clean('registration',True),clean('aircraft_type'),clean('operator'),clean('country'),photo_url,clean('photo_credit'),photo_link,'manual',now))
        c.commit()
    return {'ok':True,'icao':code}

'''

rep(
"@app.get('/api/enrichment/settings')\ndef enrichment_settings():",
api+"@app.get('/api/enrichment/settings')\ndef enrichment_settings():"
)

p.write_text(s,encoding='utf-8')
compile(s,'app.py','exec')
print('Applied aircraft database management page successfully.')
