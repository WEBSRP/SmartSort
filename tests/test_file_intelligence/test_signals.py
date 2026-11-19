"""Phase 09: lexical contract, provenance, affinities and bounded pure transforms."""
import concurrent.futures
import copy
from dataclasses import FrozenInstanceError
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.core.file_intelligence import (
    FileContext, ExtractedMetadata, OriginInfo, Signal, SignalSet, SignalType,
    SignalExtractor, LexicalTokenizer, ConfidenceLevel,
)
from src.core.file_intelligence.signals import BASE_WEIGHTS, DOMAIN_SIGNAL_AFFINITIES


def context(**changes):
    fields=dict(path='/data/Downloads/opaque.pdf',filename='opaque.pdf',stem='opaque',
                extension='.pdf',mime_type='application/pdf',size_bytes=100,
                created_timestamp=0,modified_timestamp=0,inode=1,device=1)
    fields.update(changes)
    return FileContext(**fields)


def signal_set(**changes):
    return SignalExtractor().extract_signals(context(**changes))


@pytest.mark.parametrize('text,tokens',[
    ('DBMSLecture03',['dbms','lecture','03']),
    ('DatabaseManagementSystem',['database','management','system']),
    ('CS101_Fall2026',['cs','101','fall','2026']),
    ('HTTPServerAPI2Client',['http','server','api','2','client']),
    ('snake_case.kebab-case/path',['snake','case','kebab','case','path']),
    ('Lecture_003',['lecture','003']),
    ('asgn1',['asgn','1']),
    ('café résumé',['café','résumé']),
    ('cafe\u0301',['café']),
    ('报告 数据',['报告','数据']),
    ('invoice\x00receipt',['invoice','receipt']),
    ('!!! ___ ...',[]),
    ('123 001',['123','001']),
    (None,[]),(123,[]),('',[]),
])
def test_lexical_tokenization(text,tokens):
    assert LexicalTokenizer.tokenize(text)==tokens


@pytest.mark.parametrize('word',['the','and','for','with','download','downloads','copy','untitled','final','pdf','zip'])
def test_noise_is_filtered(word):
    assert LexicalTokenizer.tokenize(word)==[]


@pytest.mark.parametrize('raw,canonical',[
    ('hw','assignment'),('asgn1','assignment'),('asgn','assignment'),
    ('homework','assignment'),('assignments','assignment'),('lec','lecture'),
    ('slides','lecture'),('ch3','lecture'),('quizzes','exam'),('midterm','exam'),
    ('db','database'),('DBMS','database'),('sql','database'),('databases','database'),
    ('sec','security'),('cve','security'),('vulnerabilities','security'),
    ('Operating_System','os'),('operating-systems','os'),('invoices','invoice'),
    ('repositories','repository'),('analysis','analysis'),('café','café'),
    (None,''),('', ''),('x'*129,''),
])
def test_canonicalization_is_explicit_and_idempotent(raw,canonical):
    assert LexicalTokenizer.canonicalize(raw)==canonical
    assert LexicalTokenizer.canonicalize(canonical)==canonical


def test_tokenizer_preserves_repetitions_but_extractor_deduplicates_channel():
    assert LexicalTokenizer.tokenize('invoice invoice')==['invoice','invoice']
    result=signal_set(metadata=ExtractedMetadata(title='invoice invoices invoice'))
    found=[s for s in result.weighted_signals if s.signal_type is SignalType.DOCUMENT_TITLE]
    assert len(found)==1 and found[0].token=='invoice'


def test_tokenizer_limits():
    assert len(LexicalTokenizer.tokenize('token '*100000))==512
    assert LexicalTokenizer.tokenize('a'*100000)==[]
    assert all(len(t)<=64 for t in LexicalTokenizer.tokenize('meaningful '*10000))


def test_numbered_alias_keeps_series_number_as_separate_signal():
    result=signal_set(stem='asgn01DBMS')
    assert {'assignment','01','database'} <= result.tokens


def test_operating_system_phrase_is_normalized():
    assert 'os' in signal_set(stem='OperatingSystemsLecture03').tokens


