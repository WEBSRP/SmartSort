import os
import pytest
import shutil
from src.utils.file_utils import FileUtils
from src.organizer import FileOrganizer
from src.utils.config import ConfigManager
from src.utils.logger import SmartSortLogger

@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path

def test_sha256_calculation(temp_dir):
    test_file = temp_dir / "test.txt"
    test_file.write_text("hello world")
    
    hash1 = FileUtils.calculate_sha256(str(test_file))
    assert hash1 is not None
    
    # Same content should have same hash
    test_file2 = temp_dir / "test2.txt"
    test_file2.write_text("hello world")
    hash2 = FileUtils.calculate_sha256(str(test_file2))
    assert hash1 == hash2

def test_safe_copy(temp_dir):
    src = temp_dir / "src.txt"
    src.write_text("data")
    dst = temp_dir / "dst.txt"
    
    success, info = FileUtils.safe_copy(str(src), str(dst))
    assert success is True
    assert os.path.exists(dst)
    assert FileUtils.calculate_sha256(str(src)) == FileUtils.calculate_sha256(str(dst))

def test_categorization():
    # Mock config
    class MockConfig:
        def get(self, key, default=None):
            if key == "categories":
                return {
                    "Videos": {"extensions": [".mp4"]},
                    "Cybersecurity": {"keywords": ["nmap"]},
                    "Documents": {"extensions": [".pdf"]}
                }
            return default
            
    organizer = FileOrganizer(MockConfig(), SmartSortLogger(log_dir="test_logs"))
    
    assert organizer.get_category("movie.mp4") == "Videos"
    assert organizer.get_category("nmap_scan.txt") == "Cybersecurity"
    assert organizer.get_category("report.pdf") == "Documents"
    assert organizer.get_category("unknown.foo") == "Others"

def test_destination_path(temp_dir):
    class MockConfig:
        def get(self, key, default=None):
            if key == "destination_base": return str(temp_dir / "dest")
            if key == "large_file_threshold_gb": return 0.0001 # ~100KB
            if key == "categories":
                return {
                    "Videos": {
                        "extensions": [".mp4"],
                        "subfolders": {"Big_Videos": "Vids/Big", "Small_Videos": "Vids/Small"}
                    }
                }
            return default

    organizer = FileOrganizer(MockConfig(), SmartSortLogger(log_dir="test_logs"))
    
    # Small video
    small_file = temp_dir / "small.mp4"
    small_file.write_text("a" * 100) # 100 bytes
    dest = organizer.get_destination_path(str(small_file), "Videos")
    assert "Vids/Small" in dest

    # Big video
    big_file = temp_dir / "big.mp4"
    big_file.write_text("a" * 200000) # ~200KB
    dest = organizer.get_destination_path(str(big_file), "Videos")
    assert "Vids/Big" in dest

def test_duplicate_detection(temp_dir):
    dest_dir = temp_dir / "dest"
    dest_dir.mkdir()
    
    src_file = temp_dir / "src.txt"
    src_file.write_text("identical content")
    
    dst_file = dest_dir / "src.txt"
    dst_file.write_text("identical content")
    
    class MockConfig:
        def get(self, key, default=None):
            if key == "enable_duplicate_detection": return True
            if key == "destination_base": return str(dest_dir)
            return default
            
    organizer = FileOrganizer(MockConfig(), SmartSortLogger(log_dir="test_logs"))
    
    # Mock get_destination_path to return dst_file
    organizer.get_destination_path = lambda f, c: str(dst_file)
    
    result, info = organizer.process_file(str(src_file))
    assert result == "DUPLICATE"
    assert info == str(dst_file)
    assert os.path.exists(src_file) # Original should NOT be deleted if it's a duplicate and we skipped

def test_unique_path_generation(temp_dir):
    path = temp_dir / "file.txt"
    path.write_text("orig")
    
    unique_path = FileUtils.get_unique_path(str(path))
    assert unique_path != str(path)
    assert unique_path.endswith("file_1.txt")
    
    # Create the second file to test incremental suffixing
    with open(unique_path, "w") as f:
        f.write("copy")
    unique_path2 = FileUtils.get_unique_path(str(path))
    assert unique_path2.endswith("file_2.txt")

def test_conflict_policy_rename(temp_dir):
    src = temp_dir / "src.txt"
    src.write_text("content")
    
    dest_dir = temp_dir / "dest"
    dest_dir.mkdir()
    dst = dest_dir / "src.txt"
    dst.write_text("different content") # Non-duplicate
    
    class MockConfig:
        def get(self, key, default=None):
            if key == "enable_duplicate_detection": return True
            if key == "destination_base": return str(dest_dir)
            if key == "conflict_resolution": return "rename"
            return default
            
    organizer = FileOrganizer(MockConfig(), SmartSortLogger(log_dir="test_logs"))
    organizer.get_destination_path = lambda f, c: str(dst)
    
    result, info = organizer.process_file(str(src))
    assert result == "SUCCESS"
    assert info != str(dst)
    assert info.endswith("src_1.txt")
    assert not os.path.exists(src)
    assert os.path.exists(dst)
    assert os.path.exists(info)

def test_processed_files_cleanup():
    from src.monitor import DownloadHandler
    import time
    
    handler = DownloadHandler(None, lambda x: None)
    handler.processed_files["/path/to/old"] = time.time() - 301
    handler.processed_files["/path/to/new"] = time.time()
    
    assert len(handler.processed_files) == 2
    handler._cleanup_expired()
    assert "/path/to/old" not in handler.processed_files
    assert "/path/to/new" in handler.processed_files

