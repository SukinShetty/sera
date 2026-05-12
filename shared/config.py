"""
shared/config.py — Loads and provides access to SERA's main configuration.

Think of this as the "settings manager."
Every part of SERA reads its settings from here instead of hard-coding paths
or values into individual files. That way, you only need to change one file
(sera_config.json) to update the whole system.

Usage in other files:
    from shared.config import CONFIG, PROJECT_ROOT

    vault_path = PROJECT_ROOT / CONFIG["paths"]["vault_root"]
"""

import json
from pathlib import Path

# The project root is two levels up from this file: shared/config.py → shared/ → project root
PROJECT_ROOT = Path(__file__).parent.parent


def load_config(config_path: Path = None) -> dict:
    """
    Load and return the main SERA configuration from sera_config.json.

    If no path is provided, it automatically finds sera_config.json in the
    project root folder. Raises a clear error if the file is missing.
    """
    if config_path is None:
        config_path = PROJECT_ROOT / "sera_config.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"\n[SERA Config Error] Configuration file not found at:\n  {config_path}\n\n"
            "Please make sure 'sera_config.json' exists in the project root folder.\n"
            "If you just cloned the repo, the file should already be there."
        )

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    _validate_config_structure(config, config_path)
    return config


def _validate_config_structure(config: dict, path: Path) -> None:
    """
    Check that the config file has the minimum required sections.
    Raises a clear, non-technical error if anything is missing.
    """
    required_sections = ["project", "paths"]
    missing = [s for s in required_sections if s not in config]

    if missing:
        raise ValueError(
            f"\n[SERA Config Error] The file '{path.name}' is missing required sections:\n"
            + "\n".join(f"  - '{s}'" for s in missing)
            + "\n\nPlease check sera_config.json and make sure it has 'project' and 'paths' sections."
        )


def get_path(key: str) -> Path:
    """
    Convenience helper: get a resolved, absolute path from the 'paths' section.

    Example: get_path("vault_root") returns the full path to the vault folder.
    """
    raw = CONFIG.get("paths", {}).get(key)
    if raw is None:
        raise KeyError(
            f"\n[SERA Config Error] Path key '{key}' not found in sera_config.json 'paths' section.\n"
            f"Available keys: {list(CONFIG.get('paths', {}).keys())}"
        )
    return PROJECT_ROOT / raw


# Load the config once when this module is first imported.
# All other modules should import CONFIG from here rather than loading the file themselves.
CONFIG = load_config()
