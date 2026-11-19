import hashlib
import shutil
import os
import stat
from typing import Tuple, Optional

class FileUtils:
    @staticmethod
    def remove_verified_duplicate(src, dst, validate=None):
        """Return (removed, source_hash, error), preserving files on doubt.

        Compare SHA-256 of distinct regular files and recheck both identities
        after hashing and caller validation before removing only the source.
        A different hash is an ordinary collision, not an error.
        """
        def snapshot(path):
            info = os.lstat(path)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Duplicate verification requires regular non-symlink files")
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

        try:
            source_before, target_before = snapshot(src), snapshot(dst)
            if source_before[:2] == target_before[:2]:
                raise ValueError("Source and destination are the same physical file")
            if source_before[2] != target_before[2]:
                return False, None, None
            source_hash = FileUtils.calculate_sha256(src)
            target_hash = FileUtils.calculate_sha256(dst)
            if not source_hash or not target_hash:
                raise ValueError("Could not read both files for duplicate hash verification")
            if snapshot(src) != source_before or snapshot(dst) != target_before:
                raise ValueError("File changed during duplicate hash verification")
            if source_hash != target_hash:
                return False, source_hash, None
            if validate is not None:
                validate()
            # Metadata timestamps can have coarse filesystem resolution. Re-read
            # both hashes before deletion to catch same-size writes during the
            # first comparison even when stat timestamps did not advance.
            if (FileUtils.calculate_sha256(src) != source_hash or
                    FileUtils.calculate_sha256(dst) != target_hash):
                raise ValueError("File contents changed before duplicate source removal")
            if snapshot(src) != source_before or snapshot(dst) != target_before:
                raise ValueError("File changed before duplicate source removal")
            os.remove(src)
            return True, source_hash, None
        except (OSError, ValueError, TypeError) as error:
            return False, None, str(error)

    @staticmethod
    def calculate_sha256(file_path: str) -> Optional[str]:
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(1024 * 1024), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception:
            return None

    @staticmethod
    def safe_copy(src: str, dst: str) -> Tuple[bool, str]:
        """
        Copy src to dst, verify with SHA256, and return success status and message/hash.
        """
        try:
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            
            # 1. Copy file
            shutil.copy2(src, dst)
            
            # 2. Verify
            src_hash = FileUtils.calculate_sha256(src)
            dst_hash = FileUtils.calculate_sha256(dst)
            
            if src_hash and src_hash == dst_hash:
                return True, src_hash
            else:
                # Cleanup failed copy
                if os.path.exists(dst):
                    os.remove(dst)
                return False, "Hash mismatch"
        except Exception as e:
            if os.path.exists(dst):
                os.remove(dst)
            return False, str(e)

    @staticmethod
    def get_unique_path(path: str) -> str:
        """
        If path exists, append _1, _2, etc. to make it unique.
        """
        if not os.path.exists(path):
            return path
        dir_name, file_name = os.path.split(path)
        base_name, ext = os.path.splitext(file_name)
        counter = 1
        while True:
            new_file_name = f"{base_name}_{counter}{ext}"
            new_path = os.path.join(dir_name, new_file_name)
            if not os.path.exists(new_path):
                return new_path
            counter += 1