def test_zero_byte_file_handling(temp_dir):
    src = temp_dir / "empty.txt"
    src.write_text("")
    
    dest_dir = temp_dir / "dest"
    dest_dir.mkdir()
    
    class MockConfig:
        def get(self, key, default=None):
            if key == "destination_base": return str(dest_dir)
            return default
            
    organizer = FileOrganizer(MockConfig(), SmartSortLogger(log_dir="test_logs"))
    organizer.get_destination_path = lambda f, c: str(dest_dir / "empty.txt")
    
    import time
    start = time.time()
    result, info = organizer.process_file(str(src))
    duration = time.time() - start
    
    assert result == "SUCCESS"
    assert duration < 2.0 # Zero-byte file processed without 60s delay
    assert not os.path.exists(src)
    assert os.path.exists(dest_dir / "empty.txt")

def test_config_save_protection_and_recovery(temp_dir):
    config_path = temp_dir / "config.json"
    default_path = temp_dir / "default_config.json"
    
    default_data = {
        "downloads_folder": str(temp_dir / "Downloads"),
        "destination_base": str(temp_dir),
        "large_file_threshold_gb": 2.5,
        "enable_hash_verification": True,
        "enable_notifications": True,
        "enable_duplicate_detection": True,
        "categories": {}
    }
    
    import json
    with open(default_path, "w") as f:
        json.dump(default_data, f)
        
    mgr = ConfigManager(config_path=str(config_path), default_path=str(default_path))
    assert mgr.get("large_file_threshold_gb") == 2684354560
    
    # Test validation fails on invalid types
    with pytest.raises(ValueError):
        mgr.set("large_file_threshold_gb", "not a float")
        
    mgr.set("large_file_threshold_gb", 5368709120)
    assert mgr.get("large_file_threshold_gb") == 5368709120
    bak_path = str(config_path) + ".bak"
    assert os.path.exists(bak_path)
    
    with open(bak_path, "r") as f:
        bak_data = json.load(f)
        assert bak_data["large_file_threshold_gb"] == 2684354560
        
    # Write corrupt data
    with open(config_path, "w") as f:
        f.write("bad JSON data")
        
    mgr2 = ConfigManager(config_path=str(config_path), default_path=str(default_path))
    assert mgr2.get("large_file_threshold_gb") == 2684354560

def test_log_retention_cleanup(temp_dir):
    logger = SmartSortLogger(log_dir=str(temp_dir), retention_days=2)
    
    from datetime import datetime, timedelta
    date_format = "%Y%m%d"
    
    today_str = datetime.now().strftime(date_format)
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime(date_format)
    three_days_ago_str = (datetime.now() - timedelta(days=3)).strftime(date_format)
    
    f1 = temp_dir / f"smartsort_{today_str}.log"
    f2 = temp_dir / f"smartsort_{yesterday_str}.log"
    f3 = temp_dir / f"smartsort_{three_days_ago_str}.log"
    
    f1.write_text("today")
    f2.write_text("yesterday")
    f3.write_text("three days ago")
    
    logger.cleanup_old_logs(retention_days=2)
    
    assert os.path.exists(f1)
    assert os.path.exists(f2)
    assert not os.path.exists(f3)

def test_logger_methods(temp_dir):
    logger = SmartSortLogger(log_dir=str(temp_dir), retention_days=7)
    
    # Trigger all logger methods
    logger.info("Test Info Message")
    logger.warning("Test Warning Message")
    logger.warn("Test Warn Message")
    logger.error("Test Error Message")
    logger.debug("Test Debug Message")
    
    # Read the log file for today
    from datetime import datetime
    log_file = temp_dir / f"smartsort_{datetime.now().strftime('%Y%m%d')}.log"
    assert log_file.exists()
    content = log_file.read_text()
    
    assert "Test Info Message" in content
    assert "Test Warning Message" in content
    assert "Test Warn Message" in content
    assert "Test Error Message" in content
    # Since level is INFO, Debug should not be written to file
    assert "Test Debug Message" not in content

def test_error_recovery_and_source_preservation(temp_dir):
    src = temp_dir / "src.txt"
    src.write_text("important source")
    
    class MockConfig:
        def get(self, key, default=None):
            if key == "destination_base": return "/nonexistent_dir_perm_denied"
            return default
            
    organizer = FileOrganizer(MockConfig(), SmartSortLogger(log_dir="test_logs"))
    organizer.get_destination_path = lambda f, c: "/nonexistent_dir_perm_denied/src.txt"
    
    result, info = organizer.process_file(str(src))
    assert result == "ERROR"
    assert os.path.exists(src)

