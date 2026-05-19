from enum import Enum


class ToolErrorType(str, Enum):
    """Classification of tool errors for targeted recovery guidance."""

    REPLACEMENT_MISMATCH = "replacement_mismatch"
    UNSUPPORTED_EDIT_TARGET = "unsupported_edit_target"
    EXECUTION_FAILURE = "execution_failure"


class ToolError(Exception):
    """Raised when a tool encounters an error."""

    message: str
    error_type: ToolErrorType

    def __init__(
        self,
        message: str,
        error_type: ToolErrorType = ToolErrorType.EXECUTION_FAILURE,
    ):
        self.message = message
        self.error_type = error_type
        super().__init__(message)

    def __str__(self):
        return self.message


class EditorToolParameterMissingError(ToolError):
    """Raised when a required parameter is missing for a tool command."""

    command: str
    parameter: str

    def __init__(self, command: str, parameter: str):
        self.command = command
        self.parameter = parameter
        self.message: str = (
            f"Parameter `{parameter}` is required for command: {command}."
        )


class EditorToolParameterInvalidError(ToolError):
    """Raised when a parameter is invalid for a tool command."""

    parameter: str
    value: str

    def __init__(self, parameter: str, value: str, hint: str | None = None):
        self.parameter = parameter
        self.value = value
        self.message: str = (
            f"Invalid `{parameter}` parameter: {value}. {hint}"
            if hint
            else f"Invalid `{parameter}` parameter: {value}."
        )


class FileValidationError(ToolError):
    """Raised when a file fails validation checks (size, type, etc.)."""

    path: str
    reason: str

    def __init__(
        self,
        path: str,
        reason: str,
        error_type: ToolErrorType = ToolErrorType.EXECUTION_FAILURE,
    ):
        self.path = path
        self.reason = reason
        self.error_type = error_type
        self.message: str = f"File validation failed for {path}: {reason}"
        super().__init__(self.message, error_type=error_type)
