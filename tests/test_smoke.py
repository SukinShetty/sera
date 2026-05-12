"""
tests/test_smoke.py — Session 0 smoke tests for the SERA shared foundation.

These tests verify that the core building blocks of SERA work correctly
before any other session builds on top of them.

Run all tests:
    python -m pytest tests/test_smoke.py -v

Each test has a clear description of what it's checking and why it matters.
"""

import sys
import tempfile
from pathlib import Path

import pytest

# Make sure Python can find the SERA modules regardless of where pytest is run from
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config import load_config, get_path, PROJECT_ROOT
from shared.file_io import ensure_dir, read_markdown, write_markdown
from shared.validators import validate_schema, assert_valid


# ===========================================================================
# TEST 1 — Config loads correctly
# ===========================================================================

class TestConfig:

    def test_config_loads_and_has_required_sections(self):
        """
        The sera_config.json file must load without errors and contain
        the 'project' and 'paths' sections that the rest of SERA depends on.
        """
        config = load_config()

        assert isinstance(config, dict), "Config should be a dictionary"
        assert "project" in config, "Config must have a 'project' section"
        assert "paths" in config, "Config must have a 'paths' section"

    def test_config_project_name_is_correct(self):
        """The project name in the config must match the expected SERA name."""
        config = load_config()
        assert config["project"]["name"] == "SERA Vault OS"

    def test_config_paths_are_strings(self):
        """All path values in the config must be strings (not empty, not None)."""
        config = load_config()
        for key, value in config["paths"].items():
            if key.startswith("_"):
                continue  # Skip comment keys
            assert isinstance(value, str), f"Path '{key}' must be a string, got {type(value)}"
            assert len(value) > 0, f"Path '{key}' must not be empty"

    def test_get_path_returns_absolute_path(self):
        """get_path() must return an absolute Path object rooted at the project root."""
        vault_path = get_path("vault_root")
        assert vault_path.is_absolute(), "get_path() must return an absolute path"
        assert str(PROJECT_ROOT) in str(vault_path), "Path must be inside the project root"

    def test_config_missing_file_raises_clear_error(self, tmp_path):
        """If sera_config.json is missing, the error message must be human-readable."""
        fake_path = tmp_path / "nonexistent_config.json"
        with pytest.raises(FileNotFoundError) as exc_info:
            load_config(fake_path)
        assert "sera_config.json" in str(exc_info.value).lower() or "nonexistent" in str(exc_info.value).lower()


# ===========================================================================
# TEST 2 — ensure_dir works
# ===========================================================================

class TestEnsureDir:

    def test_creates_single_directory(self, tmp_path):
        """ensure_dir must create a folder that does not exist yet."""
        target = tmp_path / "new_folder"
        assert not target.exists()
        result = ensure_dir(target)
        assert result.exists()
        assert result.is_dir()

    def test_creates_nested_directories(self, tmp_path):
        """ensure_dir must create multiple levels of nested folders at once."""
        target = tmp_path / "level1" / "level2" / "level3"
        assert not target.exists()
        ensure_dir(target)
        assert target.exists()
        assert target.is_dir()

    def test_does_not_fail_if_directory_already_exists(self, tmp_path):
        """Calling ensure_dir on an existing folder must not raise an error."""
        target = tmp_path / "existing"
        target.mkdir()
        ensure_dir(target)  # Should not raise
        assert target.exists()

    def test_returns_path_object(self, tmp_path):
        """ensure_dir must return a Path object pointing to the directory."""
        target = tmp_path / "my_dir"
        result = ensure_dir(target)
        assert isinstance(result, Path)
        assert result == target


# ===========================================================================
# TEST 3 — Markdown read/write works
# ===========================================================================

