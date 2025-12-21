"""
JSONL utilities with atomic writes and file locking.
Ensures data integrity for all JSONL file operations.
"""

import os
import json
import tempfile
import shutil
from typing import Any, List, Optional
from datetime import datetime

import portalocker


def ensure_dir(filepath: str) -> None:
    """Ensure the directory for a file exists."""
    dirname = os.path.dirname(filepath)
    if dirname:
        os.makedirs(dirname, exist_ok=True)


def atomic_append_jsonl(filepath: str, data: dict) -> None:
    """
    Atomically append a JSON object to a JSONL file with file locking.
    
    This ensures:
    1. File is locked during write to prevent corruption
    2. Data is flushed before unlock
    3. Directory is created if needed
    """
    ensure_dir(filepath)
    
    line = json.dumps(data, default=str) + "\n"
    
    with portalocker.Lock(filepath, mode='a', timeout=10) as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def atomic_write_json(filepath: str, data: Any) -> None:
    """
    Atomically write JSON data to a file.
    
    Uses write-to-temp-then-rename pattern for atomicity.
    """
    ensure_dir(filepath)
    
    dirname = os.path.dirname(filepath) or "."
    
    with tempfile.NamedTemporaryFile(
        mode='w',
        dir=dirname,
        suffix='.tmp',
        delete=False
    ) as tmp:
        json.dump(data, tmp, indent=2, default=str)
        tmp.flush()
        os.fsync(tmp.fileno())
        temp_path = tmp.name
    
    shutil.move(temp_path, filepath)


def read_jsonl(filepath: str, limit: Optional[int] = None) -> List[dict]:
    """
    Read a JSONL file with file locking.
    
    Args:
        filepath: Path to the JSONL file
        limit: Optional limit on number of records (from end)
    
    Returns:
        List of parsed JSON objects
    """
    if not os.path.exists(filepath):
        return []
    
    results = []
    
    try:
        with portalocker.Lock(filepath, mode='r', timeout=10) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except (IOError, portalocker.LockException):
        return []
    
    if limit and limit > 0:
        return results[-limit:]
    
    return results


def read_jsonl_reverse(filepath: str, limit: int = 25) -> List[dict]:
    """
    Read the last N records from a JSONL file.
    More efficient for large files when only recent data is needed.
    """
    if not os.path.exists(filepath):
        return []
    
    results = read_jsonl(filepath, limit=limit)
    results.reverse()
    return results


def backup_jsonl(filepath: str) -> Optional[str]:
    """
    Create a timestamped backup of a JSONL file.
    
    Returns the backup filepath or None if failed.
    """
    if not os.path.exists(filepath):
        return None
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.dirname(filepath) or "."
    basename = os.path.basename(filepath)
    backup_path = os.path.join(backup_dir, f"{basename}.{timestamp}.bak")
    
    try:
        shutil.copy2(filepath, backup_path)
        return backup_path
    except IOError:
        return None
