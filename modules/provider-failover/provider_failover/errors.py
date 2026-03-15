"""LLM provider error hierarchy for provider-failover module.

All provider errors inherit from LLMError, which carries a ``retryable``
flag indicating whether the caller may retry the request.
"""

from __future__ import annotations


class LLMError(Exception):
    """Base class for all LLM provider errors.

    Attributes:
        retryable: True if the error is transient and the request may be
            retried; False if retrying would not help.
    """

    def __init__(self, message: str = "", *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderUnavailableError(LLMError):
    """Raised when the provider is temporarily unavailable (e.g. 503)."""

    def __init__(self, message: str = "", *, retryable: bool = True) -> None:
        super().__init__(message, retryable=retryable)


class RateLimitError(LLMError):
    """Raised when the provider rate limit is exceeded (e.g. 429)."""

    def __init__(self, message: str = "", *, retryable: bool = True) -> None:
        super().__init__(message, retryable=retryable)


class AuthenticationError(LLMError):
    """Raised when authentication credentials are invalid (e.g. 401)."""

    def __init__(self, message: str = "", *, retryable: bool = False) -> None:
        super().__init__(message, retryable=retryable)


class ContentFilterError(LLMError):
    """Raised when the provider rejects content due to safety filters."""

    def __init__(self, message: str = "", *, retryable: bool = False) -> None:
        super().__init__(message, retryable=retryable)


class ContextLengthError(LLMError):
    """Raised when the request exceeds the provider's context window."""

    def __init__(self, message: str = "", *, retryable: bool = False) -> None:
        super().__init__(message, retryable=retryable)
