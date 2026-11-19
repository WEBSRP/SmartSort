"""Phase 10: exact scores, deterministic graphs, bounded reversible propagation."""
import copy
from dataclasses import replace
import itertools
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys

import pytest

from src.core.file_intelligence import (
    FileContext, FileCluster, FileRelationship, ExtractedMetadata, OriginInfo,
    SignalSet, Signal, SignalType, SignalExtractor, RelationshipEngine, ConfidenceLevel,
)

NOW=1700000000.0


def file(name='item.pdf',tokens=None,**changes):
    stem,extension=os.path.splitext(name)
    values=dict(path='/data/'+name,filename=name,stem=stem,extension=extension,
                mime_type='',size_bytes=100,created_timestamp=NOW,modified_timestamp=NOW,inode=1,device=1)
    values.update(changes)
    ctx=FileContext(**values)
    if tokens is not None:
        ctx.signals=SignalSet(tokens=set(tokens))
    return ctx


def groups(clusters):
    return {frozenset(c.file_paths) for c in clusters}


def test_exact_similarity_formula_and_shared_tokens():
    a=file('a.pdf',{'alpha','beta'},origin=OriginInfo(domain='example.com'))
    b=file('b.pdf',{'alpha','gamma'},origin=OriginInfo(domain='EXAMPLE.COM'),created_timestamp=NOW+899)
    score,shared=RelationshipEngine().calculate_similarity(a,b)
    assert score==pytest.approx(.65/3+.20+.15)
    assert shared=={'alpha'}
    assert (score,shared)==RelationshipEngine().calculate_similarity(b,a)


@pytest.mark.parametrize('a,b,bonus',[(NOW,NOW+899,.15),(NOW,NOW+900,0),(0,0,0),(-1,-1,0),(float('nan'),NOW,0),(True,NOW,0),(float('inf'),NOW,0)])
def test_time_bonus_requires_real_positive_timestamps(a,b,bonus):
    first=file('a.pdf',{'alpha'},created_timestamp=a)
    second=file('b.pdf',{'alpha'},created_timestamp=b)
    assert RelationshipEngine().calculate_similarity(first,second)[0]==pytest.approx(.65+bonus)


def test_origin_time_alone_never_forms_edge():
    a=file('a.pdf',set(),origin=OriginInfo(domain='github.com'))
    b=file('b.pdf',set(),origin=OriginInfo(domain='github.com'))
    score,shared=RelationshipEngine().calculate_similarity(a,b)
    assert score==pytest.approx(.35) and not shared
    assert RelationshipEngine().cluster_files([a,b])==[]


def test_weak_format_parent_and_origin_tokens_are_not_identity():
    a=file('alpha.pdf');b=file('beta.pdf')
    for ctx in (a,b):
        ctx.origin=OriginInfo(domain='github.com')
        SignalExtractor().extract_signals(ctx)
    score,shared=RelationshipEngine().calculate_similarity(a,b)
    assert score==pytest.approx(.35)
    assert not shared
    assert RelationshipEngine().cluster_files([a,b])==[]


def test_zero_weight_features_are_not_identity():
    a=file('a.pdf');b=file('b.pdf')
    for ctx in (a,b):
        ctx.signals=SignalSet({'alpha'},[Signal('alpha',SignalType.DOCUMENT_TITLE,0,'metadata.title')])
    assert RelationshipEngine().cluster_files([a,b])==[]


def test_lecture_cluster_has_stable_name_domain_and_series_edges():
    contexts=[file(n) for n in ['Lecture_1_DBMS.pdf','Lecture_2_DBMS.pptx','Lecture_3_DBMS.zip']]
    clusters=RelationshipEngine().cluster_files(contexts)
    assert len(clusters)==1
    cluster=clusters[0]
    assert cluster.cluster_name=='DBMS_Lectures'
    assert cluster.inferred_domain=='College'
    assert cluster.inferred_hierarchy==['College','DBMS_Lectures']
    assert cluster.shared_keywords=={'database','lecture'}
    assert len(cluster.relationships)==2
    assert all(r.relationship_type=='SIBLING_SERIES' for r in cluster.relationships)
    assert all(ctx.cluster_id==cluster.cluster_id for ctx in contexts)
    assert all(len(ctx.related_file_paths)==2 for ctx in contexts)


