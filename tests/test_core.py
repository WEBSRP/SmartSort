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
