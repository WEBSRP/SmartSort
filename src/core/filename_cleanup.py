"""Smart Filename Cleanup module for SmartSort."""

import os
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

_CDN_TO_SITE = {
    "redd.it": "reddit",
    "redditmedia.com": "reddit",
    "redditstatic.com": "reddit",
    "pinimg.com": "pinterest",
    "fbcdn.net": "facebook",
    "cdninstagram.com": "instagram",
    "twimg.com": "twitter",
    "ytimg.com": "youtube",
    "ggpht.com": "youtube",
    "googleusercontent.com": "google",
    "gstatic.com": "google",
    "githubusercontent.com": "github",
    "githubassets.com": "github",
    "imgur.com": "imgur",
    "wp.com": "wordpress",
    "unsplash.com": "unsplash",
    "pexels.com": "pexels",
    "pixabay.com": "pixabay",
    "flickr.com": "flickr",
    "staticflickr.com": "flickr",
    "deviantart.net": "deviantart",
    "artstation.com": "artstation",
    "wallpaperflare.com": "wallpaperflare",
    "wallpapercave.com": "wallpapercave",
    "wallpaperaccess.com": "wallpaperaccess",
    "wikimedia.org": "wikipedia",
    "wikipedia.org": "wikipedia",
    "medium.com": "medium",
}

_GENERIC_NAMES = frozenset([
    "_", "download", "image", "img", "photo", "new", "file", "untitled", 
    "copy", "scan", "document", "screenshot", "capture", "temp", "tmp", 
    "unknown", "noname", "none", "default", "blank", "test", "sample", "example"
])

_EXTENSION_FALLBACKS = {
    # Images
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image", 
    ".gif": "image", ".bmp": "image", ".svg": "image", ".tiff": "image", 
    ".tif": "image", ".ico": "image", ".heic": "image", ".heif": "image",
    # Documents
    ".pdf": "document", ".doc": "document", ".docx": "document", 
    ".odt": "document", ".rtf": "document", ".txt": "document",
    # Presentations
    ".ppt": "presentation", ".pptx": "presentation", ".odp": "presentation",
    # Spreadsheets
    ".xls": "spreadsheet", ".xlsx": "spreadsheet", ".ods": "spreadsheet", ".csv": "spreadsheet",
    # Videos
    ".mp4": "video", ".mkv": "video", ".avi": "video", ".mov": "video", 
    ".wmv": "video", ".flv": "video", ".webm": "video",
    # Audio
    ".mp3": "audio", ".flac": "audio", ".wav": "audio", ".aac": "audio", 
    ".ogg": "audio", ".m4a": "audio",
    # Archives
    ".zip": "archive", ".rar": "archive", ".7z": "archive", ".tar": "archive", 
    ".gz": "archive", ".bz2": "archive", ".xz": "archive",
    # Disk images
    ".iso": "diskimage", ".img": "diskimage",
    # Packages
    ".deb": "package", ".rpm": "package", ".appimage": "package",
    # Executables
    ".exe": "installer", ".msi": "installer",
    # Fonts
    ".ttf": "font", ".otf": "font", ".woff": "font", ".woff2": "font",
    # Ebooks
    ".epub": "ebook", ".mobi": "ebook"
}

class FilenameCleanup:
    """Evaluates filenames for quality and generates clean replacements."""

    def __init__(self, enabled: bool = False, min_length: int = 4, max_length: int = 80):
        self.enabled = enabled
        self.min_length = min_length
        self.max_length = max_length

    def needs_cleanup(self, filename: str) -> bool:
        """Determines if a filename needs to be cleaned up."""
        if not self.enabled:
            return False
            
        name, _ = os.path.splitext(filename)
        name = name.strip()
        
        if not name or not any(c.isalnum() for c in name):
            return True
            
        if len(name) < self.min_length or len(name) > self.max_length:
            return True
            
        name_lower = name.lower()
        if name_lower in _GENERIC_NAMES:
            return True
            
        if name.isdigit():
            return True
            
        camera_pattern = re.compile(r'^(?:IMG|DSC|DCIM|DJI|PXL|PANO|VID|MOV|WP|P)[_-]?\d+$', re.IGNORECASE)
        if camera_pattern.match(name):
            return True
            
        if len(name) >= 8 and len(set(name_lower)) <= 2:
            return True
            
        return False

    def generate_clean_name(self, file_path: str) -> str:
        """Generates a clean replacement name for a file."""
        dirname, filename = os.path.split(file_path)
        name, ext = os.path.splitext(filename)
        
        site_name = self._extract_source_website(file_path)
        if site_name:
            return site_name + ext
            
        if len(name) > self.max_length:
            truncated = self._truncate_name(name)
            if len(truncated) >= self.min_length:
                return truncated + ext
                
        fallback = _EXTENSION_FALLBACKS.get(ext.lower(), "file")
        return fallback + ext

    def _extract_source_website(self, file_path: str) -> Optional[str]:
        """Extracts source website name from file xattrs."""
        url = self._read_xattr(file_path, 'user.xdg.referrer.url')
        if url:
            site = self._domain_to_site_name(url)
            if site:
                return site
                
        url = self._read_xattr(file_path, 'user.xdg.origin.url')
        if url:
            site = self._domain_to_site_name(url)
            if site:
                return site
                
        return None

    @staticmethod
    def _read_xattr(file_path: str, attr_name: str) -> Optional[str]:
        """Reads an extended attribute from a file."""
        try:
            val = os.getxattr(file_path, attr_name.encode('utf-8'))
            return val.decode('utf-8', errors='ignore')
        except (OSError, AttributeError, UnicodeDecodeError):
            return None

    @staticmethod
    def _domain_to_site_name(url: str) -> Optional[str]:
        """Extracts a site name from a URL."""
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return None
            
        hostname = hostname.lower().strip('.')
        if hostname.startswith('www.'):
            hostname = hostname[4:]
            
        if hostname in _CDN_TO_SITE:
            return _CDN_TO_SITE[hostname]
            
        for cdn, site in _CDN_TO_SITE.items():
            if hostname.endswith('.' + cdn):
                return site
                
        parts = hostname.split('.')
        if len(parts) >= 2:
            site = parts[-2]
            if len(site) >= 2 and site.isalnum():
                return site
                
        return None

    def _truncate_name(self, name: str) -> str:
        """Truncates a name to max_length and sanitizes it."""
        if len(name) <= self.max_length:
            return self._sanitize_name(name)
            
        truncated = name[:self.max_length]
        
        # Find last word boundary
        last_space = truncated.rfind(' ')
        last_underscore = truncated.rfind('_')
        last_hyphen = truncated.rfind('-')
        
        boundary = max(last_space, last_underscore, last_hyphen)
        
        if boundary > self.max_length // 2:
            truncated = truncated[:boundary]
            
        return self._sanitize_name(truncated)

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitizes a string to be a safe filename."""
        # Replace unsafe chars
        unsafe_pattern = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
        sanitized = unsafe_pattern.sub('_', name)
        
        # Collapse spaces and underscores
        sanitized = re.sub(r'[\s_]+', '_', sanitized)
        
        # Strip leading/trailing chars
        return sanitized.strip('_. ')
