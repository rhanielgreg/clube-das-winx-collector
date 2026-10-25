"""Coleta segura do ranking: BisectHosting/SFTP -> snapshot SQLite -> Supabase."""
from datetime import datetime, timezone
import errno
import hashlib
import logging
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import uuid
from stats import confirmed_stats
from verified_life import extract_verified
from ttf_saved_life import extract_saved_lives, verify_source_files

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'), format='%(asctime)s %(levelname)s %(message)s')
LOG = logging.getLogger('winx-collector')
SESSION = None


def required(key):
    value = os.getenv(key, '').strip()
    if not value:
        raise RuntimeError(f'Variavel obrigatoria ausente: {key}')
    return value


def http_session():
    global SESSION
    if SESSION is None:
        import requests
        SESSION = requests.Session()
    return SESSION


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def file_signature(attributes):
    return attributes.st_size, attributes.st_mtime


def remote_manifest(sftp, remote):
    manifest = {}
    for suffix in ('', '-wal', '-shm', '-journal'):
        try:
            manifest[suffix] = file_signature(sftp.stat(remote + suffix))
        except OSError as error:
            if suffix == '' or not (isinstance(error,FileNotFoundError) or error.errno==errno.ENOENT):
                raise
    return manifest


def download_consistent_snapshot(sftp, remote, local):
    """Rejeita a coleta se DB/WAL/SHM mudarem ou aparecerem durante o download."""
    before = remote_manifest(sftp, remote)
    if before.get('-journal',(0,))[0]>0:
        raise ValueError('players.db possui journal ativo; tentar novamente sem alterar a origem')
    for suffix in before:
        sftp.get(remote + suffix, str(local) + suffix)
    after = remote_manifest(sftp, remote)
    if before != after:
        raise ValueError('players.db mudou durante o download')

    connection = sqlite3.connect(str(local))
    try:
        connection.execute('PRAGMA query_only = ON')
        check = connection.execute('PRAGMA integrity_check').fetchone()[0]
        if check != 'ok':
            raise ValueError('Falha de integridade do SQLite')
        fields='username, name, isDead, data, steamid, world' if os.getenv('LIFE_PIPELINE_VERSION','').strip()=='ttf-mp-v1' else 'username, name, isDead, data'
        return connection.execute('SELECT '+fields+' FROM networkPlayers').fetchall()
    finally:
        connection.close()


def extract(rows, salt):
    observed_at = utcnow()
    observations = []
    for username, character, dead, blob in rows:
        if not username or not character:
            continue
        blob_bytes = blob or b''
        player_key = hashlib.sha256(f'{salt}:player:{username}'.encode()).hexdigest()
        character_key = hashlib.sha256(f'{salt}:character:{username}:{character}'.encode()).hexdigest()
        observations.append({
            'p_player_key': player_key,
            'p_steam_username': str(username)[:80],
            'p_character_key': character_key,
            'p_character_name': str(character)[:80],
            'p_alive': dead == 0 if isinstance(dead,(int,bool)) and dead in (0,1) else None,
            'p_blob_sha256': hashlib.sha256(blob_bytes).hexdigest(),
            'p_observed_at': observed_at,
            **confirmed_stats(blob_bytes),
        })
    return observations


def supabase_headers(prefer=None):
    key = required('SUPABASE_SERVICE_ROLE_KEY')
    headers = {
        'apikey': key,
        'Content-Type': 'application/json',
    }
    if not key.startswith('sb_'):
        headers['Authorization'] = 'Bearer ' + key
    if prefer:
        headers['Prefer'] = prefer
    return headers


def supabase_url(path):
    return required('SUPABASE_URL').rstrip('/') + '/rest/v1/' + path.lstrip('/')


def rpc(name, payload):
    response = http_session().post(supabase_url('rpc/' + name), json=payload, headers=supabase_headers(), timeout=25)
    response.raise_for_status()
    if not response.content:
        return None
    return response.json()


def acquire_lock(owner):
    ttl = int(os.getenv('COLLECTOR_LOCK_TTL_SECONDS', '240'))
    return bool(rpc('acquire_collector_lock', {'p_owner': owner, 'p_ttl_seconds': ttl}))


def release_lock(owner):
    try:
        rpc('release_collector_lock', {'p_owner': owner})
    except Exception:
        LOG.exception('Nao foi possivel liberar o lock; ele expirara automaticamente')


def begin_run():
    response = http_session().post(supabase_url('collector_runs'), json={'status': 'running'},
                                   headers=supabase_headers('return=representation'), timeout=20)
    response.raise_for_status()
    return response.json()[0]['id']


