import hashlib
import shutil
import os
from typing import Tuple, Optional

class FileUtils:
    @staticmethod
    def calculate_sha256(file_path: str) -> Optional[str]:
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
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
