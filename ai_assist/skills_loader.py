"""Load and manage Agent Skills following agentskills.io specification"""

import re
import subprocess
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .config import get_config_dir


class SkillMetadata(BaseModel):
    """Skill metadata from YAML frontmatter (progressive disclosure)"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str  # Required, 1-64 chars
    description: str  # Required, 1-1024 chars
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=list)

    # Internal fields
    skill_path: Path
    source_type: str  # 'git' or 'local'
    source_url: str | None = None

    def validate(self):
        """Validate skill metadata against agentskills.io spec"""
        # Name: 1-64 chars, lowercase + hyphens, no consecutive hyphens
        if not 1 <= len(self.name) <= 64:
            raise ValueError(f"Name must be 1-64 characters: {self.name}")

        if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", self.name):
            raise ValueError(f"Invalid name format: {self.name}")

        if "--" in self.name:
            raise ValueError(f"Name cannot contain consecutive hyphens: {self.name}")

        # Description: 1-1024 chars
        if not 1 <= len(self.description) <= 1024:
            raise ValueError("Description must be 1-1024 characters")

        # Compatibility: max 500 chars
        if self.compatibility and len(self.compatibility) > 500:
            raise ValueError("Compatibility must be <= 500 characters")

        # Directory name must match skill name
        if self.skill_path.name != self.name:
            raise ValueError(f"Directory '{self.skill_path.name}' must match name '{self.name}'")


class SkillContent(BaseModel):
    """Full skill content including body"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    metadata: SkillMetadata
    body: str  # Markdown content after frontmatter

    # File references (loaded on-demand)
    scripts: dict[str, Path] = Field(default_factory=dict)
    references: dict[str, Path] = Field(default_factory=dict)
    assets: dict[str, Path] = Field(default_factory=dict)


class SkillsLoader:
    """Load and manage Agent Skills from multiple sources"""

    def __init__(self):
        """Initialize skills loader"""
        self.cache_dir = get_config_dir() / "skills-cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load_skill_from_local(self, skill_path: Path) -> SkillContent:
        """Load a skill from a local directory

        Args:
            skill_path: Path to skill directory containing SKILL.md

        Returns:
            SkillContent with full skill data

        Raises:
            FileNotFoundError: If SKILL.md doesn't exist
            ValueError: If SKILL.md is invalid
        """
        skill_file = skill_path / "SKILL.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"SKILL.md not found in {skill_path}")

        # Parse SKILL.md
        metadata, body = self._parse_skill_file(skill_file, skill_path, "local", None)

        # Discover file references
        scripts = self._discover_files(skill_path / "scripts")
        references = self._discover_files(skill_path / "references")
        assets = self._discover_files(skill_path / "assets")

        return SkillContent(metadata=metadata, body=body, scripts=scripts, references=references, assets=assets)

    def load_skill_from_git(self, repo_url: str, skill_subpath: str, branch: str = "main") -> SkillContent:
        """Load a skill from a git repository

        Args:
            repo_url: Git repository URL (e.g., 'anthropics/skills')
            skill_subpath: Path to skill within repo (e.g., 'skills/pdf')
            branch: Git branch/tag to use

        Returns:
            SkillContent with full skill data

        Raises:
            FileNotFoundError: If skill doesn't exist in repo
            ValueError: If SKILL.md is invalid
        """
        # Clone/update repository
        repo_dir = self._ensure_repo_cached(repo_url, branch)

        # Navigate to skill directory
        skill_path = repo_dir / skill_subpath
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill path '{skill_subpath}' not found in repository")

        skill_file = skill_path / "SKILL.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"SKILL.md not found in {skill_path}")

        # Parse SKILL.md
        metadata, body = self._parse_skill_file(skill_file, skill_path, "git", repo_url)

        # Discover file references
        scripts = self._discover_files(skill_path / "scripts")
        references = self._discover_files(skill_path / "references")
        assets = self._discover_files(skill_path / "assets")

        return SkillContent(metadata=metadata, body=body, scripts=scripts, references=references, assets=assets)

    def _parse_skill_file(
        self, skill_file: Path, skill_path: Path, source_type: str, source_url: str | None
    ) -> tuple[SkillMetadata, str]:
        """Parse SKILL.md file into metadata and body

        Args:
            skill_file: Path to SKILL.md
            skill_path: Path to skill directory
            source_type: 'git' or 'local'
            source_url: Git URL if source_type is 'git'

        Returns:
            Tuple of (SkillMetadata, body_markdown)
        """
        content = skill_file.read_text()

        # Extract YAML frontmatter
        if not content.startswith("---\n"):
            raise ValueError("SKILL.md must start with YAML frontmatter (---)")

        parts = content.split("---\n", 2)
        if len(parts) < 3:
            raise ValueError("SKILL.md must have valid YAML frontmatter delimited by ---")

        frontmatter_text = parts[1]
        body = parts[2].strip()

        # Parse YAML
        try:
            frontmatter = yaml.safe_load(frontmatter_text)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML frontmatter: {e}") from e

        # Build metadata
        metadata = SkillMetadata(
            name=frontmatter["name"],
            description=frontmatter["description"],
            license=frontmatter.get("license"),
            compatibility=frontmatter.get("compatibility"),
            metadata=frontmatter.get("metadata", {}),
            allowed_tools=frontmatter.get("allowed-tools", "").split() if frontmatter.get("allowed-tools") else [],
            skill_path=skill_path,
            source_type=source_type,
            source_url=source_url,
        )

        # Validate metadata
        metadata.validate()

        return metadata, body

    def _ensure_repo_cached(self, repo_url: str, branch: str) -> Path:
        """Clone or update git repository to cache

        Args:
            repo_url: Repository URL (e.g., 'anthropics/skills' or 'https://github.com/anthropics/skills')
            branch: Branch/tag to checkout

        Returns:
            Path to cached repository
        """
        # Normalize repo URL to full GitHub URL
        if not repo_url.startswith("http"):
            # Assume GitHub
            repo_url = f"https://github.com/{repo_url}"

        # Generate cache directory name from repo URL and branch
        # e.g., 'anthropics_skills_main'
        cache_name = repo_url.replace("https://", "").replace("http://", "").replace("/", "_").replace(".", "_")
        cache_name = f"{cache_name}_{branch}"
        repo_cache_dir = self.cache_dir / cache_name

        if repo_cache_dir.exists():
            # Update existing repo
            try:
                subprocess.run(
                    ["git", "-C", str(repo_cache_dir), "fetch", "origin"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "-C", str(repo_cache_dir), "checkout", branch],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "-C", str(repo_cache_dir), "pull", "origin", branch],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to update repository: {e.stderr}")
                # Continue with cached version
        else:
            # Clone new repo
            try:
                subprocess.run(
                    ["git", "clone", "--branch", branch, "--depth", "1", repo_url, str(repo_cache_dir)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                raise ValueError(f"Failed to clone repository: {e.stderr}") from e

        return repo_cache_dir

    def _discover_files(self, directory: Path) -> dict[str, Path]:
        """Discover files in a directory

        Args:
            directory: Directory to scan

        Returns:
            Dict mapping filename to full path
        """
        if not directory.exists():
            return {}

        files = {}
        for file_path in directory.iterdir():
            if file_path.is_file():
                files[file_path.name] = file_path

        return files