class TestMarkdownReadWrite:

    def test_write_and_read_back_with_frontmatter(self, tmp_path):
        """
        Write a Markdown file with frontmatter metadata, then read it back.
        The frontmatter and body must both be recovered correctly.
        """
        file_path = tmp_path / "notes" / "research.md"
        frontmatter = {
            "title": "Market Hypothesis",
            "client": "Acme Corp",
            "status": "draft",
        }
        body = "# Hypothesis\n\nUsers prefer a shorter onboarding flow."

        write_markdown(file_path, body, frontmatter)
        assert file_path.exists()

        read_fm, read_body = read_markdown(file_path)

        assert read_fm.get("title") == "Market Hypothesis"
        assert read_fm.get("client") == "Acme Corp"
        assert read_fm.get("status") == "draft"
        assert "Users prefer a shorter onboarding flow" in read_body

    def test_write_without_frontmatter(self, tmp_path):
        """Writing a file with no frontmatter should still work correctly."""
        file_path = tmp_path / "plain.md"
        body = "# Plain note\n\nNo metadata here."
        write_markdown(file_path, body)

        read_fm, read_body = read_markdown(file_path)
        assert read_fm == {}
        assert "Plain note" in read_body

    def test_write_creates_parent_directories(self, tmp_path):
        """write_markdown must create missing parent folders automatically."""
        file_path = tmp_path / "deep" / "nested" / "folder" / "note.md"
        write_markdown(file_path, "Content here.")
        assert file_path.exists()

    def test_read_missing_file_raises_clear_error(self, tmp_path):
        """Reading a file that doesn't exist must raise a FileNotFoundError."""
        missing = tmp_path / "ghost.md"
        with pytest.raises(FileNotFoundError) as exc_info:
            read_markdown(missing)
        assert "ghost.md" in str(exc_info.value)

    def test_roundtrip_preserves_special_characters(self, tmp_path):
        """Frontmatter values with colons must survive a write-then-read roundtrip."""
        file_path = tmp_path / "special.md"
        frontmatter = {"title": "Q1: Market Research", "client": "Acme Corp"}
        write_markdown(file_path, "Body content.", frontmatter)
        read_fm, _ = read_markdown(file_path)
        assert "Market Research" in read_fm.get("title", "")


# ===========================================================================
# TEST 4 — Validator gives readable errors when schema is missing or wrong
# ===========================================================================

class TestValidators:

    RESEARCH_SCHEMA = {
        "required": ["title", "client", "status"],
        "properties": {
            "status": {"allowed": ["draft", "active", "complete"]},
            "title":  {"type": "string"},
        }
    }

    def test_valid_data_returns_no_errors(self):
        """Valid data must return an empty error list."""
        good_data = {"title": "Test", "client": "Acme", "status": "draft"}
        errors = validate_schema(good_data, self.RESEARCH_SCHEMA, context="note")
        assert errors == []

    def test_missing_required_fields_reported_clearly(self):
        """
        If required fields are missing, validate_schema must return
        plain-English errors that name the missing fields.
        """
        bad_data = {"title": "Test Only"}  # missing 'client' and 'status'
        errors = validate_schema(bad_data, self.RESEARCH_SCHEMA, context="research_note")

        assert len(errors) >= 2
        assert any("client" in e for e in errors), f"'client' not mentioned in errors: {errors}"
        assert any("status" in e for e in errors), f"'status' not mentioned in errors: {errors}"
        assert all("research_note" in e for e in errors), "Context label must appear in every error"

    def test_invalid_allowed_value_reported(self):
        """An invalid value for an 'allowed' constraint must be clearly reported."""
        bad_data = {"title": "Test", "client": "Acme", "status": "unknown_status"}
        errors = validate_schema(bad_data, self.RESEARCH_SCHEMA, context="note")
        assert any("status" in e and "unknown_status" in e for e in errors)

    def test_wrong_type_reported(self):
        """A field with the wrong type must produce a clear error."""
        bad_data = {"title": 12345, "client": "Acme", "status": "draft"}
        errors = validate_schema(bad_data, self.RESEARCH_SCHEMA, context="note")
        assert any("title" in e and "string" in e for e in errors)

    def test_assert_valid_raises_on_bad_data(self):
        """assert_valid must raise ValueError with a readable message on invalid data."""
        schema = {"required": ["name", "email"]}
        bad_data = {}

        with pytest.raises(ValueError) as exc_info:
            assert_valid(bad_data, schema, context="user_profile")

        message = str(exc_info.value)
        assert "name" in message
        assert "email" in message
        assert "user_profile" in message

    def test_assert_valid_passes_silently_on_good_data(self):
        """assert_valid must not raise anything when the data is valid."""
        schema = {"required": ["name"]}
        good_data = {"name": "Acme Corp"}
        assert_valid(good_data, schema, context="client")  # Must not raise

    def test_non_dict_data_returns_clear_error(self):
        """Passing a non-dict value (e.g., a list) must return a clear error."""
        errors = validate_schema(["not", "a", "dict"], self.RESEARCH_SCHEMA, context="bad_input")
        assert len(errors) == 1
        assert "dictionary" in errors[0].lower()
