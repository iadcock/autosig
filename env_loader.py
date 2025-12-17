"""
Centralized environment variable loader.
Checks multiple sources to find configuration values:
1. Direct os.getenv()
2. REPLIT_* prefixed variables (for deployments)
3. config_local.py fallback (optional, gitignored)
"""

import os
from typing import Optional


def load_env(key: str) -> Optional[str]:
    """
    Load an environment variable from multiple sources.
    
    Checks in order:
    1. os.getenv(key)
    2. os.getenv(f"REPLIT_{key}")
    3. config_local.py attribute
    
    Returns the first non-empty value found, or None.
    """
    value = os.getenv(key)
    if value:
        return value
    
    value = os.getenv(f"REPLIT_{key}")
    if value:
        return value
    
    try:
        import config_local
        value = getattr(config_local, key, None)
        if value:
            return value
    except ImportError:
        pass
    except Exception:
        pass
    
    return None


def get_checked_sources() -> list:
    """Return list of sources that were checked."""
    sources = ["os.getenv", "REPLIT_*"]
    try:
        import config_local
        sources.append("config_local.py")
    except ImportError:
        sources.append("config_local.py (not found)")
    return sources


def get_runtime_type() -> str:
    """Determine if running in deployment or workspace."""
    if os.getenv("REPL_SLUG") and os.getenv("REPLIT_DEPLOYMENT"):
        return "deployment"
    elif os.getenv("REPL_SLUG"):
        return "workspace"
    else:
        return "unknown"


def diagnose_env(keys: list) -> dict:
    """
    Generate diagnostic info for environment variables.
    Does NOT expose actual secret values.
    
    Args:
        keys: List of environment variable names to check
        
    Returns:
        Dict with runtime info and key presence status
    """
    result = {
        "runtime": get_runtime_type(),
        "checked_sources": get_checked_sources()
    }
    
    for key in keys:
        value = load_env(key)
        result[key] = value is not None and len(value) > 0
    
    return result
