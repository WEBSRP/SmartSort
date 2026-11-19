"""Useful standalone-code routing without disassembling projects."""
from pathlib import Path
from types import SimpleNamespace
import pytest

from src.core.sorting_tester import preview_sorting
from src.core.file_intelligence.mime import DeterministicMime
from src.core.file_intelligence.context import ExtractedMetadata
from src.core.directory_organizer import DirectoryOrganizer
from src.organizer import FileOrganizer
from src.monitor import FileMonitor


class Config:
 def __init__(self,root,**changes):
  self.config=dict(sorting_mode='intelligence',rules=[],downloads_folder=str(root),destination_base=str(root/'sorted'),enable_origin_detection=False,enable_notifications=False,smart_filename_cleanup=False)
  self.config.update(changes)
 def get(self,key,default=None):return self.config.get(key,default)
class Logger:
 def __getattr__(self,name):return lambda *a,**kw:None


@pytest.fixture(autouse=True)
def private_state(tmp_path,monkeypatch):
 for key,name in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state')]:monkeypatch.setenv(key,str(tmp_path/'.state'/name))


@pytest.mark.parametrize('name,language',[('fix_click.sh','Shell'),('helper.py','Python'),('helper.js','JavaScript'),('helper.ts','TypeScript'),('main.c','C'),('main.cpp','C++'),('fix.ps1','PowerShell'),('script.rb','Ruby')])
def test_filename_only_code_previews_identify_language_without_claiming_content(tmp_path,name,language):
 result=preview_sorting(Config(tmp_path).config,[],filename=name,size_bytes=5*1024**2)
 assert result.proposal.relative_target==f'Code/{language}/{name}'
 assert result.proposal.confidence_level.value=='UNKNOWN'
 assert result.proposal.confidence_score==0 and result.source_kind=='filename'
 assert not (tmp_path/'sorted').exists()


@pytest.mark.parametrize('name,text,language',[
 ('fix_click.sh','#!/bin/bash\nprintf "%s\\n" hello\n','Shell'),
 ('helper.py','def helper():\n    return 42\n','Python'),
 ('helper.js','function helper() { return 42; }\n','JavaScript'),
 ('main.cpp','int main() { return 0; }\n','C++'),
])
def test_real_loose_code_uses_content_language_consistently_in_tester_download_and_folder(tmp_path,name,text,language):
 source=tmp_path/name;source.write_text(text)
 config=Config(tmp_path);download=FileOrganizer(config,Logger());folder=DirectoryOrganizer(config,Logger())
 preview=preview_sorting(config.config,[],file_path=str(source)).proposal
 proposal=download.analyze_download(str(source));plan=folder.plan(str(tmp_path),[str(source)])
 assert preview.relative_target==proposal.relative_target==f'Projects/Source/{language}/{name}'
 assert plan.items[0].target_path==str(tmp_path/f'Projects/Source/{language}/{name}')
 assert proposal.confidence_level.value!='UNKNOWN'
 assert any('language' in item.source_field or 'language' in item.description.lower() for item in proposal.evidence)
 assert source.read_text()==text


@pytest.mark.parametrize('status',['UNSUPPORTED','CORRUPTED','TIMEOUT'])
def test_code_type_fallback_keeps_language_when_content_is_unavailable(tmp_path,monkeypatch,status):
 source=tmp_path/'fix_click.sh';source.write_text('unreadable synthetic code')
 config=Config(tmp_path)
 for instance in [FileOrganizer(config,Logger()),DirectoryOrganizer(config,Logger())]:
  monkeypatch.setattr(instance.extractor_registry,'extract_metadata',lambda *a,**kw:ExtractedMetadata(extraction_status=status))
  target=instance.analyze_download(str(source)).target_path if isinstance(instance,FileOrganizer) else instance.plan(str(tmp_path),[str(source)]).items[0].target_path
  assert target.endswith('/Code/Shell/fix_click.sh')


@pytest.mark.parametrize('marker',['requirements.txt','setup.py','__init__.py','Makefile','Dockerfile','package.json','pyproject.toml'])
def test_project_files_assets_and_selected_subfolder_are_never_moved(tmp_path,marker):
 project=tmp_path/'my-project';assets=project/'src/assets';assets.mkdir(parents=True)
 (project/marker).write_text('QA project marker')
 source=assets/'helper.py';source.write_text('def helper(): return 42\n')
 logo=assets/'logo.png';logo.write_bytes(b'QA logo')
 config=Config(tmp_path);folder=DirectoryOrganizer(config,Logger());download=FileOrganizer(config,Logger())
 assert str(source) not in folder.scan(str(tmp_path))
 assert not folder.preview(str(assets)).items
 assert not folder.plan(str(assets),[str(source),str(logo)]).items
 assert download.process_file(str(source))[0]=='SKIPPED'
 with pytest.raises(ValueError,match='intact'):preview_sorting(config.config,[],file_path=str(source))
 monitor=FileMonitor(str(tmp_path),download,lambda *a:pytest.fail('project asset was queued'))
 monitor.event_handler._handle_event(str(source));monitor.event_handler._handle_event(str(logo))
 assert not monitor.event_handler.pending_files
 assert source.exists() and logo.read_bytes()==b'QA logo'


def test_untrusted_language_never_becomes_a_path_component():
 assert DeterministicMime.get_sorting_parts('.sh',code_language='../../escape')==('Code','Shell')
 assert DeterministicMime.get_sorting_parts('.bin',code_language='../../escape')==('Others',)