def test_named_series_does_not_require_adjacent_numbers_or_timestamps():
    a=file('Lecture_01_OS.pdf',created_timestamp=0)
    b=file('Lecture_99_OS.pdf',created_timestamp=0)
    score,shared=RelationshipEngine().calculate_similarity(a,b)
    assert score==pytest.approx(.9)
    assert shared=={'lecture','os'}
    assert len(RelationshipEngine().cluster_files([a,b]))==1


def test_course_numbers_are_not_removed_as_series_numbers():
    a=file('CS101_Lecture_01.pdf',created_timestamp=0)
    b=file('CS102_Lecture_02.pdf',created_timestamp=0)
    score,shared=RelationshipEngine().calculate_similarity(a,b)
    assert score<.60
    assert '101' not in shared and '102' not in shared


def test_series_bonus_requires_same_parent_and_compatible_topic():
    engine=RelationshipEngine()
    a=file('Lecture_1_DBMS.pdf',created_timestamp=0)
    b=file('Lecture_2_OS.pdf',created_timestamp=0)
    assert engine.calculate_similarity(a,b)[0]<.60
    b=file('Lecture_2_DBMS.pdf',path='/elsewhere/Lecture_2_DBMS.pdf',created_timestamp=0)
    assert engine.calculate_similarity(a,b)[0]==pytest.approx(.65)


def test_smartsort_project_name_and_domain():
    contexts=[file('SmartSort_Report.docx'),file('SmartSort_Code.zip')]
    cluster=RelationshipEngine().cluster_files(contexts)[0]
    assert cluster.cluster_name=='SmartSort'
    assert cluster.inferred_domain=='Projects'
    assert cluster.shared_keywords=={'smart','sort'}


def test_unrelated_files_are_unclustered():
    contexts=[file('VacationPhoto.jpg'),file('PayrollInvoice.pdf'),file('NmapScan.xml')]
    assert RelationshipEngine().cluster_files(contexts)==[]
    assert all(ctx.cluster_id is None for ctx in contexts)


def test_multiple_clusters_remain_disjoint():
    contexts=[file('Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf'),file('Lecture_1_OS.pdf'),file('Lecture_2_OS.pdf'),file('VacationPhoto.jpg')]
    clusters=RelationshipEngine().cluster_files(contexts)
    assert len(clusters)==2
    assert sorted(c.cluster_name for c in clusters)==['DBMS_Lectures','OS_Lectures']
    assert contexts[-1].cluster_id is None


def test_sparse_file_inherits_supported_topic_without_classifying_or_renaming():
    contexts=[file('Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf'),file('Lecture_3.zip')]
    before=copy.deepcopy(contexts[-1])
    cluster=RelationshipEngine().cluster_files(contexts)[0]
    sparse=contexts[-1]
    assert len(cluster.file_paths)==3
    assert cluster.cluster_name=='DBMS_Lectures'
    inherited=[s for s in sparse.signals.weighted_signals if s.signal_type is SignalType.CLUSTER_CONTEXT]
    assert [s.token for s in inherited]==['database']
    assert inherited[0].weight==pytest.approx(.3*cluster.cluster_confidence)
    assert sparse.confidence_score>before.confidence_score
    assert sparse.classification_domain==before.classification_domain=='Others'
    assert sparse.confidence is before.confidence is ConfidenceLevel.UNKNOWN
    assert sparse.subcategories==[] and sparse.proposed_destination==''
    assert sparse.path==before.path and sparse.metadata==before.metadata
    assert sparse.signals.domain_affinities==SignalExtractor().extract_signals(before).domain_affinities


