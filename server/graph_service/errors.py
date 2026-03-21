class GraphServiceError(Exception):
    """Base exception for service-level failures."""


class ResourceNotFoundError(GraphServiceError):
    """Raised when a requested graph resource does not exist."""


class ServiceNotReadyError(GraphServiceError):
    """Raised when a service is used before startup initialization."""
