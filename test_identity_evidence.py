from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_ttf_saved_life import row, SALT, NAMESPACE
from ttf_saved_life import extract_saved_lives
from collector import download_consistent_snapshot
from identity_evidence import compare


def save(path, rows):
    with closing(sqlite3.connect(path)) as db:
        with db:
            db.execute('create table networkPlayers(username text,name text,isDead integer,data blob,steamid STRING,world text)')
            db.executemany('insert into networkPlayers values(?,?,?,?,?,?)',rows)


class IdentityEvidenceTests(unittest.TestCase):
    def test_same_source_id_different_account_is_collision(self):
        item=row()
        other=(*item[:4],76561198000000001,item[5])
        with self.assertRaisesRegex(ValueError,'duplicate source life'):
            extract_saved_lives([item,other],SALT,NAMESPACE)

    def test_missing_distance_is_unknown_not_zero(self):
        item=row()
        from test_ttf_saved_life import encoded
        blob=item[3].split(encoded('distanceTracker'))[0]
        observed=extract_saved_lives([(*item[:3],blob,*item[4:])],SALT,NAMESPACE)[0]
        self.assertNotIn('distance_total_m',observed['p_metrics'])
        self.assertNotIn('survival_world_days',observed['p_metrics'])

    def test_comparison_death_rename_birth_and_no_private_identifiers(self):
        with tempfile.TemporaryDirectory() as folder:
            old=Path(folder)/'old.db';new=Path(folder)/'new.db';item=row()
            save(old,[item]);save(new,[(item[0],'Renomeado',1,*item[3:]),row(life=2)])
            before=hashlib.sha256(old.read_bytes()).hexdigest()
            evidence=compare(old,new)
            self.assertEqual(evidence['transitions'],{'True->False':1})
            self.assertEqual(evidence['renames'],1);self.assertEqual(evidence['new_ids'],1)
            self.assertFalse(evidence['activation_authorized'])
            self.assertNotIn(str(item[4]),json.dumps(evidence))
            self.assertNotIn('Renomeado',json.dumps(evidence))
            self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(),before)

    def test_copy_with_sidecar_is_not_accepted_as_detached_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'players.db';save(path,[row()])
            Path(str(path)+'-wal').touch()
            with self.assertRaisesRegex(ValueError,'sidecars'):compare(path,path)

    def test_equal_size_mtime_content_change_is_detected_before_sqlite(self):
        class SFTP:
            reads=0
            def stat(self,path):
                if path.endswith(('-wal','-shm','-journal')):raise FileNotFoundError(path)
                return SimpleNamespace(st_size=4,st_mtime=1)
            def get(self,remote,target):
                self.reads+=1;Path(target).write_bytes(b'AAAA' if self.reads==1 else b'BBBB')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'tamanho/mtime'):
                download_consistent_snapshot(SFTP(),'/players.db',Path(folder)/'copy.db')
            self.assertFalse(list(Path(folder).glob('*.verify')))

    def test_stable_double_read_preserves_legacy_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.db';save(source,[row()])
            class SFTP:
                reads=0
                def stat(self,path):
                    if path.endswith(('-wal','-shm','-journal')):raise FileNotFoundError(path)
                    return SimpleNamespace(st_size=source.stat().st_size,st_mtime=1)
                def get(self,remote,target):self.reads+=1;shutil.copyfile(source,target)
            sftp=SFTP()
            with patch.dict('os.environ',{'LIFE_PIPELINE_VERSION':'legacy'}):
                rows=download_consistent_snapshot(sftp,'/players.db',Path(folder)/'copy.db')
            self.assertEqual(sftp.reads,2);self.assertEqual(len(rows[0]),4)


if __name__=='__main__':unittest.main()
