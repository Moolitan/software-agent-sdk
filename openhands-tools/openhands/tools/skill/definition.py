"""Skill tool — lets the agent load skill guides on demand."""

import os
from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import Field

from openhands.sdk.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    register_tool,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


class SkillAction(Action):
    """Input schema for the skill tool."""

    name: str = Field(
        description=(
            "The skill name to load (e.g. 'xlsx', 'docx', 'pptx', 'pdf'). "
            "Use 'list' to see all available skills."
        )
    )


class SkillObservation(Observation):
    """Output schema for the skill tool."""

    skill_name: str = Field(description="The skill that was loaded")
    skill_path: str = Field(default="", description="Path to the SKILL.md file")


TOOL_DESCRIPTION = """\
Load a skill guide to get best practices, correct libraries, and proven patterns \
for a specific task or domain.

Usage:
* skill(name="list")  — show all available skills with descriptions.
* skill(name="<skill_name>")  — load the full guide for a specific skill.

IMPORTANT: Before writing code for a task, call this tool with name="list" to \
check if a relevant skill exists. If one matches, load it and follow its guidance.\
"""


class SkillTool(ToolDefinition[SkillAction, SkillObservation]):
    """Tool that lets the agent load skill guides on demand."""

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState",
        skills_dir: str = "",
    ) -> Sequence["SkillTool"]:
        from openhands.tools.skill.impl import SkillExecutor

        # Resolve skills directory
        if not skills_dir:
            skills_dir = os.path.join(
                str(conv_state.workspace.working_dir), ".agents", "skills"
            )

        executor = SkillExecutor(skills_dir=skills_dir)

        # Build description with available skill names
        skill_names = executor.list_skill_names()
        desc = TOOL_DESCRIPTION
        if skill_names:
            desc += f"\n\nAvailable skills: {', '.join(sorted(skill_names))}"

        return [
            cls(
                description=desc,
                action_type=SkillAction,
                observation_type=SkillObservation,
                annotations=ToolAnnotations(
                    title="skill",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


register_tool(SkillTool.name, SkillTool)
