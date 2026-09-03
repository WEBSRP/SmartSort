# SmartSort File Intelligence Engine: Download Organizer Integration

## 1. Overview & Real-Time Workflow

The **Download Organizer** processes individual files in **real-time** as they are written to the monitored Downloads directory (`~/Downloads`).

Because incoming downloads arrive one at a time, the download pipeline emphasizes **deep provenance detection** (recovering the download URL and referrer from local browser databases) and **content extraction** to establish context immediately.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ DOWNLOAD ORGANIZER REAL-TIME PIPELINE                                       │
│                                                                             │
│  [New File Detected in ~/Downloads]                                         │
│         │                                                                   │
│         ▼                                                                   │
│  1. Watchdog Event Debounce & (inode, device) Physical Identity Tracking    │
│         │                                                                   │
│         ▼                                                                   │
│  2. Smart Filename Cleanup (Evaluates generic/hash names)                   │
│         │                                                                   │
│         ▼                                                                   │
│  3. Origin Provenance Resolution                                            │
│     - Query browser SQLite history (`downloads` table in Chrome/Firefox)    │
│     - Read xattrs (`user.xdg.origin.url`)                                   │
│         │                                                                   │
│         ▼                                                                   │
│  4. Fast Content & Metadata Extraction                                      │
│     $\rightarrow$ Generates FileContext for incoming download               │
│         │                                                                   │
│         ▼                                                                   │
│  5. Multi-Signal Classification & Confidence Scoring                        │
│         │                                                                   │
│         ▼                                                                   │
│  6. Organization Planner Proposals                                          │
│     - User rules evaluated first; Intelligence hierarchy as fallback        │
│         │                                                                   │
│         ▼                                                                   │
│  7. Large Video / High-Risk Approval Check (if applicable)                  │
│         │                                                                   │
│         ▼                                                                   │
│  8. Safe 6-Stage Transfer Execution                                         │
│     - Unique collision renaming, duplicate preservation, SHA-256 verify     │
│         │                                                                   │
│         ▼                                                                   │
│  9. Interactive Notification Dispatch                                       │
│     - Displays category & opens destination via `FileManager1` DBus         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. `FileOrganizer` Class Refactoring

`FileOrganizer` in `src/organizer.py` is updated to delegate categorization to the File Intelligence Engine while preserving existing logging, notification, and large file approval flows:

```python
class FileOrganizer:
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
        # Intelligence Components
        self.extractor_registry = ExtractorRegistry()
        self.origin_detector = OriginDetector(config_manager)
        self.classifier = MultiSignalClassifier(config_manager)
        self.planner = OrganizationPlanner(self.rule_manager, config_manager)

    def analyze_download(self, file_path: str, override_filename: Optional[str] = None) -> OrganizationProposal:
        """Profiles an incoming download and generates an intelligent proposal."""
        # 1. Build FileContext
        ctx = FileContextBuilder.build(file_path)
        if override_filename:
            ctx.filename = override_filename

        # 2. Extract origin from browser DB / xattrs
        ctx.origin = self.origin_detector.detect_origin(file_path)

        # 3. Extract format metadata & text preview
        ctx.metadata = self.extractor_registry.extract_metadata(file_path)

        # 4. Classify domain & subcategories
        self.classifier.classify(ctx)

        # 5. Plan destination relative to destination_base
        base_dest = Path(self.config.get("destination_base", os.path.expanduser("~"))).expanduser().resolve()
        proposal = self.planner.plan_file(ctx, str(base_dest))
        return proposal
```

---

## 3. Real-Time Performance Guarantees

In daemon mode, file event handling must remain non-blocking:
1. **Extraction Timeout**: Hard 2.0-second timeout per download file.
2. **Bounded Buffer Read**: Max 64 KB text extracted.
3. **Thread Safety**: All extraction occurs inside the worker thread created by `MonitorThread`, ensuring the GUI and file watchdog observer never lag.