def test_all_documented_channel_weights_and_source_fields():
    ctx=context(path='/data/Course/SourceFile.py',stem='Lecture03DBMS',extension='.py',
                metadata=ExtractedMetadata(title='Database Lecture',headings=['Assignments'],
                    code_language='Python',code_symbols=['buildReport'],keywords=['nmap'],
                    text_preview='quarterly invoice',toc_entries=['course/lecture.pdf'],
                    author='Sony',subject='Podcast',extractor_name='MediaExtractor',
                    exif_tags={'Make':'Canon'}),origin=OriginInfo(domain='github.com'))
    result=SignalExtractor().extract_signals(ctx)
    expected={SignalType.DOCUMENT_TITLE:.90,SignalType.ORIGIN_DOMAIN:.85,
              SignalType.DOCUMENT_HEADING:.75,SignalType.ARCHIVE_CONTENT:.70,
              SignalType.FILENAME_TOKEN:.65,SignalType.CODE_SYNTAX:.65,
              SignalType.CONTENT_KEYWORD:.50,SignalType.MEDIA_METADATA:.50,
              SignalType.EXIF_CAMERA:.50,SignalType.DIRECTORY_CONTEXT:.40,
              SignalType.EXTENSION_HINT:.20}
    assert {s.signal_type for s in result.weighted_signals}==set(expected)
    assert all(s.weight==expected[s.signal_type] for s in result.weighted_signals)
    assert {'metadata.title','metadata.headings','stem','origin.domain','metadata.toc_entries',
            'metadata.code_symbols','metadata.keywords','metadata.text_preview','parent_directory',
            'extension'} <= {s.source for s in result.weighted_signals}
    assert ctx.signals is result


def test_same_token_in_independent_channels_is_preserved():
    result=signal_set(stem='invoice',metadata=ExtractedMetadata(title='Invoice',keywords=['invoice'],text_preview='invoice invoice'))
    found=[s for s in result.weighted_signals if s.token=='invoice']
    assert {s.signal_type for s in found}=={SignalType.DOCUMENT_TITLE,SignalType.FILENAME_TOKEN,SignalType.CONTENT_KEYWORD}
    assert len(found)==3


def test_repeated_headings_keywords_archive_entries_do_not_inflate_scores():
    a=signal_set(metadata=ExtractedMetadata(headings=['nmap'],keywords=['invoice'],toc_entries=['repository/main.py']))
    b=signal_set(metadata=ExtractedMetadata(headings=['nmap']*60,keywords=['invoice']*20,toc_entries=['repository/main.py']*500))
    assert a.to_dict()==b.to_dict()


def test_domain_affinities_follow_weighted_sum_and_normalize():
    result=signal_set(stem='',extension='',path='',filename='',metadata=ExtractedMetadata(title='lecture',text_preview='nmap'))
    raw={'College':.90*.85,'Work':.90*.15,'Cybersecurity':.50*.95}
    total=sum(raw.values())
    assert result.domain_affinities==pytest.approx({k:v/total for k,v in raw.items()})
    assert sum(result.domain_affinities.values())==pytest.approx(1.0)


@pytest.mark.parametrize('text,domain',[
    ('lecture assignment syllabus','College'),('repository dockerfile backend','Projects'),
    ('nmap wireshark metasploit','Cybersecurity'),('quarterly timesheet contract','Work'),
    ('wallpaper screenshot','Images'),('soundtrack podcast','Audio'),('screencast video','Videos'),
])
def test_domain_affinity_topics(text,domain):
    result=signal_set(metadata=ExtractedMetadata(title=text))
    assert max(result.domain_affinities,key=result.domain_affinities.get)==domain
    assert all(math.isfinite(v) and 0<=v<=1 for v in result.domain_affinities.values())


def test_unknown_terms_and_numeric_tokens_do_not_invent_affinities():
    result=signal_set(stem='opaque03',extension='',path='')
    assert result.tokens=={'opaque','03'}
    assert result.domain_affinities=={}


def test_extension_is_weak_format_evidence_not_confidence():
    ctx=context(stem='',filename='',path='',extension='.zip')
    result=SignalExtractor().extract_signals(ctx)
    assert result.weighted_signals==[Signal('archive',SignalType.EXTENSION_HINT,.2,'extension')]
    assert result.domain_affinities=={'Archives':1.0}
    assert ctx.confidence is ConfidenceLevel.UNKNOWN
    assert ctx.classification_domain=='Others'


