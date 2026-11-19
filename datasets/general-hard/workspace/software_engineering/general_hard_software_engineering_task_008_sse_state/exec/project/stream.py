"""Legacy chunk decoder; whole simple frames still work."""
class SSEDecoder:
    def __init__(self): self.buffer=''
    def feed(self,chunk):
        self.buffer+=chunk.decode('utf-8',errors='ignore')
        frames=self.buffer.split('\n\n');self.buffer=frames.pop();result=[]
        for frame in frames:
            fields={}
            for line in frame.split('\n'):
                if ':' in line:
                    name,value=line.split(':',1);fields[name]=value.lstrip()
            if 'data' in fields:result.append({'id':fields.get('id',''),'event':fields.get('event','message'),'data':fields['data']})
        return result
    def close(self): self.buffer=''
