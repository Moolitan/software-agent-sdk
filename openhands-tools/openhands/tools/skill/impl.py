"""Skill tool executor — reads SKILL.md files from the skills directory."""

from pathlib import Path
from typing import TYPE_CHECKING

from openhands.sdk.tool import ToolExecutor


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation

from openhands.tools.skill.definition import SkillAction, SkillObservation


class SkillExecutor(ToolExecutor[SkillAction, SkillObservation]):
    """Reads skill guides from the skills directory."""

    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir).resolve()
        # Pre-scan available skills (directories containing SKILL.md)
        self._skills: dict[str, Path] = {}
        if self.skills_dir.is_dir():
            for entry in sorted(self.skills_dir.iterdir()):
                skill_md = entry / "SKILL.md"
                if entry.is_dir() and skill_md.is_file():
                    self._skills[entry.name] = skill_md

    def list_skill_names(self) -> list[str]:
        return list(self._skills.keys())

    def _list_skills(self) -> str:
        """Return a formatted list of available skills with descriptions."""
        if not self._skills:
            return "No skills available."

        lines = [f"Available skills ({len(self._skills)}):\n"]
        for name, path in sorted(self._skills.items()):
            # Extract description from SKILL.md frontmatter
            desc = self._extract_description(path)
            lines.append(f"  - {name}: {desc}")
        lines.append('\nTo load a skill, call: skill(name="<skill_name>")')
        return "\n".join(lines)

    @staticmethod
    def _extract_description(skill_md: Path) -> str:
        """Extract the description field from SKILL.md YAML frontmatter."""
        try:
            text = skill_md.read_text(encoding="utf-8")
        except Exception:
            return "(cannot read)"

        in_frontmatter = False
        desc_lines: list[str] = []
        collecting_desc = False

        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "---":
                if in_frontmatter:
                    break  # end of frontmatter
                in_frontmatter = True
                continue
            if not in_frontmatter:
                continue

            if stripped.startswith("description:"):
                val = stripped[len("description:") :].strip().strip('"').strip("'")
                if val:
                    desc_lines.append(val)
                collecting_desc = True
                continue

            if collecting_desc:
                # Continuation lines (indented or quoted)
                if line.startswith(" ") or line.startswith("\t"):
                    desc_lines.append(stripped.strip('"').strip("'"))
                else:
                    collecting_desc = False

        desc = " ".join(desc_lines)
        # Truncate to ~200 chars for the list view
        if len(desc) > 200:
            desc = desc[:197] + "..."
        return desc or "(no description)"

    def __call__(
        self,
        action: SkillAction,
        _conversation: "LocalConversation | None" = None,
    ) -> SkillObservation:
        name = action.name.strip()

        # Special case: list all skills
        if name == "list":
            return SkillObservation.from_text(
                text=self._list_skills(),
                skill_name="list",
                skill_path="",
            )

        # Look up the skill
        if name not in self._skills:
            available = ", ".join(sorted(self._skills.keys()))
            return SkillObservation.from_text(
                text=(
                    f"Skill '{name}' not found.\n"
                    f"Available skills: {available}\n"
                    f'Use skill(name="list") to see descriptions.'
                ),
                skill_name=name,
                skill_path="",
                is_error=True,
            )

        skill_md = self._skills[name]
        try:
            content = skill_md.read_text(encoding="utf-8")
        except Exception as e:
            return SkillObservation.from_text(
                text=f"Error reading {skill_md}: {e}",
                skill_name=name,
                skill_path=str(skill_md),
                is_error=True,
            )

        # Also list related resource files (scripts/, references/)
        skill_dir = skill_md.parent
        resources: list[str] = []
        for sub in ["scripts", "references", "assets"]:
            sub_dir = skill_dir / sub
            if sub_dir.is_dir():
                files = sorted(f.name for f in sub_dir.iterdir() if f.is_file())
                if files:
                    resources.append(f"  {sub}/: {', '.join(files)}")

        result = content
        if resources:
            result += "\n\n--- Skill Resources ---\n" + "\n".join(resources)

        return SkillObservation.from_text(
            text=result,
            skill_name=name,
            skill_path=str(skill_md),
        )
