"""Bounded explicit support/contradiction checks, never an unrestricted semantic Judge."""
import re,unicodedata
def compact(v):return re.sub(r'\s+','',unicodedata.normalize('NFKC',v)).casefold()
def signal(fid,quote,channel):
 s=compact(quote);raw=unicodedata.normalize('NFKC',quote).casefold();has=lambda pat:bool(re.search(pat,s,re.I));hasraw=lambda pat:bool(re.search(pat,raw,re.I))
 return {
 'F01':lambda:has(r'青禾工单|qinghedesk'),
 'F02':lambda:'2.1' in re.findall(r'(?<![0-9])[0-9]+(?:\.[0-9]+)+(?![0-9])',s),
 'F03':lambda:has(r'team'),
 'F04':lambda:has(r'(?<![0-9])149(?:\.0+)?(?![0-9])(?!\.[0-9])|一百四十九|onehundred(?:and)?forty.nine') and has(r'cny|rmb|人民币|元|yuan') and has(r'工作区|workspace') and has(r'月|month'),
 'F05':lambda:has(r'(?<![0-9])6(?:\.0+)?%|百分之六(?![十百一二三四五六七八九])|sixpercent|(?<![0-9.])0\.06(?![0-9])') and has(r'税|vat'),
 'F06':lambda:hasraw(r'2026\s*[-/年]\s*11\s*[-/月]\s*18(?![0-9])|18\s+november\s+2026|november\s+18,?\s+2026') and hasraw(r'(?<![0-9])(?:09:00|9:00|9\s*a\.?m\.?)(?![0-9])') and has(r'asia/shanghai|utc\+0?8|gmt\+0?8'),
 'F07':lambda:has(r'(?<![0-9])14(?![0-9])|十四|fourteen') and has(r'试用|trial'),
 'F08':lambda:has(r'(?<![0-9])10(?![0-9])|十位|十名|tenmembers') and has(r'成员|members') and has(r'工作区|workspace'),
 'F09':lambda:has(r'外发|消息|messages|outgoing') and has(r'发送|确认|sent|send|confirmation|review'),
 'F10':lambda:has(r'csv') and has(r'导出|export'),
 'F11':lambda:has(r'中国大陆|mainlandchina') and has(r'认证|certification|certified'),
 'F12':lambda:has(r'pdf') and has(r'ocr|扫描|scanned|searchable|搜索')
 }[fid]()
def clauses(text):
 # Decimal price/version points remain inside their clauses.
 return [s.strip() for s in re.split(r'[。！？!?;；,，\n]+|(?<!\d)\.(?!\d)',text) if s.strip()]
def negated(s,match):
 prefix=s[max(0,match.start()-90):match.start()];matched=s[match.start():match.end()];span=s[max(0,match.start()-30):min(len(s),match.end()+30)]
 english_tail=r'\b(?:no|not|never|without|neither|cannot|can.t)\b(?:\s+[A-Za-z]+){0,3}\s*$'
 chinese_tail=r'(?:不(?:会|能|再)?|无需|不需要|没有|未|并非|不(?:宣称|作|提供|承诺|声称|支持|保证|意味着|代表|表示).{0,10})$'
 coordinated_object=bool(re.search(r'\bnot\s+(?:offer|promise|provide|claim)\b.{0,120}\bor\s*$',prefix,re.I) and not re.search(r'\b(?:but|however|yet)\b',prefix,re.I))
 return bool(re.search(english_tail,prefix,re.I) or coordinated_object or re.search(chinese_tail,prefix) or re.search(r'\b(?:not|never|cannot)\b|不(?:会|受|支持|在|含)|未|无需|没有',matched,re.I) or re.search(r'outside\s+(?:current\s+)?support',span,re.I))
