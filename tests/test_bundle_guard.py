"""Recursive sorting must preserve cohesive apps/projects and their assets."""
import os
from pathlib import Path
import time
import pytest
from src.core.directory_organizer import DirectoryOrganizer
from src.monitor import FileMonitor
from src.organizer import FileOrganizer
from src.utils.folder_guard import is_protected_folder, protected_folder_for


class Config:
 def __init__(self,root):
  self.data=dict(downloads_folder=str(root),destination_base=str(root/'sorted'),sorting_mode='intelligence',rules=[],enable_origin_detection=False,enable_notifications=False,smart_filename_cleanup=False)
 def get(self,key,default=None):return self.data.get(key,default)
class Logger:
 def __getattr__(self,name):return lambda *a,**kw:None


def bundle(root,kind):
 folder=root/('Example.AppDir' if kind=='appdir' else 'Example.app' if kind=='mac' else 'example-'+kind)
 (folder/'assets/icons').mkdir(parents=True)
 logo=folder/'assets/icons/logo.png';logo.write_bytes(b'QA logo bytes')
 if kind=='apprun':(folder/'AppRun').write_text('#!/bin/sh\n')
 elif kind=='electron':(folder/'resources').mkdir();(folder/'resources/app.asar').write_bytes(b'QA asar')
 elif kind=='python':(folder/'pyproject.toml').write_text('[project]\nname="example"\n')
 elif kind=='node':(folder/'package.json').write_text('{"name":"example","main":"main.js"}')
 elif kind=='elf':
  executable=folder/'example';executable.write_bytes(b'\x7fELF'+b'\0'*64);executable.chmod(0o755)
 elif kind=='windows':(folder/'example.exe').write_bytes(b'MZ'+b'\0'*64)
 elif kind=='launcher':(folder/'example.desktop').write_text('[Desktop Entry]\nType=Application\n')
 elif kind=='manual':(folder/'.smartsort-ignore').touch()
 return folder,logo


@pytest.mark.parametrize('kind',['appdir','mac','apprun','electron','python','node','elf','windows','launcher','manual'])
def test_recursion_keeps_entire_bundle_intact_and_sorts_loose_files(tmp_path,monkeypatch,kind):
 folder,logo=bundle(tmp_path,kind);loose=tmp_path/'loose';loose.mkdir();plain=loose/'plain.txt';plain.write_text('Neutral sample payload')
 assert is_protected_folder(folder)
 assert protected_folder_for(logo,tmp_path)==str(folder)
 instance=DirectoryOrganizer(Config(tmp_path),Logger())
 assert instance.scan(str(tmp_path))==[str(plain)]
 # Passing an internal asset explicitly must not bypass the scan exclusion.
 manual=instance.plan(str(tmp_path),[str(logo)]);assert not manual.items and manual.warnings
 plan=instance.plan(str(tmp_path),instance.scan(str(tmp_path)))
 result=instance.execute(plan)
 assert result.success_count==1 and result.error_count==0 and logo.read_bytes()==b'QA logo bytes'
 assert (tmp_path/'Documents/plain.txt').is_file()
 assert instance.scan(str(folder))==[]
 preview=instance.preview(str(folder));assert not preview.items and preview.warnings


@pytest.mark.parametrize('kind',['appdir','electron','node','elf','manual'])
def test_live_handler_and_direct_downloads_do_not_disassemble_bundles(tmp_path,monkeypatch,kind):
 folder,logo=bundle(tmp_path,kind);instance=FileOrganizer(Config(tmp_path),Logger())
 monkeypatch.setattr(instance.extractor_registry,'extract_metadata',lambda *a,**kw:pytest.fail('bundle contents inspected'))
 status,info=instance.process_file(str(logo));assert status=='SKIPPED' and 'intact' in info
 with pytest.raises(ValueError,match='intact'):instance.analyze_download(str(logo))
 monitor=FileMonitor(str(tmp_path),instance,lambda *a:pytest.fail('bundle callback'))
 monitor.event_handler._handle_directory(str(folder));monitor.event_handler._handle_event(str(logo))
 assert not monitor.event_handler.pending_files and logo.exists()


def test_bundle_added_after_review_rejects_internal_source_before_transfer(tmp_path):
 folder=tmp_path/'plain';folder.mkdir();source=folder/'asset.txt';source.write_text('Neutral sample payload')
 instance=DirectoryOrganizer(Config(tmp_path),Logger());plan=instance.plan(str(tmp_path),instance.scan(str(tmp_path)))
 (folder/'.smartsort-ignore').touch()
 result=instance.execute(plan)
 assert result.error_count==1 and source.exists() and not (tmp_path/'Documents/asset.txt').exists()


def test_ordinary_nested_photos_and_single_installer_are_not_bundles(tmp_path):
 folder=tmp_path/'photos/assets';folder.mkdir(parents=True);photo=folder/'4739201.png';photo.write_bytes(b'QA image')
 installer=tmp_path/'sample.AppImage';installer.write_bytes(b'\x7fELF'+b'\0'*64);installer.chmod(0o755)
 assert not is_protected_folder(tmp_path/'photos')
 # A loose installer plus a separate photo directory isn't an app resource layout.
 assert not is_protected_folder(tmp_path)
 paths=DirectoryOrganizer(Config(tmp_path),Logger()).scan(str(tmp_path))
 assert str(photo) in paths and str(installer) in paths


def test_live_bundle_creation_cancels_pending_logo_event(tmp_path):
 folder=tmp_path/'extracting';folder.mkdir();logo=folder/'logo.png'
 instance=FileOrganizer(Config(tmp_path),Logger());calls=[]
 monitor=FileMonitor(str(tmp_path),instance,calls.append);monitor.start()
 try:
  logo.write_bytes(b'QA logo bytes')
  deadline=time.monotonic()+3
  while not monitor.event_handler.pending_files and time.monotonic()<deadline:time.sleep(.01)
  assert monitor.event_handler.pending_files
  (folder/'AppRun').write_text('#!/bin/sh\n')
  deadline=time.monotonic()+5
  while monitor.event_handler.pending_files and time.monotonic()<deadline:time.sleep(.02)
  assert not monitor.event_handler.pending_files and not calls and logo.exists()
 finally:
  monitor.stop()


def test_watch_root_bundle_is_preserved(tmp_path):
 folder,logo=bundle(tmp_path,'appdir')
 instance=FileOrganizer(Config(folder),Logger())
 assert instance.process_file(str(logo))[0]=='SKIPPED'
 assert DirectoryOrganizer(Config(folder),Logger()).scan(str(folder))==[]
