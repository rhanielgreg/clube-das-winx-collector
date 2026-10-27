import unittest
from ttf_saved_life import read_saved_record,SOURCE_FILES,observational_evidence
from collector import failure_code
from test_ttf_saved_life import row,SALT

def record():
 return '\n'.join(['version=1','deleted=false','characterID=Fixture_1792000000_1','username=Account','forename=Name','surname=One','isDead=true','deathDateStamp=19930712','deathRealTimestamp=1792460631','distance=123.5','gameTimeSeconds=50','dailySeries='])

class OperationsTests(unittest.TestCase):
 def test_record_requires_exact_id_state_and_complete_writer_fields(self):
  data=read_saved_record(record(),'Fixture_1792000000_1')
  self.assertFalse(data['alive']);self.assertEqual(data['distance_total_m'],123.5)
  self.assertEqual(data['death_recorded_at'],'2026-10-20T01:43:51+00:00')
  self.assertFalse(data['world_namespace_verified']);self.assertFalse(data['activation_authorized'])
  for invalid in [record().replace('isDead=true','isDead=unknown'),record().replace('dailySeries=',''),record()+'\nusername=Other',record().replace('distance=123.5','distance=nan'),record().replace('deathRealTimestamp=1792460631','deathRealTimestamp=0')]:
   with self.assertRaises(ValueError):read_saved_record(invalid,'Fixture_1792000000_1')
  with self.assertRaises(ValueError):read_saved_record(record(),'Another_1792000000_2')
 def test_missing_optional_metric_is_unknown_and_shared_source_is_pinned(self):
  data=read_saved_record(record().replace('distance=123.5\n',''),'Fixture_1792000000_1')
  self.assertIsNone(data['distance_total_m']);self.assertNotIn('survival_world_days',data)
  self.assertIn('media/lua/shared/TTF_StatsMP_Shared.lua',SOURCE_FILES)
 def test_failure_codes_use_phase_without_secret_messages(self):
  AuthenticationException=type('AuthenticationException',(Exception,),{})
  self.assertEqual(failure_code(AuthenticationException('secret'),'source'),'source_auth_failed')
  self.assertEqual(failure_code(ValueError('private id'),'parser'),'parser_or_identity_invalid')
  self.assertEqual(failure_code(ValueError('private sql'),'ingestion'),'ingestion_failed')
  self.assertEqual(failure_code(ValueError('private blob'),'source'),'snapshot_invalid')
 def test_legacy_identity_guard_prevents_same_name_reuse_or_lost_id(self):
  item=row();rows=[item[:4]];empty={'contract':'observational-v1','items':{}}
  first=observational_evidence(rows,SALT,'scope',empty)
  previous={'contract':'observational-v1','items':{'scope:'+first[0]['character_token']:first[0]}}
  self.assertEqual(observational_evidence(rows,SALT,'scope',previous),first)
  with self.assertRaises(ValueError):observational_evidence([row(life=2)[:4]],SALT,'scope',previous)
  with self.assertRaises(ValueError):observational_evidence([(item[0],item[1],0,b'opaque')],SALT,'scope',previous)
  renamed=observational_evidence([(item[0],'Different',*item[2:4])],SALT,'scope',previous)
  self.assertEqual(renamed[0]['life_digest'],first[0]['life_digest'])
  self.assertNotEqual(renamed[0]['character_token'],first[0]['character_token'])
 def test_legacy_main_persists_observations_without_native_ingestion(self):
  from collector import main
  from unittest.mock import patch
  settings={'LIFE_PIPELINE_VERSION':'legacy','PLAYER_HASH_SALT':SALT,'SFTP_HOST':'fixture.invalid','SFTP_DB_PATH':'/players.db','DRY_RUN':'false'}
  with patch.dict('os.environ',settings),patch('collector.acquire_lock',return_value=True),patch('collector.release_lock'),patch('collector.begin_run',return_value='fixture'),patch('collector.collect_rows',return_value=[row()[:4]]),patch('collector.push') as push,patch('collector.finish_run') as finish,patch('collector.rpc',return_value={'contract':'observational-v1','items':{}}):
   main()
   self.assertIn('p_character_key',push.call_args.args[0][0])
   self.assertNotIn('p_life_token',push.call_args.args[0][0])
   self.assertEqual(len(finish.call_args.kwargs['source_diagnostics']),1)

if __name__=='__main__':unittest.main()
