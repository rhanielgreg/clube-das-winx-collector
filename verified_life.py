"""Contrato futuro assinado por emissor confiável do servidor; nunca infere vidas por nome.

WinxLifeV1 NÃO é um campo alegadamente existente no TTF. É um contrato opt-in,
indisponível até instalar/validar um emissor autorizado e a migração do banco.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
import math
import re
import uuid
from probe_stats import anchored_value
from stats import ttf_observation_counters

UNITS = {key: 'count' for key in ('kills_total','kills_firearm','kills_melee','kills_vehicle','kills_axe',
    'kills_blunt','kills_small_blunt','kills_long_blade','kills_small_blade','kills_spear','kills_unarmed','kills_other')}
UNITS.update(played_seconds='seconds', survival_world_days='world_days', distance_total_m='meters',
             distance_walked_m='meters', distance_vehicle_m='meters')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate telemetry key')
        result[key] = value
    return result


def verify_envelope(envelope, signing_key):
    if not isinstance(envelope, dict) or not isinstance(signing_key, str) or len(signing_key) < 32:
        raise ValueError('signed source/key unavailable')
    raw, signature = envelope.get('payload_json'), envelope.get('signature')
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > 20000 or not isinstance(signature, str):
        raise ValueError('invalid source envelope')
    expected = hmac.new(signing_key.encode('utf-8'), raw.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError('source signature mismatch')
    payload = json.loads(raw, object_pairs_hook=unique_object)
    if payload.get('schema') != 'winx-life-v1' or not isinstance(payload.get('account_id'), str) or not re.fullmatch(r'[0-9]{17}', payload['account_id']):
        raise ValueError('unverified source account/schema')
    if any(not isinstance(payload.get(field),str) or not 1<=len(payload[field])<=80 for field in ('source_username','character_name')):
        raise ValueError('signed snapshot binding absent')
    if not uuid.UUID(payload['world_id']).int or not uuid.UUID(payload['life_id']).int:
        raise ValueError('empty source identity')
    timestamp = datetime.fromisoformat(payload['source_observed_at'].replace('Z', '+00:00'))
    if timestamp.tzinfo is None or timestamp > datetime.now(timezone.utc) + timedelta(minutes=1):
        raise ValueError('invalid source timestamp')
    if payload.get('alive') is not None and not isinstance(payload['alive'], bool):
        raise ValueError('invalid life state')
    values = payload.get('metrics')
    if not isinstance(values, dict):
        raise ValueError('metrics absent')
    for key, record in values.items():
        if key not in UNITS or not isinstance(record, dict) or record.get('unit') != UNITS[key] or record.get('scope') != 'life':
            raise ValueError('unknown metric/unit/scope')
        n = record.get('value')
        if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or n < 0 or n > 31536000000:
            raise ValueError('invalid metric value')
        if UNITS[key] == 'count' and (int(n) != n or n > 2000000000):
            raise ValueError('invalid counter')
    return payload


def extract_verified(rows, salt, signing_key, *, read_envelope=None, observed_at=None):
    observations = []
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    for username, character, dead, blob in rows:
        if not username or not character:
            continue
        raw_blob = blob or b''
        if read_envelope is None and dead == 1 and b'WinxLifeV1' not in raw_blob:
            # Morto legado continua no arquivo antigo, sem atribuir uma vida nova.
            # Ausência/ambiguidade de vivo ou desconhecido NÃO é ignorada.
            continue
        # Leitura em modData; não escreve no save/mod/servidor.
        envelope = read_envelope(raw_blob) if read_envelope else json.loads(anchored_value(raw_blob, 'WinxLifeV1'))
        source = verify_envelope(envelope, signing_key)
        if source['source_username'] != str(username) or source['character_name'] != str(character):
            raise ValueError('signed identity differs from SQLite row')
        alive = dead == 0 if isinstance(dead,(int,bool)) and dead in (0,1) else None
        if source.get('alive') is not alive:
            raise ValueError('signed life state differs from SQLite snapshot')
        metrics = {key: {**record, 'validated': True} for key, record in source['metrics'].items()}
        if source.get('ttf_counters_are_lifetime') is True:
            counters = ttf_observation_counters(raw_blob)
            if counters is None:
                raise ValueError('TTF counters unavailable')
            digest = hashlib.sha256(json.dumps(counters, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            if not hmac.compare_digest(digest, str(source.get('ttf_metrics_digest', ''))):
                raise ValueError('signed TTF digest differs from snapshot')
            for name, value in counters.items():
                if name in metrics and metrics[name]['value'] != value:
                    raise ValueError('signed metric differs from TTF counter')
                metrics[name] = {'value': value, 'unit': UNITS[name], 'scope': 'life', 'validated': True,
                                 'coverage': 'complete_life' if source.get('ttf_coverage') == 'complete_life' else 'observed_lower_bound'}
        observations.append({
            'p_world_id': str(uuid.UUID(source['world_id'])),
            'p_account_token': hmac.new(salt.encode(), ('account:' + source['account_id']).encode(), hashlib.sha256).hexdigest(),
            'p_life_token': hmac.new(salt.encode(), ('life:' + source['life_id']).encode(), hashlib.sha256).hexdigest(),
            'p_character_name': str(character)[:80], 'p_steam_username': str(username)[:80],
            'p_alive': alive, 'p_observed_at': observed_at,
            'p_source_sha256': hashlib.sha256(raw_blob).hexdigest(), 'p_metrics': metrics,
        })
    return observations