def test_sparse_file_cannot_bridge_two_incompatible_courses():
    contexts=[file('Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf'),file('Lecture_1_OS.pdf'),file('Lecture_2_OS.pdf'),file('Lecture_3.zip')]
    clusters=RelationshipEngine().cluster_files(contexts)
    assert len(clusters)==2
    assert contexts[-1].cluster_id is None
    assert not any(s.signal_type is SignalType.CLUSTER_CONTEXT for s in contexts[-1].signals.weighted_signals)


def test_generic_series_can_form_group_without_inventing_subject():
    contexts=[file('Lecture_1.pdf'),file('Lecture_2.pdf')]
    cluster=RelationshipEngine().cluster_files(contexts)[0]
    assert cluster.shared_keywords=={'lecture'}
    assert cluster.cluster_name=='Lectures'


def test_confidence_boost_matches_documented_formula_and_does_not_repeat():
    contexts=[file('Lecture_1_DBMS.pdf',confidence_score=.6,confidence=ConfidenceLevel.PROBABLE),file('Lecture_2_DBMS.pdf',confidence_score=.4)]
    engine=RelationshipEngine()
    cluster=engine.cluster_files(contexts)[0]
    assert contexts[0].confidence_score==pytest.approx(.6+.30*(1-.6)*cluster.cluster_confidence)
    before=[ctx.to_dict() for ctx in contexts]
    first=cluster.to_dict()
    assert engine.cluster_files(contexts)[0].to_dict()==first
    assert [ctx.to_dict() for ctx in contexts]==before


def test_serialized_rerun_does_not_compound_or_pollute_features():
    contexts=[file('Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf'),file('Lecture_3.zip')]
    engine=RelationshipEngine()
    first=engine.cluster_files(contexts)
    payload=[ctx.to_dict() for ctx in contexts]
    restored=[FileContext.from_dict(json.loads(json.dumps(ctx))) for ctx in payload]
    assert [c.to_dict() for c in engine.cluster_files(restored)]==[c.to_dict() for c in first]
    assert [ctx.to_dict() for ctx in restored]==payload


def test_reclustering_clears_stale_links_inheritance_and_boost():
    contexts=[file('Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf'),file('Lecture_3.zip')]
    engine=RelationshipEngine();engine.cluster_files(contexts)
    sparse=contexts[-1]
    assert 'database' in sparse.signals.tokens
    assert engine.cluster_files([sparse])==[]
    assert sparse.cluster_id is None and sparse.related_file_paths==[]
    assert 'database' not in sparse.signals.tokens
    assert sparse.confidence_score==0
    assert sparse.relationship_base_confidence is None


def test_new_classifier_score_is_preserved_as_new_boost_baseline():
    contexts=[file('Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf')]
    engine=RelationshipEngine();engine.cluster_files(contexts)
    contexts[0].confidence_score=.8
    engine.cluster_files(contexts)
    assert contexts[0].relationship_base_confidence==.8
    assert contexts[0].confidence_score==pytest.approx(.86)


def test_new_local_signal_survives_old_inherited_signal_cleanup():
    contexts=[file('Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf'),file('Lecture_3.zip')]
    engine=RelationshipEngine();engine.cluster_files(contexts)
    sparse=contexts[-1]
    sparse.signals.weighted_signals.append(Signal('database',SignalType.DOCUMENT_TITLE,.9,'metadata.title'))
    engine.cluster_files([sparse])
    assert 'database' in sparse.signals.tokens
    assert any(s.token=='database' and s.signal_type is SignalType.DOCUMENT_TITLE for s in sparse.signals.weighted_signals)


def test_archive_member_link_is_visible_without_payload_access():
    archive=file('bundle.zip',set(),metadata=ExtractedMetadata(toc_entries=['project/opaque.bin']))
    member=file('opaque.bin',set())
    score,shared=RelationshipEngine().calculate_similarity(archive,member)
    assert score>=.75 and not shared
    cluster=RelationshipEngine().cluster_files([archive,member])[0]
    assert cluster.relationships[0].relationship_type=='ARCHIVE_EXTRACT'


def test_archive_exact_relative_member_path():
    archive=file('bundle.zip',set(),metadata=ExtractedMetadata(toc_entries=['project/report.pdf']))
    member=file('report.pdf',set(),path='/data/project/report.pdf')
    assert RelationshipEngine().calculate_similarity(archive,member)[0]>=.75


