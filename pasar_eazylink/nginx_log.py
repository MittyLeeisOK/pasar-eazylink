import re
from datetime import datetime, timezone
from pathlib import Path

LOG_RE=re.compile(r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>[A-Z]+) (?P<path>\S+) [^"]+" (?P<status>\d{3}) (?P<body>\d+|-) "[^"]*" "(?P<ua>[^"]*)"')

def parse_nginx_time(raw:str)->datetime:
    return datetime.strptime(raw,'%d/%b/%Y:%H:%M:%S %z')

def parse_nginx_access_line(line:str)->dict|None:
    m=LOG_RE.search(line.strip())
    if not m:return None
    d=m.groupdict();
    return {'remote_addr':d['ip'],'time':parse_nginx_time(d['time']),'method':d['method'],'path':d['path'],'status':d['status'],'body_bytes':int(d['body']) if d['body'].isdigit() else 0,'user_agent':d['ua']}

def read_tail(path:str,max_bytes:int=5*1024*1024)->list[str]:
    p=Path(path)
    if not p.exists(): return []
    with p.open('rb') as f:
        f.seek(0,2); size=f.tell(); f.seek(max(0,size-max_bytes))
        return f.read().decode(errors='ignore').splitlines()

def find_matching_request(log_path:str,db_created_at:datetime,user_agent:str,window_seconds:int,allowed_statuses:set[str])->dict|None:
    db_local=db_created_at.astimezone()
    c=[]
    for ln in read_tail(log_path):
        r=parse_nginx_access_line(ln)
        if not r or not r['path'].startswith('/sub/') or r['status'] not in allowed_statuses or r['method'] not in {'GET','HEAD'}: continue
        diff=abs((r['time'].astimezone()-db_local).total_seconds())
        if diff>window_seconds: continue
        c.append((r['user_agent']==(user_agent or ''), r['method']=='GET', r['status']=='200', r['body_bytes'], -diff, r))
    if not c: return None
    c.sort(reverse=True)
    return c[0][-1]
