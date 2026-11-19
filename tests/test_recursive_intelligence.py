"""Recursive input discovery, stable destinations and live output-loop regressions."""
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from src.core.directory_organizer import DirectoryOrganizer
from src.monitor import FileMonitor
from src.organizer import FileOrganizer
from src.utils.output_tracker import remember_output, is_recent_output


class Config:
 def __init__(self,root,**changes):
  self.data=dict(sorting_mode='intelligence',rules=[],destination_base=str(root/'sorted'),enable_origin_detection=False,enable_notifications=False,smart_filename_cleanup=False,enable_duplicate_detection=True,conflict_resolution='rename')
  self.data.update(changes)
 def get(self,key,default=None):return self.data.get(key,default)
class Logger:
 def __getattr__(self,name):return lambda *a,**kw:None


def wait_for(predicate,timeout=8):
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  if predicate():return
  time.sleep(.025)
 assert predicate(), 'live watcher timed out'


def stop_monitor(monitor):
 monitor.stop()
 wait_for(lambda:not monitor.event_handler.pending_files,12)


def test_recursive_intelligence_defaults_and_explicit_top_level_override(tmp_path):
 nested=tmp_path/'incoming/deep';nested.mkdir(parents=True)
 (tmp_path/'top.txt').write_text('plain text')
 invoice=nested/'invoice.md';invoice.write_text('# Invoice\nFinance billing invoice')
 (nested/'.hidden.txt').write_text('hidden')
 (nested/'unfinished.pdf.part').write_text('pending')
 hidden=tmp_path/'.private';hidden.mkdir();(hidden/'secret.txt').write_text('hidden')
 (tmp_path/'alias').symlink_to(nested,target_is_directory=True)
 instance=DirectoryOrganizer(Config(tmp_path),Logger())
 assert instance.scan(str(tmp_path))==sorted([str(tmp_path/'top.txt'),str(invoice)])
 assert instance.scan(str(tmp_path),recursive=False)==[str(tmp_path/'top.txt')]
 summary=instance.preview(str(tmp_path))
 assert summary.total_files==2
 assert any(item.target_path==str(tmp_path/'Work/Invoices/invoice.md') for item in summary.items)


@pytest.mark.parametrize('changes',[{'sorting_mode':'rules_first'},{'intelligence_recursive':False}])
def test_nonrecursive_preferences_are_honored(tmp_path,changes):
 nested=tmp_path/'nested';nested.mkdir();(nested/'child.txt').write_text('child')
 (tmp_path/'top.txt').write_text('top')
 instance=DirectoryOrganizer(Config(tmp_path,**changes),Logger())
 assert instance.scan(str(tmp_path))==[str(tmp_path/'top.txt')]


def test_recursive_nested_duplicates_and_second_preview_are_stable(tmp_path):
 payload=b'# Invoice\nFinance billing invoice'
 for name in ['incoming/first','incoming/second']:
  directory=tmp_path/name;directory.mkdir(parents=True);(directory/'invoice.md').write_bytes(payload)
 instance=DirectoryOrganizer(Config(tmp_path),Logger())
 plan=instance.plan(str(tmp_path),instance.scan(str(tmp_path)))
 assert len(plan.items)==2
 result=instance.execute(plan)
 assert (result.success_count,result.duplicate_count,result.error_count)==(1,1,0)
 target=tmp_path/'Work/Invoices/invoice.md'
 assert target.read_bytes()==payload
 assert not (tmp_path/'incoming/first/invoice.md').exists() and not (tmp_path/'incoming/second/invoice.md').exists()
 assert not instance.preview(str(tmp_path)).items