def test_ambiguous_archive_basename_is_not_a_link():
    archive=file('bundle.zip',set(),metadata=ExtractedMetadata(toc_entries=['a/report.pdf','b/report.pdf']))
    member=file('report.pdf',set())
    assert RelationshipEngine().calculate_similarity(archive,member)[0]<.60


@pytest.mark.parametrize('entry',['../report.pdf','/report.pdf','C:/report.pdf','bad\x00/report.pdf','a'*1025])
def test_unsafe_archive_names_do_not_create_links(entry):
    archive=file('bundle.zip',set(),metadata=ExtractedMetadata(toc_entries=[entry]))
    member=file('report.pdf',set())
    assert RelationshipEngine().cluster_files([archive,member])==[]


def test_archive_membership_does_not_match_unrelated_parent():
    archive=file('bundle.zip',set(),metadata=ExtractedMetadata(toc_entries=['report.pdf']))
    member=file('report.pdf',set(),path='/elsewhere/report.pdf')
    assert RelationshipEngine().cluster_files([archive,member])==[]


def test_graph_is_transitive_even_when_endpoints_do_not_form_edge():
    a=file('a.pdf',{'alpha','beta','gamma'})
    b=file('b.pdf',{'alpha','beta','gamma','delta'})
    c=file('c.pdf',{'beta','gamma','delta'})
    engine=RelationshipEngine()
    assert engine.calculate_similarity(a,b)[0]>=.60
    assert engine.calculate_similarity(b,c)[0]>=.60
    assert engine.calculate_similarity(a,c)[0]<.60
    assert len(engine.cluster_files([a,b,c]))==1


def test_permutations_have_identical_clusters_and_context_updates():
    originals=[file('Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf'),file('Lecture_3.zip'),file('OtherReport.txt')]
    expected=None
    for order in itertools.permutations(range(4)):
        contexts=[copy.deepcopy(originals[i]) for i in order]
        clusters=RelationshipEngine().cluster_files(contexts)
        result=([c.to_dict() for c in clusters],sorted((ctx.to_dict() for ctx in contexts),key=lambda d:d['path']))
        if expected is None: expected=result
        assert result==expected


def test_ids_change_when_membership_changes():
    a,b,c=[file(f'Lecture_{i}_DBMS.pdf') for i in (1,2,3)]
    first=RelationshipEngine().cluster_files([a,b])[0].cluster_id
    assert RelationshipEngine().cluster_files([a,b,c])[0].cluster_id!=first


def test_calculate_similarity_does_not_mutate_inputs_or_require_signals():
    a=file('Lecture_1_DBMS.pdf');b=file('Lecture_2_DBMS.pdf')
    before=[a.to_dict(),b.to_dict()]
    assert RelationshipEngine().calculate_similarity(a,b)[0]>=.60
    assert [a.to_dict(),b.to_dict()]==before
    assert a.signals is None


def test_empty_singleton_and_missing_metadata():
    engine=RelationshipEngine()
    assert engine.cluster_files([])==engine.cluster_files(None)==[]
    ctx=file(metadata=None,origin=None,signals=SignalSet())
    assert engine.cluster_files([ctx])==[]
    assert ctx.cluster_id is None


def test_input_validation_happens_before_context_mutation():
    good=file('good.pdf',{'alpha'},cluster_id='keep',confidence_score=.2)
    before=good.to_dict()
    with pytest.raises(ValueError): RelationshipEngine().cluster_files([good,None])
    assert good.to_dict()==before
    with pytest.raises(ValueError): RelationshipEngine().cluster_files([good,copy.deepcopy(good)])
    assert good.to_dict()==before


@pytest.mark.parametrize('score',[float('nan'),float('inf'),-.1,1.1,True])
def test_invalid_file_confidence_is_rejected(score):
    with pytest.raises(ValueError): RelationshipEngine().cluster_files([file(confidence_score=score)])


