"""Native frontend regression checks, isolated from user files and services."""
import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractItemView, QDialog, QMessageBox, QScrollArea

from src.gui.main_window import SmartSortGUI, RuleDialog, DirectoryOrganizerWorker, EvidenceDialog, format_directory_review
from src.core.directory_organizer import OrganizePlan, OrganizePlanItem, DirectoryPreviewSummary, OrganizeResult, FileOperationRecord, OperationStatus
from src.gui.theme import DARK, LIGHT
from src.rules.rule import Rule
from src.utils.config import ConfigManager
from src.utils.logger import SmartSortLogger


@pytest.fixture
def gui(tmp_path, monkeypatch, qapp):
    import src.gui.main_window as window
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'data'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setattr(window, 'SmartSortLogger', lambda: SmartSortLogger(log_dir=str(tmp_path / 'logs')))
    monkeypatch.setattr(window.SmartSortGUI, 'init_notification_system', lambda self: setattr(self, 'notifications_enabled', False))
    monkeypatch.setattr(window.SmartSortGUI, 'get_service_status', lambda self: 'Not Installed')
    monkeypatch.setattr(window.QSystemTrayIcon, 'isSystemTrayAvailable', lambda: False)
    monkeypatch.setattr('src.utils.autostart.AutostartManager.is_autostart_enabled', lambda self: False)
    for name in ('information', 'critical', 'warning', 'question'):
        monkeypatch.setattr(QMessageBox, name, MagicMock(return_value=QMessageBox.StandardButton.Yes))
    widget = SmartSortGUI()
    widget.show()
    qapp.processEvents()
    yield widget
    widget.really_exit = True
    widget.status_timer.stop()
    widget.threadpool.waitForDone(10000)
    widget.tray_icon.hide()
    widget.close()
    widget.deleteLater()
    qapp.processEvents()