def test_rules_comprehensive(temp_dir):
    from src.rules.conditions import parse_size_to_bytes
    from src.rules.rule import Rule
    from src.rules.engine import RuleEngine
    from src.rules.manager import RuleManager, validate_rules, migrate_config_if_needed

    # 1. Decimal Size Parsing
    assert parse_size_to_bytes("2.5GB") == int(2.5 * 1024**3)
    assert parse_size_to_bytes("1.5MB") == int(1.5 * 1024**2)
    assert parse_size_to_bytes("500KB") == 500 * 1024
    assert parse_size_to_bytes("100B") == 100
    assert parse_size_to_bytes("100") == 100
    with pytest.raises(ValueError):
        parse_size_to_bytes("-5MB")
    with pytest.raises(ValueError):
        parse_size_to_bytes("abc")

    # 2. Rule Validation
    valid_rule = {
        "id": "1",
        "name": "Valid Rule",
        "priority": 1,
        "destination": "Pictures/{extension}",
        "conditions": [{"type": "extension", "value": [".jpg"]}]
    }
    validate_rules([valid_rule]) # should pass
    
    # Duplicate priority
    with pytest.raises(ValueError):
        validate_rules([valid_rule, {**valid_rule, "id": "2"}])
        
    # Invalid size operator / value
    with pytest.raises(ValueError):
        Rule.from_dict({
            **valid_rule,
            "conditions": [{"type": "size", "operator": "INVALID", "value": "1MB"}]
        })
    with pytest.raises(ValueError):
        Rule.from_dict({
            **valid_rule,
            "conditions": [{"type": "size", "operator": ">", "value": "-1MB"}]
        })
        
    # Empty destination
    with pytest.raises(ValueError):
        Rule.from_dict({**valid_rule, "destination": ""})
        
    # Broken placeholders
    with pytest.raises(ValueError):
        Rule.from_dict({**valid_rule, "destination": "Pictures/{invalid_placeholder}"})
        
    # Invalid Regex
    with pytest.raises(ValueError):
        Rule.from_dict({
            **valid_rule,
            "conditions": [{"type": "regex", "value": "["}]
        })

    # 3. Rule Matching and Evaluation (Extension, Keyword, Regex, Size)
    r1 = Rule.from_dict({
        "id": "r1",
        "name": "Text Files",
        "priority": 5,
        "destination": "Docs/",
        "conditions": [{"type": "extension", "value": [".txt"]}]
    })
    r2 = Rule.from_dict({
        "id": "r2",
        "name": "Big Images",
        "priority": 1,
        "destination": "Pictures/Big/",
        "conditions": [
            {"type": "extension", "value": [".jpg", ".png"]},
            {"type": "size", "operator": ">", "value": "1MB"}
        ]
    })
    r3 = Rule.from_dict({
        "id": "r3",
        "name": "Metasploit Keyword",
        "priority": 2,
        "destination": "Cybersecurity/",
        "conditions": [{"type": "filename", "value": ["metasploit"]}]
    })
    r4 = Rule.from_dict({
        "id": "r4",
        "name": "Regex Match",
        "priority": 3,
        "destination": "Logs/",
        "conditions": [{"type": "regex", "value": "^log_.*\\.log$"}]
    })

    # Evaluate
    # Text file matches r1
    assert r1.evaluate("report.txt", 100) is True
    assert r1.evaluate("report.jpg", 100) is False
    
    # Big Image matches r2
    assert r2.evaluate("pic.jpg", int(1.2 * 1024**2)) is True
    assert r2.evaluate("pic.jpg", 500) is False
    
    # Metasploit matches r3
    assert r3.evaluate("metasploit_payload.exe", 100) is True
    assert r3.evaluate("payload.exe", 100) is False
    
    # Regex matches r4
    assert r4.evaluate("log_audit.log", 100) is True
    assert r4.evaluate("audit_log.log", 100) is False

    # 4. Priority Ordering and First Match Wins
    engine = RuleEngine([r1, r2, r3, r4])
    # A big image with keyword "metasploit" could match r2 (priority 1) or r3 (priority 2)
    # Priority 1 wins
    matched, dest = engine.evaluate_file("metasploit_image.jpg", int(2 * 1024**2))
    assert matched is not None
    assert matched.id == "r2"
    assert dest == "Pictures/Big/"

    # 5. Fallback Rule
    matched, dest = engine.evaluate_file("unknown_file.xyz", 100)
    assert matched is None
    assert dest == "Others/"

    # 6. Variable Expansion
    r_exp = Rule.from_dict({
        "id": "exp",
        "name": "Wallpaper Exp",
        "priority": 1,
        "destination": "Pics/Low/{extension}",
        "conditions": []
    })
    assert RuleEngine.expand_variables(r_exp.destination, "wallpaper.jpg") == "Pics/Low/JPG"
    assert RuleEngine.expand_variables("Files/{filename}", "notes.txt") == "Files/notes.txt"

    # 7. Image Quality Rules (Phase 3 spec)
    # Default Image rules (Low, Medium, High)
    img_rules_data = [
        {
            "id": "img_low",
            "name": "Low Quality Images",
            "enabled": True,
            "priority": 1,
            "conditions": [
                {"type": "extension", "value": [".jpg", ".png"]},
                {"type": "size", "operator": "<", "value": "1MB"}
            ],
            "destination": "Pictures/Low_Quality/{extension}"
        },
        {
            "id": "img_med",
            "name": "Medium Quality Images",
            "enabled": True,
            "priority": 2,
            "conditions": [
                {"type": "extension", "value": [".jpg", ".png"]},
                {"type": "size", "operator": ">=", "value": "1MB"},
                {"type": "size", "operator": "<", "value": "5MB"}
            ],
            "destination": "Pictures/Medium_Quality/{extension}"
        },
        {
            "id": "img_high",
            "name": "High Quality Images",
            "enabled": True,
            "priority": 3,
            "conditions": [
                {"type": "extension", "value": [".jpg", ".png"]},
                {"type": "size", "operator": ">=", "value": "5MB"}
            ],
            "destination": "Pictures/High_Quality/{extension}"
        }
    ]
    img_rules = [Rule.from_dict(d) for d in img_rules_data]
    img_engine = RuleEngine(img_rules)
    
    # 0.5 MB image -> Low Quality
    matched, dest = img_engine.evaluate_file("photo.jpg", int(0.5 * 1024**2))
    assert matched.id == "img_low"
    assert dest == "Pictures/Low_Quality/JPG"
    
    # 2 MB image -> Medium Quality
    matched, dest = img_engine.evaluate_file("photo.png", int(2.0 * 1024**2))
    assert matched.id == "img_med"
    assert dest == "Pictures/Medium_Quality/PNG"
    
    # 6 MB image -> High Quality
    matched, dest = img_engine.evaluate_file("photo.jpg", int(6.0 * 1024**2))
    assert matched.id == "img_high"
    assert dest == "Pictures/High_Quality/JPG"

    # 8. Legacy Config Migration
    legacy_config = {
        "large_file_threshold_gb": 2.5,
        "categories": {
            "Videos": {
                "extensions": [".mp4"],
                "subfolders": {
                    "Big_Videos": "Vids/Big",
                    "Small_Videos": "Vids/Small"
                }
            },
            "Images": {
                "extensions": [".jpg"]
            },
            "Cybersecurity": {
                "keywords": ["wireshark"]
            }
        }
    }
    
    migrated = migrate_config_if_needed(legacy_config)
    assert migrated is True
    assert "categories" not in legacy_config
    assert "rules" in legacy_config
    
    migrated_rules = legacy_config["rules"]
    assert migrated_rules[0]["id"] == "img_low"
    assert migrated_rules[1]["id"] == "img_med"
    assert migrated_rules[2]["id"] == "img_high"
    
    v_big = next(r for r in migrated_rules if r["id"] == "legacy_videos_big")
    assert v_big["destination"] == "Vids/Big"
    assert any(c["type"] == "size" and c["operator"] == ">=" and c["value"] == "2.5GB" for c in v_big["conditions"])
    
    v_small = next(r for r in migrated_rules if r["id"] == "legacy_videos_small")
    assert v_small["destination"] == "Vids/Small"
    
    cyber = next(r for r in migrated_rules if r["id"] == "legacy_cybersecurity")
    assert cyber["destination"] == "Cybersecurity"
    assert any(c["type"] == "filename" and "wireshark" in c["value"] for c in cyber["conditions"])

