class RagError(Exception):
    """Expected, user-facing application error."""


class UnsupportedFormatError(RagError):
    pass


class DuplicateDocumentError(RagError):
    pass


class OllamaUnavailableError(RagError):
    pass


class ModelMissingError(RagError):
    pass

