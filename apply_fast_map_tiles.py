from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')

old = "[map,overviewMap,detailMap].forEach(m=>L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap'}).addTo(m));"

# Some development builds used OpenTopoMap; support that form as well so the
# build patch remains safe across the current v10.6 patch chain.
old_topo = "[map,overviewMap,detailMap].forEach(m=>L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',{maxZoom:17,attribution:'Map data: © OpenStreetMap contributors, SRTM | Map style: © OpenTopoMap'}).addTo(m));"

new = r"""function addFastBaseTiles(m){
 const primary=L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{
  subdomains:'abcd',maxZoom:20,detectRetina:false,updateWhenIdle:false,updateWhenZooming:false,
  keepBuffer:3,crossOrigin:true,
  attribution:'© OpenStreetMap contributors © CARTO'
 }).addTo(m);
 let failures=0,switched=false;
 primary.on('tileerror',()=>{
  failures++;
  if(switched||failures<3)return;
  switched=true;
  m.removeLayer(primary);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{
   maxZoom:19,detectRetina:false,updateWhenIdle:false,updateWhenZooming:false,
   keepBuffer:3,crossOrigin:true,attribution:'© OpenStreetMap contributors'
  }).addTo(m);
 });
}
[map,overviewMap,detailMap].forEach(addFastBaseTiles);"""

if old in s:
    s = s.replace(old, new, 1)
elif old_topo in s:
    s = s.replace(old_topo, new, 1)
else:
    raise SystemExit('Expected Leaflet base-tile layer was not found; app.py may have changed.')

p.write_text(s, encoding='utf-8')
compile(s, 'app.py', 'exec')
print('Applied faster Leaflet base tiles with automatic OpenStreetMap fallback.')