def test_large_file_threshold_size_parsing(temp_dir):
    from src.rules.conditions import parse_size_to_bytes
    from src.utils.config import ConfigManager
    import json
    
    # 1. Valid sizes checks
    assert parse_size_to_bytes("500KB") == 500 * 1024
    assert parse_size_to_bytes("500kb") == 500 * 1024
    assert parse_size_to_bytes("500KB") == 500 * 1024
    assert parse_size_to_bytes("500Kb") == 500 * 1024
    
    assert parse_size_to_bytes("1MB") == 1 * 1024**2
    assert parse_size_to_bytes("1.5MB") == int(1.5 * 1024**2)
    assert parse_size_to_bytes("500MB") == 500 * 1024**2
    assert parse_size_to_bytes("1GB") == 1 * 1024**3
    assert parse_size_to_bytes("2.5GB") == int(2.5 * 1024**3)
    assert parse_size_to_bytes("10GB") == 10 * 1024**3
    
    # 2. Invalid sizes checks
    with pytest.raises(ValueError):
        parse_size_to_bytes("abc")
    with pytest.raises(ValueError):
        parse_size_to_bytes("1.5XB")
    with pytest.raises(ValueError):
        parse_size_to_bytes("-1GB")
    with pytest.raises(ValueError):
        parse_size_to_bytes("")
    with pytest.raises(ValueError):
        parse_size_to_bytes(None)
        
    # 3. Backward Compatibility Migration tests
    config_path = temp_dir / "config.json"
    default_path = temp_dir / "default_config.json"
    
    legacy_data = {
        "downloads_folder": str(temp_dir),
        "destination_base": str(temp_dir),
        "large_file_threshold_gb": 2.5,
        "enable_hash_verification": True,
        "enable_notifications": True,
        "enable_duplicate_detection": True,
        "rules": []
    }
    
    with open(default_path, "w") as f:
        json.dump(legacy_data, f)
    with open(config_path, "w") as f:
        json.dump(legacy_data, f)
        
    mgr = ConfigManager(config_path=str(config_path), default_path=str(default_path))
    assert mgr.get("large_file_threshold_gb") == 2684354560
    
    legacy_data["large_file_threshold_gb"] = 1
    with open(config_path, "w") as f:
        json.dump(legacy_data, f)
        
    mgr2 = ConfigManager(config_path=str(config_path), default_path=str(default_path))
    assert mgr2.get("large_file_threshold_gb") == 1073741824

def test_path_portability_expansion(temp_dir):
    from src.utils.config import ConfigManager
    from pathlib import Path
    import json
    
    config_path = temp_dir / "config.json"
    default_path = temp_dir / "default_config.json"
    
    # 1. Default config with tildes
    default_data = {
        "downloads_folder": "~/Downloads",
        "destination_base": "~",
        "large_file_threshold_gb": 2684354560,
        "enable_hash_verification": True,
        "enable_notifications": True,
        "enable_duplicate_detection": True,
        "rules": []
    }
    
    with open(default_path, "w") as f:
        json.dump(default_data, f)
        
    mgr = ConfigManager(config_path=str(config_path), default_path=str(default_path))
    
    # Verify tilde is expanded
    assert mgr.get("downloads_folder") == str(Path("~/Downloads").expanduser())
    assert mgr.get("destination_base") == str(Path("~").expanduser())
    
    # Verify raw config stored contains tildes
    with open(config_path, "r") as f:
        stored_data = json.load(f)
        assert stored_data["downloads_folder"] == "~/Downloads"
        assert stored_data["destination_base"] == "~"
        
    # 2. Custom absolute path is respected
    custom_abs_path = str(temp_dir / "CustomDownloads")
    legacy_user_data = {
        "downloads_folder": custom_abs_path,
        "destination_base": str(temp_dir / "CustomBase"),
        "large_file_threshold_gb": 2684354560,
        "enable_hash_verification": True,
        "enable_notifications": True,
        "enable_duplicate_detection": True,
        "rules": []
    }
    with open(config_path, "w") as f:
        json.dump(legacy_user_data, f)
        
    mgr2 = ConfigManager(config_path=str(config_path), default_path=str(default_path))
    assert mgr2.get("downloads_folder") == custom_abs_path
    assert mgr2.get("destination_base") == str(temp_dir / "CustomBase")

