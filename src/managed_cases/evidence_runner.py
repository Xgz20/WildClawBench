"""Trusted, offline media extraction in the credential-free rule image."""
import argparse,base64,hashlib,json,os,subprocess,tempfile
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--output',required=True)
p.add_argument('--base-contract',choices=['general','web','ppt'],default='general')
a=p.parse_args();root=Path(a.workspace);output=Path(a.output);output.mkdir(parents=True,exist_ok=True)
rows=[];pages=0;total=0
for path in sorted(root.rglob('*')):
    if not path.is_file() or path.is_symlink() or '.grading' in path.parts:continue
    raw=path.read_bytes();item={'path':path.relative_to(root).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)}
    try:item['text']=raw.decode('utf-8-sig')
    except UnicodeError:
        import fitz
        suffix=path.suffix.lower();images=[]
        if suffix in {'.png','.jpg','.jpeg','.webp'}:
            from PIL import Image
            image=Image.open(path);image.verify()
            item['images']=[{'mime':'image/png' if suffix=='.png' else 'image/webp' if suffix=='.webp' else 'image/jpeg','base64':base64.b64encode(raw).decode()}]
        elif suffix in {'.pdf','.docx','.xlsx','.pptx','.odt','.ods','.odp'}:
            with tempfile.TemporaryDirectory() as temp:
                pdf=path
                if suffix!='.pdf':
                    result=subprocess.run(['/opt/scoring-runtime/bin/soffice','--headless','--convert-to','pdf','--outdir',temp,str(path)],capture_output=True,text=True,timeout=90)
                    pdf=Path(temp)/(path.stem+'.pdf')
                    if result.returncode or not pdf.is_file():raise ValueError('MANAGED_OFFICE_RENDER_FAILED: '+item['path'])
                with fitz.open(pdf) as document:
                    if pages+len(document)>50:raise ValueError('MANAGED_MEDIA_PAGE_BUDGET_EXCEEDED')
                    item['text']='\n'.join(page.get_text() for page in document)
                    for page in document:
                        png=page.get_pixmap(matrix=fitz.Matrix(1.2,1.2)).tobytes('png')
                        images.append({'mime':'image/png','base64':base64.b64encode(png).decode()})
                    pages+=len(document);item['images']=images
        else:raise ValueError('MANAGED_BINARY_FORMAT_UNSUPPORTED: '+item['path'])
    if a.base_contract=='web' and path.suffix.lower() in {'.html','.htm'}:
        from playwright.sync_api import sync_playwright
        import http.server,functools,threading
        handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(root))
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
                page=browser.new_page();item['images']=[];item['browser']={'url':item['path'],'viewports':[]}
                page.route('**/*',lambda route: route.continue_() if route.request.url.startswith(f'http://127.0.0.1:{server.server_port}/') else route.abort())
                from urllib.parse import quote
                for width,height in [(1440,900),(390,844)]:
                    page.set_viewport_size({'width':width,'height':height})
                    page.goto(f'http://127.0.0.1:{server.server_port}/'+quote(item['path']),wait_until='networkidle',timeout=20000)
                    item['images'].append({'mime':'image/png','base64':base64.b64encode(page.screenshot(full_page=True)).decode()})
                    item['browser']['viewports'].append({'width':width,'height':height,'title':page.title(),'text':page.locator('body').inner_text()})
                browser.close();pages+=2
                if pages>50:raise ValueError('MANAGED_MEDIA_PAGE_BUDGET_EXCEEDED')
        finally:server.shutdown();server.server_close()
    for index,media in enumerate(item.get('images',[])):
        name=item['sha256']+'-'+str(index)+('.png' if media['mime']=='image/png' else '.webp' if media['mime']=='image/webp' else '.jpg')
        (output/name).write_bytes(base64.b64decode(media['base64']))
        media['file']='media-evidence/'+name
    total+=len(json.dumps(item))
    if total>16*1024*1024:raise ValueError('MANAGED_EVIDENCE_BUDGET_EXCEEDED')
    rows.append(item)
(output/'evidence.json').write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
