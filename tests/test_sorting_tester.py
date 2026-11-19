"""Sorting Tester previews the real policy without transferring user files."""
from pathlib import Path
import copy
import pytest
from src.core.sorting_tester import preview_sorting
from src.rules.rule import Rule
from src.organizer import FileOrganizer
from src.utils.file_utils import FileUtils


@pytest.fixture
def settings(tmp_path,monkeypatch):
 for key,name in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state')]:monkeypatch.setenv(key,str(tmp_path/'.state'/name))
 return dict(sorting_mode='intelligence',rules=[],destination_base=str(tmp_path/'sorted'),downloads_folder=str(tmp_path),enable_origin_detection=False,enable_notifications=False,smart_filename_cleanup=False)


def broad_rule():
 return Rule.from_dict(dict(id='pin',name='Pinned',enabled=True,priority=1,conditions=[],destination='Pinned'))


@pytest.mark.parametrize('name,category',[('4739201.mp4','Videos'),('common.txt','Documents'),('app.AppImage','Applications'),('unknown.bin','Others')])
def test_filename_tests_use_intelligence_and_type_fallback_without_file_io(settings,monkeypatch,name,category):
 monkeypatch.setattr(FileOrganizer,'analyze_download',lambda *a,**kw:pytest.fail('synthetic names are not real files'))
 before=copy.deepcopy(settings)
 result=preview_sorting(settings,[broad_rule()],filename=name,size_bytes=1234)
 assert result.proposal.relative_target==f'{category}/{name}'
 assert result.source_kind=='filename' and result.mode=='intelligence' and result.rule_priority is None
 assert result.proposal.confidence_score==0 and not Path(settings['destination_base']).exists()
 assert settings==before


@pytest.mark.parametrize('size,category',[(1024**2-1,'Small'),(1024**2,'Big')])
def test_filename_rules_first_keeps_size_condition_semantics(settings,size,category):
 settings['sorting_mode']='rules_first'
 rules=[Rule.from_dict(dict(id='small',name='Small',enabled=True,priority=1,conditions=[dict(type='size',operator='<',value='1MB')],destination='Small')),broad_rule()]
 rules[1].priority=2;rules[1].name='Big';rules[1].destination='Big'
 result=preview_sorting(settings,rules,filename='sample.bin',size_bytes=size)
 assert result.proposal.relative_target==f'{category}/sample.bin' and result.rule_priority==(1 if category=='Small' else 2)


@pytest.mark.parametrize('mode,category',[('intelligence','Work/Invoices'),('rules_first','Pinned')])
def test_real_file_analysis_matches_actual_download_preview_and_is_read_only(settings,tmp_path,monkeypatch,mode,category):
 settings['sorting_mode']=mode
 source=tmp_path/'opaque.md';payload=b'# Invoice\nFinance billing invoice';source.write_bytes(payload)
 before=source.stat();rules=[broad_rule()]
 for name in ['safe_copy','remove_verified_duplicate']:monkeypatch.setattr(FileUtils,name,lambda *a,**kw:pytest.fail('tester must never transfer or remove'))
 monkeypatch.setattr(FileOrganizer,'process_file',lambda *a,**kw:pytest.fail('tester must never execute sorting'))
 result=preview_sorting(settings,rules,file_path=str(source))
 assert result.proposal.relative_target==f'{category}/opaque.md'
 assert result.source_kind=='file' and source.read_bytes()==payload
 assert source.stat().st_mtime_ns==before.st_mtime_ns and not Path(settings['destination_base']).exists()
 assert result.rule_priority==(1 if mode=='rules_first' else None)


def test_disabled_content_extraction_is_honored(settings,tmp_path):
 source=tmp_path/'opaque.md';source.write_text('# Invoice\nFinance billing invoice')
 settings['enable_deep_content_extraction']=False
 result=preview_sorting(settings,[],file_path=str(source))
 assert result.proposal.domain=='Documents'
 assert not any(e.source_field.startswith('metadata.') for e in result.proposal.evidence)


def test_protected_bundle_is_not_inspected(settings,tmp_path,monkeypatch):
 folder=tmp_path/'Example.AppDir';folder.mkdir();source=folder/'logo.png';source.write_bytes(b'logo')
 monkeypatch.setattr('src.core.filename_cleanup.FilenameCleanup.generate_clean_name',lambda *a:pytest.fail('protected asset inspected'))
 settings['smart_filename_cleanup']=True
 with pytest.raises(ValueError,match='intact'):preview_sorting(settings,[],file_path=str(source))
 assert source.read_bytes()==b'logo'


@pytest.mark.parametrize('name,size',[('../escape.txt',0),('valid.txt',-1),('valid.txt',True),('',0)])
def test_invalid_filename_or_size_is_rejected(settings,name,size):
 with pytest.raises((ValueError,TypeError)):preview_sorting(settings,[],filename=name,size_bytes=size)


def test_missing_real_file_fails_instead_of_fabricating_analysis(settings,tmp_path):
 with pytest.raises((ValueError,OSError)):preview_sorting(settings,[],file_path=str(tmp_path/'missing.pdf'))