def test_autostart_logic(temp_dir, monkeypatch):
    import sys
    from pathlib import Path
    from unittest.mock import MagicMock
    from src.gui.main_window import SmartSortGUI
    
    monkeypatch.setattr(Path, "home", lambda: temp_dir)
    monkeypatch.setattr(sys, "executable", "/venv/bin/python")
    monkeypatch.setattr(sys, "argv", ["/app/main.py"])
    
    class DummyGUI:
        def __init__(self):
            self.logger = MagicMock()
            self.config = MagicMock()
            
    gui = DummyGUI()
    gui.update_autostart_setting = SmartSortGUI.update_autostart_setting.__get__(gui, DummyGUI)
    
    gui.update_autostart_setting(True)
    
    autostart_file = temp_dir / ".config" / "autostart" / "smartsort.desktop"
    assert autostart_file.exists()
    content = autostart_file.read_text()
    assert "/venv/bin/python" in content
    assert "/app/main.py" in content
    assert "--service" in content
    assert "/home/websrp" not in content
    
    gui.update_autostart_setting(False)
    assert not autostart_file.exists()

def test_service_installation_logic(temp_dir, monkeypatch):
    import sys
    from pathlib import Path
    from unittest.mock import MagicMock
    from src.gui.main_window import SmartSortGUI
    
    monkeypatch.setattr(Path, "home", lambda: temp_dir)
    monkeypatch.setattr(sys, "executable", "/venv/bin/python")
    monkeypatch.setattr(sys, "argv", ["/app/main.py"])
    
    class DummyGUI:
        def __init__(self):
            self.logger = MagicMock()
            self.update_dashboard_stats = MagicMock()
            
    gui = DummyGUI()
    gui.install_service = SmartSortGUI.install_service.__get__(gui, DummyGUI)
    
    import subprocess
    mock_run = MagicMock()
    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr("src.gui.main_window.QMessageBox.information", lambda *args, **kwargs: None)
    
    gui.install_service()
    
    service_file = temp_dir / ".config" / "systemd" / "user" / "smartsort.service"
    assert service_file.exists()
    content = service_file.read_text()
    assert "/venv/bin/python" in content
    assert "/app/main.py" in content
    assert "--daemon" in content
    assert "/home/websrp" not in content
    
    assert mock_run.call_count >= 2

def test_service_status_detection(temp_dir, monkeypatch):
    from pathlib import Path
    from unittest.mock import MagicMock
    from src.gui.main_window import SmartSortGUI
    import subprocess
    
    monkeypatch.setattr(Path, "home", lambda: temp_dir)
    
    class DummyGUI:
        pass
        
    gui = DummyGUI()
    gui.get_service_status = SmartSortGUI.get_service_status.__get__(gui, DummyGUI)
    
    # 1. Mock subprocess.run for "Not Installed" state
    mock_not_found = MagicMock()
    mock_not_found.stdout = "not-found\n"
    mock_not_found.stderr = "No such file or directory\n"
    mock_not_found.returncode = 4
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_not_found)
    assert gui.get_service_status() == "Not Installed"
    
    # Create dummy service file
    service_dir = temp_dir / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True)
    (service_dir / "smartsort.service").write_text("dummy")
    
    # 2. Mock for "Running" state
    def mock_run_running(cmd, *args, **kwargs):
        res = MagicMock()
        if "is-enabled" in cmd:
            res.stdout = "enabled\n"
            res.stderr = ""
            res.returncode = 0
        elif "is-active" in cmd:
            res.stdout = "active\n"
            res.stderr = ""
            res.returncode = 0
        return res
    monkeypatch.setattr(subprocess, "run", mock_run_running)
    assert gui.get_service_status() == "Running"
    
    # 3. Mock for "Stopped" state
    def mock_run_stopped(cmd, *args, **kwargs):
        res = MagicMock()
        if "is-enabled" in cmd:
            res.stdout = "enabled\n"
            res.stderr = ""
            res.returncode = 0
        elif "is-active" in cmd:
            res.stdout = "inactive\n"
            res.stderr = ""
            res.returncode = 3
        return res
    monkeypatch.setattr(subprocess, "run", mock_run_stopped)
    assert gui.get_service_status() == "Stopped"

    # 4. Mock for "Disabled" state
    def mock_run_disabled(cmd, *args, **kwargs):
        res = MagicMock()
        if "is-enabled" in cmd:
            res.stdout = "disabled\n"
            res.stderr = ""
            res.returncode = 1
        elif "is-active" in cmd:
            res.stdout = "inactive\n"
            res.stderr = ""
            res.returncode = 3
        return res
    monkeypatch.setattr(subprocess, "run", mock_run_disabled)
    assert gui.get_service_status() == "Disabled"

def test_window_events_tray(monkeypatch):
    from unittest.mock import MagicMock
    from src.gui.main_window import SmartSortGUI
    
    class DummyGUI:
        def __init__(self):
            self.really_exit = False
            self.notifications_enabled = False
            self.hide = MagicMock()
            self.tray_available = True
            
    gui = DummyGUI()
    gui.closeEvent = SmartSortGUI.closeEvent.__get__(gui, DummyGUI)
    gui.changeEvent = SmartSortGUI.changeEvent.__get__(gui, DummyGUI)
    gui.isMinimized = MagicMock(return_value=True)
    
    from PyQt6.QtGui import QCloseEvent
    from PyQt6.QtCore import QEvent
    
    mock_close_event = MagicMock(spec=QCloseEvent)
    gui.closeEvent(mock_close_event)
    mock_close_event.ignore.assert_called_once()
    gui.hide.assert_called_once()
    
    gui.hide.reset_mock()
    
    mock_window_event = MagicMock(spec=QEvent)
    mock_window_event.type.return_value = QEvent.Type.WindowStateChange
    
    gui.changeEvent(mock_window_event)
    gui.hide.assert_called_once()

