from __future__ import annotations

from .models import Response, Session, StudentPath


def record_response_evidence(*, response: Response) -> None:
    """Phase 7 integration point. Phase 6 intentionally performs no BKT math."""


def exercise_completed(*, session: Session, student_path: StudentPath) -> None:
    """Phase 8 integration point. Phase 6 intentionally makes no adaptive decision."""
