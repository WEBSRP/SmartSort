"""Inspect a real package so shared icon-theme files cannot ship again."""
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest

from src.version import VERSION


@pytest.mark.skipif(not shutil.which("dpkg-deb"), reason="Debian build tools unavailable")
def test_deb_has_only_app_owned_system_icons(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ, SMARTSORT_OUTPUT_DIR=str(tmp_path),
               SMARTSORT_PACKAGE_VERSION=f"{VERSION}+packaging-test")
    subprocess.run(["bash", str(repo / "packaging/debian/build_deb.sh")],
                   env=env, check=True, capture_output=True, timeout=90)
    package = tmp_path / f"smartsort_{VERSION}+packaging-test_all.deb"
    content = subprocess.run(["dpkg-deb", "--fsys-tarfile", str(package)],
                             check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(content)) as archive:
        members = archive.getmembers()
        files = {m.name.lstrip("./") for m in members if m.isfile()}
        assert all(member.uid == member.gid == 0 for member in members)
        for source in (repo / "src/core/file_intelligence").rglob("*.py"):
            target = "./usr/share/smartsort/" + source.relative_to(repo).as_posix()
            assert archive.extractfile(target).read() == source.read_bytes()
        assert archive.getmember("./usr/bin/smartsort").mode & 0o777 == 0o755
    icons = {p for p in files if p.startswith("usr/share/icons/")}
    assert icons
    assert all(Path(p).name.startswith("smartsort") for p in icons)
    assert "usr/share/icons/hicolor/index.theme" not in files
    assert "usr/share/icons/hicolor/icon-theme.cache" not in files
    assert not any(p.endswith((".pyc", ".pyo")) for p in files)
    assert "usr/bin/smartsort" in files
    assert "usr/share/smartsort/src/gui/theme.py" in files
    assert "usr/share/smartsort/assets/icons/check-dark.svg" in files
    assert "usr/share/smartsort/assets/icons/check-light.svg" in files

    control = subprocess.run(["dpkg-deb", "--field", str(package)], check=True,
                             capture_output=True, text=True).stdout
    depends = next(line for line in control.splitlines() if line.startswith("Depends:"))
    assert all(name in depends.split(":", 1)[1].replace(" ", "").split(",")
               for name in ("python3-pypdf", "python3-pil", "python3-mutagen"))
    assert "Suggests: python3-docx, python3-openpyxl" in control
    scripts = subprocess.run(["dpkg-deb", "--ctrl-tarfile", str(package)],
                             check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(scripts)) as archive:
        for name in ("postinst", "postrm", "prerm"):
            member = archive.getmember("./" + name)
            assert member.mode & 0o777 == 0o755
            assert member.uid == member.gid == 0
