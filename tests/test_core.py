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