def historic(s):return bool(re.search(r'旧|历史|撤销|废止|不再有效|原报价|\b(?:old|previous|historical|withdrawn|revoked|superseded|retired|obsolete)\b',s,re.I))
RULES=[
 ('F09','automatic_external_send',r'(?:自动|自行).{0,12}发送|(?:sent|sends?|send|sending).{0,20}(?:automatically|on\s+their\s+own)|automatic\s+(?:message\s+)?send(?:ing)?'),
 ('F07','automatic_billing',r'自动.{0,6}(?:扣款|收费)|(?:charge|charges|charged|billing).{0,18}automatically|automatic\s+(?:charge|charging|billing)'),
 ('F07','card_required',r'(?:需要|必须|要求).{0,8}(?:绑卡|支付卡)|(?:payment\s+)?card\s+is\s+required|(?:requires?|require).{0,10}(?:payment\s+)?card'),
 ('F12','scanned_OCR_supported',r'(?:支持|可).{0,10}(?:扫描PDF|扫描.{0,5}PDF).{0,12}OCR|(?:scanned[\s-]*PDF\s*OCR|OCR\s+for\s+scanned\s+PDFs).{0,18}(?:supported|included|available)|supports?.{0,12}(?:scanned[\s-]*PDF|OCR)'),
 ('F11','certification_claim',r'已(?:获|通过|取得).{0,12}安全认证|(?:certified\s+security|security[-\s]certified)|\b(?:has|have|is|are)\b.{0,15}(?:security\s+certification|certified)'),
 ('F11','global_service',r'(?:全球|所有地区).{0,10}(?:提供|支持|服务)|(?:global|worldwide)\s+(?:service|availability)|(?:available|supported).{0,10}worldwide'),
 ('F08','unlimited_members',r'人数不限|成员不限|无限成员|unlimited\s+(?:members|users)|no\s+(?:member|user)\s+limit'),
 ('F10','everyone_export_all_workspaces',r'所有人.{0,12}导出|跨工作区.{0,6}导出|everyone\s+can\s+export|export\s+(?:all|every)\s+workspaces?'),
 ('F04','per_user_or_year_price',r'(?:149|99|129).{0,24}(?:每人|人均|每年|年价)|(?:149|99|129).{0,32}(?:per\s+user|per\s+year)'),
 ('F04','current_tax_inclusive_quote',r'(?:149).{0,24}含税|(?:149).{0,45}(?:including\s+(?:vat|tax)|tax[-\s]inclusive|(?:vat|tax)\s+included)'),
 ('F06','already_released',r'已经上线|已正式发布|现已上线|(?:has|have)\s+(?:already\s+)?launched|is\s+now\s+available|completed\s+rollout'),
 ('EXTRA','unsupported_benefit_promise',r'行业领先|保证.{0,8}(?:节省|收益|提效)|proven\s+time\s+savings|guaranteed\s+(?:savings|results)')]
def contradictions(text,eligible):
 found=[]
 for clause in clauses(text):
  for fid,code,pattern in RULES:
   if fid!='EXTRA' and not eligible.get(fid,False):continue
   for m in re.finditer(pattern,clause,re.I):
    # 'no member limit' is itself the forbidden positive unlimited assertion.
    polarity=not negated(clause,m) or code=='unlimited_members' and m.group().lower().startswith('no ')
    if polarity and not historic(clause):found.append({'fact_id':fid,'code':code,'clause':clause,'matched':m.group()})
  for fid,pattern,code in [('F04',r'(?:99|129)\s*(?:元|人民币)|(?:CNY|RMB|人民币)\s*(?:99|129)\b','old_price_current'),('F02',r'(?:version|版本|版)\s*(?:1\.0|2\.0)\b','old_version_current'),('F07',r'30\s*(?:天|[-\s]?day).{0,10}(?:试用|trial)|(?:试用|trial).{0,10}30\s*(?:天|[-\s]?day)','old_trial_current'),('F06',r'11月1日|November\s+1(?:st)?\b|2026-11-01','old_release_date_current')]:
   if eligible.get(fid,False) and re.search(pattern,clause,re.I) and not historic(clause):found.append({'fact_id':fid,'code':code,'clause':clause})
 return found
