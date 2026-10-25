"""Leitor opt-in do TTF MP STABLE já instalado. Não instala nem modifica mods.

Perfil conferido por leitura em 25/10/2026. Exige pin das fontes e namespace
operacional estável; nunca usa nome ou rowid como identidade de vida.
"""
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import hashlib
import hmac
import math
import re
import uuid
from probe_stats import anchored_value
from stats import ttf_observation_counters
from verified_life import UNITS

SOURCE_FILES = {
 'media/lua/server/TTF_StatsMP_Server.lua':'9c3f2ce7eaa2dd5ef99ec7a92698bf615a856639c799e914ed83580a7b806e17',
 'media/lua/client/TTF_StatsMP_Client.lua':'05e717622b52b3fc340ab5654bfc89457ebe2b28300c9ce0db14e5c9ed105cdc',
 'media/lua/client/TwisTonFireStats.lua':'b6d8b95ca1a4073195978ceb95d8776ccb3aeec540c35da0a94bc4cc477cd413',
}

def verify_source_files(sftp, root, local_folder):
    """Somente stat/get. Mudança de código exige nova revisão de unidades/ciclo."""
    if not root or not root.startswith('/') or '..' in PurePosixPath(root).parts:
        raise ValueError('explicit absolute TTF_SOURCE_ROOT required')
    for index,(relative,expected) in enumerate(SOURCE_FILES.items()):
        remote=str(PurePosixPath(root)/relative)
        before=sftp.stat(remote)
        if not 0 < before.st_size <= 200000:raise ValueError('source file outside expected limits')
        local=Path(local_folder)/('source-profile-'+str(index)+'.lua')
        sftp.get(remote,str(local))
        after=sftp.stat(remote)
        if (before.st_size,before.st_mtime)!=(after.st_size,after.st_mtime) or hashlib.sha256(local.read_bytes()).hexdigest()!=expected:
            raise ValueError('installed TTF source profile changed; review required')

def extract_saved_lives(rows,salt,namespace,*,observed_at=None):
    namespace=uuid.UUID(namespace)
    if not namespace.int or not isinstance(salt,str) or len(salt)<16:raise ValueError('stable source namespace and private salt required')
    observed_at=observed_at or datetime.now(timezone.utc).isoformat()
    result=[];identities=set()
    for username,name,dead,blob,steam_id,world in rows:
        if not username or not name:raise ValueError('source row identity missing')
        if isinstance(steam_id,bool) or not isinstance(steam_id,(int,str)) or not re.fullmatch(r'[0-9]{17}',str(steam_id)):
            raise ValueError('SQLite Steam account missing or ambiguous')
        if not isinstance(world,str) or not 0<len(world)<=200:raise ValueError('source world label missing')
        metadata=anchored_value(blob or b'','TTFStatsMP')
        if not isinstance(metadata,dict) or metadata.get('username')!=str(username):raise ValueError('saved TTF identity does not match source row')
        identity=metadata.get('characterID')
        match=re.fullmatch(r'.+_([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)_([0-9]{1,6})',identity or '') if isinstance(identity,str) and len(identity)<=300 else None
        if not match or not 946684800<float(match.group(1))<=datetime.now(timezone.utc).timestamp()+60:
            raise ValueError('server-generated TTF life identity not verified')
        pair=(world,str(steam_id),identity)
        if pair in identities:raise ValueError('duplicate source life rows require investigation')
        identities.add(pair)
        counters=ttf_observation_counters(blob or b'')
        if counters is None:raise ValueError('TTF categories inconsistent')
        try:distance=anchored_value(blob,'distanceTracker')
        except (ValueError,KeyError,TypeError,IndexError):distance=None
        if distance is not None:
            if isinstance(distance,bool) or not isinstance(distance,(int,float)) or not math.isfinite(distance) or not 0<=distance<=31536000000:
                raise ValueError('invalid source distance')
            counters['distance_total_m']=distance
        # O mod pode ter sido instalado no meio de uma vida; não comprova cobertura desde o nascimento.
        metrics={key:{'value':value,'unit':UNITS[key],'scope':'life','validated':True,'coverage':'observed_lower_bound'} for key,value in counters.items()}
        result.append({'p_world_id':str(uuid.uuid5(namespace,world)),
            'p_account_token':hmac.new(salt.encode(),('account:'+str(steam_id)).encode(),hashlib.sha256).hexdigest(),
            'p_life_token':hmac.new(salt.encode(),('ttf-mp-life:'+identity).encode(),hashlib.sha256).hexdigest(),
            'p_character_name':str(name)[:80],'p_steam_username':str(username)[:80],
            'p_alive':dead==0 if isinstance(dead,(int,bool)) and dead in (0,1) else None,
            'p_observed_at':observed_at,'p_source_sha256':hashlib.sha256(blob or b'').hexdigest(),'p_metrics':metrics})
    return result
