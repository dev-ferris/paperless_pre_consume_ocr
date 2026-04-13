class DatabaseError(Exception):
    """Custom exception for database-related errors."""

    pass


class FileProcessingError(Exception):
    """Custom exception for file processing errors."""

    pass


class FileNotSupported(Exception):
    """Custom exception for unsupported file formats."""

    pass


class ConfigurationError(Exception):
    """Custom exception for configuration errors."""

    pass
