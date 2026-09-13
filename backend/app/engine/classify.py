"""
Classification policy (Build Manual section 7).

The decision *logic* lives in :mod:`engine.reconcile` next to the evidence it
reads. This module holds the policy metadata that the API, the UI and the
report all need to describe a classification consistently — including the
boundary statement that keeps the label honest.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.vocabulary import Classification


@dataclass(frozen=True)
class ClassificationInfo:
    code: str
    title: str
    trigger: str
    tone: str  # ok | warn | bad | unknown


CLASSIFICATIONS: dict[str, ClassificationInfo] = {
    Classification.COMPLIANT.value: ClassificationInfo(
        code=Classification.COMPLIANT.value,
        title="Compliant",
        trigger=(
            "Required checks pass and no material mismatch is found; evidence quality "
            "is sufficient."
        ),
        tone="ok",
    ),
    Classification.SELLER_FRAUD.value: ClassificationInfo(
        code=Classification.SELLER_FRAUD.value,
        title="Seller-side discrepancy",
        trigger=(
            "The seller's listing conflicts with the physical label and/or the official "
            "record in a pattern attributable to the online claim."
        ),
        tone="bad",
    ),
    Classification.COUNTERFEIT_OR_ILLEGAL_IMPORT.value: ClassificationInfo(
        code=Classification.COUNTERFEIT_OR_ILLEGAL_IMPORT.value,
        title="Product / official record conflict",
        trigger=(
            "Physical product identity conflicts materially with the official "
            "declaration, with sufficient evidence to flag the case for enforcement "
            "review."
        ),
        tone="bad",
    ),
    Classification.MANUAL_REVIEW.value: ClassificationInfo(
        code=Classification.MANUAL_REVIEW.value,
        title="Manual review",
        trigger=(
            "Conflicting or incomplete evidence prevents a reliable automated "
            "classification."
        ),
        tone="unknown",
    ),
}

#: Shown next to every classification, in the UI and on every report.
BOUNDARY_STATEMENT = (
    "This classification is an engineering triage label, not a legal judgment. "
    "TriVerify surfaces evidence and the deterministic rules that fired; a qualified "
    "officer remains responsible for any enforcement action."
)


def describe(classification: str | None) -> ClassificationInfo:
    if classification and classification in CLASSIFICATIONS:
        return CLASSIFICATIONS[classification]
    return ClassificationInfo(
        code=classification or "UNKNOWN",
        title="Not yet verified",
        trigger="The case has not been run through the verification engine.",
        tone="unknown",
    )