@pytest.mark.parametrize('extension,hint',[('.PDF','document'),('.tar.gz','archive'),('.mp3','audio'),('.mp4','video'),('.png','image'),('.py','code_project'),('.xlsx','spreadsheet')])
def test_extension_hints(extension,hint):
    result=signal_set(extension=extension)
    assert any(s.token==hint and s.signal_type is SignalType.EXTENSION_HINT for s in result.weighted_signals)


def test_parent_is_only_immediate_directory_without_user_ancestors():
    result=signal_set(path='/home/PRIVATE_USER/finance/opaque.pdf')
    parent=[s.token for s in result.weighted_signals if s.signal_type is SignalType.DIRECTORY_CONTEXT]
    assert parent==['finance']
    assert 'private' not in result.tokens


def test_origin_never_tokenizes_url_path_credentials_queries_or_evidence():
    result=signal_set(origin=OriginInfo(domain='https://unsafe/?token=PRIVATE',
                url='https://user:PASSWORD@github.com/PRIVATE_PATH?token=PRIVATE_QUERY#PRIVATE_FRAGMENT',
                site_name='PRIVATE_SITE',evidence_detail='PRIVATE_EVIDENCE'))
    origin=[s.token for s in result.weighted_signals if s.signal_type is SignalType.ORIGIN_DOMAIN]
    assert origin==['github.com','github']
    serialized=json.dumps(result.to_dict())
    assert 'PRIVATE' not in serialized and 'PASSWORD' not in serialized


def test_origin_mapping_does_not_trust_arbitrary_friendly_name():
    result=signal_set(origin=OriginInfo(domain='github.com.attacker.example',site_name='github'))
    assert 'github' not in result.tokens
    assert 'github.com.attacker.example' in result.tokens
    assert not result.domain_affinities


def test_exif_uses_allowlist_and_omits_gps_and_dates():
    result=signal_set(metadata=ExtractedMetadata(exif_tags={
        'Make':'Sony','Model':'Alpha','LensModel':'Zoom','Software':'Blender',
        'GPSInfo':'PRIVATE_COORDINATES','GPSLatitude':'PRIVATE_LATITUDE',
        'DateTimeOriginal':'PRIVATE_DATE','Unexpected':'PRIVATE_FIELD'}))
    camera=[s for s in result.weighted_signals if s.signal_type is SignalType.EXIF_CAMERA]
    assert {s.token for s in camera}=={'sony','alpha','zoom','blender'}
    assert 'PRIVATE' not in json.dumps(result.to_dict())


def test_office_subject_is_content_media_subject_is_media():
    office=signal_set(metadata=ExtractedMetadata(subject='database',extractor_name='DocxExtractor'))
    media=signal_set(metadata=ExtractedMetadata(subject='database',extractor_name='MediaExtractor'))
    assert any(s.token=='database' and s.signal_type is SignalType.CONTENT_KEYWORD for s in office.weighted_signals)
    assert any(s.token=='database' and s.signal_type is SignalType.MEDIA_METADATA for s in media.weighted_signals)


def test_null_metadata_fields_are_safe():
    ctx=context(path=None,filename=None,stem=None,extension=None,metadata=None,origin=None)
    assert SignalExtractor().extract_signals(ctx).to_dict()==SignalSet().to_dict()
    assert SignalExtractor().extract_signals(None)==SignalSet()


def test_malformed_field_values_are_ignored_without_stringifying_objects():
    class Trap:
        def __str__(self): raise AssertionError('object stringified')
    metadata=ExtractedMetadata(title=Trap(),headings={'nmap':1},keywords=[None,Trap()],
                               code_symbols='not a list',exif_tags={'Make':Trap()})
    result=signal_set(metadata=metadata)
    assert not result.domain_affinities


