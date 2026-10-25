import hashlib
import json
from pathlib import Path
import struct
import shutil
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import closing
from unittest.mock import patch
from datetime import datetime,timezone
from ttf_saved_life import extract_saved_lives,verify_source_files
from collector import push,download_consistent_snapshot

NAMESPACE='f0000000-0000-4000-8000-000000000001'
SALT='private-local-fixture-salt'
def encoded(value):
    if isinstance(value,str):
        b=value.encode();return b'\0'+struct.pack('>H',len(b))+b
    if isinstance(value,dict):return b'\2'+struct.pack('>i',len(value))+b''.join(encoded(k)+encoded(v) for k,v in value.items())
    return b'\1'+struct.pack('>d',value)
def row(*,life=1,name='Nome',steam=76561198000000000,distance=12345):
    sample=json.loads((Path(__file__).parent/'fixtures/ttf_only.json').read_text())[0]
    blob=bytes.fromhex(sample['ttf_only_hex'])
    epoch=format(datetime.now(timezone.utc).timestamp()-3600,'.12e')
    blob+=encoded('TTFStatsMP')+encoded({'characterID':'Conta_Nome_'+epoch+'_'+str(life),'username':'Conta'})
    blob+=encoded('distanceTracker')+encoded(distance)
    return ('Conta',name,0,blob,steam,'FixtureWorld')

