from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')


def replace_once(old: str, new: str, label: str) -> None:
    global s
    if old not in s:
        raise SystemExit(f'Expected {label} block not found; app.py patch chain may have changed.')
    s = s.replace(old, new, 1)


# Make the photo panel accurately describe the automatic lookup policy.
s = s.replace(
    'Local image, Airport-Data, or Planespotters fallback',
    'Local image or Airport-Data; external gallery links when no thumbnail is available',
    1,
)

# Do not make a known-403 Planespotters server request after Airport-Data fails.
# Instead show a registration-specific JetPhotos gallery link. This avoids scraping
# or hot-linking a copyrighted JetPhotos image while still taking the user directly
# to verified photos of the exact aircraft.
old_fallback = """ window.airportDataPhotoStatus='Airport-Data: no usable photo by registration or Mode-S';
 status.textContent=window.airportDataPhotoStatus+' · checking Planespotters…';
 await loadPlanespottersPhoto(force);"""
new_fallback = """ window.airportDataPhotoStatus='Airport-Data: no authorised thumbnail by registration or Mode-S';
 let holder=document.getElementById('detail-photo'),credit=document.getElementById('detail-photo-credit');
 let registration=String(a.registration||'').trim().toUpperCase();
 holder.className='photo-placeholder';
 if(registration){
  let gallery=`https://www.jetphotos.com/registration/${encodeURIComponent(registration)}`;
  holder.innerHTML=`No Airport-Data thumbnail available.<br><a href=\"${gallery}\" target=\"_blank\" rel=\"noopener noreferrer\">View ${registration} photos on JetPhotos</a>`;
  credit.innerHTML=`External gallery: <a href=\"${gallery}\" target=\"_blank\" rel=\"noopener noreferrer\">JetPhotos · ${registration}</a>`;
  status.textContent=`Airport-Data: no authorised thumbnail for ${registration}. Verified external gallery link available.`;
 }else{
  holder.textContent='No authorised aircraft thumbnail is currently available.';
  credit.textContent='';
  status.textContent='Airport-Data: no authorised thumbnail and no registration is available for gallery lookup.';
 }
 return;"""
replace_once(old_fallback, new_fallback, 'Airport-Data fallback')

# Add a direct JetPhotos action beside the existing external aircraft services.
button = '<button class="action" onclick="openAirportData()">Open on Airport-Data</button>'
if button in s and 'onclick="openJetPhotos()"' not in s:
    s = s.replace(
        button,
        button + '\n          <button class="action" onclick="openJetPhotos()">Open photos on JetPhotos</button>',
        1,
    )

# Add the browser-only JetPhotos helper. It deliberately opens the registration
# gallery rather than fetching or embedding JetPhotos image bytes.
anchor = 'function openPlanespotters(){\n'
if anchor not in s:
    raise SystemExit('Open Planespotters JavaScript anchor not found.')
if 'function openJetPhotos(){' not in s:
    helper = """function openJetPhotos(){
 if(!selectedAircraft){alert('Select an aircraft first.');return}
 let aircraft=latestAircraft.find(a=>a.icao===selectedAircraft);
 let registration=aircraft?.registration||selectedAircraftData?.aircraft?.registration||'';
 if(!registration){alert('No aircraft registration is currently available.');return}
 window.open(`https://www.jetphotos.com/registration/${encodeURIComponent(registration)}`,'_blank','noopener,noreferrer');
}
"""
    s = s.replace(anchor, helper + anchor, 1)

p.write_text(s, encoding='utf-8')
compile(s, 'app.py', 'exec')
print('Applied registration-first photo fallback with JetPhotos browser link and no automatic Planespotters request.')
