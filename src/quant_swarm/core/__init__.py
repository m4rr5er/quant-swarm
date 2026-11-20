"""Shared kernel: contracts (schemas + subjects) and infrastructure only.

No business logic lives here — and nothing outside core/ may be imported by
another process's business code. Cross-process communication happens solely
through bus subjects + pydantic schemas.
"""
