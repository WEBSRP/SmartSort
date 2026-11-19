"""Origin provenance uses synthetic browser profiles only, never real history."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from unittest.mock import MagicMock

import pytest

from src.core.file_intelligence import OriginDetector
from src.core.file_intelligence.context import ConfidenceLevel, OriginSource
from src.core.file_intelligence.metadata import FileContextBuilder, FileMetadataExtractor
from src.core.file_intelligence.origin import origin_from_url
from src.utils.config import ConfigManager

NOW = 1730000000.0


@pytest.fixture(autouse=True)
def isolated_profiles(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('HOME', str(tmp_path))
    for key, name in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_STATE_HOME','state'),('XDG_CACHE_HOME','cache')]:
        monkeypatch.setenv(key,str(tmp_path/name))
    monkeypatch.setattr(FileMetadataExtractor,'read_xattr',staticmethod(lambda *args: None))


def target(tmp_path,name='report.pdf'):
    path=tmp_path/'Downloads'/name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b'report')
    os.utime(path,(NOW,NOW))
    return path


def chromium(tmp_path,file,url='https://github.com/project/file?token=SECRET',*,profile='Default',browser='google-chrome',size=6,stamp=NOW,state=1,tab='https://example.com/tab',chain=True,wal=False):
    path=tmp_path/'config'/browser/profile/'History'
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    if wal:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA wal_autocheckpoint=0')
    db.executescript('''CREATE TABLE downloads (id INTEGER PRIMARY KEY,target_path TEXT,start_time INTEGER,end_time INTEGER,total_bytes INTEGER,state INTEGER,tab_url TEXT,tab_referrer_url TEXT);
CREATE INDEX downloads_target ON downloads(target_path);
CREATE TABLE downloads_url_chains (id INTEGER, chain_index INTEGER, url TEXT, PRIMARY KEY(id,chain_index));''')
    moment=int((stamp+11644473600)*1000000) if stamp is not None else None
    db.execute('INSERT INTO downloads VALUES (1,?,?,?,?,?,?,?)',(str(file),moment,moment,size,state,tab,''))
    if chain:
        db.execute('INSERT INTO downloads_url_chains VALUES (1,0,?)',(url,))
    db.commit()
    if wal:
        return path,db
    db.close()
    return path


def firefox(tmp_path,file,url='https://canvas.university.edu/files/report?auth=SECRET',*,profile='test.default-release',size=6,stamp=NOW,state=1,metadata=True,raw_path=None):
    path=tmp_path/'.mozilla/firefox'/profile/'places.sqlite'
    path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE moz_places(id INTEGER PRIMARY KEY,url TEXT);
CREATE TABLE moz_anno_attributes(id INTEGER PRIMARY KEY,name TEXT);
CREATE TABLE moz_annos(id INTEGER PRIMARY KEY,place_id INTEGER,anno_attribute_id INTEGER,content TEXT,dateAdded INTEGER);
INSERT INTO moz_anno_attributes VALUES(1,'downloads/destinationFileURI'),(2,'downloads/metaData');''')
        db.execute('INSERT INTO moz_places VALUES(1,?)',(url,))
        db.execute('INSERT INTO moz_annos VALUES(1,1,1,?,?)',(raw_path or Path(file).as_uri(),int((stamp or 0)*1000000)))
        if metadata:
            db.execute('INSERT INTO moz_annos VALUES(2,1,2,?,?)',(json.dumps(dict(state=state,endTime=stamp*1000 if stamp else None,fileSize=size)),int((stamp or 0)*1000000)))
    return path


def detect(file,**kwargs):
    return OriginDetector().detect_origin(file,file_timestamp=NOW,**kwargs)


@pytest.mark.parametrize('raw,url,domain,site',[
    ('https://user:SECRET@RAW.GITHUBUSERCONTENT.COM/a/b?token=SECRET#SECRET','https://raw.githubusercontent.com/a/b','raw.githubusercontent.com','github'),
    ('HTTPS://WWW.GITHUB.COM.:443/a','https://www.github.com/a','github.com','github'),
    ('http://example.com:8080/a;jsessionid=SECRET/b?token=SECRET','http://example.com:8080/a/b','example.com','example.com'),
    ('https://sub.instructure.com/course','https://sub.instructure.com/course','sub.instructure.com','lms'),
    ('https://canvas.university.edu/files/1','https://canvas.university.edu/files/1','canvas.university.edu','lms'),
    ('https://moodle.college.edu/file','https://moodle.college.edu/file','moodle.college.edu','lms'),
    ('https://arxiv.org/pdf/123','https://arxiv.org/pdf/123','arxiv.org','academic_paper'),
    ('https://ieeexplore.ieee.org/document/1','https://ieeexplore.ieee.org/document/1','ieeexplore.ieee.org','academic_paper'),
    ('https://kaggle.com/data','https://kaggle.com/data','kaggle.com','kaggle'),
    ('https://images.unsplash.com/a','https://images.unsplash.com/a','images.unsplash.com','wallpaper'),
    ('https://i.redd.it/pic.png','https://i.redd.it/pic.png','i.redd.it','reddit'),
    ('https://github.com.attacker.invalid/file','https://github.com.attacker.invalid/file','github.com.attacker.invalid','github.com.attacker.invalid'),
    ('https://files.example.co.uk/a','https://files.example.co.uk/a','files.example.co.uk','files.example.co.uk'),
    ('http://[::1]:8080/a','http://[::1]:8080/a','::1','::1'),
    ('https://bücher.example/a','https://xn--bcher-kva.example/a','xn--bcher-kva.example','xn--bcher-kva.example'),
])
def test_url_sanitization_and_local_site_mapping(raw,url,domain,site):
    origin=origin_from_url(raw)
    assert (origin.url,origin.domain,origin.site_name)==(url,domain,site)
    assert 'SECRET' not in json.dumps(origin.to_dict())


@pytest.mark.parametrize('url',[None,123,'','example.com/file','//example.com/file','file:///secret','javascript:alert(1)','data:text/plain,secret','blob:https://example.com/id','https://','https://host:99999/file','https://host:bad/file','https://[broken/file','https://bad_host/file','https://host/a\nsecret','https://host/%00secret','https://host\\@evil/file','https://host:0/file','https://'+'a'*5000])
def test_invalid_urls_are_unknown(url):
    assert origin_from_url(url).source is OriginSource.UNKNOWN


def test_xattr_priority_sanitizes_and_skips_browser_access(tmp_path,monkeypatch):
    file=target(tmp_path)
    values={'user.xdg.origin.url':'https://u:SECRET@github.com/project?token=SECRET#SECRET','user.xdg.referrer.url':'https://other.example/'}
    monkeypatch.setattr(FileMetadataExtractor,'read_xattr',staticmethod(lambda p,a: values[a]))
    monkeypatch.setattr(OriginDetector,'_discover_databases',lambda self: pytest.fail('browser history queried despite xattr'))
    origin=detect(file)
    assert origin.url=='https://github.com/project'
    assert origin.confidence is ConfidenceLevel.CONFIRMED
    assert origin.source is OriginSource.EXTENDED_ATTRIBUTE
    assert 'SECRET' not in json.dumps(origin.to_dict())


def test_invalid_origin_xattr_uses_valid_referrer(tmp_path,monkeypatch):
    monkeypatch.setattr(FileMetadataExtractor,'read_xattr',staticmethod(lambda p,a:'javascript:bad' if a.endswith('origin.url') else 'https://gitlab.com/project?key=SECRET'))
    assert detect(target(tmp_path)).site_name=='gitlab'


def test_foundation_xattrs_share_secure_sanitization(tmp_path,monkeypatch):
    file=target(tmp_path)
    monkeypatch.setattr(FileMetadataExtractor,'read_extended_attributes',classmethod(lambda cls,p:{'user.xdg.origin.url':'https://name:SECRET@example.com/file?token=SECRET'}))
    origin=FileContextBuilder.build_initial_context(file).origin
    assert origin.url=='https://example.com/file'
    assert origin.domain=='example.com'


def test_chromium_chain_exact_match(tmp_path):
    file=target(tmp_path)
    chromium(tmp_path,file)
    origin=detect(file)
    assert origin.url=='https://github.com/project/file'
    assert origin.source is OriginSource.BROWSER_SQLITE
    assert origin.confidence is ConfidenceLevel.CONFIRMED


def test_chromium_final_redirect_precedes_tab_url(tmp_path):
    file=target(tmp_path)
    path=chromium(tmp_path,file)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO downloads_url_chains VALUES(1,1,?)',('https://cdn.example/file?secret=SECRET',))
    assert detect(file).url=='https://cdn.example/file'


def test_chromium_tab_fallback_without_chain(tmp_path):
    file=target(tmp_path)
    chromium(tmp_path,file,chain=False,tab='https://github.com/release?secret=SECRET')
    assert detect(file).url=='https://github.com/release'


def test_chromium_minimal_schema(tmp_path):
    file=target(tmp_path)
    path=tmp_path/'config/chromium/Default/History'
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE downloads(target_path TEXT,tab_url TEXT)')
        db.execute('INSERT INTO downloads VALUES(?,?)',(str(file),'https://example.com/a?secret=SECRET'))
    origin=detect(file)
    assert origin.url=='https://example.com/a'
    assert origin.confidence is ConfidenceLevel.PROBABLE


def test_legacy_chromium_path_and_unix_timestamp(tmp_path):
    file=target(tmp_path)
    path=tmp_path/'config/chromium/Default/History';path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE downloads(full_path TEXT,url TEXT,start_time INTEGER,total_bytes INTEGER)')
        db.execute('INSERT INTO downloads VALUES(?,?,?,?)',(str(file),'https://example.com/download',int(NOW),6))
    assert detect(file).confidence is ConfidenceLevel.CONFIRMED


@pytest.mark.parametrize('browser',['google-chrome','chromium','BraveSoftware/Brave-Browser','microsoft-edge'])
@pytest.mark.parametrize('profile',['Default','Profile 1'])
def test_chromium_profile_discovery(tmp_path,browser,profile):
    file=target(tmp_path)
    chromium(tmp_path,file,browser=browser,profile=profile)
    assert detect(file).source is OriginSource.BROWSER_SQLITE


def test_firefox_annotations_and_metadata(tmp_path):
    file=target(tmp_path)
    firefox(tmp_path,file)
    origin=detect(file)
    assert origin.url=='https://canvas.university.edu/files/report'
    assert origin.site_name=='lms'
    assert origin.confidence is ConfidenceLevel.CONFIRMED


@pytest.mark.parametrize('name',["résumé #1%.pdf","file_%.pdf","name' OR 1=1 --.pdf"])
def test_special_filenames_are_parameterized_and_uri_decoded(tmp_path,name):
    file=target(tmp_path,name)
    firefox(tmp_path,file)
    assert detect(file).source is OriginSource.BROWSER_SQLITE


def test_firefox_missing_metadata_has_lower_confidence(tmp_path):
    file=target(tmp_path)
    firefox(tmp_path,file,metadata=False)
    assert detect(file).confidence is ConfidenceLevel.PROBABLE


def test_firefox_minimal_annotation_schema(tmp_path):
    file=target(tmp_path)
    path=tmp_path/'.mozilla/firefox/custom.default/places.sqlite';path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE moz_places(id INTEGER,url TEXT);CREATE TABLE moz_annos(place_id INTEGER,content TEXT,dateAdded INTEGER);')
        db.execute('INSERT INTO moz_places VALUES(1,?)',('https://example.com/file?secret=SECRET',))
        db.execute('INSERT INTO moz_annos VALUES(1,?,?)',(file.as_uri(),int(NOW*1000000)))
    assert detect(file).url=='https://example.com/file'


def test_firefox_profiles_ini_external_profile(tmp_path):
    file=target(tmp_path)
    path=firefox(tmp_path,file)
    external=tmp_path/'external';external.mkdir()
    path.rename(external/'places.sqlite')
    ini=tmp_path/'.mozilla/firefox/profiles.ini'
    ini.write_text(f'[Profile0]\nName=External\nIsRelative=0\nPath={external}\n')
    assert detect(file).source is OriginSource.BROWSER_SQLITE


@pytest.mark.parametrize('family',['chromium','firefox'])
def test_filename_fallback_requires_size_and_time(tmp_path,family):
    file=target(tmp_path)
    old=tmp_path/'OldDownloads'/file.name
    (chromium if family=='chromium' else firefox)(tmp_path,old)
    origin=detect(file)
    assert origin.source is OriginSource.BROWSER_SQLITE
    assert origin.confidence is ConfidenceLevel.PROBABLE
    assert 'filename' in origin.evidence_detail


@pytest.mark.parametrize('size,stamp,state',[(99,NOW,1),(6,NOW-172800,1),(6,NOW,2),(6,NOW,0)])
@pytest.mark.parametrize('family',['chromium','firefox'])
def test_contradicting_download_records_are_rejected(tmp_path,size,stamp,state,family):
    file=target(tmp_path)
    (chromium if family=='chromium' else firefox)(tmp_path,file,size=size,stamp=stamp,state=state)
    assert detect(file).source is OriginSource.UNKNOWN


@pytest.mark.parametrize('family',['chromium','firefox'])
def test_filename_alone_does_not_establish_origin(tmp_path,family):
    file=target(tmp_path)
    old=tmp_path/'elsewhere'/file.name
    if family=='chromium': chromium(tmp_path,old,size=None,stamp=None)
    else: firefox(tmp_path,old,metadata=False,stamp=None)
    assert detect(file).source is OriginSource.UNKNOWN


def test_conflicting_profiles_remain_unknown(tmp_path):
    file=target(tmp_path)
    chromium(tmp_path,file,url='https://one.example/file')
    firefox(tmp_path,file,url='https://two.example/file')
    assert detect(file).source is OriginSource.UNKNOWN


def test_matching_profiles_coalesce_after_sanitization(tmp_path):
    file=target(tmp_path)
    chromium(tmp_path,file,url='https://example.com/file?token=ONE')
    firefox(tmp_path,file,url='https://example.com/file?token=TWO')
    assert detect(file).url=='https://example.com/file'


def test_no_timestamp_exact_path_is_probable(tmp_path):
    file=target(tmp_path)
    chromium(tmp_path,file,stamp=None)
    assert detect(file).confidence is ConfidenceLevel.PROBABLE


def test_wal_only_committed_records_are_visible_without_modifying_browser(tmp_path):
    file=target(tmp_path)
    path,db=chromium(tmp_path,file,wal=True)
    try:
        before={p.name:(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).digest()) for p in path.parent.iterdir()}
        assert Path(str(path)+'-wal').stat().st_size>0
        origin=detect(file)
        assert origin.url=='https://github.com/project/file'
        after={p.name:(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).digest()) for p in path.parent.iterdir()}
        assert after==before
    finally:
        db.close()


def test_exclusively_locked_browser_can_use_private_snapshot(tmp_path):
    file=target(tmp_path)
    path=chromium(tmp_path,file)
    db=sqlite3.connect(path)
    db.execute('BEGIN EXCLUSIVE')
    try:
        assert detect(file).source is OriginSource.BROWSER_SQLITE
    finally:
        db.rollback();db.close()


def test_rollback_journal_is_skipped(tmp_path):
    file=target(tmp_path)
    path=chromium(tmp_path,file)
    db=sqlite3.connect(path)
    db.execute('BEGIN EXCLUSIVE');db.execute('UPDATE downloads SET total_bytes=7')
    try:
        assert detect(file).source is OriginSource.UNKNOWN
    finally:
        db.rollback();db.close()


def test_empty_wal_does_not_hide_closed_database(tmp_path):
    file=target(tmp_path)
    path=chromium(tmp_path,file)
    Path(str(path)+'-wal').write_bytes(b'')
    assert detect(file).source is OriginSource.BROWSER_SQLITE


def test_sqlite_opens_only_private_snapshots_and_cleans_them(tmp_path,monkeypatch):
    file=target(tmp_path)
    original=chromium(tmp_path,file)
    real_connect=sqlite3.connect
    opened=[]
    def checked(database_uri,*args,**kwargs):
        assert str(original) not in database_uri
        assert 'mode=ro' in database_uri
        opened.append(Path(database_uri.split('?',1)[0].removeprefix('file://')))
        return real_connect(database_uri,*args,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',checked)
    assert detect(file).source is OriginSource.BROWSER_SQLITE
    assert opened and all(not path.exists() for path in opened)


def test_snapshot_permissions_are_private(tmp_path,monkeypatch):
    file=target(tmp_path);chromium(tmp_path,file)
    original=OriginDetector._connection
    def check(uri,deadline):
        path=Path(uri.split('?',1)[0].removeprefix('file://'))
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
        return original(uri,deadline)
    monkeypatch.setattr(OriginDetector,'_connection',staticmethod(check))
    assert detect(file).source is OriginSource.BROWSER_SQLITE


def test_disabled_detector_performs_no_io(tmp_path,monkeypatch):
    config=MagicMock();config.get.return_value=False
    detector=OriginDetector(config)
    monkeypatch.setattr(FileMetadataExtractor,'read_xattr',staticmethod(lambda *args: pytest.fail('xattr read while disabled')))
    monkeypatch.setattr(Path,'home',lambda: pytest.fail('profile discovery while disabled'))
    assert detector.detect_origin('/arbitrary').source is OriginSource.UNKNOWN


def test_config_toggle_persists_and_updates_live_detector(tmp_path):
    file=target(tmp_path)
    config=ConfigManager(config_path=tmp_path/'settings.json')
    detector=OriginDetector(config)
    assert config.get('enable_origin_detection') is True
    config.set('enable_origin_detection',False)
    assert ConfigManager(config_path=config.config_path).get('enable_origin_detection') is False
    assert detector.detect_origin(file).source is OriginSource.UNKNOWN


def test_corrupt_missing_and_unsupported_databases_are_unknown(tmp_path):
    file=target(tmp_path)
    assert detect(file).source is OriginSource.UNKNOWN
    path=tmp_path/'config/google-chrome/Default/History';path.parent.mkdir(parents=True);path.write_bytes(b'corrupt')
    assert detect(file).source is OriginSource.UNKNOWN
    path.unlink()
    with sqlite3.connect(path) as db: db.execute('CREATE TABLE unrelated(value TEXT)')
    assert detect(file).source is OriginSource.UNKNOWN


def test_snapshot_byte_limit_and_deadline(tmp_path):
    file=target(tmp_path);chromium(tmp_path,file)
    detector=OriginDetector();detector.MAX_SNAPSHOT_BYTES=1
    assert detector.detect_origin(file).source is OriginSource.UNKNOWN
    detector=OriginDetector();detector.TIMEOUT_SECONDS=-1
    assert detector.detect_origin(file).source is OriginSource.UNKNOWN


@pytest.mark.parametrize('size',[-1,True,1.5,'6'])
def test_invalid_size_is_unknown(tmp_path,size):
    assert detect(target(tmp_path),file_size=size).source is OriginSource.UNKNOWN


@pytest.mark.parametrize('timestamp',[True,'now',float('nan'),float('inf')])
def test_invalid_timestamp_is_unknown(tmp_path,timestamp):
    assert OriginDetector().detect_origin(target(tmp_path),file_timestamp=timestamp).source is OriginSource.UNKNOWN


def test_sql_failure_never_discloses_private_backend_error(tmp_path,monkeypatch):
    file=target(tmp_path);chromium(tmp_path,file)
    def fail(*args): raise sqlite3.OperationalError('SECRET https://user:SECRET@example.com/?token=SECRET')
    monkeypatch.setattr(OriginDetector,'_chromium_rows',fail)
    origin=detect(file)
    assert origin.source is OriginSource.UNKNOWN
    assert 'SECRET' not in json.dumps(origin.to_dict())


def test_no_network_calls_and_headless_import(tmp_path):
    repo=Path(__file__).resolve().parents[2]
    script='import sys,socket; socket.getaddrinfo=lambda *a: (_ for _ in ()).throw(AssertionError("network")); from src.core.file_intelligence import OriginDetector; from src.core.file_intelligence.origin import origin_from_url; assert origin_from_url("https://github.com/file").site_name=="github"; assert not any(k.startswith("PyQt6") for k in sys.modules)'
    subprocess.run([sys.executable,'-c',script],cwd=tmp_path,env=dict(os.environ,PYTHONPATH=str(repo),PYTHONDONTWRITEBYTECODE='1'),check=True,timeout=10)


def test_concurrent_detection_has_no_shared_connections(tmp_path):
    file=target(tmp_path);chromium(tmp_path,file)
    detector=OriginDetector()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        origins=list(pool.map(lambda _:detector.detect_origin(file,file_timestamp=NOW),range(8)))
    assert all(origin.url=='https://github.com/project/file' for origin in origins)


def test_oversized_url_is_not_silently_truncated(tmp_path):
    file=target(tmp_path)
    chromium(tmp_path,file,url='https://example.com/'+'a'*5000,tab='')
    assert detect(file).source is OriginSource.UNKNOWN


def test_profiles_ini_fifo_and_history_fifo_are_not_opened(tmp_path):
    file=target(tmp_path)
    root=tmp_path/'.mozilla/firefox';root.mkdir(parents=True)
    os.mkfifo(root/'profiles.ini')
    path=tmp_path/'config/google-chrome/Default/History';path.parent.mkdir(parents=True)
    os.mkfifo(path)
    assert detect(file).source is OriginSource.UNKNOWN


def test_profiles_ini_symlink_is_skipped(tmp_path):
    file=target(tmp_path)
    root=tmp_path/'.mozilla/firefox';root.mkdir(parents=True)
    secret=tmp_path/'secret';secret.write_text('[Profile0]\nPath=/unrelated\n')
    (root/'profiles.ini').symlink_to(secret)
    assert detect(file).source is OriginSource.UNKNOWN


def test_snapshot_retries_one_concurrent_change(tmp_path,monkeypatch):
    file=target(tmp_path);path=chromium(tmp_path,file)
    original=OriginDetector._identity
    calls=[]
    def changing(candidate):
        identity=original(candidate)
        if candidate==path:
            calls.append(candidate)
            if len(calls)==2:
                return identity[:-1]+(identity[-1]+1,)
        return identity
    monkeypatch.setattr(OriginDetector,'_identity',staticmethod(changing))
    assert detect(file).source is OriginSource.BROWSER_SQLITE
    assert len(calls)==4


def test_continuously_changing_snapshot_is_rejected(tmp_path,monkeypatch):
    file=target(tmp_path);path=chromium(tmp_path,file)
    original=OriginDetector._identity
    calls=[]
    def changing(candidate):
        identity=original(candidate)
        if candidate==path:
            calls.append(candidate)
            return identity[:-1]+(identity[-1]+len(calls),)
        return identity
    monkeypatch.setattr(OriginDetector,'_identity',staticmethod(changing))
    assert detect(file).source is OriginSource.UNKNOWN
    assert len(calls)==4


def test_exact_path_precedes_large_filename_collision_set(tmp_path):
    file=target(tmp_path)
    path=chromium(tmp_path,tmp_path/'old'/file.name)
    with sqlite3.connect(path) as db:
        for i in range(2,72):
            db.execute('INSERT INTO downloads SELECT ?,?,start_time,end_time,total_bytes,state,tab_url,tab_referrer_url FROM downloads WHERE id=1', (i,str(tmp_path/f'old{i}'/file.name)))
        db.execute('UPDATE downloads SET target_path=?,tab_url=? WHERE id=71',(str(file),'https://correct.example/file'))
    assert detect(file).url=='https://correct.example/file'


def test_too_many_exact_matches_remain_unknown(tmp_path):
    file=target(tmp_path)
    path=chromium(tmp_path,file)
    with sqlite3.connect(path) as db:
        for i in range(2,70):
            db.execute('INSERT INTO downloads SELECT ?,target_path,start_time,end_time,total_bytes,state,tab_url,tab_referrer_url FROM downloads WHERE id=1',(i,))
    assert detect(file).source is OriginSource.UNKNOWN


def test_filename_wildcards_are_not_patterns(tmp_path):
    file=target(tmp_path,'report_%.pdf')
    chromium(tmp_path,tmp_path/'old/report_1.pdf')
    assert detect(file).source is OriginSource.UNKNOWN


def test_malformed_firefox_json_does_not_become_provenance(tmp_path):
    file=target(tmp_path)
    path=firefox(tmp_path,file)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE moz_annos SET content='not JSON' WHERE anno_attribute_id=2")
    assert detect(file).source is OriginSource.UNKNOWN


def test_firefox_failed_download_is_rejected_even_with_exact_path(tmp_path):
    file=target(tmp_path)
    firefox(tmp_path,file,state=False)
    assert detect(file).source is OriginSource.UNKNOWN


def test_discovery_profile_limit_is_enforced(tmp_path):
    file=target(tmp_path)
    for i in range(4):
        chromium(tmp_path,file,profile=f'Profile {i}')
    detector=OriginDetector();detector.MAX_PROFILES=2
    assert len(list(detector._discover_databases()))==2


def test_database_symlink_is_not_followed(tmp_path):
    file=target(tmp_path)
    path=chromium(tmp_path,file)
    other=tmp_path/'elsewhere';path.rename(other);path.symlink_to(other)
    assert detect(file).source is OriginSource.UNKNOWN


def test_target_directory_does_not_trigger_history_read(tmp_path,monkeypatch):
    monkeypatch.setattr(OriginDetector,'_discover_databases',lambda self: pytest.fail('history read for directory'))
    assert detect(tmp_path).source is OriginSource.UNKNOWN


def test_firefox_exact_path_precedes_large_filename_collision_set(tmp_path):
    file=target(tmp_path)
    path=firefox(tmp_path,tmp_path/'old'/file.name,metadata=False)
    with sqlite3.connect(path) as db:
        for i in range(2,72):
            db.execute('INSERT INTO moz_places VALUES(?,?)',(i,'https://other.example/file'))
            db.execute('INSERT INTO moz_annos VALUES(?,?,1,?,?)',(i,i,(tmp_path/f'old{i}'/file.name).as_uri(),int(NOW*1000000)))
        db.execute('UPDATE moz_annos SET content=? WHERE id=71',(file.as_uri(),))
        db.execute('UPDATE moz_places SET url=? WHERE id=71',('https://correct.example/file',))
    assert detect(file).url=='https://correct.example/file'
