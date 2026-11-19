"""Recognize cohesive application/project directories without opening their assets."""
import os
from pathlib import Path
import stat

_BUNDLE_SUFFIXES = ('.app', '.appdir', '.bundle', '.framework', '.plugin')
_PROJECT_MARKERS = (
    'package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod', 'CMakeLists.txt',
    'pom.xml', 'build.gradle', 'build.gradle.kts', 'composer.json', 'Gemfile',
    'requirements.txt', 'setup.py', 'setup.cfg', '__init__.py', 'Makefile',
    'makefile', 'Dockerfile', 'pubspec.yaml', 'build.sbt', 'mix.exs',
)
_ASSET_DIRS = {'assets', 'resources', 'lib', 'libs', 'plugins', 'bin'}


def _regular(path):
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def is_protected_folder(directory):
    """Protect known bundles and cohesive project layouts; never execute files."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        return False
    if directory.name.casefold().endswith(_BUNDLE_SUFFIXES):
        return True
    if _regular(directory / '.smartsort-ignore') or _regular(directory / 'AppRun'):
        return True
    if any(_regular(directory / marker) for marker in _PROJECT_MARKERS):
        return True
    if (_regular(directory / '.git') or _regular(directory / '.git/HEAD')
            or _regular(directory / 'DEBIAN/control')
            or _regular(directory / 'resources/app.asar')
            or _regular(directory / 'resources/default_app.asar')):
        return True
    # Portable apps often ship an executable alongside icons, libraries or
    # resource folders. Examine bounded top-level names and executable headers,
    # never image/document contents or a recursive directory inventory.
    names, files, directories = set(), [], set()
    try:
        with os.scandir(directory) as entries:
            for index, entry in enumerate(entries):
                if index >= 512:
                    break
                if entry.is_symlink():
                    continue
                names.add(entry.name.casefold())
                if entry.is_dir(follow_symlinks=False):
                    directories.add(entry.name.casefold())
                elif entry.is_file(follow_symlinks=False):
                    files.append(entry)
    except OSError:
        # An unreadable directory must not be dissected by a recursive scan.
        return True
    if any(name.endswith(('.sln', '.csproj', '.fsproj', '.vbproj')) for name in names):
        return True
    resource_layout = bool(directories & _ASSET_DIRS)
    has_launcher = any(name.endswith('.desktop') for name in names)
    has_libraries = any(name.endswith(('.dll', '.dylib')) or name.endswith('.so') or '.so.' in name for name in names)
    has_icons = any(name.endswith(('.png', '.svg', '.ico', '.icns')) for name in names)
    if has_launcher and resource_layout:
        return True
    if resource_layout and ('main.py' in names or any(name.endswith(('.sln', '.csproj')) for name in names)):
        return True
    if not (resource_layout or has_libraries or has_icons):
        return False
    for entry in files:
        lower = entry.name.casefold()
        if lower.endswith(('.exe', '.jar')):
            return True
        try:
            if not entry.stat(follow_symlinks=False).st_mode & 0o111:
                continue
            descriptor = os.open(entry.path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(descriptor, 'rb') as handle:
                if handle.read(4) == b'\x7fELF':
                    return True
        except OSError:
            continue
    return False


def _protected_parent(root):
    # Selecting a project's src/assets subfolder must not bypass its parent
    # boundary. Stop at collection/system/home roots to avoid treating unrelated
    # parent directories as one enormous application.
    current = root.parent
    home = Path.home()
    for _ in range(12):
        if (current == home or current == current.parent or
                str(current) in ('/tmp', '/var/tmp', '/home', '/usr', '/opt', '/var') or
                current.name.casefold() in ('downloads', 'documents', 'desktop', 'projects')):
            break
        if is_protected_folder(current):
            return str(current)
        current = current.parent
    return None


def protected_folder_for(path, root):
    """Find a protecting folder, including a selected project's parent boundary."""
    path, root = Path(os.path.abspath(path)), Path(os.path.abspath(root))
    try:
        path.relative_to(root)
    except ValueError:
        return None
    current = path if path.is_dir() else path.parent
    while True:
        if is_protected_folder(current):
            return str(current)
        if current == root:
            return _protected_parent(root)
        parent = current.parent
        if parent == current:
            return None
        current = parent