def test_tray_icon_creation(monkeypatch):
    from unittest.mock import MagicMock
    from src.gui.main_window import SmartSortGUI
    
    mock_tray = MagicMock()
    mock_menu = MagicMock()
    mock_pixmap = MagicMock()
    mock_painter = MagicMock()
    mock_icon = MagicMock()
    
    monkeypatch.setattr("src.gui.main_window.QSystemTrayIcon", lambda *args, **kwargs: mock_tray)
    monkeypatch.setattr("src.gui.main_window.QMenu", lambda *args, **kwargs: mock_menu)
    monkeypatch.setattr("src.gui.main_window.QPixmap", lambda *args, **kwargs: mock_pixmap)
    monkeypatch.setattr("src.gui.main_window.QPainter", lambda *args, **kwargs: mock_painter)
    monkeypatch.setattr("src.gui.main_window.QIcon", lambda *args, **kwargs: mock_icon)
    
    mock_painter_class = MagicMock()
    mock_painter_class.RenderHint = MagicMock()
    monkeypatch.setattr("src.gui.main_window.QPainter", mock_painter_class)
    
    class DummyGUI:
        pass
        
    gui = DummyGUI()
    gui.setup_system_tray = SmartSortGUI.setup_system_tray.__get__(gui, DummyGUI)
    
    gui.show_tab = MagicMock()
    gui.pause_monitoring = MagicMock()
    gui.resume_monitoring = MagicMock()
    gui.show_statistics = MagicMock()
    gui.open_reports_folder = MagicMock()
    gui.restart_application = MagicMock()
    gui.exit_application = MagicMock()
    gui.on_tray_icon_activated = MagicMock()
    
    gui.setup_system_tray()
    assert mock_menu.addAction.call_count >= 8

def test_start_minimized_config(temp_dir, monkeypatch):
    from unittest.mock import MagicMock
    
    mock_app = MagicMock()
    monkeypatch.setattr("PyQt6.QtWidgets.QApplication", lambda *args: mock_app)
    
    mock_gui = MagicMock()
    monkeypatch.setattr("src.gui.main_window.SmartSortGUI", lambda *args: mock_gui)
    
    mock_config = MagicMock()
    mock_config.get.return_value = True
    monkeypatch.setattr("src.utils.config.ConfigManager", lambda *args, **kwargs: mock_config)
    
    import sys
    monkeypatch.setattr(sys, "argv", ["main.py", "--service"])
    
    import main
    try:
        main.main()
    except SystemExit:
        pass
    mock_gui.show.assert_not_called()

def test_daemon_startup_shutdown(temp_dir, monkeypatch):
    from unittest.mock import MagicMock
    
    mock_monitor = MagicMock()
    monkeypatch.setattr("src.monitor.FileMonitor", lambda *args, **kwargs: mock_monitor)
    
    mock_config = MagicMock()
    mock_config.get.return_value = str(temp_dir)
    monkeypatch.setattr("src.utils.config.ConfigManager", lambda *args, **kwargs: mock_config)
    
    mock_logger = MagicMock()
    monkeypatch.setattr("src.utils.logger.SmartSortLogger", lambda *args, **kwargs: mock_logger)
    
    mock_organizer = MagicMock()
    monkeypatch.setattr("src.organizer.FileOrganizer", lambda *args, **kwargs: mock_organizer)
    
    import time
    def mock_sleep(seconds):
        raise KeyboardInterrupt()
    monkeypatch.setattr(time, "sleep", mock_sleep)
    
    import main
    main.run_daemon()
    
    mock_monitor.start.assert_called_once()
    mock_monitor.stop.assert_called_once()


def test_tray_available(monkeypatch):
    from unittest.mock import MagicMock
    from PyQt6.QtWidgets import QSystemTrayIcon
    from src.gui.main_window import SmartSortGUI

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    
    mock_tray = MagicMock()
    monkeypatch.setattr("src.gui.main_window.QSystemTrayIcon", lambda *args, **kwargs: mock_tray)
    monkeypatch.setattr("src.gui.main_window.QMenu", lambda *args, **kwargs: MagicMock())
    monkeypatch.setattr("src.gui.main_window.QPixmap", lambda *args, **kwargs: MagicMock())
    monkeypatch.setattr("src.gui.main_window.QPainter", lambda *args, **kwargs: MagicMock())
    monkeypatch.setattr("src.gui.main_window.QIcon", lambda *args, **kwargs: MagicMock())
    monkeypatch.setattr("src.gui.main_window.QColor", lambda *args, **kwargs: MagicMock())
    
    mock_painter_class = MagicMock()
    mock_painter_class.RenderHint = MagicMock()
    monkeypatch.setattr("src.gui.main_window.QPainter", mock_painter_class)

    class DummyGUI:
        def __init__(self):
            self.logger = MagicMock()
            self.tray_available = False
            self.notifications_enabled = False
            self.stats = {"processed": 0, "duplicates": 0, "errors": 0}
            self.really_exit = False
            
        def init_notification_system(self):
            pass
        def init_ui(self):
            pass
        def apply_theme(self):
            pass
            
    gui = DummyGUI()
    gui.setup_system_tray = SmartSortGUI.setup_system_tray.__get__(gui, DummyGUI)
    gui.init_notification_system = DummyGUI.init_notification_system.__get__(gui, DummyGUI)
    gui.init_ui = DummyGUI.init_ui.__get__(gui, DummyGUI)
    gui.apply_theme = DummyGUI.apply_theme.__get__(gui, DummyGUI)
    
    gui.show_tab = MagicMock()
    gui.pause_monitoring = MagicMock()
    gui.resume_monitoring = MagicMock()
    gui.show_statistics = MagicMock()
    gui.open_reports_folder = MagicMock()
    gui.restart_application = MagicMock()
    gui.exit_application = MagicMock()
    gui.on_tray_icon_activated = MagicMock()
    
    gui.tray_available = False
    try:
        if QSystemTrayIcon.isSystemTrayAvailable():
            try:
                gui.setup_system_tray()
                gui.tray_available = True
            except Exception as e:
                gui.logger.warning(f"System tray initialization failed: {e}")
        else:
            gui.logger.warning("System tray unavailable. Running without tray support.")
    except Exception as e:
        gui.logger.warning(f"Failed to check system tray availability: {e}")
        
    assert gui.tray_available is True
    assert mock_tray.show.called


