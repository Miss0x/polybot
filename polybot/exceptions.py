class APIRequestError(Exception):
    """Raised when an upstream API request fails."""


class DataValidationError(Exception):
    """Raised when external data cannot be parsed into expected structure."""
