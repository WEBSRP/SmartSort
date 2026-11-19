"""Only verified, unchanged matching files authorize source removal."""
from pathlib import Path
import pytest
from src.utils.file_utils import FileUtils
from src.organizer import FileOrganizer
from src.core.directory_organizer import DirectoryOrganizer, OperationStatus


class Logger:
 def __getattr__(self,name):return lambda *a,**kw:None
class Config:
 def __init__(self,root,**changes):
  self.data=dict(destination_base=str(root/'sorted'),sorting_mode='rules_first',rules=[dict(id='pin',name='Pinned',enabled=True,priority=1,conditions=[],destination='Pinned')],enable_duplicate_detection=True,enable_notifications=False,enable_origin_detection=False,smart_filename_cleanup=False,conflict_resolution='rename')
  self.data.update(changes)
 def get(self,key,default=None):return self.data.get(key,default)


def copies(tmp_path,payload=b'identical'):
 src=tmp_path/'source';dst=tmp_path/'destination';src.write_bytes(payload);dst.write_bytes(payload);return src,dst


@pytest.mark.parametrize('payload',[b'',b'identical',b'x'*(2*1024**2)])
def test_only_source_is_removed_after_hash_match(tmp_path,payload):
 src,dst=copies(tmp_path,payload)
 removed,digest,error=FileUtils.remove_verified_duplicate(src,dst)
 assert removed and digest and error is None
 assert not src.exists() and dst.read_bytes()==payload


@pytest.mark.parametrize('failed',['source','target','both'])
def test_unreadable_hash_never_authorizes_removal(tmp_path,monkeypatch,failed):
 src,dst=copies(tmp_path);original=FileUtils.calculate_sha256
 monkeypatch.setattr(FileUtils,'calculate_sha256',lambda path:None if failed=='both' or Path(path)==(src if failed=='source' else dst) else original(path))
 removed,_,error=FileUtils.remove_verified_duplicate(src,dst)
 assert not removed and error and src.exists() and dst.exists()


@pytest.mark.parametrize('which',['source','target'])
def test_mutation_during_hashing_prevents_removal(tmp_path,monkeypatch,which):
 src,dst=copies(tmp_path);original=FileUtils.calculate_sha256
 def changing(path):
  digest=original(path)
  if Path(path)==dst:(src if which=='source' else dst).write_bytes(b'changed!!')
  return digest
 monkeypatch.setattr(FileUtils,'calculate_sha256',changing)
 removed,_,error=FileUtils.remove_verified_duplicate(src,dst)
 assert not removed and error and src.exists() and dst.exists()


def test_same_size_different_bytes_is_a_collision(tmp_path):
 src,dst=copies(tmp_path);dst.write_bytes(b'different')
 removed,_,error=FileUtils.remove_verified_duplicate(src,dst)
 assert not removed and error is None and src.exists() and dst.read_bytes()==b'different'


def test_deletion_error_is_reported_without_modifying_destination(tmp_path,monkeypatch):
 import src.utils.file_utils as module
 src,dst=copies(tmp_path)
 def denied(path):raise PermissionError('test deletion denied')
 monkeypatch.setattr(module.os,'remove',denied)
 removed,_,error=FileUtils.remove_verified_duplicate(src,dst)
 assert not removed and 'denied' in error and src.exists() and dst.read_bytes()==b'identical'


@pytest.mark.parametrize('which',['source','target'])
def test_symlinks_never_authorize_removal(tmp_path,which):
 src,dst=copies(tmp_path);real=tmp_path/'real';real.write_bytes(b'identical')
 path=src if which=='source' else dst;path.unlink();path.symlink_to(real)
 removed,_,error=FileUtils.remove_verified_duplicate(src,dst)
 assert not removed and error and src.exists() and dst.exists() and real.exists()


def test_same_path_is_never_deleted(tmp_path):
 src,dst=copies(tmp_path)
 removed,_,error=FileUtils.remove_verified_duplicate(src,src)
 assert not removed and error and src.exists()


def test_validation_failure_preserves_source(tmp_path):
 src,dst=copies(tmp_path)
 def changed_boundary():raise ValueError('boundary changed')
 removed,_,error=FileUtils.remove_verified_duplicate(src,dst,changed_boundary)
 assert not removed and 'boundary' in error and src.exists() and dst.exists()


@pytest.mark.parametrize('kind',['download','folder'])
@pytest.mark.parametrize('case',['match','hash_failure','deletion_failure','disabled','collision'])
def test_organizers_remove_only_verified_duplicates(tmp_path,monkeypatch,kind,case):
 src=tmp_path/'incoming.txt';src.write_bytes(b'identical')
 folder=tmp_path/('sorted/Pinned' if kind=='download' else 'Pinned');folder.mkdir(parents=True)
 dst=folder/src.name;dst.write_bytes(b'different' if case=='collision' else b'identical')
 before=dst.read_bytes();config=Config(tmp_path,enable_duplicate_detection=case!='disabled')
 instance=FileOrganizer(config,Logger()) if kind=='download' else DirectoryOrganizer(config,Logger())
 if case=='hash_failure':monkeypatch.setattr(FileUtils,'calculate_sha256',lambda *a:None)
 if case=='deletion_failure':
  import src.utils.file_utils as module
  original=module.os.remove
  def denied(path,*a,**kw):
   if Path(path)==src:raise PermissionError('test source removal denied')
   return original(path,*a,**kw)
  monkeypatch.setattr(module.os,'remove',denied)
 if kind=='download':
  instance.notification_manager.send_success_notification=lambda *a:False
  status,_=instance.process_file(str(src))
 else:
  plan=instance.plan(str(tmp_path),[str(src)]);result=instance.execute(plan)
  status=result.records[0].status.value
 assert dst.read_bytes()==before
 if case=='match':assert status=='DUPLICATE' and not src.exists()
 elif case in ['hash_failure','deletion_failure']:assert status in ['ERROR','FAILED'] and src.exists()
 else:assert status in ['SUCCESS','COLLISION_RESOLVED'] and not src.exists() and (folder/'incoming_1.txt').read_bytes()==b'identical'


@pytest.mark.parametrize('failed_read',[3,4])
def test_final_hash_read_failure_keeps_both_copies(tmp_path,monkeypatch,failed_read):
 src,dst=copies(tmp_path);original=FileUtils.calculate_sha256;calls=[]
 def flaky(path):
  calls.append(path)
  return None if len(calls)==failed_read else original(path)
 monkeypatch.setattr(FileUtils,'calculate_sha256',flaky)
 removed,_,error=FileUtils.remove_verified_duplicate(src,dst)
 assert not removed and error and src.read_bytes()==dst.read_bytes()==b'identical'
