"""Rule-first, read-only destination planning with current-tree containment."""

import os
import re
import stat

from src.core.file_intelligence.classifier import MultiSignalClassifier
from src.core.file_intelligence.mime import DeterministicMime
from src.core.file_intelligence.context import (
    ConfidenceLevel, EvidenceItem, FileContext, OrganizationProposal, SignalType,
)
from src.rules.engine import RuleEngine


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class OrganizationPlanner:
    """Emits proposals; callers must revalidate paths when executing transfers."""

    MAX_HIERARCHY_DEPTH = 16
    MAX_EVIDENCE = 8192

    def __init__(self, rule_manager, config):
        self.rule_manager = rule_manager
        self.config = config  # Explicit root argument is authoritative; no config I/O.
        self.rule_engine = RuleEngine(rule_manager.rules)

    @staticmethod
    def _path(value):
        try:
            value = os.fspath(value)
        except TypeError as exc:
            raise ValueError("A non-empty filesystem path is required") from exc
        if not isinstance(value, str) or not value or len(value) > 4096 or _CONTROL.search(value) or "\\" in value:
            raise ValueError("Invalid or oversized planning path")
        return value

    @staticmethod
    def _component(value):
        if (not isinstance(value, str) or not value or not value.strip() or
                value in (".", "..") or "/" in value or "\\" in value or _CONTROL.search(value)):
            raise ValueError("Invalid destination path component")
        try:
            if len(os.fsencode(value)) > 255:
                raise ValueError("Destination path component exceeds 255 bytes")
        except UnicodeError as exc:
            raise ValueError("Destination component cannot be represented on this filesystem") from exc
        return value

    @staticmethod
    def _resolve(path, directory=False):
        try:
            # realpath supports missing suffixes on the supported Python range.
            # stat below fails closed on loops, permission errors and non-dir
            # ancestors even on versions whose non-strict realpath ignores them.
            resolved = os.path.realpath(path)
            try:
                info = os.stat(resolved)
            except FileNotFoundError:
                info = None
            if info is not None:
                valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
                if not valid:
                    raise ValueError("Planning path has an incompatible existing file type")
            return resolved
        except (OSError, RuntimeError) as exc:
            raise ValueError("Cannot safely resolve planning path") from exc

    def _validate_boundary(self, root_dir, target_path):
        root = self._resolve(os.path.abspath(self._path(root_dir)), directory=True)
        lexical = os.path.abspath(self._path(target_path))
        if lexical == os.path.abspath(os.fspath(root_dir)):
            raise ValueError("Target must name a file beneath the destination root")
        target = self._resolve(lexical)
        if target == root or os.path.commonpath([root, target]) != root:
            raise ValueError("Destination escapes the configured root directory")
        return root, target

    def plan_file(self, context, root_dir, *, override_filename=None, destination_routes=None):
        if not isinstance(context, FileContext):
            raise ValueError("Planning requires a FileContext")
        source = self._path(context.path)
        filename = self._component(context.filename)
        if os.path.basename(source) != filename:
            raise ValueError("Context filename must match its source basename")
        if override_filename is not None:
            filename = self._component(override_filename)
        if isinstance(context.size_bytes, bool) or not isinstance(context.size_bytes, int) or context.size_bytes < 0:
            raise ValueError("Planning requires a non-negative integer file size")
        root_abs = os.path.abspath(self._path(root_dir))
        # Honor live rule-manager changes, using the existing engine's priority,
        # enabled-state, condition and variable-expansion semantics unchanged.
        self.rule_engine = RuleEngine(self.rule_manager.rules)
        rule, destination = self.rule_engine.evaluate_file(source, context.size_bytes)
        if rule is not None:
            if override_filename is not None and "{filename}" in rule.destination:
                extension = os.path.splitext(source)[1].lstrip(".").upper()
                destination = rule.destination.replace("{extension}", extension).replace("{filename}", filename)
            destination = self._path(destination)
            if _SCHEME.match(destination) or ".." in destination.split("/"):
                raise ValueError("Unsafe custom rule destination")
            for part in destination.split("/"):
                if part not in ("", "."):
                    self._component(part)
            if "{filename}" in rule.destination:
                if destination.endswith("/"):
                    raise ValueError("Filename rule destination must name a file")
                relative = destination
            else:
                relative = os.path.join(destination, filename)
            domain = _CONTROL.sub(" ", str(rule.name)[:256])
            level, score = ConfidenceLevel.CONFIRMED, 1.0
            evidence = [EvidenceItem(SignalType.FILENAME_TOKEN,
                        f"Matched custom user rule: '{domain}' (Priority {rule.priority})",
                        1.0, "rules")]
        else:
            score = context.confidence_score
            level = context.confidence
            if (isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1 or
                    not isinstance(level, ConfidenceLevel)):
                raise ValueError("Classification must have a finite score and typed confidence level")
            if (not isinstance(context.evidence_list, list) or len(context.evidence_list) > self.MAX_EVIDENCE or
                    any(not isinstance(e, EvidenceItem) for e in context.evidence_list)):
                raise ValueError("Classification evidence is invalid or exceeds its planning budget")
            evidence = list(context.evidence_list)
            domain = context.classification_domain
            if score < .35 or level in (ConfidenceLevel.UNKNOWN, ConfidenceLevel.NOT_AVAILABLE) or domain == "Others":
                parts = list(DeterministicMime.get_sorting_parts(context.extension, context.mime_type,
                    getattr(context.metadata, "code_language", None)))
                domain = parts[0]
                level, score = ConfidenceLevel.UNKNOWN, 0.0
                evidence.append(EvidenceItem(SignalType.EXTENSION_HINT,
                    f"Insufficient content evidence; file-type fallback to {'/'.join(parts)}", 0.0, "extension"))
            else:
                self._component(domain)
                if domain not in MultiSignalClassifier.DOMAINS:
                    raise ValueError("Unrecognized classification domain")
                if (not isinstance(context.subcategories, (list, tuple)) or
                        len(context.subcategories) > self.MAX_HIERARCHY_DEPTH):
                    raise ValueError("Invalid or excessive classification hierarchy")
                parts = [domain] + [self._component(p) for p in context.subcategories]
                # Loose source files gain a useful language folder without
                # inventing a project name or rewriting explicit project paths.
                language = DeterministicMime.get_code_folder(context.extension,
                    getattr(context.metadata, "code_language", None))
                if parts == ["Projects", "Source"] and language:
                    parts.append(language)
                    evidence.append(EvidenceItem(SignalType.CODE_SYNTAX,
                        f"Source language: {language}", 0.0, "metadata.code_language"
                        if getattr(context.metadata, "code_language", None) else "extension"))
                if domain == "Others":
                    parts = [domain]
            relative = os.path.join(*parts, filename)
        target_root = root_abs
        if destination_routes is not None:
            target_root, relative, key = destination_routes.route(relative, is_rule=rule is not None)
            if key is not None:
                evidence.append(EvidenceItem(SignalType.DIRECTORY_CONTEXT,
                    f"Using Linux desktop {key.title()} folder", 0.0, "desktop.directories"))
        target_lexical = os.path.join(target_root, relative)
        root, target = self._validate_boundary(target_root, target_lexical)
        if destination_routes is not None:
            destination_routes.selected_root = root
        relative_target = os.path.relpath(target, root)
        proposal = OrganizationProposal(
            source_path=os.path.abspath(source), target_path=target, relative_target=relative_target,
            domain=domain, hierarchy_segments=relative_target.split(os.sep)[:-1],
            confidence_level=level, confidence_score=score, evidence=evidence,
            is_rule_override=rule is not None, rule_name=domain if rule is not None else "")
        context.proposed_destination = target
        return proposal