def test_batch_and_vocabulary_budgets_are_explicit():
    engine=RelationshipEngine();engine.MAX_FILES=1
    with pytest.raises(ValueError): engine.cluster_files([file('a.pdf'),file('b.pdf')])
    engine=RelationshipEngine();engine.MAX_VOCABULARY=1
    with pytest.raises(ValueError): engine.cluster_files([file('a.pdf',{'alpha','beta'})])


def test_oversized_signal_inputs_are_rejected():
    ctx=file(tokens={f'word{i}' for i in range(2100)})
    with pytest.raises(ValueError): RelationshipEngine().cluster_files([ctx])


def test_identity_tokens_and_cluster_names_are_bounded():
    contexts=[file('a.pdf',{f'token_{i}' for i in range(400)}),file('b.pdf',{f'token_{i}' for i in range(400)})]
    cluster=RelationshipEngine().cluster_files(contexts)[0]
    assert len(cluster.shared_keywords)<=32 and len(cluster.cluster_name)<=64
    assert all(len(edge.shared_tokens)<=256 for edge in cluster.relationships)


def test_relationship_and_cluster_json_roundtrip():
    cluster=RelationshipEngine().cluster_files([file('Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf')])[0]
    restored=FileCluster.from_dict(json.loads(json.dumps(cluster.to_dict())))
    assert restored==cluster
    assert FileRelationship.from_dict(cluster.relationships[0].to_dict())==cluster.relationships[0]


@pytest.mark.parametrize('score',[-1,1.1,True,float('nan'),float('inf')])
def test_models_reject_invalid_scores(score):
    with pytest.raises(ValueError): FileRelationship('/a','/b','TOKEN_SIMILARITY',score)
    with pytest.raises(ValueError): FileCluster('cluster','name',cluster_confidence=score)


def test_models_have_independent_default_collections():
    a,b=FileCluster('a','a'),FileCluster('b','b')
    a.shared_keywords.add('test');a.file_paths.append('/a')
    assert not b.shared_keywords and not b.file_paths


def test_old_context_json_defaults_bookkeeping_fields():
    data=file().to_dict();data.pop('relationship_base_confidence');data.pop('relationship_confidence_boost')
    restored=FileContext.from_dict(data)
    assert restored.relationship_base_confidence is None and restored.relationship_confidence_boost==0


def test_forest_matches_exhaustive_graph_for_strong_profiles():
    rng=random.Random(19)
    contexts=[file(f'item_{i}.pdf',set(rng.sample(['alpha','beta','gamma','delta','epsilon','zeta','theta'],4))) for i in range(16)]
    engine=RelationshipEngine();adj=[set() for _ in contexts]
    for i,a in enumerate(contexts):
        for j in range(i+1,len(contexts)):
            if engine.calculate_similarity(a,contexts[j])[0]>=.6:
                adj[i].add(j);adj[j].add(i)
    expected=set();seen=set()
    for i in range(len(contexts)):
        if i in seen: continue
        pending=[i];component=set();seen.add(i)
        while pending:
            node=pending.pop();component.add(contexts[node].path)
            for other in adj[node]-seen:
                seen.add(other);pending.append(other)
        if len(component)>1: expected.add(frozenset(component))
    assert groups(engine.cluster_files(contexts))==expected


def test_repeated_engine_calls_do_not_retain_other_batches():
    engine=RelationshipEngine()
    engine.cluster_files([file('Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf')])
    unrelated=[file('Beach.jpg'),file('Payroll.pdf')]
    assert engine.cluster_files(unrelated)==[]


