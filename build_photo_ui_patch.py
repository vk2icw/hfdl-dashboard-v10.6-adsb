from pathlib import Path

source = Path('app.py')
target = Path('build_app.py')
text = source.read_text(encoding='utf-8')

old_css = ".aircraft-photo{width:100%;height:250px;object-fit:cover;border-radius:10px;border:1px solid var(--border);background:#0b1020}"
new_css = ".aircraft-photo-frame{min-height:180px;display:flex;align-items:center;justify-content:center;border-radius:10px;border:1px solid var(--border);background:#0b1020;overflow:hidden;padding:10px}.aircraft-photo-link{display:flex;align-items:center;justify-content:center;width:100%;height:100%;cursor:zoom-in}.aircraft-photo{display:block;width:auto;height:auto;max-width:100%;max-height:320px;object-fit:contain;border-radius:8px;background:#0b1020}.photo-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}.photo-actions a{display:inline-block}"
if old_css not in text:
    raise SystemExit('Expected aircraft photo CSS was not found; app.py may have changed.')
text = text.replace(old_css, new_css, 1)

old_generic = """ if(a.photo_src){\n   photo.className='';\n   photo.innerHTML=`<img class=\"aircraft-photo\" src=\"${a.photo_src}\" alt=\"Aircraft ${a.registration||a.icao}\" onerror=\"this.parentElement.className='photo-placeholder';this.parentElement.textContent='Photograph could not be loaded.'\">`;\n   let creditText=a.photo_credit?`Photo: ${a.photo_credit}`:`Photo source: ${a.photo_source||'configured source'}`;\n   credit.innerHTML=a.photo_link?`${creditText} · <a href=\"${a.photo_link}\" target=\"_blank\" rel=\"noopener\">View source</a>`:creditText;\n }else{"""
new_generic = """ if(a.photo_src){\n   photo.className='aircraft-photo-frame';\n   let fullPhotoHref=a.photo_link||a.photo_src;\n   photo.innerHTML=`<a class=\"aircraft-photo-link\" href=\"${fullPhotoHref}\" target=\"_blank\" rel=\"noopener noreferrer\" title=\"Open full image or source\"><img class=\"aircraft-photo\" src=\"${a.photo_src}\" alt=\"Aircraft ${a.registration||a.icao}\" onerror=\"this.closest('#detail-photo').className='photo-placeholder';this.closest('#detail-photo').textContent='Photograph could not be loaded.'\"></a>`;\n   let creditText=a.photo_credit?`Photo: ${a.photo_credit}`:`Photo source: ${a.photo_source||'configured source'}`;\n   let sourceAction=a.photo_link?`<a href=\"${a.photo_link}\" target=\"_blank\" rel=\"noopener noreferrer\">View source</a>`:'';\n   credit.innerHTML=`${creditText}<div class=\"photo-actions\"><a href=\"${fullPhotoHref}\" target=\"_blank\" rel=\"noopener noreferrer\">View full image</a>${sourceAction?` · ${sourceAction}`:''}</div>`;\n }else{"""
if old_generic not in text:
    raise SystemExit('Expected generic aircraft photo renderer was not found; app.py may have changed.')
text = text.replace(old_generic, new_generic, 1)

old_planespotters = """  holder.className='';\n  holder.innerHTML=`<a href=\"${photo.link}\" target=\"_blank\" rel=\"noopener noreferrer\">\n    <img class=\"aircraft-photo\" src=\"${photo.thumbnail_url}\"\n      alt=\"Aircraft ${a.registration||a.icao||selectedAircraft}\"\n      referrerpolicy=\"no-referrer-when-downgrade\"\n      onerror=\"this.parentElement.parentElement.className='photo-placeholder';this.parentElement.parentElement.textContent='Planespotters thumbnail could not be loaded.'\">\n  </a>`;\n  let photographer=photo.photographer||'Unknown photographer';\n  credit.innerHTML=`© ${photographer} · Photo supplied by\n    <a href=\"${photo.link}\" target=\"_blank\" rel=\"noopener noreferrer\">Planespotters.net</a>\n    · <a href=\"${photo.link}\" target=\"_blank\" rel=\"noopener noreferrer\">Open original photograph</a>`;\n  status.textContent=`${data.cached?'Cached':'Fresh'} Planespotters Photo API result. Click the thumbnail to open the original page.`;"""
new_planespotters = """  holder.className='aircraft-photo-frame';\n  holder.innerHTML=`<a class=\"aircraft-photo-link\" href=\"${photo.link}\" target=\"_blank\" rel=\"noopener noreferrer\" title=\"Open original photograph\">\n    <img class=\"aircraft-photo\" src=\"${photo.thumbnail_url}\"\n      alt=\"Aircraft ${a.registration||a.icao||selectedAircraft}\"\n      referrerpolicy=\"no-referrer-when-downgrade\"\n      onerror=\"this.closest('#detail-photo').className='photo-placeholder';this.closest('#detail-photo').textContent='Planespotters thumbnail could not be loaded.'\">\n  </a>`;\n  let photographer=photo.photographer||'Unknown photographer';\n  credit.innerHTML=`© ${photographer} · Photo supplied by\n    <a href=\"${photo.link}\" target=\"_blank\" rel=\"noopener noreferrer\">Planespotters.net</a>\n    <div class=\"photo-actions\"><a href=\"${photo.link}\" target=\"_blank\" rel=\"noopener noreferrer\">Open original photograph</a></div>`;\n  status.textContent=`${data.cached?'Cached':'Fresh'} Planespotters Photo API result. Thumbnail is shown without forced enlargement; click it to open the original page.`;"""
if old_planespotters not in text:
    raise SystemExit('Expected Planespotters photo renderer was not found; app.py may have changed.')
text = text.replace(old_planespotters, new_planespotters, 1)

target.write_text(text, encoding='utf-8')
print(f'Photo UI patch applied: {target}')
