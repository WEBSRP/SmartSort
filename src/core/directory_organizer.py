import os
import hashlib
import shutil
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Tuple, Dict
from pathlib import Path
from datetime import datetime

from src.rules.engine import RuleEngine
from src.rules.manager import RuleManager
from src.utils.file_utils import FileUtils
from src.utils.config import ConfigManager
from src.utils.logger import SmartSortLogger


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


@dataclass
class OrganizePlan:
    items: List[OrganizePlanItem]
    root_dir: str
    total_files: int
    category_counts: Dict[str, int]


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


@dataclass
class OrganizeResult:
    records: List[FileOperationRecord]
    success_count: int = 0
    collision_count: int = 0
    duplicate_count: int = 0
    skip_count: int = 0
    error_count: int = 0
    cancelled: bool = False


@dataclass
class DirectoryPreviewSummary:
    total_files: int
    category_counts: Dict[str, int]
    items: List[OrganizePlanItem]


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

    def _validate_root(self, root_dir: str):
        if not os.path.exists(root_dir):
            raise ValueError(f"Root directory does not exist: {root_dir}")
        if not os.path.isdir(root_dir):
            raise ValueError(f"Root path is not a directory: {root_dir}")
        
        resolved_path = os.path.abspath(root_dir)
        if resolved_path in self.PROTECTED_ROOTS:
            raise ValueError(f"Cannot organize protected root directory: {root_dir}")

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
            try:
                rel = os.path.relpath(file_path, root_dir)
                parts = Path(rel).parts
                if any(p.startswith('.') for p in parts):
                    return True
            except ValueError:
                pass

        return False

    def scan(self, root_dir: str, recursive: bool = False) -> List[str]:
        self._validate_root(root_dir)
        results = []
        
        if not recursive:
            with os.scandir(root_dir) as it:
                for entry in it:
                    if entry.is_file() and not self._is_excluded(entry.path, root_dir):
                        results.append(os.path.abspath(entry.path))
        else:
            for dirpath, dirnames, filenames in os.walk(root_dir, followlinks=False):
                # Do not recurse into hidden directories
                dirnames[:] = [d for d in dirnames if not d.startswith('.')]
                for f in filenames:
                    file_path = os.path.join(dirpath, f)
                    if not self._is_excluded(file_path, root_dir) and os.path.isfile(file_path):
                        results.append(os.path.abspath(file_path))
                        
        results.sort()
        return results

    def plan(self, root_dir: str, file_paths: List[str]) -> OrganizePlan:
        engine = RuleEngine(self.rule_manager.rules)
        items = []
        category_counts = {}
        
        for file_path in file_paths:
            try:
                file_size = os.path.getsize(file_path)
            except OSError:
                continue
                
            rule, relative_dest = engine.evaluate_file(file_path, file_size)
            
            if rule and '{filename}' in rule.destination:
                target = Path(root_dir) / relative_dest
            else:
                target = Path(root_dir) / relative_dest / os.path.basename(file_path)
                
            target_str = os.path.abspath(str(target))
            root_abs = os.path.abspath(root_dir)
            
            if os.path.commonpath([root_abs, target_str]) != root_abs:
                continue
                
            source_str = os.path.abspath(file_path)
            if source_str == target_str:
                continue
                
            category = rule.name if rule else 'Others'
            rule_name = rule.name if rule else 'Default'
            
            items.append(OrganizePlanItem(
                source_path=source_str,
                target_path=target_str,
                category=category,
                rule_name=rule_name
            ))
            category_counts[category] = category_counts.get(category, 0) + 1
            
        return OrganizePlan(
            items=items,
            root_dir=root_dir,
            total_files=len(items),
            category_counts=category_counts
        )

    def preview(self, root_dir: str, recursive: bool = False) -> DirectoryPreviewSummary:
        file_paths = self.scan(root_dir, recursive)
        plan = self.plan(root_dir, file_paths)
        return DirectoryPreviewSummary(
            total_files=plan.total_files,
            category_counts=plan.category_counts,
            items=plan.items
        )

    def execute(self, plan: OrganizePlan, progress_callback: Optional[Callable] = None, cancel_check: Optional[Callable] = None) -> OrganizeResult:
        result = OrganizeResult(records=[])
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
            
            os.makedirs(os.path.dirname(target), exist_ok=True)
            
            if os.path.exists(target):
                src_hash = FileUtils.calculate_sha256(src)
                dst_hash = FileUtils.calculate_sha256(target)
                
                if detect_duplicates and src_hash == dst_hash:
                    result.records.append(FileOperationRecord(
                        source=src, target=target, category=category, rule_name=rule_name,
                        status=OperationStatus.DUPLICATE, hash=src_hash, size=src_size
                    ))
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

            try:
                shutil.copy2(src, target)
                
                if not (os.path.exists(target) and os.path.isfile(target) and not os.path.islink(target)):
                    raise Exception("Target missing or invalid after copy")
                    
                if os.path.getsize(target) != src_size:
                    raise Exception("Size verification failed after copy")
                    
                if src_hash is None:
                    src_hash = FileUtils.calculate_sha256(src)
                    
                dst_hash = FileUtils.calculate_sha256(target)
                if src_hash != dst_hash:
                    raise Exception("Hash verification failed after copy")
                    
            except Exception as e:
                try:
                    if os.path.exists(target):
                        os.remove(target)
                except OSError:
                    pass
                result.records.append(FileOperationRecord(
                    source=src, target=target, category=category, rule_name=rule_name,
                    status=OperationStatus.FAILED, error=str(e), size=src_size
                ))
                result.error_count += 1
                continue

            try:
                os.remove(src)
                if os.path.exists(src):
                    raise Exception("Source file still exists after removal")
            except Exception as e:
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
            
            if collision_resolved:
                result.collision_count += 1
            else:
                result.success_count += 1

        return result

    def generate_report(self, root_dir: str, result: OrganizeResult) -> str:
        report_path = os.path.join(root_dir, "SmartSort_Arrangement.md")
        tmp_path = report_path + ".tmp"
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_files = len(result.records)
        
        summary_line = (f"{result.success_count} Verified & Moved | "
                        f"{result.collision_count} Collision Resolved | "
                        f"{result.duplicate_count} Duplicate Preserved | "
                        f"{result.skip_count} Skipped | "
                        f"{result.error_count} Errors")

        toc_entries = []
        
        verified_records = [r for r in result.records if r.status == OperationStatus.VERIFIED_AND_MOVED]
        categories = {}
        for r in verified_records:
            categories.setdefault(r.category, []).append(r)
            
        for cat in sorted(categories.keys()):
            toc_entries.append(f"- [{cat}](#{cat.lower().replace(' ', '-')})")

        collision_records = [r for r in result.records if r.status == OperationStatus.COLLISION_RESOLVED]
        if collision_records:
            toc_entries.append("- [Collision Resolved](#collision-resolved)")

        duplicate_records = [r for r in result.records if r.status == OperationStatus.DUPLICATE]
        if duplicate_records:
            toc_entries.append("- [Duplicates (Source Preserved)](#duplicates-source-preserved)")

        skipped_records = [r for r in result.records if r.status == OperationStatus.SKIPPED]
        if skipped_records:
            toc_entries.append("- [Skipped](#skipped)")

        failed_records = [r for r in result.records if r.status == OperationStatus.FAILED]
        if failed_records:
            toc_entries.append("- [Failed](#failed)")

        toc_str = "\n".join(toc_entries)

        lines = [
            "# SmartSort Arrangement Index\n",
            f"**Root Directory:** `{root_dir}`  ",
            f"**Date of Operation:** `{now_str}`  ",
            f"**Total Files Processed:** `{total_files}`  ",
            f"**Summary:** {summary_line}  \n",
            "---\n",
            "## Table of Contents\n",
            toc_str,
            "\n---\n"
        ]

        def add_record(r, show_duplicate=False):
            filename = os.path.basename(r.target if not show_duplicate else r.source)
            lines.append(f"### {filename}")
            if not show_duplicate:
                lines.append(f"- **Original Path:** `{r.source}`")
                lines.append(f"- **Final Location:** `{r.target}`")
            else:
                lines.append(f"- **Source Path:** `{r.source}`")
                lines.append(f"- **Existing Destination:** `{r.target}`")
                
            lines.append(f"- **Category:** {r.category}")
            lines.append(f"- **Size:** {self._format_size(r.size)}")
            if r.hash:
                lines.append(f"- **SHA-256:** `{r.hash}`")
            lines.append(f"- **Status:** `{r.status.value}`")
            if r.error:
                lines.append(f"- **Error:** {r.error}")
            
            if show_duplicate:
                source_uri = Path(r.source).as_uri()
                target_uri = Path(r.target).as_uri()
                lines.append(f"- **Actions:** [Open Source]({source_uri}) | [Open Existing Destination]({target_uri})\n")
            else:
                file_uri = Path(r.target).as_uri()
                folder_uri = Path(os.path.dirname(r.target)).as_uri()
                lines.append(f"- **Actions:** [Open File]({file_uri}) | [Open Folder]({folder_uri})\n")

        for cat in sorted(categories.keys()):
            lines.append(f"## {cat}\n")
            for r in categories[cat]:
                add_record(r)

        if collision_records:
            lines.append("## Collision Resolved\n")
            for r in collision_records:
                add_record(r)

        if duplicate_records:
            lines.append("## Duplicates (Source Preserved)\n")
            for r in duplicate_records:
                add_record(r, show_duplicate=True)

        if skipped_records:
            lines.append("## Skipped\n")
            for r in skipped_records:
                add_record(r)

        if failed_records:
            lines.append("## Failed\n")
            for r in failed_records:
                add_record(r)

        report_content = "\n".join(lines)
        
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(report_content)
            
        os.replace(tmp_path, report_path)
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