def test_global_input_and_signal_limits():
    entries=[f'course_{i}/topic{i}_'+'x '*500 for i in range(10000)]
    ctx=context(metadata=ExtractedMetadata(headings=entries,toc_entries=entries,code_symbols=entries))
    result=SignalExtractor().extract_signals(ctx)
    assert len(result.weighted_signals)<=2048
    assert all(len(s.token)<=253 for s in result.weighted_signals)
    assert all(math.isfinite(v) for v in result.domain_affinities.values())


def test_repeated_extraction_replaces_only_signal_field():
    ctx=context(metadata=ExtractedMetadata(title='Invoice'),origin=OriginInfo(domain='github.com'),classification_domain='Custom',confidence=ConfidenceLevel.PROBABLE,subcategories=['Keep'])
    original=copy.deepcopy(ctx)
    first=SignalExtractor().extract_signals(ctx)
    second=SignalExtractor().extract_signals(ctx)
    assert first==second and first is not second
    original.signals=second
    assert ctx==original


def test_concurrent_extraction_is_deterministic_and_has_independent_results():
    extractor=SignalExtractor()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:extractor.extract_signals(context(metadata=ExtractedMetadata(title='DBMS Lecture03'))),range(12)))
    assert all(result.to_dict()==results[0].to_dict() for result in results)
    results[0].tokens.add('only-first')
    assert 'only-first' not in results[1].tokens


def test_signal_is_frozen_and_round_trips():
    value=Signal('invoice',SignalType.DOCUMENT_TITLE,.9,'metadata.title')
    with pytest.raises(FrozenInstanceError): value.weight=.1
    assert Signal.from_dict(json.loads(json.dumps(value.to_dict())))==value


@pytest.mark.parametrize('weight',[-1,1.1,True,float('nan'),float('inf'),-float('inf'),'0.5'])
def test_signal_invalid_weight_is_rejected(weight):
    with pytest.raises(ValueError): Signal('test',SignalType.CONTENT_KEYWORD,weight,'metadata.text_preview')


@pytest.mark.parametrize('kwargs',[{'token':''},{'token':None},{'source':''},{'signal_type':'CONTENT_KEYWORD'}])
def test_signal_invalid_contract_is_rejected(kwargs):
    values=dict(token='invoice',signal_type=SignalType.CONTENT_KEYWORD,weight=.5,source='metadata.keywords')
    values.update(kwargs)
    with pytest.raises(ValueError): Signal(**values)


def test_signal_set_defaults_are_independent():
    a,b=SignalSet(),SignalSet()
    a.tokens.add('nmap');a.domain_affinities['Cybersecurity']=1
    assert b==SignalSet()


def test_signal_set_and_file_context_json_round_trip():
    ctx=context(metadata=ExtractedMetadata(title='DBMS Lecture03'),origin=OriginInfo(domain='github.com'))
    result=SignalExtractor().extract_signals(ctx)
    assert SignalSet.from_dict(json.loads(json.dumps(result.to_dict())))==result
    restored=FileContext.from_dict(json.loads(json.dumps(ctx.to_dict())))
    assert restored==ctx
    assert isinstance(restored.signals,SignalSet)


def test_none_and_legacy_signal_payloads_remain_compatible():
    ctx=context()
    assert FileContext.from_dict(ctx.to_dict()).signals is None
    old=ctx.to_dict();old['signals']={'legacy_value':123}
    assert FileContext.from_dict(old).signals=={'legacy_value':123}


@pytest.mark.parametrize('score',[float('nan'),float('inf'),-1,1.1,True])
def test_invalid_serialized_affinities_are_rejected(score):
    with pytest.raises(ValueError): SignalSet.from_dict({'domain_affinities':{'College':score}})


def test_serialization_is_independent_of_hash_seed_and_imports_no_qt(tmp_path):
    repo=Path(__file__).resolve().parents[2]
    command='''import json,sys
from src.core.file_intelligence import FileContext,ExtractedMetadata,SignalExtractor
ctx=FileContext("/data/course/Lecture03DBMS.pdf","Lecture03DBMS.pdf","Lecture03DBMS",".pdf","application/pdf",0,0,0,0,0,metadata=ExtractedMetadata(title="Database Lecture"))
print(json.dumps(SignalExtractor().extract_signals(ctx).to_dict()))
assert not any(k.startswith("PyQt6") for k in sys.modules)
'''
    outputs=[]
    for seed in ('1','2','random'):
        env=dict(os.environ,PYTHONPATH=str(repo),PYTHONHASHSEED=seed,PYTHONDONTWRITEBYTECODE='1')
        outputs.append(subprocess.run([sys.executable,'-c',command],cwd=tmp_path,env=env,capture_output=True,text=True,check=True,timeout=10).stdout)
    assert outputs[0]==outputs[1]==outputs[2]


