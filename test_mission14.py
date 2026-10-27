import unittest
from unittest.mock import patch
from collector import main,calendar_contract,reconcile_calendar
from test_operations13 import row,SALT

SETTINGS={'LIFE_PIPELINE_VERSION':'legacy','PLAYER_HASH_SALT':SALT,'SFTP_HOST':'fixture.invalid','SFTP_DB_PATH':'/players.db','DRY_RUN':'false'}

class MonthlyCalendarTests(unittest.TestCase):
 def test_marker_is_explicit_and_old_schema_has_no_monthly_mutation(self):
  for value in (None,{}, {'product14_installed':False},{'product14_installed':'true'}):
   with patch('collector.rpc',return_value=value):self.assertFalse(calendar_contract())
  with patch('collector.rpc') as rpc:reconcile_calendar(False);rpc.assert_not_called()

 def test_reconciliation_does_not_change_flags_and_checks_contract(self):
  with patch('collector.rpc',return_value={'enabled':False}) as rpc:
   reconcile_calendar(True);rpc.assert_called_once_with('reconcile_months_v2',{})
  with patch('collector.rpc',return_value=None):
   with self.assertRaises(ValueError):reconcile_calendar(True)

 def test_existing_five_minute_job_reconciles_before_source_before_ingestion_and_after(self):
  events=[]
  def rpc(name,params):
   events.append(name)
   if name=='get_public_dashboard_release_v1':return {'product14_installed':True}
   if name=='reconcile_months_v2':return {'enabled':True,'transitions':0}
   if name=='get_service_source_evidence_v1':return {'contract':'observational-v1','items':{}}
   raise AssertionError(name)
  with patch.dict('os.environ',SETTINGS),patch('collector.rpc',side_effect=rpc),patch('collector.acquire_lock',return_value=True),patch('collector.release_lock'),patch('collector.begin_run',return_value='fixture'),patch('collector.finish_run'),patch('collector.collect_rows',side_effect=lambda:events.append('source') or [row()[:4]]),patch('collector.push',side_effect=lambda _:events.append('push')):
   main()
  self.assertEqual(events.count('reconcile_months_v2'),3)
  self.assertLess(events.index('reconcile_months_v2'),events.index('source'))
  self.assertEqual(events[events.index('push')-1],'reconcile_months_v2')
  self.assertEqual(events[events.index('push')+1],'reconcile_months_v2')

 def test_missing_calendar_contract_stops_before_ingestion(self):
  def rpc(name,params):return {'product14_installed':True} if name=='get_public_dashboard_release_v1' else None
  with patch.dict('os.environ',SETTINGS),patch('collector.rpc',side_effect=rpc),patch('collector.acquire_lock',return_value=True),patch('collector.release_lock'),patch('collector.begin_run',return_value='fixture'),patch('collector.finish_run') as finish,patch('collector.collect_rows') as source,patch('collector.push') as push:
   with self.assertRaises(ValueError):main()
   source.assert_not_called();push.assert_not_called()
   self.assertEqual(finish.call_args.kwargs['error_code'],'calendar_reconciliation_failed')

 def test_native_mode_cannot_bypass_world_generation_proof(self):
  def rpc(name,params):
   if name=='get_service_pipeline_readiness_v1':return {'catalog_count':100,'contract_ready':True}
   if name=='get_public_dashboard_release_v1':return {'product14_installed':True}
   if name=='get_service_product14_readiness_v2':return {'contract_ready':False,'world_epoch_count':0}
  with patch.dict('os.environ',{**SETTINGS,'LIFE_PIPELINE_VERSION':'ttf-mp-v1'}),patch('collector.rpc',side_effect=rpc),patch('collector.acquire_lock',return_value=True),patch('collector.release_lock'),patch('collector.begin_run',return_value='fixture'),patch('collector.finish_run'),patch('collector.collect_rows') as source:
   with self.assertRaisesRegex(ValueError,'source generation'):main()
   source.assert_not_called()

 def test_dry_run_does_not_reconcile_calendar(self):
  with patch.dict('os.environ',{**SETTINGS,'DRY_RUN':'true'}),patch('collector.collect_rows',return_value=[row()[:4]]),patch('collector.reconcile_calendar') as reconcile:
   main();reconcile.assert_not_called()

if __name__=='__main__':unittest.main()
