"""Coleta segura do ranking: BisectHosting/SFTP -> snapshot SQLite -> Supabase."""
from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import uuid

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
    for suffix in ('', '-wal', '-shm'):
        try:
            manifest[suffix] = file_signature(sftp.stat(remote + suffix))
        except OSError:
            if suffix == '':
                raise
    return manifest


def download_consistent_snapshot(sftp, remote, local):
    """Rejeita a coleta se DB/WAL/SHM mudarem ou aparecerem durante o download."""
    before = remote_manifest(sftp, remote)
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
        return connection.execute('SELECT username, name, isDead, data FROM networkPlayers').fetchall()
    finally:
        connection.close()


def confirmed_stats(_blob):
    """Somente campos comprovados entram aqui; nenhum valor e inferido do BLOB."""
    return {
        'p_kills_total': None,
        'p_kills_firearm': None,
        'p_kills_melee': None,
        'p_survival_seconds': None,
    }


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
            'p_character_key': character_key,
            'p_character_name': str(character)[:80],
            'p_alive': None if dead is None else not bool(dead),
            'p_blob_sha256': hashlib.sha256(blob_bytes).hexdigest(),
            'p_observed_at': observed_at,
            **confirmed_stats(blob_bytes),
        })
    return observations


def supabase_headers(prefer=None):
    key = required('SUPABASE_SERVICE_ROLE_KEY')
    headers = {
        'apikey': key,
        'Authorization': 'Bearer ' + key,
        'Content-Type': 'application/json',
    }
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
        rpc('ingest_player_observation', item)
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
    dry_run = os.getenv('DRY_RUN', '').lower() in ('1', 'true', 'yes')
    if dry_run:
        rows = collect_rows()
        observations = extract(rows, salt)
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
        observations = extract(rows, salt)
        fingerprint = hashlib.sha256('|'.join(sorted(item['p_blob_sha256'] for item in observations)).encode()).hexdigest()
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
