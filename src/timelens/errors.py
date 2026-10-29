"""Input errors. Messages name the element id at fault."""


class TimeLensError(Exception):
    """Base class for input errors (CLI exit code 2)."""


class ModelError(TimeLensError):
    """The BPMN model is invalid or unsupported."""


class RulesError(TimeLensError):
    """The time rules or levers file is invalid."""


class LogMappingError(TimeLensError):
    """The event log mapping does not match the log."""
