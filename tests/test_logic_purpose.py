"""Model-free purpose cues and explicit manual overrides across sorting flows."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.core.sorting_tester import preview_sorting
from src.core.file_intelligence import FileContext,OriginInfo,SignalExtractor,MultiSignalClassifier
from src.core.directory_organizer import DirectoryOrganizer
from src.organizer import FileOrganizer
from src.rules.rule import Rule


class Config:
 def __init__(self,root,**changes):
  self.config=dict(sorting_mode='intelligence',rules=[],downloads_folder=str(root),destination_base=str(root/'sorted'),enable_origin_detection=False,enable_notifications=False,smart_filename_cleanup=False)
  self.config.update(changes)
 def get(self,key,default=None):return self.config.get(key,default)
 def save_config(self,data):self.config=data
class Logger:
 def __getattr__(self,name):return lambda *a,**kw:None


@pytest.fixture(autouse=True)
def private_state(tmp_path,monkeypatch):
 for key,name in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state')]:monkeypatch.setenv(key,str(tmp_path/'.state'/name))


@pytest.mark.parametrize('name,target',[
 ('leetcode_two_sum.png','Media/Images/Coding_Challenges/leetcode_two_sum.png'),
 ('coding_challenge.pdf','Projects/Coding_Challenges/coding_challenge.pdf'),
 ('leetcode_solution.py','Projects/Coding_Challenges/Python/leetcode_solution.py'),
 ('forest_wallpaper.jpg','Media/Images/Wallpapers/forest_wallpaper.jpg'),
 ('wallpaper1080p.png','Media/Images/Wallpapers/wallpaper1080p.png'),
 ('desktopBackground.png','Media/Images/Wallpapers/desktopBackground.png'),
 ('Screenshot_2026.png','Media/Images/Screenshots/Screenshot_2026.png'),
 ('leetcode_logo.png','Images/leetcode_logo.png'),
 ('4739201.png','Images/4739201.png'),
])
def test_filename_purpose_hints_are_explicit_and_do_not_invent_image_understanding(tmp_path,name,target):
 result=preview_sorting(Config(tmp_path).config,[],filename=name,size_bytes=1234)
 assert result.proposal.relative_target==target
 if name.startswith(('leetcode_logo','4739201')):assert result.proposal.confidence_level.value=='UNKNOWN'
 else:assert result.proposal.confidence_level.value=='PROBABLE'


def test_document_problem_structure_identifies_challenge_without_a_model(tmp_path):
 path=tmp_path/'opaque.txt';path.write_text('Problem statement\nFind the sum.\nConstraints: n <= 100.\nExample input: 1 2\nOutput: 3\n')
 result=FileOrganizer(Config(tmp_path),Logger()).analyze_download(str(path))
 assert result.relative_target=='Projects/Coding_Challenges/opaque.txt'
 assert any('constraints' in e.description for e in result.evidence)


@pytest.mark.parametrize('url,target',[
 ('https://leetcode.com/problems/two-sum/image.png?token=PRIVATE','Media'),
 ('https://leetcode.com.attacker.example/problems/two-sum/image.png','Others'),
 ('https://leetcode.com/images/avatar.png','Others'),
])
def test_source_cues_are_local_validated_and_do_not_leak_queries(url,target):
 ctx=FileContext('/sample/4739.png','4739.png','4739','.png','image/png',1234,0,0,0,0)
 ctx.origin=OriginInfo(url=url)
 SignalExtractor().extract_signals(ctx);MultiSignalClassifier().classify(ctx)
 assert ctx.classification_domain==target
 assert 'PRIVATE' not in repr(ctx.evidence_list)
 if target=='Media':assert ctx.subcategories==['Images','Coding_Challenges']


def manual_rule(enabled=True):
 return dict(id='manual',name='My coding screenshots',enabled=enabled,priority=1,apply_in_intelligence=True,
             conditions=[dict(type='filename',value=['practice'])],destination='Pictures/Coding_Challenges')


@pytest.mark.parametrize('kind',['download','folder','tester'])
def test_manual_rule_overrides_automatic_hints_in_intelligence(tmp_path,kind):
 source=tmp_path/'practice_wallpaper.png';source.write_bytes(b'QA image')
 config=Config(tmp_path,rules=[manual_rule()])
 if kind=='download':proposal=FileOrganizer(config,Logger()).analyze_download(str(source));target=proposal.target_path;matched=proposal.is_rule_override
 elif kind=='folder':item=DirectoryOrganizer(config,Logger()).plan(str(tmp_path),[str(source)]).items[0];target=item.target_path;matched=item.rule_name=='My coding screenshots'
 else:
  proposal=preview_sorting(config.config,[Rule.from_dict(manual_rule())],filename=source.name,size_bytes=10).proposal;target=proposal.target_path;matched=proposal.is_rule_override
 expected=tmp_path/('Pictures' if kind=='folder' else 'sorted/Pictures')/'Coding_Challenges'/source.name
 assert target==str(expected) and matched


@pytest.mark.parametrize('marked,enabled',[(False,True),(True,False)])
def test_unmarked_legacy_and_disabled_rules_do_not_override_intelligence(tmp_path,marked,enabled):
 rule=manual_rule(enabled);rule['apply_in_intelligence']=marked
 proposal=preview_sorting(Config(tmp_path).config,[Rule.from_dict(rule)],filename='practice_wallpaper.png',size_bytes=10).proposal
 assert not proposal.is_rule_override and proposal.relative_target=='Media/Images/Wallpapers/practice_wallpaper.png'


def test_manual_rule_serialization_and_boolean_validation():
 rule=Rule.from_dict(manual_rule());assert Rule.from_dict(rule.to_dict()).apply_in_intelligence is True
 with pytest.raises(ValueError):Rule.from_dict(dict(manual_rule(),apply_in_intelligence='yes'))


def test_project_protection_precedes_manual_rules(tmp_path):
 project=tmp_path/'Project';project.mkdir();(project/'pyproject.toml').write_text('[project]')
 source=project/'practice_wallpaper.png';source.write_bytes(b'QA image')
 config=Config(tmp_path,rules=[manual_rule()])
 assert FileOrganizer(config,Logger()).process_file(str(source))[0]=='SKIPPED'
 assert not DirectoryOrganizer(config,Logger()).plan(str(tmp_path),[str(source)]).items
 assert source.read_bytes()==b'QA image'
