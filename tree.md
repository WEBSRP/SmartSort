.
├── assets
│   └── icons
│       ├── hicolor
│       │   ├── 16x16
│       │   │   └── apps
│       │   │       ├── tray_blue.png
│       │   │       ├── tray_green.png
│       │   │       ├── tray_grey.png
│       │   │       ├── tray_orange.png
│       │   │       ├── tray_red.png
│       │   │       └── tray_yellow.png
│       │   ├── 22x22
│       │   │   └── apps
│       │   │       ├── tray_blue.png
│       │   │       ├── tray_green.png
│       │   │       ├── tray_grey.png
│       │   │       ├── tray_orange.png
│       │   │       ├── tray_red.png
│       │   │       └── tray_yellow.png
│       │   ├── 24x24
│       │   │   └── apps
│       │   │       ├── tray_blue.png
│       │   │       ├── tray_green.png
│       │   │       ├── tray_grey.png
│       │   │       ├── tray_orange.png
│       │   │       ├── tray_red.png
│       │   │       └── tray_yellow.png
│       │   ├── 32x32
│       │   │   └── apps
│       │   │       ├── tray_blue.png
│       │   │       ├── tray_green.png
│       │   │       ├── tray_grey.png
│       │   │       ├── tray_orange.png
│       │   │       ├── tray_red.png
│       │   │       └── tray_yellow.png
│       │   ├── icon-theme.cache
│       │   ├── index.theme
│       │   └── scalable
│       │       └── apps
│       │           ├── logo.png
│       │           ├── tray_blue.png
│       │           ├── tray_green.png
│       │           ├── tray_grey.png
│       │           ├── tray_orange.png
│       │           ├── tray_red.png
│       │           └── tray_yellow.png
│       ├── logo.png
│       ├── logo_square.png
│       ├── tray_blue_16x16.png
│       ├── tray_blue_22x22.png
│       ├── tray_blue_24x24.png
│       ├── tray_blue_32x32.png
│       ├── tray_blue.png
│       ├── tray_green_16x16.png
│       ├── tray_green_22x22.png
│       ├── tray_green_24x24.png
│       ├── tray_green_32x32.png
│       ├── tray_green.png
│       ├── tray_grey_16x16.png
│       ├── tray_grey_22x22.png
│       ├── tray_grey_24x24.png
│       ├── tray_grey_32x32.png
│       ├── tray_grey.png
│       ├── tray_orange_16x16.png
│       ├── tray_orange_22x22.png
│       ├── tray_orange_24x24.png
│       ├── tray_orange_32x32.png
│       ├── tray_orange.png
│       ├── tray_red_16x16.png
│       ├── tray_red_22x22.png
│       ├── tray_red_24x24.png
│       ├── tray_red_32x32.png
│       ├── tray_red.png
│       ├── tray_yellow_16x16.png
│       ├── tray_yellow_22x22.png
│       ├── tray_yellow_24x24.png
│       ├── tray_yellow_32x32.png
│       └── tray_yellow.png
├── build
│   ├── appimage
│   ├── deb
│   ├── flatpak
│   └── rpm
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md
├── config
│   └── config.default.json
├── CONTRIBUTING.md
├── docs
│   ├── architecture.md
│   ├── build.md
│   ├── configuration.md
│   ├── packaging.md
│   ├── release.md
│   └── rule_engine.md
├── LICENSE
├── logs
│   └── smartsort_20260725.log
├── main.py
├── packaging
│   ├── appimage
│   │   ├── appimagetool
│   │   ├── AppRun
│   │   └── build_appimage.sh
│   ├── debian
│   │   ├── build_deb.sh
│   │   ├── DEBIAN
│   │   │   ├── control
│   │   │   ├── postinst
│   │   │   ├── postrm
│   │   │   └── prerm
│   │   ├── smartsort.desktop
│   │   └── smartsort.service
│   ├── flatpak
│   │   ├── build_flatpak.sh
│   │   ├── com.smartsort.SmartSort.desktop
│   │   ├── com.smartsort.SmartSort.yml
│   │   ├── download_wheels.sh
│   │   ├── flatpak-pip-generator
│   │   ├── flatpak-pip-generator.py
│   │   ├── requirements_flatpak.txt
│   │   └── smartsort.sh
│   └── rpm
│       ├── build_rpm.sh
│       ├── smartsort.spec
│       └── SOURCES
├── __pycache__
│   └── main.cpython-313.pyc
├── pyproject.toml
├── README.md
├── reports
│   ├── appimage_build_report.md
│   ├── appimage_preparation_report.md
│   ├── appimage_validation_report.md
│   ├── appindicator_icon_resolution_report.md
│   ├── autostart_implementation_report.md
│   ├── background_startup_report.md
│   ├── build_system.md
│   ├── build_validation.md
│   ├── ci_cleanup_fix.md
│   ├── ci_fix_report.md
│   ├── ci_root_cause.md
│   ├── ci_shutdown_fix.md
│   ├── ci_shutdown_rootcause.md
│   ├── claude_audit.md
│   ├── config_initialization_fix_report.md
│   ├── config_migration_validation.md
│   ├── dark_theme_fix_report.md
│   ├── debian_packaging_report.md
│   ├── debian_postinst_fix_report.md
│   ├── debian_validation_report.md
│   ├── documentation_audit.md
│   ├── final_release_gate.md
│   ├── final_repository_validation.md
│   ├── flatpak_build_report.md
│   ├── flatpak_dependency_packaging_report.md
│   ├── flatpak_preparation_report.md
│   ├── flatpak_runtime_audit.md
│   ├── flatpak_validation_report.md
│   ├── github_actions.md
│   ├── git_hygiene.md
│   ├── gitignore_update.md
│   ├── handover.md
│   ├── handover_report.md
│   ├── icon_system_implementation_report.md
│   ├── logger_fix_report.md
│   ├── migration_notes.md
│   ├── package_capability_matrix.md
│   ├── path_management_fix_report.md
│   ├── path_manager_refactor.md
│   ├── path_portability_fix_report.md
│   ├── phase2_implementation_report.md
│   ├── phase4_background_service_report.md
│   ├── python_dependency_audit.md
│   ├── qt_lifecycle_audit.md
│   ├── readme_update_report.md
│   ├── release_candidate_audit.md
│   ├── release_readiness.md
│   ├── repository_audit.md
│   ├── repository_refactor.md
│   ├── resume.md
│   ├── rpm_packaging_report.md
│   ├── service_installation_report.md
│   ├── size_threshold_fix_report.md
│   ├── startup_automation_fix_report.md
│   ├── startup_manager_report.md
│   ├── test_results.md
│   ├── tray_compatibility_fix_report.md
│   ├── tray_icon_rendering_fix_report.md
│   ├── tray_icon_theme_fix_report.md
│   ├── tray_status_indicator_report.md
│   ├── ui_improvement_report.md
│   ├── ui_modernization_report.md
│   ├── v1_release_checklist.md
│   ├── v1_release_summary.md
│   ├── watchdog_event_stability_report.md
│   ├── xdg_config_migration.md
│   └── xdg_path_audit_report.md
├── requirements.txt
├── SECURITY.md
├── src
│   ├── gui
│   │   ├── main_window.py
│   │   ├── __pycache__
│   │   │   ├── main_window.cpython-313.pyc
│   │   │   └── tray_manager.cpython-313.pyc
│   │   └── tray_manager.py
│   ├── monitor.py
│   ├── organizer.py
│   ├── __pycache__
│   │   ├── monitor.cpython-313.pyc
│   │   └── organizer.cpython-313.pyc
│   ├── rules
│   │   ├── conditions.py
│   │   ├── engine.py
│   │   ├── manager.py
│   │   ├── __pycache__
│   │   │   ├── conditions.cpython-313.pyc
│   │   │   ├── engine.cpython-313.pyc
│   │   │   ├── manager.cpython-313.pyc
│   │   │   └── rule.cpython-313.pyc
│   │   └── rule.py
│   ├── utils
│   │   ├── autostart.py
│   │   ├── config.py
│   │   ├── file_utils.py
│   │   ├── logger.py
│   │   ├── packaging.py
│   │   ├── paths.py
│   │   └── __pycache__
│   │       ├── autostart.cpython-313.pyc
│   │       ├── config.cpython-313.pyc
│   │       ├── file_utils.cpython-313.pyc
│   │       ├── logger.cpython-313.pyc
│   │       ├── packaging.cpython-313.pyc
│   │       └── paths.cpython-313.pyc
│   └── version.py
├── test_logs
│   └── smartsort_20260725.log
├── tests
│   ├── conftest.py
│   ├── __pycache__
│   │   ├── conftest.cpython-313-pytest-8.2.2.pyc
│   │   └── test_core.cpython-313-pytest-8.2.2.pyc
│   └── test_core.py
└── tree.md

42 directories, 205 files
