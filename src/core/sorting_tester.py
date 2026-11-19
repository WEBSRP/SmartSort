"""Read-only sorting previews for hypothetical names or real files."""
import copy
import os
from dataclasses import dataclass
from types import SimpleNamespace

from src.core.file_intelligence import (
    FileContext, MultiSignalClassifier, OrganizationPlanner, OrganizationProposal,
    SignalExtractor,
)
from src.organizer import FileOrganizer
from src.utils.folder_guard import protected_folder_for
from src.utils.desktop_folders import DesktopDestinations
from src.rules.engine import RuleEngine, rules_for_mode


@dataclass
class SortingTestResult:
    proposal: OrganizationProposal
    mode: str
    source_kind: str
    rule_priority: int | None = None


class _QuietLogger:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def preview_sorting(settings, rules, *, file_path=None, filename=None, size_bytes=0):
    """Use saved routing policy; never execute a transfer or duplicate removal.

    Name-only tests classify filename/type signals, without creating a pretend
    file. Existing-file tests use the same bounded profiling and proposal path
    as an automatic download, including extraction/origin settings.
    """
    values = copy.deepcopy(settings)
    config = SimpleNamespace(get=lambda key, default=None: values.get(key, default))
    mode = config.get('sorting_mode', 'rules_first')
    if mode not in ('rules_first', 'intelligence'):
        raise ValueError('Unrecognized sorting mode')
    saved_rules = copy.deepcopy(rules)
    policy = SimpleNamespace(rules=rules_for_mode(saved_rules, mode))
    if file_path is not None:
        organizer = FileOrganizer(config, _QuietLogger())
        organizer.rule_manager = SimpleNamespace(rules=saved_rules)
        checked_path, _ = organizer._source_info(file_path)
        if (organizer._protected_download_folder(checked_path) or
                protected_folder_for(checked_path, os.path.dirname(checked_path))):
            raise ValueError('Application/project folder must remain intact')
        name = os.path.basename(os.fspath(file_path))
        override = (organizer.filename_cleanup.generate_clean_name(file_path)
                    if organizer.filename_cleanup.needs_cleanup(name) else None)
        proposal = organizer.analyze_download(file_path, override_filename=override)
        matched, _ = RuleEngine(policy.rules).evaluate_file(file_path)
        return SortingTestResult(proposal, mode, 'file', matched.priority if matched else None)

    name = OrganizationPlanner._component(filename)
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
        raise ValueError('File size must be a non-negative integer')
    stem, extension = os.path.splitext(name)
    # Pure synthetic context: no temporary file, xattrs, browser history or body
    # extraction. The path is used only for lexical rule matching.
    source = os.path.join(os.sep, '__smartsort_preview__', name)
    context = FileContext(source, name, stem, extension, '', size_bytes, 0, 0, 0, 0)
    SignalExtractor().extract_signals(context)
    MultiSignalClassifier(config).classify(context)
    root = os.path.expanduser(config.get('destination_base', '~'))
    planner = OrganizationPlanner(policy, config)
    proposal = planner.plan_file(context, root, destination_routes=DesktopDestinations(root, config))
    matched, _ = RuleEngine(policy.rules).evaluate_file(source, size_bytes)
    return SortingTestResult(proposal, mode, 'filename', matched.priority if matched else None)