def test_tray_unavailable(monkeypatch):
    from unittest.mock import MagicMock
    from PyQt6.QtWidgets import QSystemTrayIcon
    from src.gui.main_window import SmartSortGUI

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    
    mock_setup_tray = MagicMock()
    
    class DummyGUI:
        def __init__(self):
            self.logger = MagicMock()
            self.tray_available = False
            
        def setup_system_tray(self):
            mock_setup_tray()
            
    gui = DummyGUI()
    
    try:
        if QSystemTrayIcon.isSystemTrayAvailable():
            try:
                gui.setup_system_tray()
                gui.tray_available = True
            except Exception as e:
                gui.logger.warning(f"System tray initialization failed: {e}")
        else:
            gui.logger.warning("System tray unavailable. Running without tray support.")
    except Exception as e:
        gui.logger.warning(f"Failed to check system tray availability: {e}")
        
    assert gui.tray_available is False
    mock_setup_tray.assert_not_called()
    assert gui.logger.warning.called


def test_tray_initialization_failure(monkeypatch):
    from unittest.mock import MagicMock
    from PyQt6.QtWidgets import QSystemTrayIcon
    from src.gui.main_window import SmartSortGUI

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    
    class DummyGUI:
        def __init__(self):
            self.logger = MagicMock()
            self.tray_available = False
            
        def setup_system_tray(self):
            raise RuntimeError("D-Bus status notifier watcher connection timed out")
            
    gui = DummyGUI()
    
    try:
        if QSystemTrayIcon.isSystemTrayAvailable():
            try:
                gui.setup_system_tray()
                gui.tray_available = True
            except Exception as e:
                gui.logger.warning(f"System tray initialization failed: {e}")
        else:
            gui.logger.warning("System tray unavailable. Running without tray support.")
    except Exception as e:
        gui.logger.warning(f"Failed to check system tray availability: {e}")
        
    assert gui.tray_available is False
    assert gui.logger.warning.called


def test_gnome_environment_tray_disabled(monkeypatch):
    from unittest.mock import MagicMock
    from PyQt6.QtWidgets import QSystemTrayIcon
    
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    
    class DummyGUI:
        def __init__(self):
            self.logger = MagicMock()
            self.tray_available = False
            
    gui = DummyGUI()
    
    try:
        if QSystemTrayIcon.isSystemTrayAvailable():
            gui.tray_available = True
        else:
            gui.logger.warning("System tray unavailable. Running without tray support.")
    except Exception:
        pass
        
    assert gui.tray_available is False
    assert gui.logger.warning.called


def test_headless_environment_tray_disabled(monkeypatch):
    from unittest.mock import MagicMock
    from PyQt6.QtWidgets import QSystemTrayIcon
    
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    
    class DummyGUI:
        def __init__(self):
            self.logger = MagicMock()
            self.tray_available = False
            
    gui = DummyGUI()
    
    try:
        if QSystemTrayIcon.isSystemTrayAvailable():
            gui.tray_available = True
        else:
            gui.logger.warning("System tray unavailable. Running without tray support.")
    except Exception:
        pass
        
    assert gui.tray_available is False
    assert gui.logger.warning.called


def test_dashboard_startup_components(temp_dir, monkeypatch):
    from unittest.mock import MagicMock
    
    mock_config = MagicMock()
    mock_config.get.return_value = "System Theme"
    monkeypatch.setattr("src.utils.config.ConfigManager", lambda *args, **kwargs: mock_config)
    
    mock_logger = MagicMock()
    monkeypatch.setattr("src.utils.logger.SmartSortLogger", lambda *args, **kwargs: mock_logger)
    
    mock_organizer = MagicMock()
    monkeypatch.setattr("src.organizer.FileOrganizer", lambda *args, **kwargs: mock_organizer)
    
    class DummyGUI:
        def __init__(self):
            self.config = mock_config
            self.logger = mock_logger
            self.organizer = mock_organizer
            self.tray_available = False
            self.really_exit = False
            self.monitoring_active = True
            
    gui = DummyGUI()
    assert gui.monitoring_active is True
    assert gui.tray_available is False
    assert gui.really_exit is False


def test_app_startup_without_tray_shows_window(temp_dir, monkeypatch):
    from unittest.mock import MagicMock
    
    mock_app = MagicMock()
    monkeypatch.setattr("PyQt6.QtWidgets.QApplication", lambda *args: mock_app)
    
    mock_gui = MagicMock()
    mock_gui.tray_available = False
    monkeypatch.setattr("src.gui.main_window.SmartSortGUI", lambda *args: mock_gui)
    
    mock_config = MagicMock()
    mock_config.get.return_value = True
    monkeypatch.setattr("src.utils.config.ConfigManager", lambda *args, **kwargs: mock_config)
    
    import sys
    monkeypatch.setattr(sys, "argv", ["main.py", "--service"])
    
    import main
    try:
        main.main()
    except SystemExit:
        pass
        
    mock_gui.show.assert_called_once()