@pytest.mark.parametrize('changes,recursive',[({},True),({'downloads_recursive':False},False),({'sorting_mode':'rules_first'},False)])
def test_watch_scope_tracks_mode_and_saved_preference(tmp_path,changes,recursive,monkeypatch):
 import src.monitor as module
 calls=[]
 class Observer:
  def schedule(self,handler,path,**kwargs):calls.append((path,kwargs))
  def start(self):pass
 monkeypatch.setattr(module,'Observer',Observer)
 monitor=module.FileMonitor(str(tmp_path),SimpleNamespace(config=Config(tmp_path,**changes)),lambda *a:None)
 monitor.start()
 assert calls==[(str(tmp_path),{'recursive':recursive})]


def test_recursive_live_downloads_suppress_own_outputs_but_allow_later_edits(tmp_path):
 incoming=tmp_path/'incoming/deep';incoming.mkdir(parents=True)
 instance=FileOrganizer(Config(tmp_path),Logger());instance.notification_manager.send_success_notification=lambda *a:False
 calls=[];lock=threading.Lock()
 def callback(path):
  result=instance.process_file(path)
  with lock:calls.append((path,result))
 monitor=FileMonitor(str(tmp_path),instance,callback);monitor.start()
 try:
  source=incoming/'plain.txt';source.write_text('Neutral sample payload')
  target=tmp_path/'sorted/Documents/plain.txt'
  wait_for(lambda:target.exists() and not source.exists())
  wait_for(lambda:len(calls)==1)
  assert calls[0][1][0]=='SUCCESS'
  # Let creation events from SmartSort's copy drain; they must not launch another sort.
  time.sleep(1.3)
  assert len(calls)==1
  target.write_text('# Invoice\nFinance billing invoice')
  info=target.stat();os.utime(target,ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
  moved=tmp_path/'sorted/Work/Invoices/plain.txt'
  wait_for(lambda:moved.exists() and not target.exists())
  wait_for(lambda:len(calls)==2)
  assert calls[-1][1][0]=='SUCCESS'
  time.sleep(1.3)
  assert len(calls)==2
 finally:stop_monitor(monitor)


def test_populated_directory_moved_into_watched_tree_is_discovered_once(tmp_path):
 watch=tmp_path/'watch';watch.mkdir();staging=tmp_path/'staging';(staging/'deep').mkdir(parents=True)
 (staging/'deep/plain.txt').write_text('Neutral sample payload')
 (staging/'deep/.hidden.txt').write_text('private')
 (staging/'deep/pending.txt.part').write_text('pending')
 instance=FileOrganizer(Config(watch),Logger());instance.notification_manager.send_success_notification=lambda *a:False
 calls=[]
 def callback(path):calls.append((path,instance.process_file(path)))
 monitor=FileMonitor(str(watch),instance,callback);monitor.start()
 try:
  staging.rename(watch/'incoming')
  target=watch/'sorted/Documents/plain.txt'
  wait_for(lambda:target.exists() and len(calls)==1)
  assert calls[0][1][0]=='SUCCESS'
  assert (watch/'incoming/deep/.hidden.txt').exists() and (watch/'incoming/deep/pending.txt.part').exists()
  time.sleep(1.3)
  assert len(calls)==1
 finally:stop_monitor(monitor)


def test_hidden_symlinked_and_outside_events_are_ignored(tmp_path,monkeypatch):
 watch=tmp_path/'watch';watch.mkdir();outside=tmp_path/'outside';outside.mkdir();(outside/'data.txt').write_text('outside')
 (watch/'alias').symlink_to(outside,target_is_directory=True)
 hidden=watch/'.private';hidden.mkdir();(hidden/'data.txt').write_text('hidden')
 instance=SimpleNamespace(config=Config(watch),logger=Logger())
 monitor=FileMonitor(str(watch),instance,lambda *a:pytest.fail('unsafe event callback'))
 for path in [outside/'data.txt',watch/'alias/data.txt',hidden/'data.txt']:
  monitor.event_handler._handle_event(str(path))
 assert not monitor.event_handler.pending_files


def test_output_tracking_expires_when_file_changes(tmp_path):
 path=tmp_path/'file.txt';path.write_text('original');remember_output(str(path));assert is_recent_output(str(path))
 path.write_text('different payload');assert not is_recent_output(str(path))
