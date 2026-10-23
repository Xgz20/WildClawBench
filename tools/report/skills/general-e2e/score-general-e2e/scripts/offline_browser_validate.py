"""Self-contained HTML observations in a fresh offline browser context.

No file/HTTP navigation, server, CDP, browser-policy change, scores, or rubric.
The caller supplies a SHA-bound UTF-8 HTML file and an explicit action plan.
"""
import argparse, hashlib, json, pathlib, re, sys, tempfile

SNAPSHOT = r'''() => ({
  url: location.href, title: document.title,
  viewport: {width: innerWidth, height: innerHeight},
  documentWidth: document.documentElement.scrollWidth,
  bodyWidth: document.body.scrollWidth,
  reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
  active: (() => {const e=document.activeElement; const c=getComputedStyle(e);return {tag:e.tagName,id:e.id,text:e.textContent,outline:c.outline,outlineOffset:c.outlineOffset}})(),
  controls: [...document.querySelectorAll('button,[role="button"],a,input,select,textarea,[tabindex]')].map(e=>{
    const r=e.getBoundingClientRect(), c=getComputedStyle(e), id=e.getAttribute('aria-controls'), panel=id?document.getElementById(id):null;
    return {tag:e.tagName,id:e.id,role:e.getAttribute('role'),name:e.innerText||e.getAttribute('aria-label'),tabindex:e.getAttribute('tabindex'),expanded:e.getAttribute('aria-expanded'),controls:id,
      box:{x:r.x,y:r.y,width:r.width,height:r.height},display:c.display,visibility:c.visibility,color:c.color,background:c.backgroundColor,
      outline:c.outline,transition:c.transition,animation:c.animation,
      panel:panel?{id:panel.id,hidden:panel.hidden,role:panel.getAttribute('role'),labelledby:panel.getAttribute('aria-labelledby'),text:panel.innerText}:null}
  }), headings:[...document.querySelectorAll('h1,h2,h3,h4')].map(e=>({tag:e.tagName,text:e.innerText})), bodyText:document.body.innerText
})'''

