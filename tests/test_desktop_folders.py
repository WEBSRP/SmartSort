"""Default download routes reuse desktop folders, including external locations."""
import hashlib
from pathlib import Path
import pytest
from src.organizer import FileOrganizer
from src.core.sorting_tester import preview_sorting
from src.core.directory_organizer import DirectoryOrganizer
from src.utils.desktop_folders import desktop_folders
from src.utils.file_utils import FileUtils


class Config:
 def __init__(self,home,**changes):
  self.config=dict(destination_base=str(home),downloads_folder=str(home/'Downloads'),sorting_mode='intelligence',rules=[],use_desktop_folders=True,enable_origin_detection=False,enable_notifications=False,smart_filename_cleanup=False)
  self.config.update(changes)
 def get(self,key,default=None):return self.config.get(key,default)
 def save_config(self,data):self.config=data
class Logger:
 def __getattr__(self,name):return lambda *a,**kw:None


@pytest.fixture
def desktop(tmp_path,monkeypatch):
 home=tmp_path/'home';(home/'Downloads').mkdir(parents=True)
 config=tmp_path/'config';config.mkdir();pictures=tmp_path/'external/Pictures'
 values={'PICTURES':pictures,'VIDEOS':home/'My Videos','MUSIC':home/'My Music','DOCUMENTS':home/'My Documents','DOWNLOAD':home/'Downloads'}
 path=config/'user-dirs.dirs'
 path.write_text('\n'.join(f'XDG_{key}_DIR="{value}"' for key,value in values.items())+'\n')
 monkeypatch.setattr(Path,'home',lambda:home)
 for key,folder in [('XDG_CONFIG_HOME',config),('XDG_DATA_HOME',tmp_path/'data'),('XDG_CACHE_HOME',tmp_path/'cache'),('XDG_STATE_HOME',tmp_path/'state')]:monkeypatch.setenv(key,str(folder))
 return home,values,path


@pytest.mark.parametrize('name,category,remainder',[
 ('4739201.png','PICTURES','4739201.png'),('4739201.mp4','VIDEOS','4739201.mp4'),
 ('4739201.wav','MUSIC','4739201.wav'),('common.txt','DOCUMENTS','common.txt'),
 ('fix_click.sh','DOCUMENTS','Code/Shell/fix_click.sh'),
 ('sample.AppImage','DOWNLOAD','Applications/sample.AppImage'),
 ('opaque.bin','DOWNLOAD','Others/opaque.bin'),
])
def test_filename_tester_uses_existing_desktop_roots(desktop,name,category,remainder):
 home,folders,_=desktop
 result=preview_sorting(Config(home).config,[],filename=name,size_bytes=1234)
 assert result.proposal.target_path==str(folders[category]/remainder)
 assert not (home/'Images').exists() and not (home/'Media').exists() and not (home/'Audio').exists()
 assert any(e.source_field=='desktop.directories' for e in result.proposal.evidence)


@pytest.mark.parametrize('name,payload,category,remainder',[
 ('4739201.png',b'not an image','PICTURES','4739201.png'),
 ('4739201.mp4',b'not a video','VIDEOS','4739201.mp4'),
 ('4739201.wav',b'not audio','MUSIC','4739201.wav'),
 ('opaque.md',b'# Invoice\nFinance billing invoice','DOCUMENTS','Work/Invoices/opaque.md'),
 ('lecture_DBMS.md',b'# DBMS Lecture\nCollege database lecture course','DOCUMENTS','College/DBMS/Lectures/lecture_DBMS.md'),
])
def test_actual_download_and_tester_agree_and_transfer_stays_in_selected_folder(desktop,name,payload,category,remainder):
 home,folders,_=desktop;source=home/'Downloads'/name;source.write_bytes(payload)
 config=Config(home);instance=FileOrganizer(config,Logger());instance.notification_manager.send_success_notification=lambda *a:False
 expected=folders[category]/remainder
 assert instance.analyze_download(str(source)).target_path==str(expected)
 assert preview_sorting(config.config,[],file_path=str(source)).proposal.target_path==str(expected)
 status,target=instance.process_file(str(source))
 assert status=='SUCCESS' and target==str(expected) and expected.read_bytes()==payload and not source.exists()
 assert not (home/'Images').exists() and not (home/'Media').exists()


def test_semantic_media_image_uses_pictures_not_media_tree(desktop):
 home,folders,_=desktop
 result=preview_sorting(Config(home).config,[],filename='wallpaper.png',size_bytes=1000)
 assert result.proposal.target_path==str(folders['PICTURES']/'Wallpapers/wallpaper.png')