def test_no_filesystem_or_network_access_during_extraction(monkeypatch):
    import builtins,socket
    ctx=context(metadata=ExtractedMetadata(title='Lecture03DBMS'),origin=OriginInfo(domain='github.com'))
    def forbidden(*args,**kwargs): raise AssertionError('I/O attempted')
    monkeypatch.setattr(builtins,'open',forbidden)
    monkeypatch.setattr(os,'stat',forbidden)
    monkeypatch.setattr(os,'scandir',forbidden)
    monkeypatch.setattr(socket,'getaddrinfo',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    assert SignalExtractor().extract_signals(ctx).weighted_signals


def test_extracted_text_and_origin_feed_signal_api(tmp_path,monkeypatch):
    from src.core.file_intelligence import FileContextBuilder,OriginDetector
    from src.core.file_intelligence.extractors import ExtractorRegistry
    from src.core.file_intelligence.metadata import FileMetadataExtractor
    file=tmp_path/'DBMSLecture03.md'
    file.write_text('# DBMS Lecture 03\n\nAssignments in relational algebra.\n')
    monkeypatch.setattr(FileMetadataExtractor,'read_xattr',staticmethod(lambda p,a:'https://canvas.university.edu/files?token=SECRET' if a.endswith('origin.url') else None))
    ctx=FileContextBuilder.build_initial_context(file)
    ctx.metadata=ExtractorRegistry().extract_metadata(file)
    ctx.origin=OriginDetector().detect_origin(file)
    result=SignalExtractor().extract_signals(ctx)
    assert {'database','lecture','03','assignment','lms'} <= result.tokens
    assert max(result.domain_affinities,key=result.domain_affinities.get)=='College'
    assert 'SECRET' not in json.dumps(result.to_dict())
    assert file.read_text().startswith('# DBMS Lecture 03')
    assert ctx.classification_domain=='Others'


def test_archive_extractor_output_supplies_content_signals(tmp_path):
    import zipfile
    from src.core.file_intelligence import FileContextBuilder
    from src.core.file_intelligence.extractors import ExtractorRegistry
    file=tmp_path/'bundle.zip'
    with zipfile.ZipFile(file,'w') as archive:
        archive.writestr('repository/Makefile','all:\n')
        archive.writestr('repository/main.py','print("do not run")')
    ctx=FileContextBuilder.build_initial_context(file)
    ctx.metadata=ExtractorRegistry().extract_metadata(file)
    result=SignalExtractor().extract_signals(ctx)
    assert 'code_project' in result.tokens and 'makefile' in result.tokens
    assert any(s.token=='repository' and s.signal_type is SignalType.ARCHIVE_CONTENT for s in result.weighted_signals)
    assert result.domain_affinities['Projects']>result.domain_affinities['Archives']
    assert sorted(p.name for p in tmp_path.iterdir())==['bundle.zip']


def test_ipv6_domain_is_an_atomic_origin_feature():
    result=signal_set(origin=OriginInfo(domain='::1'))
    assert any(s.token=='::1' and s.signal_type is SignalType.ORIGIN_DOMAIN for s in result.weighted_signals)


@pytest.mark.parametrize('data',[{'domain_affinities':{'College':float('nan')}},
    {'domain_affinities':{'':.5}},{'tokens':{' '}},{'weighted_signals':['not a signal']}])
def test_signal_set_constructor_rejects_invalid_schema(data):
    with pytest.raises(ValueError): SignalSet(**data)


def test_long_acronym_and_combining_sequences_stay_bounded():
    import time
    started=time.monotonic()
    assert LexicalTokenizer.tokenize('A'*65536)==[]
    assert LexicalTokenizer.tokenize('\u0315\u0300'*32768)==[]
    assert time.monotonic()-started<1