@pytest.mark.parametrize('theme,colors', [('light', LIGHT), ('dark', DARK)])
@pytest.mark.parametrize('page', range(6))
def test_all_pages_in_both_themes(gui, qapp, theme, colors, page):
    gui.change_theme(1 if theme == 'dark' else 2)
    gui.resize(860, 620)
    QTest.mouseClick(gui.nav_buttons[page], Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert gui.tabs.currentIndex() == page
    assert gui.nav_buttons[page].isChecked()
    assert gui.page_title.text() == gui.page_details[page][0]
    assert gui.palette().color(QPalette.ColorRole.Window).name() == colors['background']
    assert not gui.grab().isNull()
    # Scrolling pages contain all controls even at the minimum window size.
    for scroll in gui.tabs.currentWidget().findChildren(QScrollArea):
        assert scroll.widgetResizable()
        assert scroll.viewport().width() > 450
        assert scroll.horizontalScrollBar().maximum() == 0


def test_theme_switch_persists_and_synchronizes(gui, monkeypatch):
    gui.theme_picker.setCurrentIndex(1)
    assert gui.cmb_theme.currentIndex() == 1
    assert gui.config.get('theme') == 'dark'
    saved = ConfigManager(config_path=gui.config.config_path)
    assert saved.get('theme') == 'dark'
    gui.cmb_theme.setCurrentIndex(2)
    assert gui.theme_picker.currentIndex() == 2
    assert gui.config.get('theme') == 'light'
    monkeypatch.setattr(gui, 'is_system_dark_mode', lambda: True)
    gui.theme_picker.setCurrentIndex(0)
    assert gui.is_dark_theme
    monkeypatch.setattr(gui, 'is_system_dark_mode', lambda: False)
    gui.on_system_theme_changed(Qt.ColorScheme.Light)
    assert not gui.is_dark_theme
    gui.change_theme(1)
    gui.on_system_theme_changed(Qt.ColorScheme.Light)
    assert gui.is_dark_theme


def test_tray_shortcuts_follow_pages(gui):
    expected = {'Open Dashboard': gui.tab_dashboard, 'Open Rules': gui.tab_rules,
                'Open Rule Tester': gui.tab_tester, 'Open Settings': gui.tab_settings}
    for action in gui.tray_icon.contextMenu().actions():
        if action.text() in expected:
            action.trigger()
            assert gui.tabs.currentWidget() is expected[action.text()]
            assert gui.nav_buttons[gui.tabs.currentIndex()].isChecked()


def test_no_tray_close_does_not_hide_app(gui):
    assert not gui.tray_available
    gui.really_exit = False
    assert gui.close()
    assert gui.really_exit


def test_pause_resume_dashboard(gui):
    QTest.mouseClick(gui.btn_toggle_monitor, Qt.MouseButton.LeftButton)
    assert not gui.monitoring_active
    assert gui.lbl_monitoring_val.text() == 'Paused'
    assert gui.btn_toggle_monitor.text() == 'Resume monitoring'
    QTest.mouseClick(gui.btn_toggle_monitor, Qt.MouseButton.LeftButton)
    assert gui.monitoring_active
    assert gui.btn_toggle_monitor.text() == 'Pause monitoring'


def test_tables_are_read_only(gui):
    for table in (gui.table_logs, gui.table_rules):
        assert table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers


def test_folder_operation_locks_options_and_recovers(gui):
    gui._set_organizer_running_ui(True)
    controls = (gui.txt_target_dir, gui.chk_recursive, gui.chk_gen_report,
                gui.btn_preview, gui.btn_organize, gui.btn_browse_dir)
    assert all(not widget.isEnabled() for widget in controls)
    gui.on_dir_worker_error('Test error')
    assert all(widget.isEnabled() for widget in controls)
    assert gui.progress_organize.value() == 0
    assert not gui.btn_cancel_organize.isEnabled()


def test_rule_tester_and_activity_preserve_literal_text(gui):
    rule = Rule.from_dict({'id': 'literal', 'name': '<b>My rule</b>', 'priority': 1,
                          'enabled': True, 'conditions': [], 'destination': 'Docs/<draft>'})
    gui.organizer.rule_manager.rules = [rule]
    gui.run_rule_test()
    assert gui.lbl_test_match.text() == '<b>My rule</b>'
    assert gui.lbl_test_match.textFormat() == Qt.TextFormat.PlainText
    assert gui.lbl_test_dest.text().endswith('/Docs/<draft>/wallpaper.jpg')
    gui.on_worker_finished('/tmp/<img src=x>.txt', 'SKIPPED', '<draft>')
    assert '<img src=x>.txt' in gui.log_display.toPlainText()


def test_rule_dialog_validation_save_and_edit(gui):
    dialog = RuleDialog(gui, existing_priorities={1, 2})
    dialog.save_clicked()
    QMessageBox.critical.assert_called()
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.txt_name.setText('Reports')
    dialog.txt_dest.setText('Documents/{extension}')
    dialog.chk_cond_ext.setChecked(True)
    dialog.txt_cond_ext.setText('.pdf, .txt')
    dialog.save_clicked()
    assert dialog.result() == QDialog.DialogCode.Accepted
    rule = dialog.result_rule
    assert rule.priority == 3
    edit = RuleDialog(gui, rule=rule, existing_priorities={1, 2, 3})
    assert edit.txt_name.text() == 'Reports'
    edit.txt_name.setText('Work reports')
    edit.save_clicked()
    assert edit.result_rule.id == rule.id
    assert edit.result_rule.name == 'Work reports'
    dialog.close()
    edit.close()


def test_rule_toggle_reorder_and_delete(gui):
    gui.table_rules.selectRow(1)
    rule_id = gui.get_selected_rule_id()
    gui.disable_rule_clicked()
    assert not next(r for r in gui.organizer.rule_manager.rules if r.id == rule_id).enabled
    gui.enable_rule_clicked()
    assert next(r for r in gui.organizer.rule_manager.rules if r.id == rule_id).enabled
    gui.move_rule_up()
    assert gui.organizer.rule_manager.rules[0].id == rule_id
    gui.move_rule_down()
    assert gui.organizer.rule_manager.rules[1].id == rule_id
    gui.delete_rule_clicked()
    assert all(r.id != rule_id for r in gui.organizer.rule_manager.rules)


def test_invalid_settings_do_not_save(gui):
    before = gui.config.config_path.read_text()
    gui.txt_thresh.setText('invalid')
    gui.save_settings()
    assert gui.config.config_path.read_text() == before
    QMessageBox.critical.assert_called()


def test_settings_save(gui):
    gui.txt_thresh.setText('512MB')
    gui.chk_notif.setChecked(False)
    gui.chk_dup.setChecked(False)
    gui.chk_smart_cleanup.setChecked(True)
    gui.cmb_conflict.setCurrentText('skip')
    gui.save_settings()
    saved = json.loads(gui.config.config_path.read_text())
    assert saved['large_file_threshold_gb'] == 512 * 1024**2
    assert saved['enable_notifications'] is False
    assert saved['enable_duplicate_detection'] is False
    assert saved['smart_filename_cleanup'] is True
    assert saved['conflict_resolution'] == 'skip'
    assert gui.organizer.filename_cleanup.enabled


def test_about_dialog_has_current_version(gui, monkeypatch):
    from src.version import VERSION
    shown = []
    monkeypatch.setattr(QMessageBox, 'exec', lambda box: shown.append(box.text()))
    gui.show_about_dialog()
    assert f'Version {VERSION}' in shown[0]


def test_notification_is_shown_once(gui, monkeypatch):
    import sys
    backend = MagicMock()
    monkeypatch.setitem(sys.modules, 'notify2', backend)
    gui.notifications_enabled = True
    gui.show_notification('Title', 'Body')
    backend.Notification.assert_called_once_with('Title', 'Body')
    backend.Notification.return_value.show.assert_called_once()


def test_service_poll_runs_off_ui_thread(gui, qapp):
    release = threading.Event()
    started = threading.Event()
    threads = []
    def slow_query():
        threads.append(threading.current_thread())
        started.set()
        release.wait(2)
        return 'Not Installed'
    gui.get_service_status = slow_query
    try:
        gui.refresh_dashboard()
        assert started.wait(1)
        assert threads[0] is not threading.main_thread()
        gui.change_theme(1)
        assert gui.is_dark_theme
        assert gui._service_worker is not None
    finally:
        release.set()
        gui.threadpool.waitForDone(3000)
        qapp.processEvents()
    assert gui.lbl_service_val.text() == 'Not Installed'
    assert gui._service_worker is None


def test_log_refresh_clears_missing_files(gui):
    gui.table_logs.setRowCount(2)
    for path in Path(gui.logger.log_dir).glob('*.log'):
        path.unlink()
    gui.refresh_logs()
    assert gui.table_logs.rowCount() == 0


def test_folder_preview_via_ui_preserves_sources(gui, tmp_path, qapp):
    folder = tmp_path / 'inbox'
    folder.mkdir()
    source = folder / 'report.pdf'
    source.write_bytes(b'untouched preview content')
    gui.tabs.setCurrentWidget(gui.tab_organizer)
    gui.txt_target_dir.setText(str(folder))
    QTest.mouseClick(gui.btn_preview, Qt.MouseButton.LeftButton)
    for _ in range(150):
        qapp.processEvents()
        if gui.active_dir_worker is None:
            break
        QTest.qWait(20)
    assert gui.active_dir_worker is None
    assert 'Preview Complete' in gui.lbl_organize_status.text()
    assert 'report.pdf' in gui.txt_organize_summary.toPlainText()
    assert source.read_bytes() == b'untouched preview content'
    assert gui.btn_preview.isEnabled()


def test_preview_cancel_is_honored(gui):
    organizer = MagicMock()
    worker = DirectoryOrganizerWorker(organizer, '/tmp', mode='preview')
    finished = []
    worker.signals.finished.connect(lambda result, _: finished.append(result))
    worker.cancel()
    worker.run()
    assert finished[0].cancelled
    organizer.preview.assert_not_called()


def test_changed_folder_clears_previous_report(gui, tmp_path):
    gui.last_report_path = '/previous/report.md'
    gui.btn_open_arrangement_md.setEnabled(True)
    gui.txt_target_dir.setText(str(tmp_path))
    assert not gui.last_report_path
    assert not gui.btn_open_arrangement_md.isEnabled()


def test_new_download_folder_restarts_watcher(gui, tmp_path):
    folder = tmp_path / 'downloads'
    folder.mkdir()
    gui.txt_downloads.setText(str(folder))
    old_monitor = MagicMock()
    old_monitor.wait.return_value = True
    gui.monitor_thread = old_monitor
    gui.start_monitor = MagicMock()
    gui.save_settings()
    old_monitor.stop.assert_called_once()
    old_monitor.wait.assert_called_once_with(2000)
    gui.start_monitor.assert_called_once()
    assert gui.config.get('downloads_folder') == str(folder)


def test_invalid_download_folder_does_not_save(gui, tmp_path):
    before = gui.config.config_path.read_text()
    gui.txt_downloads.setText(str(tmp_path / 'missing'))
    gui.save_settings()
    assert gui.config.config_path.read_text() == before
    QMessageBox.critical.assert_called()


def reviewed_plan(gui, root, items=None, warnings=None):
    root.mkdir(exist_ok=True)
    gui.txt_target_dir.setText(str(root))
    if items is None:
        items = [OrganizePlanItem(str(root / 'Lecture_DBMS.md'), str(root / 'College/DBMS/Lectures/Lecture_DBMS.md'),
            'College', 'Intelligence', 'PROBABLE', ['Filename supports College', 'Title supports DBMS'],
            .74, 'cluster-demo', 'DBMS_Lectures')]
    plan = OrganizePlan(items, str(root), len(items), {'College': len(items)} if items else {},
                        1 if items else 0, list(warnings or []))
    worker = DirectoryOrganizerWorker(gui.dir_organizer, str(root), mode='preview',
                                      plan=plan, review_key=gui._directory_review_key())
    gui.active_dir_worker = worker
    gui.on_dir_worker_preview_ready(DirectoryPreviewSummary(plan.total_files, plan.category_counts,
        list(plan.items), plan.cluster_count, list(plan.warnings)))
    return plan


def test_rich_preview_shows_confidence_clusters_warnings_and_literal_evidence(gui, tmp_path):
    item = OrganizePlanItem(str(tmp_path / '<img src=x>.md'), str(tmp_path / 'College/DBMS/<draft>.md'),
        'College', 'Intelligence', 'UNCERTAIN', ['Title <b>literal</b>', 'A\nforged row'], .44, 'id', 'DBMS')
    reviewed_plan(gui, tmp_path, [item], ['One file excluded'])
    text = gui.txt_organize_summary.toPlainText()
    assert 'Planned moves: 1' in text and 'Clusters discovered: 1' in text
    assert '[UNCERTAIN (44%)]' in text and 'Cluster: DBMS' in text
    assert 'Title <b>literal</b>' in text and r'A\x0aforged row' in text
    assert 'One file excluded' in text and '<img src=x>.md' in text
    assert gui.btn_inspect_evidence.isEnabled() and gui._reviewed_plan is not None


def test_every_move_is_visible_and_full_evidence_is_inspectable(gui, tmp_path):
    items = [OrganizePlanItem(str(tmp_path / f'item_{i}.md'), str(tmp_path / f'Others/item_{i}.md'),
             'Others', 'Intelligence', 'UNKNOWN', [f'reason {j}' for j in range(20)], 0) for i in range(75)]
    reviewed_plan(gui, tmp_path, items)
    text = gui.txt_organize_summary.toPlainText()
    assert 'item_74.md' in text and '12 further reasons' in text
    dialog = EvidenceDialog(items[-1], gui)
    assert 'reason 19' in dialog.details.toPlainText() and dialog.details.isReadOnly()
    dialog.close()


def test_inspection_opens_selected_file_without_side_effects(gui, tmp_path, monkeypatch):
    reviewed_plan(gui, tmp_path)
    shown = []
    monkeypatch.setattr(EvidenceDialog, 'exec', lambda dialog: shown.append(dialog.details.toPlainText()))
    QTest.mouseClick(gui.btn_inspect_evidence, Qt.MouseButton.LeftButton)
    assert 'Lecture_DBMS.md' in shown[0] and 'Filename supports College' in shown[0]
    assert not (tmp_path / 'College').exists()


def test_organize_without_review_only_previews(gui, tmp_path, monkeypatch):
    gui.txt_target_dir.setText(str(tmp_path))
    preview = MagicMock();monkeypatch.setattr(gui, 'on_preview_dir', preview)
    start = MagicMock();monkeypatch.setattr(gui.threadpool, 'start', start)
    gui.on_organize_dir()
    preview.assert_called_once();start.assert_not_called()


def test_declining_review_does_not_schedule_transfers(gui, tmp_path, monkeypatch):
    reviewed_plan(gui, tmp_path)
    monkeypatch.setattr(QMessageBox, 'exec', lambda box: QMessageBox.StandardButton.No)
    start = MagicMock();monkeypatch.setattr(gui.threadpool, 'start', start)
    gui.on_organize_dir()
    start.assert_not_called()
    assert gui._reviewed_plan is not None


def test_confirmation_is_plain_text_and_executes_a_frozen_review(gui, tmp_path, monkeypatch):
    original = reviewed_plan(gui, tmp_path, warnings=['Skipped source'])
    inspected = []
    def confirm(box):
        inspected.append((box.text(), box.textFormat(), box.defaultButton().text()))
        return QMessageBox.StandardButton.Yes
    monkeypatch.setattr(QMessageBox, 'exec', confirm)
    pending = [];monkeypatch.setattr(gui.threadpool, 'start', pending.append)
    gui.on_organize_dir()
    worker = pending[0]
    assert 'exactly 1 reviewed' in inspected[0][0] and 'Planning warnings: 1' in inspected[0][0]
    assert inspected[0][1] is Qt.TextFormat.PlainText and 'No' in inspected[0][2]
    assert worker.review_plan == original and worker.review_plan is not original
    original.items.clear()
    assert len(worker.review_plan.items) == 1 and gui._reviewed_plan is None
    assert not gui.btn_organize.isEnabled()
    gui.on_dir_worker_finished(OrganizeResult([], cancelled=True), '')


@pytest.mark.parametrize('change', ['root', 'recursive', 'report', 'rules', 'settings'])
def test_review_is_invalidated_by_routing_or_selection_changes(gui, tmp_path, change):
    reviewed_plan(gui, tmp_path)
    if change == 'root':
        folder = tmp_path / 'other';folder.mkdir();gui.txt_target_dir.setText(str(folder))
    elif change == 'recursive':gui.chk_recursive.setChecked(not gui.chk_recursive.isChecked())
    elif change == 'report':gui.chk_gen_report.setChecked(not gui.chk_gen_report.isChecked())
    elif change == 'rules':gui.refresh_rules_table()
    else:gui.save_settings()
    assert gui._reviewed_plan is None and not gui.btn_inspect_evidence.isEnabled()


def test_late_preview_after_policy_change_is_not_executable(gui, tmp_path):
    plan = reviewed_plan(gui, tmp_path)
    worker = DirectoryOrganizerWorker(gui.dir_organizer, str(tmp_path), mode='preview',
                                      plan=plan, review_key=gui._directory_review_key())
    gui.active_dir_worker = worker
    gui.config.set('enable_origin_detection', not gui.config.get('enable_origin_detection'))
    gui.on_dir_worker_preview_ready(DirectoryPreviewSummary(1, {'College': 1}, plan.items, 1))
    assert gui._reviewed_plan is None and 'preview again' in gui.lbl_organize_details.text()


def test_mutated_summary_cannot_authorize_a_different_execution_snapshot(gui, tmp_path):
    plan = reviewed_plan(gui, tmp_path)
    worker = DirectoryOrganizerWorker(gui.dir_organizer, str(tmp_path), mode='preview',
                                      plan=plan, review_key=gui._directory_review_key())
    gui.active_dir_worker = worker
    item = OrganizePlanItem(str(tmp_path / 'other.md'), str(tmp_path / 'Other/other.md'), 'Other', 'Rule')
    gui.on_dir_worker_preview_ready(DirectoryPreviewSummary(1, {'College': 1}, [item], 1))
    assert gui._reviewed_plan is None


def test_queued_preview_arriving_after_cancel_does_not_create_a_review(gui, tmp_path):
    plan = reviewed_plan(gui, tmp_path)
    worker = DirectoryOrganizerWorker(gui.dir_organizer, str(tmp_path), mode='preview',
                                      plan=plan, review_key=gui._directory_review_key())
    gui.active_dir_worker = worker
    worker.cancel()
    gui.on_dir_worker_preview_ready(DirectoryPreviewSummary(1, {'College': 1}, plan.items, 1))
    assert gui._reviewed_plan is None and 'Cancelled' in gui.lbl_organize_status.text()


def test_settings_changed_during_confirmation_stop_execution(gui, tmp_path, monkeypatch):
    reviewed_plan(gui, tmp_path)
    def confirm(box):
        gui.config.set('conflict_resolution', 'overwrite')
        return QMessageBox.StandardButton.Yes
    monkeypatch.setattr(QMessageBox, 'exec', confirm)
    start = MagicMock();monkeypatch.setattr(gui.threadpool, 'start', start)
    gui.on_organize_dir()
    start.assert_not_called();assert gui._reviewed_plan is None


def test_review_worker_executes_exact_subset_without_rescan_or_replanning(gui, tmp_path, monkeypatch):
    source = tmp_path / 'one.md';source.write_text('one')
    new_file = tmp_path / 'unreviewed.md';new_file.write_text('leave')
    gui.dir_organizer.rule_manager.rules = [Rule.from_dict({'name': 'Pinned', 'priority': 1, 'conditions': [], 'destination': 'Pinned'})]
    plan = gui.dir_organizer.plan(str(tmp_path), [str(source)])
    worker = DirectoryOrganizerWorker(gui.dir_organizer, str(tmp_path), plan=plan, generate_report=False)
    monkeypatch.setattr(gui.dir_organizer, 'scan', lambda *a, **k: pytest.fail('unreviewed rescan'))
    monkeypatch.setattr(gui.dir_organizer, 'plan', lambda *a: pytest.fail('unreviewed replan'))
    results = [];worker.signals.finished.connect(lambda result, _: results.append(result))
    worker.run()
    assert results[0].success_count == 1 and new_file.read_text() == 'leave'
    assert not source.exists() and (tmp_path / 'Pinned/one.md').read_text() == 'one'


def test_review_worker_uses_approved_collision_policy_after_settings_change(gui, tmp_path):
    source = tmp_path / 'one.md';source.write_text('new')
    target = tmp_path / 'Pinned/one.md';target.parent.mkdir();target.write_text('old')
    gui.dir_organizer.rule_manager.rules = [Rule.from_dict({'name': 'Pinned', 'priority': 1, 'conditions': [], 'destination': 'Pinned'})]
    plan = gui.dir_organizer.plan(str(tmp_path), [str(source)])
    worker = DirectoryOrganizerWorker(gui.dir_organizer, str(tmp_path), plan=plan, generate_report=False,
        execution_options={'conflict_resolution': 'skip', 'enable_duplicate_detection': True})
    gui.config.set('conflict_resolution', 'overwrite')
    results = [];worker.signals.finished.connect(lambda result, _: results.append(result))
    worker.run()
    assert results[0].skip_count == 1 and target.read_text() == 'old' and source.exists()


def test_review_worker_rejects_changed_source_without_deleting_it(gui, tmp_path):
    source = tmp_path / 'one.md';source.write_text('old')
    gui.dir_organizer.rule_manager.rules = [Rule.from_dict({'name': 'Pinned', 'priority': 1, 'conditions': [], 'destination': 'Pinned'})]
    plan = gui.dir_organizer.plan(str(tmp_path), [str(source)])
    source.write_text('changed since review')
    worker = DirectoryOrganizerWorker(gui.dir_organizer, str(tmp_path), plan=plan, generate_report=False)
    results = [];worker.signals.finished.connect(lambda result, _: results.append(result))
    worker.run()
    assert results[0].error_count == 1 and source.read_text() == 'changed since review'


def test_execution_results_keep_actual_paths_and_planning_warnings(gui, tmp_path):
    plan = reviewed_plan(gui, tmp_path, warnings=['Excluded source'])
    gui._executing_review = plan
    record = FileOperationRecord(plan.items[0].source_path, str(tmp_path / 'College/renamed_1.md'),
                                  'College', 'Intelligence', OperationStatus.COLLISION_RESOLVED)
    gui.on_dir_worker_finished(OrganizeResult([record], collision_count=1), '')
    text = gui.txt_organize_summary.toPlainText()
    assert 'renamed_1.md' in text and '[PROBABLE (74%)]' in text and 'Excluded source' in text
    assert gui._reviewed_plan is None and not gui.btn_open_arrangement_md.isEnabled()


def test_intelligence_settings_save_reload_and_validate(gui):
    gui.chk_origin_detection.setChecked(False)
    gui.chk_deep_content.setChecked(False)
    gui.save_settings()
    loaded = ConfigManager(config_path=gui.config.config_path)
    assert loaded.get('enable_origin_detection') is False
    assert loaded.get('enable_deep_content_extraction') is False
    with pytest.raises(ValueError):loaded.set('enable_deep_content_extraction', 'yes')


@pytest.mark.parametrize('download', [False, True])
def test_deep_content_toggle_controls_both_organizers(gui, tmp_path, monkeypatch, download):
    source = tmp_path / 'opaque.md';source.write_text('# Invoice\nFinance invoice')
    gui.config.set('enable_origin_detection', False)
    gui.config.set('enable_deep_content_extraction', False)
    instance = gui.organizer if download else gui.dir_organizer
    instance.rule_manager.rules = []
    monkeypatch.setattr(instance.extractor_registry, 'extract_metadata', lambda *a, **k: pytest.fail('deep extraction disabled'))
    if download:
        proposal = instance.analyze_download(str(source));assert proposal.domain == 'Documents'
    else:
        plan = instance.plan(str(tmp_path), [str(source)]);assert plan.items[0].category == 'Documents'
    assert source.exists()


@pytest.mark.parametrize('theme', [1, 2])
def test_evidence_review_and_settings_remain_usable_at_minimum_size(gui, tmp_path, qapp, theme):
    gui.change_theme(theme);gui.resize(860, 620)
    reviewed_plan(gui, tmp_path)
    gui.tabs.setCurrentWidget(gui.tab_organizer);qapp.processEvents()
    assert not gui.grab().isNull() and gui.cmb_review_file.count() == 1
    for page in (gui.tab_organizer, gui.tab_settings):
        gui.tabs.setCurrentWidget(page);qapp.processEvents()
        for scroll in page.findChildren(QScrollArea):assert scroll.horizontalScrollBar().maximum() == 0


def test_sorting_mode_save_preserves_rules_and_shows_current_policy(gui):
    import copy
    rules = copy.deepcopy(gui.config.get('rules'))
    assert gui.cmb_sorting_mode.currentData() == 'rules_first'
    assert all('Rules first' in label.text() for label in gui._sorting_mode_labels)
    gui.cmb_sorting_mode.setCurrentIndex(gui.cmb_sorting_mode.findData('intelligence'))
    assert gui.config.get('sorting_mode') == 'rules_first'
    assert 'not applied' in gui.lbl_sorting_mode_help.text()
    gui.save_settings()
    loaded = ConfigManager(config_path=gui.config.config_path)
    assert loaded.get('sorting_mode') == 'intelligence'
    assert loaded.get('rules') == rules
    assert all('Content intelligence' in label.text() for label in gui._sorting_mode_labels)
    assert gui.lbl_rules_val.text() == 'Not applied'
    assert 'Restart button' in QMessageBox.information.call_args[0][2]
    assert gui.organizer.config.get('sorting_mode') == gui.dir_organizer.config.get('sorting_mode') == 'intelligence'


def test_sorting_mode_change_invalidates_review(gui, tmp_path):
    reviewed_plan(gui, tmp_path)
    old_key = gui._review_key
    gui.cmb_sorting_mode.setCurrentIndex(gui.cmb_sorting_mode.findData('intelligence'))
    gui.save_settings()
    assert gui._directory_review_key() != old_key
    assert gui._reviewed_plan is None
    assert not gui.btn_inspect_evidence.isEnabled()


def test_gui_saved_intelligence_mode_changes_real_destination(gui, tmp_path):
    source = tmp_path / 'Lecture_DBMS.md'
    source.write_text('# DBMS Lecture\nDatabase course lecture notes and normalization')
    gui.config.set('enable_origin_detection', False)
    previous = gui.dir_organizer.plan(str(tmp_path), [str(source)])
    assert previous.items[0].target_path == str(tmp_path / 'Documents/College/Lecture_DBMS.md')
    gui.cmb_sorting_mode.setCurrentIndex(gui.cmb_sorting_mode.findData('intelligence'))
    gui.save_settings()
    changed = gui.dir_organizer.plan(str(tmp_path), [str(source)])
    assert changed.items[0].target_path == str(tmp_path / 'College/DBMS/Lectures/Lecture_DBMS.md')
    assert changed.items[0].rule_name == 'Intelligence'
    assert source.exists()


def test_queued_preview_keeps_selected_mode_and_rules(gui, tmp_path):
    source = tmp_path / 'Lecture_DBMS.md'
    source.write_text('# DBMS Lecture\nDatabase course lecture notes')
    worker = DirectoryOrganizerWorker(gui.dir_organizer, str(tmp_path), mode='preview')
    summaries = []
    worker.signals.preview_ready.connect(summaries.append)
    gui.config.set('sorting_mode', 'intelligence')
    gui.dir_organizer.rule_manager.rules.clear()
    worker.run()
    assert len(summaries) == 1
    assert summaries[0].items[0].target_path == str(tmp_path / 'Documents/College/Lecture_DBMS.md')
    assert source.exists()


def test_change_mode_shortcut_opens_setting(gui, qapp):
    gui._open_sorting_mode_settings()
    qapp.processEvents()
    assert gui.tabs.currentWidget() is gui.tab_settings
    assert gui.cmb_sorting_mode.isVisible()


def test_intelligence_recursion_default_and_per_mode_preferences(gui):
 assert not gui.chk_recursive.isChecked()
 gui.cmb_sorting_mode.setCurrentIndex(gui.cmb_sorting_mode.findData('intelligence'))
 gui.save_settings()
 assert gui.chk_recursive.isChecked() and gui.chk_downloads_recursive.isEnabled()
 gui.chk_recursive.setChecked(False)
 assert gui.config.get('intelligence_recursive') is False
 gui.cmb_sorting_mode.setCurrentIndex(gui.cmb_sorting_mode.findData('rules_first'))
 gui.save_settings()
 gui.chk_recursive.setChecked(True)
 assert gui.config.get('dir_organizer_recursive') is True
 gui.cmb_sorting_mode.setCurrentIndex(gui.cmb_sorting_mode.findData('intelligence'))
 gui.save_settings()
 assert not gui.chk_recursive.isChecked()


def test_download_recursion_save_restarts_monitor_and_keeps_folder_preference(gui,monkeypatch):
 from types import SimpleNamespace
 gui.cmb_sorting_mode.setCurrentIndex(gui.cmb_sorting_mode.findData('intelligence'));gui.save_settings()
 calls=[]
 gui.monitor_thread=SimpleNamespace(stop=lambda:calls.append('stop'),wait=lambda timeout:True)
 monkeypatch.setattr(gui,'start_monitor',lambda:calls.append('start'))
 gui.chk_downloads_recursive.setChecked(False);gui.save_settings()
 assert calls==['stop','start']
 assert gui.config.get('downloads_recursive') is False and gui.chk_recursive.isChecked()
 gui.monitor_thread=SimpleNamespace(stop=lambda:None,wait=lambda timeout:True)


def test_filename_tester_uses_selected_intelligence_mode(gui):
 gui.config.set('sorting_mode','intelligence')
 gui.organizer.rule_manager.rules=[Rule.from_dict(dict(id='pin',name='Pinned',enabled=True,priority=1,conditions=[],destination='Pinned'))]
 gui.txt_test_filename.setText('4739201.mp4')
 gui.run_rule_test()
 assert gui.lbl_test_dest.text().endswith('/Videos/4739201.mp4')
 assert 'UNKNOWN' in gui.lbl_test_confidence.text() and 'fallback' in gui.txt_test_evidence.toPlainText()
 assert 'not inspected' in gui.lbl_test_scope.text()


def test_existing_file_tester_analyzes_content_in_worker_without_moving(gui,tmp_path,qapp):
 import time
 source=tmp_path/'opaque.md';source.write_text('# Invoice\nFinance billing invoice')
 gui.config.set('sorting_mode','intelligence');gui.config.set('enable_origin_detection',False)
 gui.cmb_test_source.setCurrentIndex(1);gui.txt_test_path.setText(str(source));gui.run_rule_test()
 assert gui._tester_worker is not None and not gui.btn_test_sorting.isEnabled()
 deadline=time.monotonic()+8
 while gui._tester_worker is not None and time.monotonic()<deadline:QTest.qWait(20)
 assert gui._tester_worker is None and gui.btn_test_sorting.isEnabled()
 assert gui.lbl_test_dest.text().endswith('/Work/Invoices/opaque.md')
 assert 'invoice' in gui.txt_test_evidence.toPlainText().lower() and source.exists()
 assert 'no files moved' in gui.lbl_test_scope.text()


def test_tester_ignores_result_after_inputs_change(gui,tmp_path,monkeypatch):
 source=tmp_path/'opaque.md';source.write_text('# Invoice\nFinance billing invoice')
 gui.config.set('sorting_mode','intelligence');gui.config.set('enable_origin_detection',False)
 pending=[];monkeypatch.setattr(gui.threadpool,'start',pending.append)
 gui.cmb_test_source.setCurrentIndex(1);gui.txt_test_path.setText(str(source));gui.run_rule_test()
 worker=pending[0]
 gui.txt_test_path.setText(str(tmp_path/'different.md'))
 worker.run()
 assert gui.lbl_test_dest.text()=='N/A' and gui.btn_test_sorting.isEnabled() and gui._tester_worker is None


def test_tester_settings_changes_invalidate_previous_preview(gui):
 gui.run_rule_test();assert gui.lbl_test_dest.text()!='N/A'
 gui.cmb_sorting_mode.setCurrentIndex(gui.cmb_sorting_mode.findData('intelligence'));gui.save_settings()
 assert gui.lbl_test_dest.text()=='N/A'


def test_tester_worker_errors_clear_results_and_reenable_button(gui,tmp_path,qapp):
 import time
 gui.cmb_test_source.setCurrentIndex(1);gui.txt_test_path.setText(str(tmp_path/'missing.pdf'));gui.run_rule_test()
 deadline=time.monotonic()+8
 while gui._tester_worker is not None and time.monotonic()<deadline:QTest.qWait(20)
 assert gui.lbl_test_dest.text()=='N/A' and gui.btn_test_sorting.isEnabled()
 assert 'Unable to analyze' in gui.lbl_test_match.text() and gui.txt_test_evidence.toPlainText()


def test_tester_worker_keeps_snapshot_and_survives_theme_change(gui,tmp_path,monkeypatch):
 source=tmp_path/'opaque.md';source.write_text('# Invoice\nFinance billing invoice')
 gui.config.set('sorting_mode','intelligence');gui.config.set('enable_origin_detection',False)
 pending=[];monkeypatch.setattr(gui.threadpool,'start',pending.append)
 gui.cmb_test_source.setCurrentIndex(1);gui.txt_test_path.setText(str(source));gui.run_rule_test()
 gui.change_theme(1)
 pending[0].run()
 assert gui.lbl_test_dest.text().endswith('/Work/Invoices/opaque.md') and gui.btn_test_sorting.isEnabled()


def test_tester_discards_queued_result_after_rules_change(gui,tmp_path,monkeypatch):
 source=tmp_path/'opaque.md';source.write_text('# Invoice\nFinance billing invoice')
 gui.config.set('sorting_mode','rules_first');gui.config.set('enable_origin_detection',False)
 pending=[];monkeypatch.setattr(gui.threadpool,'start',pending.append)
 gui.cmb_test_source.setCurrentIndex(1);gui.txt_test_path.setText(str(source));gui.run_rule_test()
 worker=pending[0]
 gui.organizer.rule_manager.rules=[Rule.from_dict(dict(id='new',name='New',enabled=True,priority=1,conditions=[],destination='New'))]
 worker.run()
 assert gui.lbl_test_dest.text()=='N/A' and gui._tester_worker is None and gui.btn_test_sorting.isEnabled()


@pytest.mark.parametrize('filename,extension,ending',[('4739201.mp4','.jpg','Videos/4739201.mp4'),('4739201','.mp4','Videos/4739201.mp4')])
def test_tester_optional_extension_does_not_override_real_filename_suffix(gui,filename,extension,ending):
 gui.config.set('sorting_mode','intelligence')
 gui.txt_test_filename.setText(filename);gui.txt_test_ext.setText(extension);gui.run_rule_test()
 assert gui.lbl_test_dest.text().endswith('/'+ending)


def test_shell_filename_preview_shows_language_without_zero_type_confidence(gui):
 gui.config.set('sorting_mode','intelligence')
 gui.txt_test_filename.setText('fix_click.sh');gui.txt_test_size.setText('5MB');gui.txt_test_ext.setText('.sh')
 gui.run_rule_test()
 assert gui.lbl_test_dest.text().endswith('/Code/Shell/fix_click.sh')
 assert 'File type recognized' in gui.lbl_test_confidence.text() and '0%' not in gui.lbl_test_confidence.text()
 assert 'not inspected' in gui.lbl_test_scope.text()


def test_desktop_folder_preference_is_visible_saved_and_invalidates_tester(gui):
 assert gui.chk_desktop_folders.isChecked()
 assert 'Pictures:' in gui.lbl_desktop_folders.text() and 'Music:' in gui.lbl_desktop_folders.text()
 gui.run_rule_test();assert gui.lbl_test_dest.text()!='N/A'
 gui.chk_desktop_folders.setChecked(False);gui.save_settings()
 assert gui.config.get('use_desktop_folders') is False and gui.lbl_test_dest.text()=='N/A'


def test_rule_editor_can_teach_content_intelligence(gui):
 dialog=RuleDialog(gui,existing_priorities=set())
 assert dialog.chk_intelligence_rule.isChecked()
 dialog.txt_name.setText('My wallpapers');dialog.txt_dest.setText('Pictures/My Wallpapers');dialog.chk_cond_fn.setChecked(True);dialog.txt_cond_fn.setText('my_wallpaper')
 dialog.save_clicked();rule=dialog.result_rule
 assert rule.apply_in_intelligence and rule.to_dict()['apply_in_intelligence'] is True
 edited=RuleDialog(gui,rule=rule,existing_priorities={rule.priority})
 assert edited.chk_intelligence_rule.isChecked()
 gui.config.set('sorting_mode','intelligence');gui.organizer.rule_manager.rules=[rule]
 gui.txt_test_filename.setText('my_wallpaper.png');gui.run_rule_test()
 assert gui.lbl_test_match.text()=='My wallpapers' and '/Pictures/My Wallpapers/' in gui.lbl_test_dest.text()


@pytest.mark.parametrize("action", ["popup", "page", "expire"])
def test_folder_reverse_offer(gui, qapp, tmp_path, action):
    src, dst = tmp_path / "hello.txt", tmp_path / "sorted/hello.txt"
    src.write_text("hello")
    plan = OrganizePlan([OrganizePlanItem(str(src), str(dst), "Docs", "Rule")], str(tmp_path), 1, {})
    result = gui.dir_organizer.execute(plan, capture_undo=True)
    result.undo.complete()
    gui.on_dir_worker_finished(result, "")
    journal, button, popup, reverse = gui.undo_offers[0]
    assert popup.isVisible() and reverse.objectName() == "primary"
    if action == "popup":
        reverse.click()
    else:
        popup.close()
        assert button.isEnabled()
        if action == "expire":
            journal.deadline = 0
        button.click()
    gui.threadpool.waitForDone(5000)
    qapp.processEvents()
    assert not gui.undo_offers
    if action == "expire":
        assert dst.exists() and not src.exists()
    else:
        assert src.read_text() == "hello" and not dst.exists()
        assert "Restored 1" in gui.lbl_organize_details.text()