def finish_run(run_id, status, count=0, error_code=None, fingerprint=None):
    payload = {
        'status': status,
        'finished_at': utcnow(),
        'records_seen': count,
        'error_code': error_code,
        'source_fingerprint': fingerprint,
    }
    response = http_session().patch(supabase_url(f'collector_runs?id=eq.{run_id}'), json=payload,
                                    headers=supabase_headers('return=minimal'), timeout=20)
    response.raise_for_status()


def push(observations):
    for item in observations:
        rpc('ingest_life_observation_v1' if os.getenv('LIFE_PIPELINE_VERSION', '').strip() in ('life-v1','ttf-mp-v1') else 'ingest_player_observation', item)
    LOG.info('Sincronizados %d personagens', len(observations))


def collect_rows():
    import paramiko
    client = paramiko.SSHClient()
    with tempfile.TemporaryDirectory() as folder:
        known_hosts_file = Path(folder) / 'known_hosts'
        known_hosts_file.write_text(required('SFTP_KNOWN_HOSTS').rstrip() + '\n', encoding='utf-8')
        client.load_host_keys(str(known_hosts_file))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(
                hostname=required('SFTP_HOST'),
                port=int(os.getenv('SFTP_PORT', '2022')),
                username=required('SFTP_USER'),
                password=required('SFTP_PASSWORD'),
                timeout=20,
                auth_timeout=20,
                banner_timeout=20,
                look_for_keys=False,
                allow_agent=False,
            )
            sftp = client.open_sftp()
            try:
                if os.getenv('LIFE_PIPELINE_VERSION','').strip()=='ttf-mp-v1':
                    verify_source_files(sftp,required('TTF_SOURCE_ROOT'),folder)
                for attempt in range(1, 4):
                    local = Path(folder) / 'players.db'
                    try:
                        return download_consistent_snapshot(sftp, required('SFTP_DB_PATH'), local)
                    except (sqlite3.DatabaseError, ValueError, OSError):
                        if attempt == 3:
                            raise
                        delay = 2 ** attempt
                        LOG.warning('Snapshot inconsistente/indisponivel, tentativa %d/3; retry em %ds', attempt, delay)
                        for suffix in ('', '-wal', '-shm'):
                            (Path(folder) / ('players.db' + suffix)).unlink(missing_ok=True)
                        time.sleep(delay)
            finally:
                sftp.close()
        finally:
            client.close()


def main():
    salt = required('PLAYER_HASH_SALT')
    pipeline = os.getenv('LIFE_PIPELINE_VERSION', '').strip()
    if pipeline not in ('', 'legacy', 'life-v1', 'ttf-mp-v1'):
        raise ValueError('unsupported life pipeline version')
    def extract_for_pipeline(rows):
        if pipeline=='ttf-mp-v1':return extract_saved_lives(rows,salt,required('LIFE_SOURCE_NAMESPACE_UUID'))
        return extract_verified(rows,salt,required('LIFE_ATTESTATION_KEY')) if pipeline == 'life-v1' else extract(rows,salt)
    if pipeline in ('life-v1','ttf-mp-v1'):
        # Verificação somente leitura, antes de coletar/escrever. Nunca fallback
        # silencioso para mesclar vidas por nome quando o contrato novo falhar.
        contract = rpc('get_service_pipeline_readiness_v1', {})
        if not isinstance(contract, dict) or contract.get('catalog_count') != 100 or contract.get('contract_ready') is not True:
            raise ValueError('life contract/catalog not installed')
    dry_run = os.getenv('DRY_RUN', '').lower() in ('1', 'true', 'yes')
    if dry_run:
        if os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_SERVICE_ROLE_KEY'):
            rpc('get_public_ranking_status', {})
            LOG.info('Conexao Supabase validada em modo somente leitura')
        rows = collect_rows()
        observations = extract_for_pipeline(rows)
        LOG.info('DRY_RUN concluido: %d personagens; nenhuma informacao enviada', len(observations))
        return

    owner = str(uuid.uuid4())
    if not acquire_lock(owner):
        LOG.info('Outra coleta esta ativa; execucao encerrada sem erro')
        return

    run_id = None
    try:
        run_id = begin_run()
        rows = collect_rows()
        observations = extract_for_pipeline(rows)
        hash_field = 'p_source_sha256' if pipeline in ('life-v1','ttf-mp-v1') else 'p_blob_sha256'
        fingerprint = hashlib.sha256('|'.join(sorted(item[hash_field] for item in observations)).encode()).hexdigest()
        push(observations)
        finish_run(run_id, 'success', len(observations), fingerprint=fingerprint)
    except Exception as error:
        error_code = type(error).__name__[:80]
        LOG.exception('Coleta falhou (%s); nenhuma credencial foi registrada', error_code)
        if run_id:
            try:
                finish_run(run_id, 'failed', error_code=error_code)
            except Exception:
                LOG.exception('Tambem falhou o registro remoto do erro')
        raise
    finally:
        release_lock(owner)


if __name__ == '__main__':
    main()
