"""AIFMD Annex IV Canonical Model — Two-Layer Architecture.

Layer 1 — Source Canonical (source_entities.py):
    Rich domain entities (Fund, Manager, Positions, etc.) that can be
    reused across multiple report types.

Layer 2 — Report Canonical (model.py):
    AIFMD Annex IV specific report fields (Q1-Q38 AIFM, Q1-Q302 AIF).

Projection (projection.py):
    Maps Source Canonical → Report Canonical (forward projection) and
    Report Canonical → Source Canonical (reverse-lift for ESMA/FCA imports).

All adapters populate the Source Canonical; the projection layer then
produces Report Canonical instances for validation and XML packaging.
"""
