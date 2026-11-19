"""Known file formats must not need semantic keywords to avoid Others."""
from types import SimpleNamespace
from pathlib import Path
import pytest

from src.organizer import FileOrganizer
from src.core.directory_organizer import DirectoryOrganizer
from src.core.file_intelligence.mime import DeterministicMime
from src.core.file_intelligence.context import ExtractedMetadata


class Config:
 def __init__(self,root,**changes):
  self.data=dict(rules=[],sorting_mode='intelligence',destination_base=str(root/'sorted'),enable_origin_detection=False,enable_notifications=False,smart_filename_cleanup=False,large_file_threshold_gb=2.5)
  self.data.update(changes)
 def get(self,key,default=None):return self.data.get(key,default)

class Logger:
 def __getattr__(self,name):return lambda *a,**kw:None


@pytest.mark.parametrize('name,category', [
 ('4739201.mp4','Videos'),('recording.MKV','Videos'),('clip.3gp','Videos'),
 ('common.txt','Documents'),('opaque.pdf','Documents'),('4739201.PNG','Images'),
 ('download.wav','Audio'),('cursor_3.24.12_amd64.deb','Applications'),
 ('Freebuff-0.0.171-linux-x86_64.AppImage','Applications'),
 ('com.innersloth.spacemafia_2026.8.18.xapk','Applications'),
 ('app.apk','Applications'),('software.rpm','Applications'),
 ('bundle.zip','Archives'),('opaque.bin','Others'),
])
@pytest.mark.parametrize('status',['UNSUPPORTED','SUCCESS','CORRUPTED'])
def test_download_and_folder_agree_on_known_type_when_content_is_uninformative(tmp_path,monkeypatch,name,category,status):
 path=tmp_path/name;path.write_bytes(b'neutral synthetic payload\n')
 config=Config(tmp_path)
 download=FileOrganizer(config,Logger());folder=DirectoryOrganizer(config,Logger())
 for instance in (download,folder):
  monkeypatch.setattr(instance.extractor_registry,'extract_metadata',lambda *a,**kw:ExtractedMetadata(extraction_status=status))
 proposal=download.analyze_download(str(path))
 plan=folder.plan(str(tmp_path),[str(path)])
 assert proposal.relative_target==f'{category}/{name}'
 assert len(plan.items)==1 and plan.items[0].target_path==str(tmp_path/category/name)
 assert proposal.confidence_level.value=='UNKNOWN' and proposal.confidence_score==0
 assert any('fallback' in item.description.casefold() for item in proposal.evidence)
 assert not proposal.is_rule_override
 download.notification_manager.send_success_notification=lambda *a:False
 result,target=download.process_file(str(path))
 assert result=='SUCCESS' and Path(target).read_bytes()==b'neutral synthetic payload\n'


def test_semantic_evidence_keeps_intelligent_hierarchy(tmp_path):
 path=tmp_path/'opaque.md';path.write_text('# Invoice\nFinance invoice total payment due\n')
 proposal=FileOrganizer(Config(tmp_path),Logger()).analyze_download(str(path))
 assert proposal.relative_target=='Work/Invoices/opaque.md'


def test_custom_rule_still_wins_over_type_fallback(tmp_path):
 path=tmp_path/'clip.mp4';path.write_bytes(b'neutral')
 rule=dict(id='custom',name='Pinned',enabled=True,priority=1,conditions=[],destination='Pinned')
 proposal=FileOrganizer(Config(tmp_path,sorting_mode='rules_first',rules=[rule]),Logger()).analyze_download(str(path))
 assert proposal.relative_target=='Pinned/clip.mp4' and proposal.is_rule_override