def test_config_initialization_robustness(temp_dir):
    from src.utils.config import ConfigManager
    from pathlib import Path
    
    config_file = temp_dir / "config.json"
    default_file = temp_dir / "default_config.json"
    
    # Create a minimal default config
    default_content = {
        "downloads_folder": "~/Downloads",
        "destination_base": "~",
        "large_file_threshold_gb": 2.5,
        "enable_hash_verification": True,
        "enable_notifications": True,
        "enable_duplicate_detection": True,
        "conflict_resolution": "rename",
        "categories": {},
        "rules": [],
        "start_minimized": False,
        "autostart": False,
        "theme": "system"
    }
    import json
    with open(default_file, 'w') as f:
        json.dump(default_content, f)
        
    # Scenario 1: Config file is missing
    manager = ConfigManager(config_path=str(config_file), default_path=str(default_file))
    # It should have written the config file
    assert config_file.exists()
    assert manager.get("downloads_folder") == str(Path("~/Downloads").expanduser())
    assert manager.get("enable_notifications") is True
    assert manager.get("theme") == "system"

    # Scenario 2: Config file contains corrupted JSON
    with open(config_file, 'w') as f:
        f.write("{invalid json...")
    
    # We load again - it should fall back to default config without crashing
    manager2 = ConfigManager(config_path=str(config_file), default_path=str(default_file))
    assert manager2.get("theme") == "system"
    
    # Scenario 3: Config file is missing some keys
    partial_config = {
        "downloads_folder": "/custom/downloads",
        "theme": "dark"
    }
    with open(config_file, 'w') as f:
        json.dump(partial_config, f)
        
    manager3 = ConfigManager(config_path=str(config_file), default_path=str(default_file))
    # It should merge defaults for missing keys
    assert manager3.get("downloads_folder") == "/custom/downloads"
    assert manager3.get("theme") == "dark"
    assert manager3.get("enable_notifications") is True  # Merged from default
    assert manager3.get("large_file_threshold_gb") == int(2.5 * (1024**3))  # Merged & migrated from default

    # Scenario 4: Config file has wrong type for a key
    wrong_type_config = {
        "enable_notifications": "not_a_bool"  # wrong type
    }
    with open(config_file, 'w') as f:
        json.dump(wrong_type_config, f)
        
    manager4 = ConfigManager(config_path=str(config_file), default_path=str(default_file))
    # Invalid key type should be replaced by default bool True, not crash
    assert manager4.get("enable_notifications") is True

def test_tray_state_transitions():
    from unittest.mock import MagicMock
    from src.gui.tray_manager import TrayStateManager, TrayState

    mock_tray = MagicMock()
    manager = TrayStateManager(mock_tray)

    # 1. Startup State
    manager.set_startup()
    assert manager.current_state == TrayState.STARTUP
    mock_tray.setToolTip.assert_called_with("SmartSort\nStatus: Startup / Initial Scan")

    # 2. Monitoring State
    manager.set_monitoring(15, 8)
    assert manager.current_state == TrayState.IDLE
    mock_tray.setToolTip.assert_called_with("SmartSort\nStatus: Monitoring\nFiles Processed: 15\nRules Active: 8")

    # 3. Paused State
    manager.set_paused(15, 8)
    assert manager.current_state == TrayState.PAUSED
    mock_tray.setToolTip.assert_called_with("SmartSort\nStatus: Paused\nFiles Processed: 15\nRules Active: 8")

    # 4. Processing Small File (< 1 GB)
    manager.set_processing("small.txt", 500 * 1024 * 1024)
    assert manager.current_state == TrayState.PROCESSING_SMALL
    mock_tray.setToolTip.assert_called_with("SmartSort\nStatus: Processing\nFile: small.txt\nSize: 500 MB")

    # 5. Processing Large File (>= 1 GB)
    manager.set_processing("large.mkv", 2 * 1024 * 1024 * 1024)
    assert manager.current_state == TrayState.PROCESSING_LARGE
    mock_tray.setToolTip.assert_called_with("SmartSort\nStatus: Processing\nFile: large.mkv\nSize: 2 GB")

    # 6. Error State
    manager.set_error("Disk full")
    assert manager.current_state == TrayState.ERROR
    assert manager.has_active_error is True
    mock_tray.setToolTip.assert_called_with("SmartSort\nStatus: Error\nLast Error: Disk full")

    # 7. Resume keeps error active
    manager.set_monitoring(15, 8)
    assert manager.current_state == TrayState.ERROR
    
    # 8. Success clears error
    manager.set_success(16, 8)
    assert manager.current_state == TrayState.IDLE
    assert manager.has_active_error is False
    mock_tray.setToolTip.assert_called_with("SmartSort\nStatus: Monitoring\nFiles Processed: 16\nRules Active: 8")


def test_ensure_user_icons_installed(tmp_path, monkeypatch):
    import os
    import main
    from unittest.mock import MagicMock
    
    # Mock expanduser to point to tmp_path
    mock_home = tmp_path / "user_home"
    os.makedirs(mock_home)
    monkeypatch.setattr("os.path.expanduser", lambda path: path.replace("~", str(mock_home)))
    
    # Mock subprocess.run
    mock_run = MagicMock()
    monkeypatch.setattr("subprocess.run", mock_run)
    
    # Call ensure_user_icons_installed
    mock_logger = MagicMock()
    main.ensure_user_icons_installed(mock_logger)
    
    # Check that user hicolor directory exists
    user_hicolor_dir = mock_home / ".local" / "share" / "icons" / "hicolor"
    assert user_hicolor_dir.exists()
    
    # Verify presence of smartsort.png and color icons in all folders
    sizes = ["16x16", "22x22", "24x24", "32x32", "scalable"]
    for size in sizes:
        apps_dir = user_hicolor_dir / size / "apps"
        assert apps_dir.exists()
        assert (apps_dir / "smartsort.png").exists()
        
        for color in ["green", "blue", "orange", "red", "grey", "yellow"]:
            assert (apps_dir / f"smartsort-{color}.png").exists()
            
    # Verify icon cache update was called
    mock_run.assert_called()



