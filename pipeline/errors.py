"""Pipeline errors."""


class PipelineError(Exception):
    """Raised when a pipeline stage fails."""

    def __init__(self, stage_name: str, message: str) -> None:
        self.stage_name = stage_name
        self.message = message
        super().__init__(f"[{stage_name}] {message}")