def test_no_filesystem_network_or_execution_during_clustering(monkeypatch):
    import builtins,socket
    contexts=[file('Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf')]
    def forbidden(*args,**kwargs): raise AssertionError('I/O attempted')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(os,'stat',forbidden)
    monkeypatch.setattr(os,'scandir',forbidden);monkeypatch.setattr(socket,'getaddrinfo',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    assert RelationshipEngine().cluster_files(contexts)


def test_fresh_import_and_hash_seed_independent_serialization(tmp_path):
    repo=Path(__file__).resolve().parents[2]
    script='''import json,sys
from src.core.file_intelligence import FileContext,RelationshipEngine
items=[FileContext('/data/'+name,name,name.rsplit('.',1)[0],'.pdf','',1,1700000000,0,0,0) for name in ('Lecture_1_DBMS.pdf','Lecture_2_DBMS.pdf','Lecture_3.zip')]
print(json.dumps([c.to_dict() for c in RelationshipEngine().cluster_files(items)]))
assert not any(k.startswith('PyQt6') for k in sys.modules)
'''
    outputs=[]
    for seed in ('1','2','random'):
        outputs.append(subprocess.run([sys.executable,'-c',script],cwd=tmp_path,env=dict(os.environ,PYTHONPATH=str(repo),PYTHONHASHSEED=seed,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,check=True,timeout=10).stdout)
    assert outputs[0]==outputs[1]==outputs[2]


def test_series_origin_time_can_reach_cutoff_with_empty_lexical_sets():
    a=file('Lecture_1_DBMS.pdf',set(),origin=OriginInfo(domain='example.com'))
    b=file('Lecture_2_DBMS.pdf',set(),origin=OriginInfo(domain='example.com'))
    assert RelationshipEngine().calculate_similarity(a,b)[0]==pytest.approx(.60)
    assert len(RelationshipEngine().cluster_files([a,b]))==1


def test_byte_escaped_linux_paths_have_deterministic_ids():
    contexts=[file('Lecture_1_DBMS.pdf',path='/data/\udcff/Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf',path='/data/\udcff/Lecture_2_DBMS.pdf')]
    clusters=RelationshipEngine().cluster_files(contexts)
    assert len(clusters)==1
    assert FileCluster.from_dict(json.loads(json.dumps(clusters[0].to_dict())))==clusters[0]


def test_upper_bound_prune_preserves_one_token_subset_edges():
    origin=OriginInfo(domain='example.com')
    a=file('a.pdf',{'alpha','beta'},origin=origin)
    b=file('b.pdf',{'alpha'},origin=origin)
    assert RelationshipEngine().calculate_similarity(a,b)[0]==pytest.approx(.675)
    assert len(RelationshipEngine().cluster_files([a,b]))==1
    a=file('a.pdf',{'alpha','beta','gamma'},origin=origin)
    assert RelationshipEngine().calculate_similarity(a,b)[0]<.60
    assert RelationshipEngine().cluster_files([a,b])==[]


def test_pruned_graph_matches_reference_with_variable_sizes_and_provenance():
    engine=RelationshipEngine()
    rng=random.Random(128)
    vocabulary=['alpha','beta','gamma','delta','epsilon','zeta','theta','kappa','lambda','omega']
    for _ in range(4):
        contexts=[file(f'item_{i}.pdf',set(rng.sample(vocabulary,rng.randint(1,8))),
                       origin=OriginInfo(domain=rng.choice(['a.example','b.example',''])),
                       created_timestamp=NOW+rng.choice([0,500,1000])) for i in range(20)]
        adj=[set() for _ in contexts]
        for i in range(len(contexts)):
            for j in range(i+1,len(contexts)):
                if engine.calculate_similarity(contexts[i],contexts[j])[0]>=.6:
                    adj[i].add(j);adj[j].add(i)
        expected=set();seen=set()
        for i in range(len(contexts)):
            if i in seen: continue
            pending=[i];part=set();seen.add(i)
            while pending:
                node=pending.pop();part.add(contexts[node].path)
                for other in adj[node]-seen:
                    seen.add(other);pending.append(other)
            if len(part)>1: expected.add(frozenset(part))
        assert groups(engine.cluster_files(contexts))==expected


def test_related_path_lists_are_independent_of_cluster_and_siblings():
    contexts=[file('Lecture_1_DBMS.pdf'),file('Lecture_2_DBMS.pdf')]
    cluster=RelationshipEngine().cluster_files(contexts)[0]
    contexts[0].related_file_paths.clear()
    assert len(contexts[1].related_file_paths)==1
    assert len(cluster.file_paths)==2
