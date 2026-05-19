import os
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from openhands.sdk.tool import ToolExecutor


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation
from openhands.tools.file_editor.definition import (
    CommandLiteral,
    FileEditorAction,
    FileEditorObservation,
)
from openhands.tools.file_editor.editor import FileEditor
from openhands.tools.file_editor.exceptions import ToolError, ToolErrorType


# Binary / special-format extensions that should never be edited with file_editor
_UNSUPPORTED_EDIT_EXTENSIONS: set[str] = {
    ".xlsx",
    ".xls",
    ".xlsm",
    ".xlsb",  # Excel
    ".docx",
    ".doc",  # Word
    ".pptx",
    ".ppt",  # PowerPoint
    ".pdf",  # PDF
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".7z",  # Archives
    ".exe",
    ".dll",
    ".so",
    ".dylib",  # Binaries
    ".pyc",
    ".pyo",
    ".class",  # Compiled
    ".sqlite",
    ".db",  # Databases
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",  # Images (handled separately by editor)
    ".bmp",
    ".webp",
    ".ico",
    ".svg",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",  # Media
    ".mov",
    ".mkv",
    ".flac",
    ".ogg",
}


# Module-global editor instance (lazily initialized in file_editor)
_GLOBAL_EDITOR: FileEditor | None = None


class FileEditorExecutor(ToolExecutor):
    """File editor executor with configurable file restrictions."""

    def __init__(
        self,
        workspace_root: str | None = None,
        allowed_edits_files: list[str] | None = None,
    ):
        self.editor: FileEditor = FileEditor(workspace_root=workspace_root)
        self.allowed_edits_files: set[Path] | None = (
            {Path(f).resolve() for f in allowed_edits_files}
            if allowed_edits_files
            else None
        )
        # Track consecutive replacement mismatch failures per file
        self._mismatch_counts: dict[str, int] = defaultdict(int)

    def _check_unsupported_extension(
        self, path: str, command: str
    ) -> FileEditorObservation | None:
        """Pre-check: reject edits on binary/special-format files early."""
        if command == "view":
            return None  # viewing is always allowed

        ext = os.path.splitext(path)[1].lower()
        if ext in _UNSUPPORTED_EDIT_EXTENSIONS:
            return FileEditorObservation.from_text(
                text=(
                    f"Cannot edit '{path}': this is a {ext} file which is a "
                    f"binary or special format that cannot be modified with the "
                    f"text editor tool.\n"
                    f"Do NOT retry file_editor on this file. Instead:\n"
                    f"1. Check if a skill is available for handling {ext} files "
                    f"and use the skill-guided workflow.\n"
                    f"2. If no skill exists, write a script using an appropriate "
                    f"library to programmatically create or modify this file."
                ),
                command=command,
                is_error=True,
                error_type=ToolErrorType.UNSUPPORTED_EDIT_TARGET.value,
            )
        return None

    def _build_mismatch_observation(
        self,
        e: ToolError,
        command: CommandLiteral,
        path: str,
    ) -> FileEditorObservation:
        """Build an observation for replacement mismatch with escalating guidance."""
        self._mismatch_counts[path] += 1
        count = self._mismatch_counts[path]

        base_msg = e.message

        if count >= 2:
            guidance = (
                f"\n\n⚠ This is the {count}th consecutive replacement mismatch "
                f"on '{path}'. Your editing assumption for this file is invalid.\n"
                f"STOP retrying str_replace with large blocks on this file.\n"
                f"You MUST:\n"
                f"1. Use file_editor with command='view' to re-read the file's "
                f"current content.\n"
                f"2. Based on the ACTUAL current content, construct a new, "
                f"smaller, and more targeted edit.\n"
                f"3. If the file content has diverged significantly from your "
                f"expectation, consider using command='create' to rewrite it, "
                f"or use the 'insert' command for additions."
            )
        else:
            guidance = (
                f"\n\nYour old_str did not match the file's actual content. "
                f"Before retrying, you MUST re-read the file using "
                f"file_editor(command='view', path='{path}') to see the "
                f"current content, then construct a new edit based on what "
                f"is actually in the file. Use smaller, more targeted "
                f"replacements."
            )

        return FileEditorObservation.from_text(
            text=base_msg + guidance,
            command=command,
            is_error=True,
            error_type=ToolErrorType.REPLACEMENT_MISMATCH.value,
        )

    def __call__(
        self,
        action: FileEditorAction,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> FileEditorObservation:
        # Pre-check for unsupported file extensions
        ext_check = self._check_unsupported_extension(action.path, action.command)
        if ext_check is not None:
            return ext_check

        # Enforce allowed_edits_files restrictions
        if self.allowed_edits_files is not None and action.command != "view":
            action_path = Path(action.path).resolve()
            if action_path not in self.allowed_edits_files:
                return FileEditorObservation.from_text(
                    text=(
                        f"Operation '{action.command}' is not allowed "
                        f"on file '{action_path}'. "
                        f"Only the following files can be edited: "
                        f"{sorted(str(p) for p in self.allowed_edits_files)}"
                    ),
                    command=action.command,
                    is_error=True,
                )

        result: FileEditorObservation | None = None
        try:
            result = self.editor(
                command=action.command,
                path=action.path,
                file_text=action.file_text,
                view_range=action.view_range,
                old_str=action.old_str,
                new_str=action.new_str,
                insert_line=action.insert_line,
            )
            # On success, reset the mismatch counter for this file
            if action.command == "str_replace":
                self._mismatch_counts[action.path] = 0
        except ToolError as e:
            if e.error_type == ToolErrorType.REPLACEMENT_MISMATCH:
                result = self._build_mismatch_observation(
                    e, action.command, action.path
                )
            elif e.error_type == ToolErrorType.UNSUPPORTED_EDIT_TARGET:
                result = FileEditorObservation.from_text(
                    text=e.message,
                    command=action.command,
                    is_error=True,
                    error_type=ToolErrorType.UNSUPPORTED_EDIT_TARGET.value,
                )
            else:
                result = FileEditorObservation.from_text(
                    text=e.message,
                    command=action.command,
                    is_error=True,
                    error_type=ToolErrorType.EXECUTION_FAILURE.value,
                )
        assert result is not None, "file_editor should always return a result"
        return result


def file_editor(
    command: CommandLiteral,
    path: str,
    file_text: str | None = None,
    view_range: list[int] | None = None,
    old_str: str | None = None,
    new_str: str | None = None,
    insert_line: int | None = None,
) -> FileEditorObservation:
    """A global FileEditor instance to be used by the tool."""

    global _GLOBAL_EDITOR
    if _GLOBAL_EDITOR is None:
        _GLOBAL_EDITOR = FileEditor()

    result: FileEditorObservation | None = None
    try:
        result = _GLOBAL_EDITOR(
            command=command,
            path=path,
            file_text=file_text,
            view_range=view_range,
            old_str=old_str,
            new_str=new_str,
            insert_line=insert_line,
        )
    except ToolError as e:
        result = FileEditorObservation.from_text(
            text=e.message,
            command=command,
            is_error=True,
            error_type=e.error_type.value if hasattr(e, "error_type") else None,
        )
    assert result is not None, "file_editor should always return a result"
    return result
