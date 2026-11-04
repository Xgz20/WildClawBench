#!/usr/bin/env python3
"""Read-only, identity-bound native termination audit; never assign a score."""
from pathlib import Path
import argparse,hashlib,json

FIELDS=('conversation_id','conversation_request_id','trace_id','message_id','model',
    'http_begin_status_code','http_end_status_code','finish_flag','finish_reason','model_error',
    'total_chunks','total_cost_ms','prompt_tokens','completion_tokens','text_content_chars','recv_length','origin_length')

def audit(binding_path,session_path,log_path):
    binding=json.loads(binding_path.read_text(encoding='utf-8'))
    records=[json.loads(line) for line in session_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    last=next(row for row in reversed(records) if row.get('type')=='message' and row.get('role')=='assistant')
    provider=last.get('providerData',{});request=binding['runtime_snapshot']['request']
    trace=provider['traceId'];rid=binding['request_id'];sid=binding['conversation_id']
    if provider.get('conversationRequestId')!=rid or last.get('sessionId')!=sid:
        raise ValueError('NATIVE_TERMINATION_IDENTITY_MISMATCH')
    raw=''.join(block.get('text','') for block in last['content'] if block.get('type')=='output_text')
    # Earlier progress messages may also be output_text. The last SDK message
    # must be present intact, never compared by an arbitrary substring prefix.
    sdk_message_id=last.get('id',provider['messageId'])
    blocks=[block.get('text','') for block in request['assistantMessage']['content']
        if block.get('type') in {'text','output_text'} and block.get('messageId',sdk_message_id)==sdk_message_id]
    if not blocks or blocks[-1]!=raw:raise ValueError('NATIVE_TERMINATION_TEXT_MISMATCH')
    ends=[];events=[];digest=hashlib.sha256()
    with log_path.open('rb') as handle:
        for number,rawline in enumerate(handle,1):
            digest.update(rawline);line=rawline.decode('utf-8',errors='replace').rstrip('\n')
            if 'qua.end: ' in line and 'SseMonitor' in line:
                try:value=json.loads(line.split('qua.end: ',1)[1])
                except json.JSONDecodeError:continue
                if value.get('trace_id')!=trace or value.get('conversation_request_id')!=rid:continue
                ends.append({'line':number,'line_sha256':hashlib.sha256(rawline).hexdigest(),
                    'fields':{k:value.get(k) for k in FIELDS}})
            elif sid in line and 'RESULT: completed successfully' in line:
                # Some native versions omit the session ID on ACP RESULT;
                # record only lines carrying the same explicit session ID.
                events.append({'line':number,'text':line})
    if not ends or ends[-1]['fields']['message_id']!=provider.get('messageId'):
        raise ValueError('NATIVE_TERMINAL_MODEL_MESSAGE_MISSING')
    final=ends[-1]['fields'];warnings=[]
    if not final.get('finish_reason'):warnings.append('missing_model_finish_reason')
    if raw and final.get('prompt_tokens') in {'0',0} and final.get('completion_tokens') in {'0',0}:
        warnings.append('zero_usage_despite_nonempty_text')
    return {'schema_version':'workbuddy-native-termination-audit/v1',
        'identity':{'conversation_id':sid,'request_id':rid,'trace_id':trace,'message_id':provider['messageId']},
        'input_locks':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in [binding_path,session_path]],
        'native_log':{'path':str(log_path),'sha256':digest.hexdigest()},
        'native_request_state':request['state'],'last_output_chars':len(raw),
        'original_raw_and_runtime_output_equal':True,'model_ends':ends,'bound_terminal_events':events,
        'warnings':warnings,'candidate_or_score_modified':False,'root_cause_upstream_protocol_proven':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-binding',type=Path,required=True)
    parser.add_argument('--session-jsonl',type=Path,required=True)
    parser.add_argument('--native-log',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    data=audit(args.runtime_binding,args.session_jsonl,args.native_log)
    with args.output.open('x',encoding='utf-8') as handle:json.dump(data,handle,ensure_ascii=False,indent=2);handle.write('\n')
    print(json.dumps({'status':'PASS','output':str(args.output),'warnings':data['warnings'],'model_end_count':len(data['model_ends'])}))