def run(args, *, emit=True):
    source=args.html.resolve(strict=True)
    if args.html.is_symlink() or not source.is_file():raise ValueError('HTML_REGULAR_FILE_REQUIRED')
    raw=source.read_bytes()
    if len(raw)>10*1024*1024:raise ValueError('HTML_SIZE_LIMIT')
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=args.expected_sha256:raise ValueError('HTML_SHA_MISMATCH')
    document=raw.decode('utf-8',errors='strict')
    plan=json.loads(args.plan.read_text(encoding='utf-8'))
    if not isinstance(plan,list) or not 1<=len(plan)<=250:raise ValueError('PLAN_INVALID')
    for step in plan:
        if not isinstance(step,dict) or step.get('action') not in ('viewport','reduced_motion','snapshot','press','click','screenshot','wait'):
            raise ValueError('PLAN_ACTION_UNSUPPORTED')
        if step['action']=='screenshot' and not re.fullmatch(r'[A-Za-z0-9_-]+\.png',step.get('name','')):
            raise ValueError('SCREENSHOT_BASENAME_REQUIRED')
        if step['action']=='press' and step.get('key') not in ('Tab','Shift+Tab','Enter','Space','Escape','ArrowDown','ArrowUp','Home','End'):
            raise ValueError('KEY_UNSUPPORTED')
        if step['action']=='viewport' and not (240<=step.get('width',0)<=3000 and 240<=step.get('height',0)<=3000):
            raise ValueError('VIEWPORT_OUT_OF_RANGE')
        if step['action']=='wait' and not 0<=step.get('ms',0)<=1000:raise ValueError('WAIT_OUT_OF_RANGE')
    output=args.output_dir.resolve()
    output.mkdir(parents=True,exist_ok=False)
    blocked,console,errors,observations=[],[],[],[]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as api:
        browser=api.chromium.launch(headless=True,args=['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run','--disable-default-apps','--disable-extensions'])
        context=browser.new_context(offline=True,service_workers='block',accept_downloads=False,permissions=[],viewport={'width':1280,'height':900})
        def abort(route):
            blocked.append({'url':route.request.url,'method':route.request.method,'resource_type':route.request.resource_type})
            route.abort('blockedbyclient')
        context.route('**/*',abort)
        page=context.new_page()
        page.on('console',lambda msg:console.append({'type':msg.type,'text':msg.text}))
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.set_content(document,wait_until='load')
        assert page.url=='about:blank','UNEXPECTED_NAVIGATION'
        for index,step in enumerate(plan):
            action=step['action'];item={'index':index,'action':action,'parameters':step}
            if action=='viewport':page.set_viewport_size({'width':step['width'],'height':step['height']})
            elif action=='reduced_motion':page.emulate_media(reduced_motion=step.get('value','reduce'))
            elif action=='snapshot':item['snapshot']=page.evaluate(SNAPSHOT)
            elif action=='press':page.keyboard.press(step['key'])
            elif action=='click':page.locator(step['selector']).click(timeout=3000)
            elif action=='wait':page.wait_for_timeout(step.get('ms',0))
            elif action=='screenshot':
                file=output/step['name'];page.screenshot(path=str(file),full_page=True)
                item['file']={'path':str(file),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
            if page.url!='about:blank':raise RuntimeError('UNEXPECTED_NAVIGATION')
            observations.append(item)
        version=browser.version
        context.close();browser.close()
    if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise RuntimeError('INPUT_CHANGED_DURING_OBSERVATION')
    result={'profile':'offline-inline-html-observation/v1','input':{'path':str(source),'sha256':digest,'size':len(raw)},'browser_version':version,'browser_url':'about:blank','page_network_policy':'offline context plus abort-all requests; no file/HTTP navigation; no server or CDP','os_network_isolation_claimed':False,'rule_or_rubric_applied':False,'blocked_page_requests':blocked,'console':console,'page_errors':errors,'observations':observations}
    (output/'observations.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if emit:
        print(json.dumps({'observations':str(output/'observations.json'),'input_sha256':digest,'browser_version':version,'steps':len(observations),'blocked_page_requests':len(blocked),'page_errors':len(errors)}))
    return result

def probe(output):
    """Exercise public synthetic HTML only; never reads a candidate or rubric."""
    with tempfile.TemporaryDirectory(prefix='general-judge-browser-probe-') as temporary:
        temporary = pathlib.Path(temporary)
        html = temporary/'probe.html'
        raw = b'<!doctype html><title>judge-offline-probe</title><button aria-expanded="false" onclick="this.setAttribute(\'aria-expanded\',\'true\')">Details</button><script>fetch("https://offline-probe.example.invalid/").catch(()=>{});</script>'
        html.write_bytes(raw)
        plan = temporary/'plan.json'
        plan.write_text(json.dumps([{'action':'snapshot'},{'action':'press','key':'Tab'},{'action':'press','key':'Enter'},{'action':'viewport','width':420,'height':900},{'action':'reduced_motion'},{'action':'snapshot'},{'action':'screenshot','name':'probe.png'}]),encoding='utf-8')
        result = run(argparse.Namespace(html=html,expected_sha256=hashlib.sha256(raw).hexdigest(),plan=plan,output_dir=output),emit=False)
        snapshots = [step['snapshot'] for step in result['observations'] if 'snapshot' in step]
        if not (snapshots[0]['controls'][0]['expanded']=='false' and snapshots[-1]['controls'][0]['expanded']=='true' and snapshots[-1]['reducedMotion'] and snapshots[-1]['viewport']['width']==420 and result['blocked_page_requests'] and not result['page_errors']):
            raise RuntimeError('OFFLINE_BROWSER_PROBE_FAILED')
        (output/'probe-input.html').write_bytes(raw)
        return {'status':'PASS','profile':result['profile'],'browser_version':result['browser_version'],'observations':str(output/'observations.json'),'fixture_sha256':hashlib.sha256(raw).hexdigest(),'candidate_used':False,'page_requests_blocked':len(result['blocked_page_requests']),'os_network_isolation_claimed':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html',type=pathlib.Path)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--plan',type=pathlib.Path)
    parser.add_argument('--probe',action='store_true',help='Validate the offline environment using a public synthetic fixture only')
    parser.add_argument('--output-dir',type=pathlib.Path,required=True)
    args=parser.parse_args()
    if args.probe:
        if args.html or args.expected_sha256 or args.plan:parser.error('--probe cannot consume candidate input')
        print(json.dumps(probe(args.output_dir)))
    else:
        if not (args.html and args.expected_sha256 and args.plan):parser.error('--html, --expected-sha256 and --plan are required')
        run(args)
