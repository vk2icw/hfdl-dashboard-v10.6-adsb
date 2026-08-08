import json
import urllib.request

REG='VH-VGR'
API=f'https://airport-data.com/api/ac_thumb.json?r={REG}&n=2'
headers={
    'User-Agent':'HFDL-Operations-Dashboard/10.6 smoke test',
    'Accept':'application/json',
    'Accept-Encoding':'identity',
}

req=urllib.request.Request(API,headers=headers)
with urllib.request.urlopen(req,timeout=20) as r:
    payload=json.loads(r.read().decode('utf-8','replace'))

if payload.get('status') != 200:
    raise SystemExit(f'Airport-Data API status was {payload.get("status")!r}')
items=payload.get('data')
if not isinstance(items,list) or not items:
    raise SystemExit('Airport-Data returned no photographs for VH-VGR')

item=next((x for x in items if isinstance(x,dict) and x.get('image')),None)
if not item:
    raise SystemExit('Airport-Data returned no usable thumbnail record for VH-VGR')

image=item['image']
link=item.get('link')
photographer=item.get('photographer')

img_req=urllib.request.Request(image,headers={'User-Agent':'HFDL-Operations-Dashboard/10.6 smoke test'})
with urllib.request.urlopen(img_req,timeout=20) as r:
    content_type=(r.headers.get('Content-Type') or '').lower()
    sample=r.read(64)

if not content_type.startswith('image/'):
    raise SystemExit(f'Thumbnail did not return an image content type: {content_type!r}')
if not sample:
    raise SystemExit('Thumbnail response was empty')

print('Airport-Data smoke test passed')
print('registration:', REG)
print('image:', image)
print('link:', link)
print('photographer:', photographer)
print('content-type:', content_type)
