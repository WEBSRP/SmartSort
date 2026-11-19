"""Download-only extraction boundary: bounded JSON, kill/reap, no Qt or pool."""

import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import threading
import time

from src.core.file_intelligence.context import ExtractedMetadata


MAX_OUTPUT_BYTES = 1024 * 1024
_SLOTS = threading.BoundedSemaphore(2)
_WORKER_CODE = "from src.core.file_intelligence.extractors.isolated import _worker_main; _worker_main()"


def _failure(status):
    return ExtractedMetadata(extractor_name="download-worker", extraction_status=status,
                             error_message="Bounded download extraction unavailable")


def extract_metadata(file_path, timeout_seconds):
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or
            not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
        return _failure("TIMEOUT")
    deadline = time.monotonic() + min(2.0, timeout_seconds)
    if not _SLOTS.acquire(timeout=max(0, deadline - time.monotonic())):
        return _failure("TIMEOUT")
    process = None
    completed = False
    try:
        path = os.fsdecode(os.fspath(file_path))
        if not path or len(path) > 4096 or "\0" in path:
            return _failure("FAILED")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _failure("TIMEOUT")
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(Path(__file__).resolve().parents[4]), env.get("PYTHONPATH")]))
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        request = json.dumps({"path": path, "timeout": remaining})
        process = subprocess.Popen([sys.executable, "-B", "-c", _WORKER_CODE, request],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            start_new_session=True, env=env)
        output = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return _failure("TIMEOUT")
                events = selector.select(remaining)
                if not events:
                    return _failure("TIMEOUT")
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    selector.unregister(process.stdout)
                    break
                output.extend(chunk)
                if len(output) > MAX_OUTPUT_BYTES:
                    return _failure("FAILED")
        process.wait(timeout=max(.001, deadline - time.monotonic()))
        if process.returncode:
            return _failure("FAILED")
        result = ExtractedMetadata.from_dict(json.loads(output))
        completed = True
        return result
    except subprocess.TimeoutExpired:
        return _failure("TIMEOUT")
    except Exception:
        return _failure("FAILED")
    finally:
        if process is not None:
            if not completed or process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()
            process.stdout.close()
        _SLOTS.release()


def _worker_main():
    import contextlib
    import resource
    import stat
    try:
        request = json.loads(sys.argv[1])
        for which, limit in ((resource.RLIMIT_AS, 512 * 1024 * 1024),
                             (resource.RLIMIT_CPU, max(1, math.ceil(request["timeout"])))):
            _, hard = resource.getrlimit(which)
            ceiling = limit if hard == resource.RLIM_INFINITY else min(limit, hard)
            resource.setrlimit(which, (ceiling, ceiling))
        from src.core.file_intelligence.extractors.base import ExtractorRegistry
        from src.core.file_intelligence.extractors.pdf import PdfExtractor, _extract_pdf
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
            registry = ExtractorRegistry()
            extractor = registry.get_extractor(request["path"])
            if isinstance(extractor, PdfExtractor):
                # Already isolated: reuse the bounded PDF parser directly,
                # avoiding a second nested interpreter/timeout lifecycle.
                descriptor = os.open(request["path"], os.O_RDONLY | os.O_NONBLOCK)
                with os.fdopen(descriptor, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ValueError("Input must be regular")
                    result = _extract_pdf(stream, PdfExtractor.MAX_TEXT_BYTES)
            elif extractor is None:
                result = ExtractedMetadata(extraction_status="UNSUPPORTED")
            else:
                result = extractor.extract(request["path"])
        output = json.dumps(result.to_dict(), ensure_ascii=True)
        if len(output) > MAX_OUTPUT_BYTES:
            output = json.dumps(_failure("FAILED").to_dict())
    except Exception:
        output = json.dumps(_failure("FAILED").to_dict())
    print(output)
