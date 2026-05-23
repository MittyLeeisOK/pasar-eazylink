import os, shlex
from pathlib import Path
CONFIG_FILE=Path('/etc/pasar-easylink.env')
TG_ENV=Path('/etc/sub-notify.env')
DEFAULT_CONFIG={
'PASAR_PANEL_HOST':'https://127.0.0.1','PASAR_PANEL_PORT':'8000','PASAR_API_KEY':'',
'SHLINK_API_BASE':'https://go.mitty.space/rest/v3','SHLINK_API_KEY':'','SHORT_DOMAIN':'https://go.mitty.space','SUB_BASE_URL':'https://pasar.mitty.space/sub',
'TG_BOT_TOKEN':'','TG_CHAT_ID':'','TG_THREAD_ID':'',
'PASARGUARD_DB_PATH':'/var/lib/pasarguard/db.sqlite3','NGINX_ACCESS_LOG':'/var/log/nginx/access.log','DB_MONITOR_STATE_FILE':'/var/lib/pasar-eazylink/db-monitor.state',
'DB_MONITOR_POLL_SECONDS':'15','DB_MONITOR_DEDUP_SECONDS':'120','DB_MONITOR_LOOKUP_NGINX_IP':'true','DB_MONITOR_NGINX_LOOKBACK_SECONDS':'600','DB_MONITOR_NGINX_STATUS':'200,304','DISPLAY_TIMEZONE':'local'}

def parse_env_file(path:Path)->dict:
 d={}
 if not path.exists(): return d
 for raw in path.read_text(errors='ignore').splitlines():
  s=raw.strip()
  if not s or s.startswith('#') or '=' not in s: continue
  k,v=s.split('=',1)
  try:d[k.strip()]=(shlex.split(v.strip()) or [''])[0]
  except:d[k.strip()]=v.strip().strip('"\'')
 return d

def write_env_file(path:Path,data:dict):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text('\n'.join([f"{k}={shlex.quote(str(data.get(k,'')))}" for k in DEFAULT_CONFIG])+"\n")
 os.chmod(path,0o600)

def load_config()->dict:
 if not CONFIG_FILE.exists(): write_env_file(CONFIG_FILE,DEFAULT_CONFIG.copy())
 c=DEFAULT_CONFIG.copy(); c.update(parse_env_file(CONFIG_FILE)); return c

def save_config(cfg:dict): write_env_file(CONFIG_FILE,cfg)
