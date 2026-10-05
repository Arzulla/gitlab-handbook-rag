"""Project exception hierarchy. Catch the specific subclass; never swallow silently."""


class HandbookRagError(Exception):
    """Base class for all project errors."""


class AccessDeniedError(HandbookRagError):
    """Role is unknown or empty: fail closed, no retrieval happens."""


class RetrievalError(HandbookRagError):
    """Vector or BM25 search failed."""


class LLMError(HandbookRagError):
    """LLM or embedding call failed after retries, or returned an invalid response."""
