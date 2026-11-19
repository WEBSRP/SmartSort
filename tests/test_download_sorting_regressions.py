"""Regressions from varied-file live Downloads validation."""
import copy
import json
from pathlib import Path

import pytest

from src.rules.conditions import ExtensionCondition
from src.rules.engine import RuleEngine
from src.rules.manager import migrate_config_if_needed, RuleManager
from src.rules.rule import Rule


@pytest.mark.parametrize('configured,name,expected', [
 ('.tar.gz','backup.tar.gz',True), ('tar.gz','BACKUP.TAR.GZ',True),
 ('.gz','backup.tar.gz',True), ('.tar.gz','backup.gz',False),
 ('.tar.gz','backup.tar.gz.exe',False), ('.pdf','parent.pdf/file.txt',False),
 ('.gz','archive.tgz',False), ('.png','image.PNG',True),
])
def test_extension_condition_supports_compound_suffixes(configured,name,expected):
 assert ExtensionCondition(configured).evaluate(name) is expected


@pytest.mark.parametrize('threshold,expected', [(2.5,'2.5GB'), (2684354560,'2684354560B')])
def test_legacy_video_migration_handles_gigabytes_and_canonical_bytes(threshold,expected):
 config={'large_file_threshold_gb':threshold,'categories':{'Videos':{'extensions':['.mp4']}}}
 assert migrate_config_if_needed(config)
 big=next(r for r in config['rules'] if r['id']=='legacy_videos_big')
 assert big['conditions'][1]['value']==expected
 rule,target=RuleEngine([Rule.from_dict(r) for r in config['rules']]).evaluate_file('sample.mp4',2684354560)
 assert rule.id=='legacy_videos_big' and target=='Videos/Big_Videos'


def broken_config():
 return {'large_file_threshold_gb':2684354560,'rules':[{
  'id':'legacy_videos_big','name':'Videos (Big)','enabled':True,'priority':4,
  'conditions':[{'type':'extension','value':['.mp4']}, {'type':'size','operator':'>=','value':'2684354560GB'}],
  'destination':'Custom/Videos'}]}


def test_repair_only_known_generated_double_conversion_is_idempotent(tmp_path):
 config=broken_config();path=tmp_path/'config.json';path.write_text(json.dumps(config));original=path.read_bytes()
 assert migrate_config_if_needed(config,str(path))
 assert config['rules'][0]['conditions'][1]['value']=='2684354560B'
 assert config['rules'][0]['destination']=='Custom/Videos'
 assert path.with_suffix('.json.bak').read_bytes()==original
 assert not migrate_config_if_needed(config,str(path))


@pytest.mark.parametrize('change', ['custom_id','custom_value','custom_operator'])
def test_video_repair_preserves_custom_rules(change):
 config=broken_config();rule=config['rules'][0]
 if change=='custom_id':rule['id']='user-video-rule'
 if change=='custom_value':rule['conditions'][1]['value']='8GB'
 if change=='custom_operator':rule['conditions'][1]['operator']='>'
 before=copy.deepcopy(config)
 assert not migrate_config_if_needed(config)
 assert config==before


@pytest.mark.parametrize('rewrite', ['same_size','new_size'])
def test_watchdog_reprocesses_changed_file_even_when_inode_is_reused(tmp_path,monkeypatch,rewrite):
 import os
 from types import SimpleNamespace
 import src.monitor as module
 path=tmp_path/'same.txt';path.write_bytes(b'first')
 seen=[];handler=module.DownloadHandler(SimpleNamespace(logger=SimpleNamespace(debug=lambda *a:None)),lambda value:seen.append(Path(value).read_bytes()))
 class InlineThread:
  def __init__(self,target,args,**kwargs):self.target=target;self.args=args
  def start(self):self.target(*self.args)
 monkeypatch.setattr(module.threading,'Thread',InlineThread)
 monkeypatch.setattr(module.time,'sleep',lambda *a:None)
 # Force the inode/device pair to be reused, as observed on the live filesystem.
 monkeypatch.setattr(module,'_get_file_identity',lambda *a:(1234,1))
 handler._handle_event(str(path));handler._handle_event(str(path))
 assert seen==[b'first']
 original=path.stat();payload=b'other' if rewrite=='same_size' else b'new payload'
 path.write_bytes(payload);os.utime(path,ns=(original.st_atime_ns,original.st_mtime_ns+1000000))
 handler._handle_event(str(path))
 assert seen==[b'first',payload]
 assert not handler.pending_files


def test_rule_manager_persists_generated_threshold_repair_with_backup(tmp_path):
 config=broken_config();path=tmp_path/'config.json';path.write_text(json.dumps(config))
 original=path.read_bytes()
 class SavedConfig:
  config_path=path
  def __init__(self):self.config=json.loads(path.read_text())
  def get(self,key,default=None):return self.config.get(key,default)
  def save_config(self,data):path.write_text(json.dumps(data));self.config=data
 manager=RuleManager(SavedConfig())
 assert manager.rules[0].evaluate('sample.mp4',2684354560)
 assert json.loads(path.read_text())['rules'][0]['conditions'][1]['value']=='2684354560B'
 assert path.with_suffix('.json.bak').read_bytes()==original


def test_old_stability_worker_keeps_replacement_pending(tmp_path,monkeypatch):
 from types import SimpleNamespace
 import src.monitor as module
 path=tmp_path/'new.txt';path.write_text('replacement')
 callbacks=[];handler=module.DownloadHandler(SimpleNamespace(logger=SimpleNamespace(debug=lambda *a:None)),callbacks.append)
 handler.pending_files[str(path)]=(2,1)
 monkeypatch.setattr(module,'_get_file_identity',lambda *a:(2,1))
 monkeypatch.setattr(module.time,'sleep',lambda *a:None)
 handler._wait_and_process(str(path),(1,1))
 assert not callbacks
 assert handler.pending_files[str(path)]==(2,1)
