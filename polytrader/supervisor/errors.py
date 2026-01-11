"""Error classes for supervisor operations with error classification.

Per observability.mdc §3: Errors must be classified as retryable or fatal.
"""


class SupervisorError(Exception):
    """Base exception for supervisor errors."""

    def __init__(self, message: str, error_class: str = "unknown") -> None:
        """Initialize supervisor error.

        Args:
            message: Error message
            error_class: Error classification ("retryable" or "fatal")
        """
        super().__init__(message)
        self.error_class = error_class
        self.message = message


class RetryableSupervisorError(SupervisorError):
    """Retryable error (network, rate limit, temporary service issues).

    These errors may succeed on retry.
    """

    def __init__(self, message: str) -> None:
        """Initialize retryable error.

        Args:
            message: Error message
        """
        super().__init__(message, error_class="retryable")


class FatalSupervisorError(SupervisorError):
    """Fatal error (invalid configuration, auth failure, permanent issues).

    These errors will not succeed on retry.
    """

    def __init__(self, message: str) -> None:
        """Initialize fatal error.

        Args:
            message: Error message
        """
        super().__init__(message, error_class="fatal")


def classify_service_error(error: Exception) -> str:
    """Classify an error as retryable or fatal.

    Per observability.mdc §3: Errors must be classified.

    Args:
        error: Exception to classify

    Returns:
        Error classification ("retryable" or "fatal")
    """
    # If error already has error_class (from SupervisorError), use it
    if isinstance(error, SupervisorError):
        return error.error_class

    error_type = type(error).__name__
    error_msg = str(error).lower()

    # Network/connection errors are retryable
    if (
        "Connection" in error_type
        or "Timeout" in error_type
        or "network" in error_msg
        or "connection" in error_msg
    ):
        return "retryable"

    # Rate limit errors are retryable
    if "429" in error_msg or "rate limit" in error_msg:
        return "retryable"

    # Auth errors are fatal
    if "401" in error_msg or "403" in error_msg or "unauthorized" in error_msg:
        return "fatal"

    # Configuration errors are fatal
    if "config" in error_msg or "invalid" in error_msg:
        return "fatal"

    # RuntimeError/ValueError from service startup are usually fatal
    if error_type in ("RuntimeError", "ValueError", "TypeError"):
        return "fatal"

    # Default to retryable (conservative)
    return "retryable"
