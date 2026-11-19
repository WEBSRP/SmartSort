import os
import hashlib
import shutil
import threading
import stat
import copy
import html
import math
import re
import tempfile
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Tuple, Dict
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace

from src.core.folder_undo import Entry, FolderUndo, identity
from src.rules.engine import RuleEngine, rules_for_mode
from src.rules.manager import RuleManager
from src.utils.file_utils import FileUtils
from src.utils.output_tracker import remember_output
from src.utils.folder_guard import protected_folder_for
from src.utils.config import ConfigManager
from src.utils.logger import SmartSortLogger
from src.core.file_intelligence import (
    FileContext, FileContextBuilder, OriginDetector, OriginInfo, SignalExtractor,
    RelationshipEngine, MultiSignalClassifier, OrganizationPlanner,
    Signal, SignalType, DeterministicMime,
)
from src.core.file_intelligence.extractors import ExtractorRegistry


class OperationStatus(Enum):
    VERIFIED_AND_MOVED = "VERIFIED_AND_MOVED"
    COLLISION_RESOLVED = "COLLISION_RESOLVED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"


@dataclass
class OrganizePlanItem:
    source_path: str
    target_path: str
    category: str
    rule_name: str
    confidence: str = "CONFIRMED"
    evidence: List[str] = field(default_factory=list)
    confidence_score: float = 1.0
    cluster_id: Optional[str] = None
    cluster_name: str = ""
    source_identity: Optional[Tuple[int, int, int, int, int]] = None


@dataclass
class OrganizePlan:
    items: List[OrganizePlanItem]
    root_dir: str
    total_files: int
    category_counts: Dict[str, int]
    cluster_count: int = 0
    warnings: List[str] = field(default_factory=list)


@dataclass
class FileOperationRecord:
    source: str
    target: str
    category: str
    rule_name: str
    status: OperationStatus
    error: str = ""
    hash: str = ""
    size: int = 0
    confidence: str = "CONFIRMED"
    evidence: List[str] = field(default_factory=list)
    cluster_name: str = ""
    confidence_score: Optional[float] = None
    cluster_id: Optional[str] = None


@dataclass
class OrganizeResult:
    records: List[FileOperationRecord]
    success_count: int = 0
    collision_count: int = 0
    duplicate_count: int = 0
    skip_count: int = 0
    error_count: int = 0
    cancelled: bool = False
    undo: Optional[FolderUndo] = field(default=None, compare=False, repr=False, init=False)
    warnings: List[str] = field(default_factory=list)


@dataclass
class DirectoryPreviewSummary:
    total_files: int
    category_counts: Dict[str, int]
    items: List[OrganizePlanItem]
    cluster_count: int = 0
    warnings: List[str] = field(default_factory=list)


