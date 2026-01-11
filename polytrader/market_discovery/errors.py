"""Error classes for market discovery with error classification.

Per observability.mdc §3: Errors must be classified as retryable or fatal.
"""


class DiscoveryError(Exception):
    """Base exception for market discovery errors."""

    def __init__(self, message: str, error_class: str = "unknown") -> None:
        """Initialize discovery error.

        Args:
            message: Error message
            error_class: Error classification ("retryable" or "fatal")
        """
        super().__init__(message)
        self.error_class = error_class
        self.message = message


class RetryableDiscoveryError(DiscoveryError):
    """Retryable error (network, rate limit, temporary API issues).

    These errors may succeed on retry.
    """

    def __init__(self, message: str) -> None:
        """Initialize retryable error.

        Args:
            message: Error message
        """
        super().__init__(message, error_class="retryable")


class FatalDiscoveryError(DiscoveryError):
    """Fatal error (invalid pattern, auth failure, permanent API issues).

    These errors will not succeed on retry.
    """

    def __init__(self, message: str) -> None:
        """Initialize fatal error.

        Args:
            message: Error message
        """
        super().__init__(message, error_class="fatal")
