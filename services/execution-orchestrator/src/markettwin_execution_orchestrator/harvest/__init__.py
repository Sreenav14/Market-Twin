"""Phase 1b deep harvest (doc 16): census maps become knowledge.

The package is imported lazily by the worker (see worker.main) and by
tests; importing it must stay cheap and cycle-free, so this init
carries no imports.
"""
