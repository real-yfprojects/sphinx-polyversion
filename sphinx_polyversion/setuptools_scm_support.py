"""Setuptools-scm compatibility utilities."""

from __future__ import annotations

import re
from typing import Dict

# Maximum number of version parts allowed (major.minor.patch.micro)
MAX_VERSION_PARTS = 4


def extract_version_from_ref_name(ref_name: str) -> str | None:
    """
    Extract a version string from a git reference name.

    This function attempts to extract version information from git tag or branch
    names to use with setuptools-scm's SETUPTOOLS_SCM_PRETEND_VERSION environment
    variable.

    Parameters
    ----------
    ref_name : str
        The git reference name (e.g., "v1.2.3", "1.0.0", "release-1.5.0")

    Returns
    -------
    str | None
        The extracted version string, or None if no version could be extracted

    Examples
    --------
    >>> extract_version_from_ref_name("v1.2.3")
    '1.2.3'
    >>> extract_version_from_ref_name("1.0.0")
    '1.0.0'
    >>> extract_version_from_ref_name("release-2.1.0")
    '2.1.0'
    >>> extract_version_from_ref_name("main")
    None

    """
    # Remove common prefixes (case insensitive, ordered by length to avoid partial matches)
    cleaned_name = ref_name
    for prefix in ["version-", "release-", "rel-", "v"]:
        if cleaned_name.lower().startswith(prefix.lower()):
            cleaned_name = cleaned_name[len(prefix):]
            break

    # Pattern to match semantic version numbers with more flexibility
    # Matches: X.Y.Z, X.Y, X, with optional prerelease/dev/post suffixes
    version_pattern = r"^(\d+(?:\.\d+)*(?:[-._]?(?:alpha|beta|rc|pre|post|dev)(?:\d+|\.?\d+)?)?(?:\+[a-zA-Z0-9._-]+)?)$"

    match = re.match(version_pattern, cleaned_name, re.IGNORECASE)
    if match:
        # Additional validation: reject overly complex version numbers
        # Extract just the numeric part before any suffix
        numeric_part = re.match(r'^(\d+(?:\.\d+)*)', cleaned_name)
        if numeric_part:
            version_parts = numeric_part.group(1).split('.')
            # Allow up to 4 numeric parts (e.g., major.minor.patch.micro)
            if len(version_parts) <= MAX_VERSION_PARTS and all(part.isdigit() for part in version_parts):
                return cleaned_name

    return None


def create_setuptools_scm_env(ref_name: str, package_name: str | None = None) -> Dict[str, str]:
    """
    Create environment variables for setuptools-scm compatibility.

    This function creates the environment variables needed to make setuptools-scm
    work without a .git directory by using the SETUPTOOLS_SCM_PRETEND_VERSION
    mechanism.

    Parameters
    ----------
    ref_name : str
        The git reference name to extract version from
    package_name : str | None, optional
        The package name for the environment variable. If None, uses a generic
        fallback that should work for most cases.

    Returns
    -------
    Dict[str, str]
        Dictionary of environment variables to set

    Examples
    --------
    >>> create_setuptools_scm_env("v1.2.3", "mypackage")
    {'SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MYPACKAGE': '1.2.3'}
    >>> create_setuptools_scm_env("v1.2.3")
    {'SETUPTOOLS_SCM_PRETEND_VERSION': '1.2.3'}

    """
    version = extract_version_from_ref_name(ref_name)
    if version is None:
        return {}

    env_vars = {}

    if package_name:
        # Normalize package name (uppercase, replace hyphens/dots with underscores)
        normalized_name = package_name.upper().replace("-", "_").replace(".", "_")
        env_vars[f"SETUPTOOLS_SCM_PRETEND_VERSION_FOR_{normalized_name}"] = version
    else:
        # Fallback to generic version variable
        env_vars["SETUPTOOLS_SCM_PRETEND_VERSION"] = version

    return env_vars
