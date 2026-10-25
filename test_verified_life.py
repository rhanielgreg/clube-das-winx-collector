import hashlib
import hmac
import json
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from verified_life import extract_verified, verify_envelope
from stats import ttf_observation_counters
from collector import push

KEY='local-fixture-key-not-a-production-secret'
WORLD='f0000000-0000-4000-8000-000000000001'
LIFE='f0000000-0000-4000-8000-000000000002'

def signed(**extra):
    body={'schema':'winx-life-v1','world_id':WORLD,'life_id':LIFE,'account_id':'76561198000000000','source_username':'Conta','character_name':'Nome',
          'source_observed_at':datetime.now(timezone.utc).isoformat(),'alive':True,
          'metrics':{'kills_total':{'value':1000,'unit':'count','scope':'life','coverage':'complete_life'}}}
    body.update(extra)
    raw=json.dumps(body,separators=(',',':'),sort_keys=True)
    return {'payload_json':raw,'signature':hmac.new(KEY.encode(),raw.encode(),hashlib.sha256).hexdigest()}

def encoded_string(value):
    raw=value.encode('utf-8')
    return b'\x00'+struct.pack('>H',len(raw))+raw

class VerifiedLifeTests(unittest.TestCase):
    def test_signed_identity_is_not_character_name(self):
        one=extract_verified([('Conta','Mesmo nome',0,b'one')],'salt',KEY,read_envelope=lambda _:signed(character_name='Mesmo nome'))[0]
        two=extract_verified([('Conta','Mesmo nome',0,b'two')],'salt',KEY,
            read_envelope=lambda _:signed(life_id='f0000000-0000-4000-8000-000000000003',character_name='Mesmo nome'))[0]
        self.assertEqual(one['p_account_token'],two['p_account_token'])
        self.assertNotEqual(one['p_life_token'],two['p_life_token'])
        self.assertNotIn('76561198000000000',json.dumps(one))

    def test_tamper_missing_identity_wrong_units_and_state_are_rejected(self):
        bad=signed();bad['payload_json']=bad['payload_json'].replace('1000','9000')
        for envelope in [bad,signed(account_id='Nome Steam'),signed(world_id='00000000-0000-0000-0000-000000000000'),
                         signed(metrics={'survival_world_days':{'value':5,'unit':'seconds','scope':'life'}}),
                         signed(metrics={'kills_total':{'value':True,'unit':'count','scope':'life'}})]:
            with self.assertRaises((ValueError,KeyError)):
                verify_envelope(envelope,KEY)
        with self.assertRaises(ValueError):
            extract_verified([('Conta','Nome',1,b'data')],'salt',KEY,read_envelope=lambda _:signed(alive=True))
        with self.assertRaises(ValueError):
            extract_verified([('Conta','Nome',0,b'no-attestation')],'salt',KEY)

    def test_real_anonymized_ttf_categories_include_vehicle_once(self):
        samples=json.loads((Path(__file__).parent/'fixtures/ttf_only.json').read_text())
        for sample in samples:
            blob=bytes.fromhex(sample['ttf_only_hex']);counters=ttf_observation_counters(blob)
            self.assertEqual(counters['kills_total'],sample['expected_total'])
            self.assertEqual(counters['kills_total'],sum(counters[k] for k in ['kills_firearm','kills_melee','kills_vehicle','kills_other']))
            digest=hashlib.sha256(json.dumps(counters,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            envelope=signed(metrics={},ttf_counters_are_lifetime=True,ttf_metrics_digest=digest,ttf_coverage='complete_life')
            augmented=blob+encoded_string('WinxLifeV1')+encoded_string(json.dumps(envelope))
            result=extract_verified([('Conta','Nome',0,augmented)],'salt',KEY)[0]
            self.assertEqual(result['p_metrics']['kills_vehicle']['value'],counters['kills_vehicle'])
            self.assertEqual(result['p_metrics']['kills_total']['value'],sample['expected_total'])

    def test_new_pipeline_does_not_fall_back_to_legacy(self):
        with patch.dict(os.environ,{'LIFE_PIPELINE_VERSION':'life-v1'}),patch('collector.rpc') as rpc:
            push([{'p_life_token':'fixture'}])
            self.assertEqual(rpc.call_args.args[0],'ingest_life_observation_v1')
        with patch.dict(os.environ,{'LIFE_PIPELINE_VERSION':'legacy'}),patch('collector.rpc') as rpc:
            push([{'p_character_key':'fixture'}])
            self.assertEqual(rpc.call_args.args[0],'ingest_player_observation')

    def test_main_uses_new_fingerprint_and_records_success_or_failure(self):
        from collector import main
        settings={'PLAYER_HASH_SALT':'fixture-salt','LIFE_PIPELINE_VERSION':' life-v1 ','LIFE_ATTESTATION_KEY':KEY,'DRY_RUN':'false'}
        observation=extract_verified([('Conta','Nome',0,b'data')],'fixture-salt',KEY,read_envelope=lambda _:signed())[0]
        for broken in (False,True):
            with patch.dict(os.environ,settings),patch('collector.rpc',return_value={'catalog_count':100,'contract_ready':True}) as rpc, \
                 patch('collector.acquire_lock',return_value=True),patch('collector.release_lock') as release, \
                 patch('collector.begin_run',return_value='fixture-run'),patch('collector.finish_run') as finish, \
                 patch('collector.collect_rows',return_value=[]),patch('collector.extract_verified') as extract, \
                 patch('collector.LOG'):
                if broken:extract.side_effect=ValueError('fixture source not verified')
                else:extract.return_value=[observation]
                if broken:
                    with self.assertRaises(ValueError):main()
                    self.assertEqual(finish.call_args.args[1],'failed')
                    self.assertFalse(any(c.args[0]=='ingest_life_observation_v1' for c in rpc.call_args_list))
                else:
                    main()
                    self.assertEqual(finish.call_args.args[1],'success')
                    self.assertEqual(finish.call_args.kwargs['fingerprint'],hashlib.sha256(observation['p_source_sha256'].encode()).hexdigest())
                    self.assertEqual(rpc.call_args.args[0],'ingest_life_observation_v1')
                release.assert_called_once()

    def test_unsigned_dead_is_not_reidentified_and_unsigned_alive_blocks(self):
        self.assertEqual(extract_verified([('Conta','Antigo',1,b'legacy')],'salt',KEY),[])
        for flag in (0,None):
            with self.assertRaises(ValueError):extract_verified([('Conta','Atual',flag,b'legacy')],'salt',KEY)

    def test_rename_preserves_source_life_and_unknown_is_not_death(self):
        first=extract_verified([('Conta','Nome',0,b'a')],'salt',KEY,read_envelope=lambda _:signed())[0]
        renamed=extract_verified([('Conta','Renomeado',0,b'b')],'salt',KEY,read_envelope=lambda _:signed(character_name='Renomeado'))[0]
        self.assertEqual(first['p_life_token'],renamed['p_life_token'])
        from collector import extract
        for flag in (2,-1,'0'):
            self.assertIsNone(extract([('Conta','Nome',flag,b'data')],'salt')[0]['p_alive'])

if __name__=='__main__':unittest.main()
