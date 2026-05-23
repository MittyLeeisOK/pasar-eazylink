import re

def parse_user_agent(ua:str)->dict:
    u=ua or ''
    lu=u.lower()
    clients=[('Shadowrocket','shadowrocket'),('Stash','stash'),('Quantumult X','quantumult'),('Surge','surge'),('Clash / Mihomo','mihomo'),('Clash / Mihomo','clash'),('sing-box','sing-box'),('v2rayN','v2rayn'),('v2rayNG','v2rayng'),('Hiddify','hiddify'),('NekoBox / Nekoray','nekobox'),('NekoBox / Nekoray','nekoray')]
    client='Unknown'
    for n,k in clients:
        if k in lu: client=n; break
    device='Unknown'; osn='Unknown'
    if 'iphone' in lu: device='iPhone'; osn='iOS'
    elif 'ipad' in lu: device='iPad'; osn='iOS'
    elif 'mac os' in lu or 'macintosh' in lu or 'darwin' in lu: device='macOS'; osn='macOS'
    elif 'android' in lu: device='Android'; osn='Android'
    elif 'windows' in lu: device='Windows'; osn='Windows'
    elif 'linux' in lu: device='Linux'; osn='Linux'
    m=re.search(r'(iPhone\d+,\d+|iPad\d+,\d+)',u)
    model=m.group(1) if m else ''
    tokens=[
        'Shadowrocket' if 'shadowrocket' in lu else (client if client!='Unknown' else ''),
        'CFNetwork' if 'cfnetwork' in lu else '',
        'Darwin' if 'darwin' in lu else '',
        model,
    ]
    summary=' / '.join([p for p in tokens if p])
    if not summary and client != 'Unknown':
        summary = client
    return {'client':client,'device_type':device,'os':osn,'model':model,'summary':summary}