def test_legacy_picture_rule_reuses_desktop_folder_and_keeps_subfolders(desktop):
 home,folders,_=desktop
 rule=dict(id='image',name='Small images',priority=1,enabled=True,conditions=[],destination='Pictures/Low_Quality/{extension}')
 config=Config(home,sorting_mode='rules_first',rules=[rule]);source=home/'Downloads/photo.png';source.write_bytes(b'fake image')
 proposal=FileOrganizer(config,Logger()).analyze_download(str(source))
 assert proposal.target_path==str(folders['PICTURES']/'Low_Quality/PNG/photo.png') and proposal.is_rule_override


@pytest.mark.parametrize('change',['custom_base','opt_out','custom_rule'])
def test_explicit_destinations_and_opt_out_are_respected(desktop,change):
 home,folders,_=desktop;config=Config(home)
 if change=='custom_base':config.config['destination_base']=str(home/'Custom')
 if change=='opt_out':config.config['use_desktop_folders']=False
 rules=[]
 if change=='custom_rule':
  from src.rules.rule import Rule
  config.config['sorting_mode']='rules_first'
  rules=[Rule.from_dict(dict(id='pin',name='Pinned',priority=1,enabled=True,conditions=[],destination='Pinned'))]
 proposal=preview_sorting(config.config,rules,filename='4739201.png',size_bytes=1000).proposal
 expected=home/'Custom/Images/4739201.png' if change=='custom_base' else home/('Pinned/4739201.png' if change=='custom_rule' else 'Images/4739201.png')
 assert proposal.target_path==str(expected)


def test_desktop_symlink_can_point_outside_home_without_allowing_child_escape(desktop):
 home,folders,path=desktop
 external=folders['PICTURES'];external.mkdir(parents=True)
 (home/'Pictures').symlink_to(external,target_is_directory=True)
 path.write_text('XDG_PICTURES_DIR="$HOME/Pictures"\n')
 source=home/'Downloads/4739201.png';source.write_bytes(b'image')
 instance=FileOrganizer(Config(home),Logger());instance.notification_manager.send_success_notification=lambda *a:False
 assert instance.process_file(str(source))==('SUCCESS',str(external/'4739201.png'))


def test_destination_escape_via_symlink_inside_selected_desktop_root_is_rejected(desktop):
 home,folders,_=desktop;external=folders['PICTURES'];external.mkdir(parents=True)
 outside=home.parent/'outside';outside.mkdir();(external/'Escape').symlink_to(outside,target_is_directory=True)
 rule=dict(id='image',name='Image',priority=1,enabled=True,conditions=[],destination='Pictures/Escape')
 source=home/'Downloads/photo.png';source.write_bytes(b'image')
 instance=FileOrganizer(Config(home,sorting_mode='rules_first',rules=[rule]),Logger())
 status,_=instance.process_file(str(source))
 assert status=='ERROR' and source.exists() and not list(outside.iterdir())


def test_user_directory_change_during_duplicate_verification_preserves_source(desktop,monkeypatch):
 home,folders,path=desktop;source=home/'Downloads/4739201.png';source.write_bytes(b'image')
 target=folders['PICTURES']/'4739201.png';target.parent.mkdir(parents=True);target.write_bytes(b'image')
 original=FileUtils.calculate_sha256;changed=[]
 def change_settings(value):
  digest=original(value)
  if not changed:
   changed.append(True);path.write_text(f'XDG_PICTURES_DIR="{home}/New Pictures"\n')
  return digest
 monkeypatch.setattr(FileUtils,'calculate_sha256',change_settings)
 status,message=FileOrganizer(Config(home),Logger()).process_file(str(source))
 assert status=='ERROR' and 'settings changed' in message and source.read_bytes()==target.read_bytes()==b'image'


def test_directory_batch_keeps_its_reviewed_root(desktop):
 home,folders,_=desktop;selected=home/'Selected';selected.mkdir();source=selected/'4739201.png';source.write_bytes(b'image')
 instance=DirectoryOrganizer(Config(home),Logger());plan=instance.plan(str(selected),[str(source)])
 assert plan.items[0].target_path==str(selected/'Images/4739201.png')


def test_parser_handles_home_and_spaces_without_executing_shell(desktop):
 home,_,path=desktop;sentinel=home/'SHOULD_NOT_EXIST'
 path.write_text(f'XDG_PICTURES_DIR="$HOME/My Photos"\nXDG_MUSIC_DIR="/tmp/$(touch {sentinel})"\nXDG_VIDEOS_DIR="/etc/unsafe"\n')
 values=desktop_folders()
 assert values['PICTURES']==str(home/'My Photos')
 assert values['MUSIC']==str(home/'Music') and values['VIDEOS']==str(home/'Videos')
 assert not sentinel.exists()
