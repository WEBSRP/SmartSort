import os
import time
import copy
import stat
import threading
from types import SimpleNamespace
from pathlib import Path
from typing import Tuple, Optional
from .utils.file_utils import FileUtils
from .utils.output_tracker import remember_output
from .utils.desktop_folders import DesktopDestinations
from .utils.folder_guard import protected_folder_for
from .utils.config import ConfigManager
from .utils.logger import SmartSortLogger
from src.rules.manager import RuleManager
from src.rules.engine import RuleEngine, rules_for_mode
from src.core.filename_cleanup import FilenameCleanup
from src.core.notifications import NotificationManager
from src.core.file_intelligence import (
    FileContext, FileContextBuilder, OriginDetector, OriginInfo, SignalExtractor,
    MultiSignalClassifier, OrganizationPlanner, OrganizationProposal,
    ConfidenceLevel, EvidenceItem, SignalType, DeterministicMime,
)
from src.core.file_intelligence.extractors import ExtractorRegistry

class FileOrganizer:
    EXTRACTION_TIMEOUT_SECONDS = 2.0
    VIDEO_EXTENSIONS = frozenset((".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".m4v", ".3gp"))

    def __init__(self, config_manager: ConfigManager, logger: SmartSortLogger):
        self.config = config_manager
        self.logger = logger
        self.rule_manager = RuleManager(config_manager)
        self.notification_manager = NotificationManager(config_manager, logger)
        self.filename_cleanup = FilenameCleanup(
            enabled=config_manager.get("smart_filename_cleanup", False),
            min_length=config_manager.get("filename_min_length", 4),
            max_length=config_manager.get("filename_max_length", 80),
        )
        self.extractor_registry = ExtractorRegistry()
        self.origin_detector = OriginDetector(config_manager)
        self.signal_extractor = SignalExtractor()
        self.classifier = MultiSignalClassifier(config_manager)
        self.planner = OrganizationPlanner(self.rule_manager, config_manager)
        self._local = threading.local()
        self._inflight_lock = threading.Lock()
        self._inflight = set()
        self._transfer_lock = threading.RLock()

    def _protected_download_folder(self, path):
        watch = self.config.get("downloads_folder")
        if not isinstance(watch, str) or not watch:
            return None
        root = os.path.realpath(os.path.expanduser(watch))
        return protected_folder_for(path, root)

    @staticmethod
    def _source_info(file_path):
        path = os.path.abspath(OrganizationPlanner._path(file_path))
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Download must be a regular non-symlink file")
        OrganizationPlanner._component(os.path.basename(path))
        return os.path.realpath(path), info

    @staticmethod
    def _identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def _base(self):
        value = os.path.expanduser(OrganizationPlanner._path(self.config.get("destination_base", os.path.expanduser("~"))))
        return self.planner._resolve(os.path.abspath(value), directory=True)

    def _snapshot_policy(self):
        # Preserve old broad rules for Rules first; only explicit manual overrides
        # take priority in Content intelligence. Saved rules are never deleted.
        return SimpleNamespace(rules=copy.deepcopy(rules_for_mode(self.rule_manager.rules,
            self.config.get("sorting_mode", "rules_first"))))

    def _policy(self):
        request = getattr(self._local, "request", None)
        return request["policy"] if request else self._snapshot_policy()

    def _proposal_for(self, file_path, override_filename=None):
        request = getattr(self._local, "request", None)
        if request and request["file"] == os.path.realpath(file_path):
            if request["proposal"] is None:
                request["proposal"] = self.analyze_download(file_path, request["override"])
            return request["proposal"]
        return self.analyze_download(file_path, override_filename)

    def analyze_download(self, file_path: str, override_filename: Optional[str] = None) -> OrganizationProposal:
        """Read-only profiling and planning; never transfers or renames a source."""
        path, info = self._source_info(file_path)
        if self._protected_download_folder(path):
            raise ValueError("Application/project folder must remain intact")
        identity = self._identity(info)
        request = getattr(self._local, "request", None)
        if request and (request["file"] != path or request["identity"] != identity):
            raise ValueError("Download changed before analysis")
        filename = os.path.basename(path)
        stem, extension = os.path.splitext(filename)
        ctx = FileContext(path, filename, stem, extension, "", info.st_size,
                          info.st_ctime, info.st_mtime, info.st_ino, info.st_dev)
        base = request["base"] if request else self._base()
        routes = DesktopDestinations(base, self.config)
        planner = copy.copy(self.planner)
        planner.rule_manager = self._policy()
        matched, _ = RuleEngine(planner.rule_manager.rules).evaluate_file(path, info.st_size)
        fallback = False
        if matched is None:
            try:
                enriched = FileContextBuilder.build_initial_context(path, read_origin_xattrs=False)
                if (enriched.path != path or
                        (enriched.device, enriched.inode, enriched.size_bytes) != (info.st_dev, info.st_ino, info.st_size)):
                    raise ValueError("Download identity changed during ingestion")
                ctx = enriched
                try:
                    ctx.origin = self.origin_detector.detect_origin(path, ctx.size_bytes)
                except Exception:
                    ctx.origin = OriginInfo()
                if self.config.get("enable_deep_content_extraction", True):
                    ctx.metadata = self.extractor_registry.extract_metadata(path, timeout_seconds=self.EXTRACTION_TIMEOUT_SECONDS)
                if ctx.metadata.extraction_status not in ("SUCCESS", "PARTIAL", "UNSUPPORTED"):
                    raise ValueError("Extraction unavailable")
                self.signal_extractor.extract_signals(ctx)
                self.classifier.classify(ctx)
            except Exception:
                fallback = True
        current_path, current = self._source_info(path)
        if current_path != path or self._identity(current) != identity:
            raise ValueError("Download changed during analysis")
        if request:
            request["video"] = ctx.mime_type.startswith("video/")
        if fallback:
            parts = DeterministicMime.get_sorting_parts(extension, ctx.mime_type)
            category = parts[0]
            target_name = OrganizationPlanner._component(override_filename if override_filename is not None else filename)
            relative = os.path.join(*parts, target_name)
            proposal = OrganizationProposal(path, os.path.join(base, relative), relative, category, relative.split(os.sep)[:-1],
                ConfidenceLevel.UNKNOWN, 0.0, [EvidenceItem(SignalType.EXTENSION_HINT,
                    "Profiling unavailable; extension-based fallback", 0.0, "extension")])
            proposal, _ = routes.apply(proposal, planner)
        else:
            proposal = planner.plan_file(ctx, base, override_filename=override_filename, destination_routes=routes)
        return self._desktop_proposal(proposal, routes)

    def _desktop_proposal(self, proposal, routes):
        request = getattr(self._local, "request", None)
        if request is not None:
            request["destination_root"] = routes.selected_root
            request["routing_signature"] = routes.signature
        return proposal

    def get_category(self, file_path: str) -> str:
        engine = RuleEngine(self._policy().rules)
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            file_size = None
        rule, _ = engine.evaluate_file(file_path, file_size)
        if rule:
            return rule.name
        if not os.path.exists(file_path):
            return "Others"
        return self._proposal_for(file_path).domain

    def get_destination_path(self, file_path: str, category: str = None, override_filename: str = None) -> str:
        try:
            return self._proposal_for(file_path, override_filename).target_path
        except ValueError as exc:
            raise ValueError(f"Destination escapes configured base directory or is invalid: {exc}") from exc

    def process_file(self, file_path: str, user_approved: bool = False) -> Tuple[str, str]:
        if not os.path.exists(file_path):
            return "SKIPPED", "File already processed or removed"
        try:
            path, info = self._source_info(file_path)
        except (OSError, ValueError, TypeError):
            return "ERROR", "Download is unavailable or unsafe"
        if self._protected_download_folder(path):
            return "SKIPPED", "Application/project folder kept intact"
        key = (info.st_dev, info.st_ino)
        with self._inflight_lock:
            if key in self._inflight:
                return "SKIPPED", "Download is already being processed"
            self._inflight.add(key)
        previous = getattr(self._local, "request", None)
        try:
            base = self._base()
            self._local.request = {"file": path, "identity": self._identity(info), "base": base,
                "destination_root": base, "routing_signature": DesktopDestinations(base, self.config).signature,
                "policy": self._snapshot_policy(),
                "override": None, "proposal": None, "video": False}
            return self._process_file(path, user_approved)
        except (OSError, ValueError, TypeError) as exc:
            return "ERROR", str(exc)
        except Exception:
            return "ERROR", "Download processing failed"
        finally:
            self._local.request = previous
            with self._inflight_lock:
                self._inflight.discard(key)

    def _validate_transfer(self, source, target):
        request = self._local.request
        if self._protected_download_folder(source):
            raise ValueError("Source became part of an application/project folder")
        path, info = self._source_info(source)
        if path != request["file"] or self._identity(info) != request["identity"]:
            raise ValueError("Download changed since analysis")
        if self._base() != request["base"]:
            raise ValueError("Destination base changed during processing")
        if DesktopDestinations(request["base"], self.config).signature != request["routing_signature"]:
            raise ValueError("Desktop folder settings changed during processing")
        _, resolved = self.planner._validate_boundary(request["destination_root"], target)
        if resolved != os.path.abspath(target):
            raise ValueError("Destination changed since analysis")

    def _process_file(self, file_path: str, user_approved: bool = False) -> Tuple[str, str]:
        """
        Process a single file: categorize, determine dest, safe copy, delete original.
        Returns (Status, Info)
        """
        if not os.path.exists(file_path):
            return "SKIPPED", "File already processed or removed"

        # Smart Filename Cleanup (evaluated before categorization)
        override_filename = None
        original_basename = os.path.basename(file_path)
        if self.filename_cleanup.needs_cleanup(original_basename):
            clean_name = self.filename_cleanup.generate_clean_name(file_path)
            override_filename = clean_name
            self.logger.info(
                f"Smart Cleanup: '{original_basename}' → '{clean_name}'"
            )

        self._local.request["override"] = override_filename
        category = self.get_category(file_path)
        try:
            dest_path = self.get_destination_path(file_path, category, override_filename=override_filename)
        except ValueError as e:
            return "ERROR", str(e)
        filename = os.path.basename(file_path)
        self._validate_transfer(file_path, dest_path)
        if os.path.realpath(dest_path) == file_path or (os.path.exists(dest_path) and os.path.samefile(file_path, dest_path)):
            return "SKIPPED", "Download is already at its destination"

        # Check for large video approval
        if ("Videos" in category or category.startswith("Videos") or
                Path(file_path).suffix.lower() in self.VIDEO_EXTENSIONS or self._local.request["video"]):
            try:
                file_size = os.path.getsize(file_path)
                threshold_bytes = self.config.get("large_file_threshold_gb")
                
                # Fallback to GB if threshold is legacy float/int < 10000
                if isinstance(threshold_bytes, (int, float)) and threshold_bytes < 10000:
                    threshold_bytes = int(threshold_bytes * (1024**3))
                elif threshold_bytes is None:
                    threshold_bytes = int(2.5 * (1024**3))
                    
                if file_size >= threshold_bytes and not user_approved:
                    # Trigger GUI/Notification for approval
                    return "AWAIT_APPROVAL", dest_path
            except OSError as e:
                self.logger.error(f"Failed to check size of {file_path}: {e}")
                return "ERROR", f"Failed to access file: {str(e)}"

        with self._transfer_lock:
            return self._transfer_file(file_path, dest_path, category, filename)

    def _transfer_file(self, file_path, dest_path, category, filename):
        # Serialize destination decisions/copies within this organizer instance.
        # Parsing remains concurrent; a second download cannot overwrite a
        # destination whose first writer has not finished its collision check.
        self._validate_transfer(file_path, dest_path)
        # Duplicate and Collision Detection
        if os.path.exists(dest_path):
            if self.config.get("enable_duplicate_detection", True):
                removed, _, error = FileUtils.remove_verified_duplicate(file_path, dest_path,
                    validate=lambda: self._validate_transfer(file_path, dest_path))
                if error:
                    return "ERROR", f"Duplicate source was preserved: {error}"
                if removed:
                    self.logger.log_action(filename, file_path, dest_path, "DUPLICATE_SOURCE_REMOVED", "SUCCESS")
                    return "DUPLICATE", dest_path
            
            # Destination file exists but either hashes differ or duplicate detection is disabled
            conflict_policy = self.config.get("conflict_resolution", "rename")
            if conflict_policy == "rename":
                dest_path = FileUtils.get_unique_path(dest_path)
            elif conflict_policy == "overwrite":
                pass # let it overwrite in safe_copy
            else: # "skip" or other unrecognized conflict policy
                self.logger.log_action(filename, file_path, dest_path, "SKIP_COLLISION", "SKIP")
                return "SKIPPED", f"Destination file already exists: {dest_path}"

        # Safe Transfer
        self._validate_transfer(file_path, dest_path)
        success, info = FileUtils.safe_copy(file_path, dest_path)
        if success:
            try:
                self._validate_transfer(file_path, dest_path)
                remember_output(dest_path)
                os.remove(file_path)
                self.logger.log_action(filename, file_path, dest_path, "TRANSFER_SUCCESS")
                try:
                    self.notification_manager.send_success_notification(dest_path)
                except Exception as notif_err:
                    self.logger.error(f"Notification error ignored during sorting: {notif_err}")
                return "SUCCESS", dest_path
            except Exception as e:
                self.logger.log_action(filename, file_path, dest_path, "DELETE_ORIGINAL_FAILED", "ERROR", str(e))
                return "ERROR", f"Failed to delete source: {str(e)}"
        else:
            self.logger.log_action(filename, file_path, dest_path, "COPY_FAILED", "ERROR", info)
            return "ERROR", info

