"""Tests for setuptools-scm support utilities."""

import pytest

from sphinx_polyversion.setuptools_scm_support import (
    create_setuptools_scm_env,
    extract_version_from_ref_name,
)


class TestExtractVersionFromRefName:
    """Test the extract_version_from_ref_name function."""

    def test_semantic_version_with_v_prefix(self):
        """Test extraction from version tag with 'v' prefix."""
        assert extract_version_from_ref_name("v1.2.3") == "1.2.3"
        assert extract_version_from_ref_name("v2.0.0") == "2.0.0"
        assert extract_version_from_ref_name("v10.15.20") == "10.15.20"

    def test_semantic_version_without_prefix(self):
        """Test extraction from plain version tag."""
        assert extract_version_from_ref_name("1.2.3") == "1.2.3"
        assert extract_version_from_ref_name("2.0.0") == "2.0.0"
        assert extract_version_from_ref_name("0.1.0") == "0.1.0"

    def test_version_with_various_prefixes(self):
        """Test extraction with different prefixes."""
        assert extract_version_from_ref_name("version-1.2.3") == "1.2.3"
        assert extract_version_from_ref_name("release-2.0.0") == "2.0.0"
        assert extract_version_from_ref_name("rel-1.5.0") == "1.5.0"

    def test_version_with_prerelease_suffixes(self):
        """Test extraction with prerelease suffixes."""
        assert extract_version_from_ref_name("v1.2.3-alpha") == "1.2.3-alpha"
        assert extract_version_from_ref_name("v1.2.3-alpha1") == "1.2.3-alpha1"
        assert extract_version_from_ref_name("v1.2.3-beta") == "1.2.3-beta"
        assert extract_version_from_ref_name("v1.2.3-rc1") == "1.2.3-rc1"
        assert extract_version_from_ref_name("v1.2.3-pre") == "1.2.3-pre"

    def test_version_with_post_release_suffixes(self):
        """Test extraction with post-release suffixes."""
        assert extract_version_from_ref_name("v1.2.3.post1") == "1.2.3.post1"
        assert extract_version_from_ref_name("v1.2.3-post1") == "1.2.3-post1"
        assert extract_version_from_ref_name("v1.2.3_post1") == "1.2.3_post1"

    def test_version_with_dev_suffixes(self):
        """Test extraction with dev suffixes."""
        assert extract_version_from_ref_name("v1.2.3-dev") == "1.2.3-dev"
        assert extract_version_from_ref_name("v1.2.3.dev1") == "1.2.3.dev1"

    def test_version_with_local_version(self):
        """Test extraction with local version identifier."""
        assert extract_version_from_ref_name("v1.2.3+local.1") == "1.2.3+local.1"
        assert extract_version_from_ref_name("v1.2.3+abc123") == "1.2.3+abc123"

    def test_two_part_version(self):
        """Test extraction of two-part versions."""
        assert extract_version_from_ref_name("v1.2") == "1.2"
        assert extract_version_from_ref_name("2.0") == "2.0"

    def test_single_digit_version(self):
        """Test extraction of single digit versions."""
        assert extract_version_from_ref_name("v1") == "1"
        assert extract_version_from_ref_name("2") == "2"

    def test_four_part_version(self):
        """Test extraction of four-part versions."""
        assert extract_version_from_ref_name("v1.2.3.4") == "1.2.3.4"
        assert extract_version_from_ref_name("2.1.0.5") == "2.1.0.5"

    def test_non_version_refs(self):
        """Test that non-version refs return None."""
        assert extract_version_from_ref_name("main") is None
        assert extract_version_from_ref_name("master") is None
        assert extract_version_from_ref_name("develop") is None
        assert extract_version_from_ref_name("feature-branch") is None
        assert extract_version_from_ref_name("fix-bug") is None

    def test_invalid_version_strings(self):
        """Test that invalid version strings return None."""
        assert extract_version_from_ref_name("v1.2.3.4.5") is None  # Too many parts (5)
        assert extract_version_from_ref_name("versionabc") is None
        assert extract_version_from_ref_name("v") is None
        assert extract_version_from_ref_name("version-") is None

    def test_case_insensitive_prefixes(self):
        """Test that prefix matching is case insensitive."""
        assert extract_version_from_ref_name("V1.2.3") == "1.2.3"
        assert extract_version_from_ref_name("VERSION-1.2.3") == "1.2.3"
        assert extract_version_from_ref_name("Release-1.2.3") == "1.2.3"


class TestCreateSetuptoolsScmEnv:
    """Test the create_setuptools_scm_env function."""

    def test_with_package_name(self):
        """Test creation with package name."""
        env = create_setuptools_scm_env("v1.2.3", "mypackage")
        assert env == {"SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MYPACKAGE": "1.2.3"}

    def test_with_package_name_normalization(self):
        """Test package name normalization."""
        env = create_setuptools_scm_env("v1.2.3", "my-package.name")
        assert env == {"SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MY_PACKAGE_NAME": "1.2.3"}
        
        env = create_setuptools_scm_env("v1.2.3", "MyPackage")
        assert env == {"SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MYPACKAGE": "1.2.3"}

    def test_without_package_name(self):
        """Test creation without package name (fallback)."""
        env = create_setuptools_scm_env("v1.2.3")
        assert env == {"SETUPTOOLS_SCM_PRETEND_VERSION": "1.2.3"}

    def test_with_non_version_ref(self):
        """Test that non-version refs return empty dict."""
        env = create_setuptools_scm_env("main", "mypackage")
        assert env == {}
        
        env = create_setuptools_scm_env("feature-branch")
        assert env == {}

    def test_with_complex_version(self):
        """Test with complex version strings."""
        env = create_setuptools_scm_env("v1.2.3-alpha1+local", "pkg")
        assert env == {"SETUPTOOLS_SCM_PRETEND_VERSION_FOR_PKG": "1.2.3-alpha1+local"}

    def test_with_empty_package_name(self):
        """Test with empty package name."""
        env = create_setuptools_scm_env("v1.2.3", "")
        assert env == {"SETUPTOOLS_SCM_PRETEND_VERSION": "1.2.3"}
        
        env = create_setuptools_scm_env("v1.2.3", None)
        assert env == {"SETUPTOOLS_SCM_PRETEND_VERSION": "1.2.3"}