class SavedLifeTests(unittest.TestCase):
    def test_container_packages_all_imported_pipeline_modules(self):
        dockerfile=(Path(__file__).parent/'Dockerfile').read_text()
        copied=' '.join(line for line in dockerfile.splitlines() if line.startswith('COPY '))
        for module in ('collector.py','stats.py','probe_stats.py','verified_life.py','ttf_saved_life.py'):
            self.assertIn(module,copied)

    def test_source_identity_same_name_rename_and_units(self):
        first_row=row()
        first=extract_saved_lives([first_row],SALT,NAMESPACE)[0]
        renamed=extract_saved_lives([(first_row[0],'Renomeado',*first_row[2:])],SALT,NAMESPACE)[0]
        second=extract_saved_lives([row(life=2)],SALT,NAMESPACE)[0]
        self.assertEqual(first['p_life_token'],renamed['p_life_token'])
        self.assertEqual(first['p_account_token'],second['p_account_token'])
        self.assertNotEqual(first['p_life_token'],second['p_life_token'])
        self.assertEqual(first['p_metrics']['distance_total_m']['unit'],'meters')
        self.assertEqual(first['p_metrics']['distance_total_m']['value'],12345)
        self.assertTrue(all(m['coverage']=='observed_lower_bound' for m in first['p_metrics'].values()))
        self.assertNotIn('survival_world_days',first['p_metrics'])
        self.assertNotIn('distance_walked_m',first['p_metrics'])
        self.assertNotIn('76561198000000000',json.dumps(first))

    def test_bad_account_duplicate_identity_distance_and_namespace_fail_closed(self):
        for item in [row(steam=float(76561198000000000)),row(steam=None),row(distance=-1),row(distance=float('nan'))]:
            with self.assertRaises(ValueError):extract_saved_lives([item],SALT,NAMESPACE)
        item=row()
        with self.assertRaises(ValueError):extract_saved_lives([item,item],SALT,NAMESPACE)
        with self.assertRaises(ValueError):extract_saved_lives([item],SALT,'00000000-0000-0000-0000-000000000000')

    def test_missing_mismatched_or_unverified_source_identity_fails_closed(self):
        item=row()
        for blob in (b'opaque', encoded('TTFStatsMP')+encoded({'username':'Outra conta','characterID':'id'}),
                     encoded('TTFStatsMP')+encoded({'username':'Conta','characterID':'Nome_sem_identidade'})):
            with self.subTest(blob_size=len(blob)),self.assertRaises(ValueError):
                extract_saved_lives([(item[0],item[1],item[2],blob,item[4],item[5])],SALT,NAMESPACE)
        unknown=extract_saved_lives([(item[0],item[1],None,*item[3:])],SALT,NAMESPACE)[0]
        dead=extract_saved_lives([(item[0],item[1],1,*item[3:])],SALT,NAMESPACE)[0]
        self.assertIsNone(unknown['p_alive'])
        self.assertFalse(dead['p_alive'])
        self.assertEqual(unknown['p_life_token'],dead['p_life_token'])
        other_world=extract_saved_lives([(*item[:5],'Outro mundo')],SALT,NAMESPACE)[0]
        self.assertNotEqual(unknown['p_world_id'],other_world['p_world_id'])

    def test_sqlite_snapshot_keeps_legacy_shape_and_exact_steam_integer(self):
        class SFTP:
            def stat(self,path):
                if path.endswith(('-wal','-shm')):raise FileNotFoundError(path)
                return SimpleNamespace(st_size=source.stat().st_size,st_mtime=1)
            def get(self,_,target):shutil.copyfile(source,target)
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.db'
            with closing(sqlite3.connect(source)) as db:
                with db:
                    db.execute('create table networkPlayers(username text,name text,isDead integer,data blob,steamid STRING,world text)')
                    db.execute('insert into networkPlayers values(?,?,?,?,?,?)',row())
            for mode,width in (('legacy',4),('life-v1',4),('ttf-mp-v1',6)):
                with patch.dict('os.environ',{'LIFE_PIPELINE_VERSION':mode}):
                    rows=download_consistent_snapshot(SFTP(),'/players.db',Path(folder)/(mode+'.db'))
                self.assertEqual(len(rows[0]),width)
                if width==6:
                    self.assertIsInstance(rows[0][4],int)
                    self.assertEqual(rows[0][4],76561198000000000)

    def test_profile_reads_only_stat_get_and_rejects_modified_source(self):
        class SFTP:
            def stat(self,_):return SimpleNamespace(st_size=7,st_mtime=1)
            def get(self,_,target):Path(target).write_bytes(b'fixture')
        expected=hashlib.sha256(b'fixture').hexdigest()
        with tempfile.TemporaryDirectory() as folder,patch('ttf_saved_life.SOURCE_FILES',{'media/source.lua':expected}):
            verify_source_files(SFTP(),'/verified-source',folder)
            with self.assertRaises(ValueError):verify_source_files(SFTP(),'relative-path',folder)
        with tempfile.TemporaryDirectory() as folder,patch('ttf_saved_life.SOURCE_FILES',{'media/source.lua':'0'*64}):
            with self.assertRaises(ValueError):verify_source_files(SFTP(),'/verified-source',folder)

    def test_new_mode_uses_existing_life_rpc_without_legacy_fallback(self):
        with patch.dict('os.environ',{'LIFE_PIPELINE_VERSION':'ttf-mp-v1'}),patch('collector.rpc') as rpc:
            push([{'p_life_token':'local-fixture'}])
            self.assertEqual(rpc.call_args.args[0],'ingest_life_observation_v1')

    def test_native_main_records_success_after_contract_guard(self):
        from collector import main
        observation=extract_saved_lives([row()],SALT,NAMESPACE)[0]
        settings={'LIFE_PIPELINE_VERSION':'ttf-mp-v1','PLAYER_HASH_SALT':SALT,'LIFE_SOURCE_NAMESPACE_UUID':NAMESPACE,'DRY_RUN':'false'}
        with patch.dict('os.environ',settings),patch('collector.rpc',return_value={'catalog_count':100,'contract_ready':True}) as rpc, \
             patch('collector.acquire_lock',return_value=True),patch('collector.release_lock') as release, \
             patch('collector.begin_run',return_value='fixture-run'),patch('collector.finish_run') as finish, \
             patch('collector.collect_rows',return_value=[]),patch('collector.extract_saved_lives',return_value=[observation]),patch('collector.LOG'):
            main()
            self.assertEqual(rpc.call_args_list[0].args[0],'get_service_pipeline_readiness_v1')
            self.assertEqual(rpc.call_args.args[0],'ingest_life_observation_v1')
            self.assertEqual(finish.call_args.args[1],'success')
            self.assertEqual(finish.call_args.kwargs['fingerprint'],hashlib.sha256(observation['p_source_sha256'].encode()).hexdigest())
            release.assert_called_once()

if __name__=='__main__':unittest.main()