class DirectoryOrganizer:
    PROTECTED_ROOTS = frozenset([
        '/', '/bin', '/sbin', '/usr', '/etc', '/lib', '/lib64',
        '/sys', '/proc', '/dev', '/boot', '/var', '/run', '/tmp'
    ])

    EXCLUDED_FILENAMES = frozenset([
        'SmartSort_Arrangement.md', 'SmartSort_Arrangement.md.tmp'
    ])

    TEMP_EXTENSIONS = frozenset([
        '.crdownload', '.part', '.tmp', '.opdownload'
    ])

    def __init__(self, config: ConfigManager, logger: SmartSortLogger):
        self.config = config
        self.logger = logger
        self.rule_manager = RuleManager(config)
        self.extractor_registry = ExtractorRegistry()
        self.origin_detector = OriginDetector(config)
        self.relationship_engine = RelationshipEngine()
        self.signal_extractor = SignalExtractor()
        self.classifier = MultiSignalClassifier(config)
        self.planner = OrganizationPlanner(self.rule_manager, config)

    def _validate_root(self, root_dir: str):
        if not os.path.exists(root_dir):
            raise ValueError(f"Root directory does not exist: {root_dir}")
        if not os.path.isdir(root_dir):
            raise ValueError(f"Root path is not a directory: {root_dir}")
        
        resolved_path = os.path.realpath(os.path.abspath(root_dir))
        if resolved_path in self.PROTECTED_ROOTS:
            raise ValueError(f"Cannot organize protected root directory: {root_dir}")
        return resolved_path

    def _is_excluded(self, file_path: str, root_dir: Optional[str] = None) -> bool:
        basename = os.path.basename(file_path)
        if basename in self.EXCLUDED_FILENAMES:
            return True
        if basename.startswith('.'):
            return True
            
        _, ext = os.path.splitext(basename)
        if ext.lower() in self.TEMP_EXTENSIONS:
            return True
            
        if os.path.islink(file_path):
            return True
            
        if root_dir:
            if protected_folder_for(file_path, root_dir):
                return True
            try:
                rel = os.path.relpath(file_path, root_dir)
                parts = Path(rel).parts
                if any(p.startswith('.') for p in parts):
                    return True
            except ValueError:
                pass

        return False

    def scan(self, root_dir: str, recursive: Optional[bool] = None) -> List[str]:
        self._validate_root(root_dir)
        if recursive is None:
            recursive = self.config.get("intelligence_recursive", True) if self.config.get("sorting_mode", "rules_first") == "intelligence" else self.config.get("dir_organizer_recursive", False)
        results = []
        if protected_folder_for(root_dir, root_dir):
            return results

        if not recursive:
            with os.scandir(root_dir) as it:
                for entry in it:
                    if entry.is_file() and not self._is_excluded(entry.path, root_dir):
                        results.append(os.path.abspath(entry.path))
        else:
            for dirpath, dirnames, filenames in os.walk(root_dir, followlinks=False):
                # Do not recurse into hidden directories
                dirnames[:] = [d for d in dirnames if not self._is_excluded(os.path.join(dirpath, d), root_dir)]
                for f in filenames:
                    file_path = os.path.join(dirpath, f)
                    if not self._is_excluded(file_path, root_dir) and os.path.isfile(file_path):
                        results.append(os.path.abspath(file_path))
                        
        results.sort()
        return results

    @staticmethod
    def _identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def _source_snapshot(self, source, root):
        source = os.path.abspath(OrganizationPlanner._path(source))
        info = os.lstat(source)
        canonical = os.path.realpath(source)
        if (not stat.S_ISREG(info.st_mode) or os.path.commonpath([root, canonical]) != root or
                self._is_excluded(canonical, root)):
            raise ValueError("Unsafe or excluded source")
        return canonical, info

    @staticmethod
    def _minimal_context(path, info):
        filename = os.path.basename(path)
        stem, extension = os.path.splitext(filename)
        return FileContext(path, filename, stem, extension, "", info.st_size,
                           info.st_ctime, info.st_mtime, info.st_ino, info.st_dev)

    def _fallback_item(self, ctx, root, identity, reason):
        parts = DeterministicMime.get_sorting_parts(ctx.extension, ctx.mime_type)
        category = parts[0]
        filename = OrganizationPlanner._component(ctx.filename)
        # Fixed extension-category vocabulary; never turn an arbitrary suffix
        # into an unchecked path component.
        target = os.path.join(root, *parts, filename)
        _, target = self.planner._validate_boundary(root, target)
        return OrganizePlanItem(ctx.path, target, category, "Fallback", "UNKNOWN",
                                [reason], 0.0, source_identity=identity)

    def plan(self, root_dir: str, file_paths: List[str]) -> OrganizePlan:
        root = self._validate_root(root_dir)
        # The explicit intelligence mode uses an empty policy snapshot; saved
        # rules remain available when switching back to rules-first sorting.
        policy = SimpleNamespace(rules=copy.deepcopy(rules_for_mode(self.rule_manager.rules,
            self.config.get("sorting_mode", "rules_first"))))
        engine = RuleEngine(policy.rules)
        self.planner.rule_manager = policy
        contexts, identities, fallback, warnings = [], {}, {}, []
        if protected_folder_for(root, root):
            warnings.append("Application/project folder kept intact; internal files are excluded from sorting.")
        for file_path in file_paths:
            try:
                path, info = self._source_snapshot(file_path, root)
            except (OSError, ValueError, TypeError):
                warnings.append("Source skipped: unavailable, unsafe or excluded")
                continue
            if path in identities:
                continue
            ctx = self._minimal_context(path, info)
            identities[path] = self._identity(info)
            contexts.append(ctx)
            try:
                matched, _ = engine.evaluate_file(path, info.st_size)
            except Exception:
                fallback[path] = "Rule evaluation failed; file excluded"
                warnings.append(f"Rule evaluation failed: {ctx.filename!r}")
                continue
            if matched is not None:
                # Explicit policy is authoritative; don't read content/history
                # merely to discard the resulting classification afterwards.
                continue
            try:
                enriched = FileContextBuilder.build_initial_context(path, read_origin_xattrs=False)
                if (enriched.path != path or
                        (enriched.device, enriched.inode, enriched.size_bytes) != (info.st_dev, info.st_ino, info.st_size)):
                    raise ValueError("Source changed during ingestion")
                if enriched.metadata.extraction_status != "SUCCESS":
                    raise ValueError("Filesystem metadata unavailable")
                contexts[-1] = ctx = enriched
                try:
                    ctx.origin = self.origin_detector.detect_origin(path, ctx.size_bytes)
                except Exception:
                    ctx.origin = OriginInfo()
                    warnings.append(f"Origin unavailable: {ctx.filename!r}")
                if self.config.get("enable_deep_content_extraction", True):
                    ctx.metadata = self.extractor_registry.extract_metadata(path)
                if ctx.metadata.extraction_status not in ("SUCCESS", "PARTIAL", "UNSUPPORTED"):
                    raise ValueError("Content extraction unavailable")
                self.signal_extractor.extract_signals(ctx)
            except Exception:
                fallback[path] = "Profiling unavailable; extension-based fallback"
                warnings.append(f"Profiling unavailable: {ctx.filename!r}")
        profiled = sorted((ctx for ctx in contexts if ctx.signals is not None and ctx.path not in fallback),
                          key=lambda ctx: ctx.path)
        clusters = []
        if len(profiled) > self.relationship_engine.MAX_FILES:
            warnings.append("Clustering skipped: batch exceeds relationship limit; individual classification retained")
        elif profiled:
            try:
                clusters = self.relationship_engine.cluster_files(profiled)
            except Exception:
                warnings.append("Clustering unavailable; individual classification retained")
        cluster_map = {cluster.cluster_id: cluster for cluster in clusters}
        domain_tokens = {"College": "college", "Projects": "project", "Cybersecurity": "security",
                         "Work": "work", "Media": "media", "Archives": "archive"}
        for ctx in profiled:
            try:
                cluster = cluster_map.get(ctx.cluster_id)
                if (cluster and cluster.inferred_domain in domain_tokens and
                        len(ctx.signals.tokens) < self.classifier.MAX_SIGNALS and
                        len(ctx.signals.weighted_signals) < self.classifier.MAX_SIGNALS):
                    token = domain_tokens[cluster.inferred_domain]
                    ctx.signals.tokens.add(token)
                    ctx.signals.weighted_signals.append(Signal(token, SignalType.CLUSTER_CONTEXT,
                        .30 * cluster.cluster_confidence, "cluster.inferred_domain"))
                self.classifier.classify(ctx)
            except Exception:
                fallback[ctx.path] = "Classification unavailable; extension-based fallback"
                warnings.append(f"Classification unavailable: {ctx.filename!r}")
        items, category_counts = [], {}
        for ctx in sorted(contexts, key=lambda ctx: ctx.path):
            try:
                _, current = self._source_snapshot(ctx.path, root)
                if self._identity(current) != identities[ctx.path]:
                    raise ValueError("Source changed during profiling")
                reason = fallback.get(ctx.path)
                if reason == "Rule evaluation failed; file excluded":
                    continue
                if reason:
                    item = self._fallback_item(ctx, root, identities[ctx.path], reason)
                else:
                    proposal = self.planner.plan_file(ctx, root)
                    cluster = cluster_map.get(ctx.cluster_id)
                    item = OrganizePlanItem(proposal.source_path, proposal.target_path, proposal.domain,
                        proposal.rule_name or "Intelligence", proposal.confidence_level.value,
                        [e.description for e in proposal.evidence], proposal.confidence_score,
                        ctx.cluster_id, cluster.cluster_name if cluster else "", identities[ctx.path])
                if item.source_path == item.target_path:
                    continue
                items.append(item)
                category_counts[item.category] = category_counts.get(item.category, 0) + 1
            except Exception:
                # Unsafe destinations never degrade into a different automatic
                # move. Other files remain independently plannable.
                warnings.append(f"Planning rejected: {ctx.filename!r}")
        return OrganizePlan(items, root, len(items), category_counts, len(clusters), warnings)

    def preview(self, root_dir: str, recursive: Optional[bool] = None) -> DirectoryPreviewSummary:
        file_paths = self.scan(root_dir, recursive)
        plan = self.plan(root_dir, file_paths)
        return DirectoryPreviewSummary(
            total_files=plan.total_files,
            category_counts=plan.category_counts,
            items=plan.items,
            cluster_count=plan.cluster_count,
            warnings=plan.warnings
        )

    def execute(self, plan: OrganizePlan, progress_callback: Optional[Callable] = None, cancel_check: Optional[Callable] = None, capture_undo: bool = False) -> OrganizeResult:
        self._validate_root(plan.root_dir)
        # Snapshot audit metadata before callbacks; transfer decisions below stay unchanged.
        metadata = {
            item.source_path: (item.confidence, list(item.evidence), item.cluster_name,
                               item.confidence_score, item.cluster_id)
            for item in plan.items
        }
        result = OrganizeResult(records=[], warnings=list(plan.warnings))
        if capture_undo:
            result.undo = FolderUndo(plan.root_dir)
        total = plan.total_files
        processed = 0
        
        # Conflict policy and duplicate detection
        conflict_policy = self.config.get('conflict_resolution', 'rename')
        detect_duplicates = self.config.get('enable_duplicate_detection', True)

        for item in plan.items:
            if cancel_check and cancel_check():
                result.cancelled = True
                break
                
            if progress_callback:
                progress_callback(processed, total, os.path.basename(item.source_path))
                
            processed += 1
            src = item.source_path
            target = item.target_path
            category = item.category
            rule_name = item.rule_name
            
            if not os.path.exists(src) or not os.access(src, os.R_OK):
                result.records.append(FileOperationRecord(
                    source=src, target=target, category=category, rule_name=rule_name,
                    status=OperationStatus.FAILED, error="Source file not found or not readable"
                ))
                result.error_count += 1
                continue
                
            try:
                src_size = os.path.getsize(src)
            except OSError as e:
                result.records.append(FileOperationRecord(
                    source=src, target=target, category=category, rule_name=rule_name,
                    status=OperationStatus.FAILED, error=f"Could not read source size: {e}"
                ))
                result.error_count += 1
                continue

            collision_resolved = False
            src_hash = None
            skip_file = False

            # Preconditions only: the copy/verify/delete protocol below is
            # unchanged. Recheck after callbacks and before creating any target.
            try:
                root = self._validate_root(plan.root_dir)
                current_source, info = self._source_snapshot(src, root)
                if current_source != os.path.abspath(src):
                    raise ValueError("Source path changed since planning")
                if item.source_identity is not None and self._identity(info) != item.source_identity:
                    raise ValueError("Source identity changed since planning")
                _, current_target = self.planner._validate_boundary(root, target)
                if current_target != os.path.abspath(target) or current_target == current_source:
                    raise ValueError("Destination changed or is a source no-op")
            except (OSError, ValueError, TypeError):
                result.records.append(FileOperationRecord(
                    source=src, target=target, category=category, rule_name=rule_name,
                    status=OperationStatus.FAILED, error="Execution safety validation failed"
                ))
                result.error_count += 1
                continue
            
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
            except OSError:
                result.records.append(FileOperationRecord(
                    source=src, target=target, category=category, rule_name=rule_name,
                    status=OperationStatus.FAILED, error="Could not create destination directory"
                ))
                result.error_count += 1
                continue
            
            backup = None
            if os.path.exists(target):
                removed, error = False, None
                if detect_duplicates:
                    target_identity = None
                    def validate_duplicate():
                        nonlocal target_identity
                        target_identity = self._identity(os.lstat(target))
                        current_root = self._validate_root(plan.root_dir)
                        current_source, current_info = self._source_snapshot(src, current_root)
                        if current_source != os.path.abspath(src):
                            raise ValueError("Duplicate source path changed since planning")
                        if item.source_identity is not None and self._identity(current_info) != item.source_identity:
                            raise ValueError("Duplicate source changed since planning")
                        _, current_destination = self.planner._validate_boundary(current_root, target)
                        if current_destination != os.path.abspath(target):
                            raise ValueError("Duplicate destination changed since planning")
                    removed, src_hash, error = FileUtils.remove_verified_duplicate(src, target, validate_duplicate)
                if error:
                    result.records.append(FileOperationRecord(
                        source=src, target=target, category=category, rule_name=rule_name,
                        status=OperationStatus.FAILED, error=f"Duplicate source was preserved: {error}", size=src_size
                    ))
                    result.error_count += 1
                    continue
                if removed:
                    result.records.append(FileOperationRecord(
                        source=src, target=target, category=category, rule_name=rule_name,
                        status=OperationStatus.DUPLICATE, hash=src_hash, size=src_size
                    ))
                    if result.undo:
                        result.undo.entries.append(Entry(src, target, target_identity, src_hash, info, True, None))
                    result.duplicate_count += 1
                    continue
                else:
                    if conflict_policy == 'rename':
                        target = FileUtils.get_unique_path(target)
                        if os.path.exists(target):
                            result.records.append(FileOperationRecord(
                                source=src, target=target, category=category, rule_name=rule_name,
                                status=OperationStatus.FAILED, error="Failed to resolve filename collision"
                            ))
                            result.error_count += 1
                            continue
                        collision_resolved = True
                    elif conflict_policy == 'skip':
                        result.records.append(FileOperationRecord(
                            source=src, target=target, category=category, rule_name=rule_name,
                            status=OperationStatus.SKIPPED, size=src_size
                        ))
                        result.skip_count += 1
                        continue

            if result.undo and os.path.lexists(target):
                try:
                    backup = result.undo.backup(target)
                except (OSError, ValueError) as error:
                    result.records.append(FileOperationRecord(src, target, category, rule_name, OperationStatus.FAILED, str(error)))
                    result.error_count += 1
                    continue

            output = target
            try:
                if backup:
                    fd, output = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".smartsort-move-")
                    os.close(fd)
                shutil.copy2(src, output)
                
                if not (os.path.exists(output) and os.path.isfile(output) and not os.path.islink(output)):
                    raise Exception("Target missing or invalid after copy")
                    
                if os.path.getsize(output) != src_size:
                    raise Exception("Size verification failed after copy")
                    
                if src_hash is None:
                    src_hash = FileUtils.calculate_sha256(src)
                    
                dst_hash = FileUtils.calculate_sha256(output)
                if not src_hash or not dst_hash or src_hash != dst_hash:
                    raise Exception("Hash verification failed after copy")
                    
                if backup:
                    if identity(target) != backup[2]:
                        raise ValueError("Existing destination changed before overwrite")
                    os.replace(output, target)
                if result.undo:
                    target_identity = identity(target)
            except Exception as e:
                try:
                    if (not backup or output != target) and os.path.exists(output):
                        os.remove(output)
                except OSError:
                    pass
                result.records.append(FileOperationRecord(
                    source=src, target=target, category=category, rule_name=rule_name,
                    status=OperationStatus.FAILED, error=str(e), size=src_size
                ))
                result.error_count += 1
                continue

            remember_output(target)
            try:
                os.remove(src)
                if os.path.exists(src):
                    raise Exception("Source file still exists after removal")
            except Exception as e:
                if backup and os.path.lexists(src):
                    try:
                        result.undo.restore_backup(backup, target, target_identity)
                    except (OSError, ValueError) as restore_error:
                        result.warnings.append(f"Could not restore overwritten destination {target}: {restore_error}")
                result.records.append(FileOperationRecord(
                    source=src, target=target, category=category, rule_name=rule_name,
                    status=OperationStatus.FAILED, error=f"Failed to delete source: {e}", size=src_size, hash=src_hash
                ))
                result.error_count += 1
                continue

            status = OperationStatus.COLLISION_RESOLVED if collision_resolved else OperationStatus.VERIFIED_AND_MOVED
            result.records.append(FileOperationRecord(
                source=src, target=target, category=category, rule_name=rule_name,
                status=status, hash=src_hash, size=src_size
            ))
            
            if result.undo:
                result.undo.entries.append(Entry(src, target, target_identity, src_hash, info, False, backup))

            if collision_resolved:
                result.collision_count += 1
            else:
                result.success_count += 1

        for record in result.records:
            confidence, evidence, name, score, cluster_id = metadata[record.source]
            record.confidence = confidence
            record.evidence = list(evidence)
            record.cluster_name = name
            record.confidence_score = score
            record.cluster_id = cluster_id
        return result

    def generate_report(self, root_dir: str, result: OrganizeResult) -> str:
        """Write the latest operation snapshot, with local links and searchable evidence.

        A sibling temporary file keeps replacement on the same filesystem. Readers
        see the old or complete new report; this is not a multi-writer transaction
        or a guarantee against every filesystem/power-loss failure.
        """
        root = self._validate_root(root_dir)
        report_path = os.path.join(root, "SmartSort_Arrangement.md")

        markdown_escapes = str.maketrans({c: "\\" + c for c in "\\`*_{}[]()#+-.!|>"})

        def visible(value):
            # Keep untrusted filenames/evidence on one Markdown line.
            return str(value).replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")

        def text(value):
            escaped = html.escape(visible(value), quote=True)
            return escaped.translate(markdown_escapes)

        def code(value):
            value = visible(value)
            fence = "`" * (1 + max((len(run) for run in re.findall(r"`+", value)), default=0))
            return fence + " " + value + " " + fence

        def uri(path):
            return Path(os.path.abspath(path)).as_uri()

        groups = {}
        clusters = {}
        for index, record in enumerate(result.records, 1):
            parent = os.path.dirname(os.path.abspath(record.target))
            relative = os.path.relpath(parent, root)
            # Do not pretend an external/manual destination is beneath the root.
            folder = relative if relative != os.pardir and not relative.startswith(os.pardir + os.sep) else parent
            groups.setdefault(folder, []).append((index, record))
            if record.cluster_name or record.cluster_id:
                key = (record.cluster_id, record.cluster_name)
                clusters.setdefault(key, []).append((index, record))

        lines = [
            "# SmartSort Arrangement Index", "",
            f"**Root Directory:** {code(root)}  ",
            f"**Date of Operation:** {code(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}  ",
            f"**Total Files Processed:** {len(result.records)}  ",
            f"**Summary:** {result.success_count} Verified & Moved | "
            f"{result.collision_count} Collision Resolved | "
            f"{result.duplicate_count} Duplicate Sources Removed | "
            f"{result.skip_count} Skipped | {result.error_count} Errors", "",
            f"**Cancelled:** {'Yes' if result.cancelled else 'No'}", "",
            "This report describes the latest operation. Unprocessed files are not listed.", "",
            "Confidence scores are estimates, not calibrated probabilities. A confirmed rule match reflects configured policy.", "",
            "## Table of Contents", "",
        ]
        folders = sorted(groups)
        for number, folder in enumerate(folders, 1):
            lines.append(f"- [{text(folder)}](#destination-{number}) ({len(groups[folder])} files)")
        if clusters:
            lines.append(f"- [Clusters](#clusters) ({len(clusters)} groups)")
        if result.warnings:
            lines.extend(["", "## Planning Warnings", ""])
            lines.extend(f"- {text(warning)}" for warning in result.warnings)

        if clusters:
            lines.extend(["", '<a id="clusters"></a>', "## Clusters", ""])
            for (cluster_id, name), members in clusters.items():
                lines.append(f"### {text(name or cluster_id)} ({len(members)} files)")
                if cluster_id:
                    lines.append(f"- **Cluster ID:** {code(cluster_id)}")
                for index, record in members:
                    lines.append(f"- [{text(os.path.basename(record.target))}](#file-{index}) — {code(record.status.value)}")
                lines.append("")

        moved = {OperationStatus.VERIFIED_AND_MOVED, OperationStatus.COLLISION_RESOLVED}
        for number, folder in enumerate(folders, 1):
            lines.extend(["", f'<a id="destination-{number}"></a>', f"## {text(folder)}", ""])
            for index, record in groups[folder]:
                lines.extend([f'<a id="file-{index}"></a>', f"### {text(os.path.basename(record.target))}", ""])
                location_label = "Final Location" if record.status in moved else "Existing Destination" if record.status == OperationStatus.DUPLICATE else "Intended Destination"
                lines.extend([
                    f"- **Original Path:** {code(record.source)}",
                    f"- **{location_label}:** {code(record.target)}",
                    f"- **Category:** {text(record.category)}",
                    f"- **Rule:** {text(record.rule_name)}",
                ])
                confidence = record.confidence
                score = record.confidence_score
                if isinstance(score, (int, float)) and math.isfinite(score) and 0 <= score <= 1:
                    confidence += f" ({score:.0%})"
                lines.append(f"- **Confidence:** {code(confidence)}")
                if record.cluster_name or record.cluster_id:
                    lines.append(f"- **Cluster:** {code(record.cluster_name or record.cluster_id)}")
                    if record.cluster_id:
                        lines.append(f"- **Cluster ID:** {code(record.cluster_id)}")
                lines.append("- **Evidence:**")
                lines.extend(f"  - {text(reason)}" for reason in record.evidence)
                if not record.evidence:
                    lines.append("  - No evidence recorded.")
                lines.append(f"- **Size:** {self._format_size(record.size)}")
                if record.hash:
                    lines.append(f"- **SHA-256:** {code(record.hash)}")
                lines.append(f"- **Status:** {code(record.status.value)}")
                if record.error:
                    lines.append(f"- **Error:** {text(record.error)}")
                if record.status in moved:
                    actions = f"[Open File](<{uri(record.target)}>) | [Open Folder](<{uri(os.path.dirname(record.target))}>)"
                elif record.status == OperationStatus.DUPLICATE:
                    actions = f"[Open Existing Destination](<{uri(record.target)}>) | [Open Folder](<{uri(os.path.dirname(record.target))}>)"
                    lines.append("- **Duplicate action:** SHA-256 matched; source copy removed; existing destination retained.")
                else:
                    actions = f"[Open Source](<{uri(record.source)}>) | [Open Source Folder](<{uri(os.path.dirname(record.source))}>)"
                lines.extend([f"- **Actions:** {actions}", ""])

        content = "\n".join(lines)
        fd, tmp_path = tempfile.mkstemp(dir=root, prefix=".SmartSort_Arrangement.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, report_path)
        finally:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
        return report_path

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024**2):.2f} MB"
        else:
            return f"{size_bytes/(1024**3):.2f} GB"
