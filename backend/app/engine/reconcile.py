"""
M5 — The verification / reconciliation engine (Build Manual section 7).

This is the intellectual centre of TriVerify. It does not ask "is this field
present?" alone; it establishes *how the three independent surfaces agree or
disagree*, and records why.

Entirely deterministic and pure: same inputs, same findings, every time. That
is what makes the golden cases usable as regression tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from typing import Any

from app.core import config
from app.engine.compare import Comparison, compare_values
from app.engine.rules import (
    CROSS_RULES,
    LISTING,
    OFFICIAL,
    PHOTO,
    RuleDef,
    RuleType,
    active_rules,
    layer_word,
)
from app.engine.vocabulary import (
    CANONICAL_FIELDS,
    EXPIRY_DATE,
    FIELD_LABELS,
    FieldStatus,
    MANUFACTURING_DATE,
    MATERIAL_FIELDS,
    PACKING_DATE,
    RuleStatus,
    SEVERITY_ORDER,
    Classification,
    Severity,
)
from app.pipeline.normalize import display_field

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass
class FieldValue:
    """One layer's value for one field, with its provenance."""

    raw: str | None = None
    norm: dict[str, Any] | None = None
    confidence: float = 1.0
    evidence_id: str | None = None
    bbox: list[float] | None = None

    @property
    def usable(self) -> bool:
        """Present, parsed, and confident enough to reason about."""
        return self.norm is not None and self.confidence >= config.CONFIDENCE_THRESHOLD

    @property
    def present(self) -> bool:
        return self.raw is not None and str(self.raw).strip() != ""

    def display(self, field_name: str) -> str:
        return display_field(field_name, self.norm) or (self.raw or "—")


@dataclass
class LayerData:
    """Everything one of the three surfaces contributed to this case."""

    layer: str
    available: bool = True
    reason: str | None = None
    source: str | None = None
    reference: str | None = None
    captured_at: datetime | None = None
    is_live: bool = False
    fields: dict[str, FieldValue] = dc_field(default_factory=dict)

    def get(self, field_name: str) -> FieldValue | None:
        if not self.available:
            return None
        return self.fields.get(field_name)


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


@dataclass
class FindingOut:
    rule_id: str
    field_name: str | None
    status: str
    severity: str
    explanation: str
    confidence: float
    evidence_ids: list[str] = dc_field(default_factory=list)
    legal_reference: str | None = None


@dataclass
class FieldOutcome:
    field_name: str
    status: str
    note: str | None = None
    is_material: bool = False
    #: Which directional pattern this field contributes, if any.
    signal: str | None = None


@dataclass
class VerificationOutcome:
    classification: str
    overall_confidence: float
    headline: str
    findings: list[FindingOut]
    field_outcomes: dict[str, FieldOutcome]
    counts: dict[str, int]
    ruleset_version: str = config.RULESET_VERSION


# Directional signals a single field can contribute.
SIGNAL_SELLER = "SELLER"
SIGNAL_COUNTERFEIT = "COUNTERFEIT"
SIGNAL_AMBIGUOUS = "AMBIGUOUS"


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------


def _evidence_ids(*values: FieldValue | None) -> list[str]:
    out: list[str] = []
    for value in values:
        if value is not None and value.evidence_id and value.evidence_id not in out:
            out.append(value.evidence_id)
    return out


def _evaluate_presence(rule: RuleDef, layers: dict[str, LayerData]) -> FindingOut:
    photo = layers.get(PHOTO)
    label = FIELD_LABELS.get(rule.field_name or "", rule.field_name or rule.rule_id)

    if photo is None or not photo.available:
        return FindingOut(
            rule_id=rule.rule_id,
            field_name=rule.field_name,
            status=RuleStatus.REVIEW.value,
            severity=rule.severity,
            explanation=(
                f"{label}: the physical label could not be read "
                f"({photo.reason if photo else 'no image supplied'}), so presence of this "
                "mandatory declaration could not be established."
            ),
            confidence=0.0,
            legal_reference=rule.legal_reference,
        )

    candidates = rule.any_of or ((rule.field_name,) if rule.field_name else ())
    found: FieldValue | None = None
    found_name: str | None = None
    low_confidence: FieldValue | None = None
    unparsed: FieldValue | None = None

    for name in candidates:
        value = photo.fields.get(name)
        if value is None or not value.present:
            continue
        if value.norm is None:
            unparsed = unparsed or value
            continue
        if value.confidence < config.CONFIDENCE_THRESHOLD:
            low_confidence = low_confidence or value
            continue
        found, found_name = value, name
        break

    if found is not None and found_name is not None:
        return FindingOut(
            rule_id=rule.rule_id,
            field_name=found_name,
            status=RuleStatus.PASS.value,
            severity=rule.severity,
            explanation=(
                f"{FIELD_LABELS.get(found_name, found_name)} is declared on the physical "
                f"label as \"{found.display(found_name)}\"."
            ),
            confidence=round(found.confidence, 4),
            evidence_ids=_evidence_ids(found),
            legal_reference=rule.legal_reference,
        )

    weak = low_confidence or unparsed
    if weak is not None:
        reason = (
            "the extracted text could not be interpreted"
            if unparsed is not None and low_confidence is None
            else f"extraction confidence {weak.confidence:.2f} is below the "
            f"{config.CONFIDENCE_THRESHOLD:.2f} threshold"
        )
        return FindingOut(
            rule_id=rule.rule_id,
            field_name=rule.field_name,
            status=RuleStatus.REVIEW.value,
            severity=rule.severity,
            explanation=(
                f"{label} appears on the label as \"{weak.raw}\" but {reason}. "
                "Routed to review rather than accepted."
            ),
            confidence=round(weak.confidence, 4),
            evidence_ids=_evidence_ids(weak),
            legal_reference=rule.legal_reference,
        )

    return FindingOut(
        rule_id=rule.rule_id,
        field_name=rule.field_name,
        status=RuleStatus.FAIL.value,
        severity=rule.severity,
        explanation=f"{rule.explanation_template} No such declaration was found on the label.",
        confidence=round(_photo_extraction_confidence(photo), 4),
        legal_reference=rule.legal_reference,
    )


def _photo_extraction_confidence(photo: LayerData) -> float:
    """How much we trust an *absence* claim: only as much as the overall read."""
    values = [v.confidence for v in photo.fields.values() if v.norm is not None]
    if not values:
        return 0.0
    return sum(values) / len(values)


def _evaluate_cross(rule: RuleDef, layers: dict[str, LayerData]) -> FindingOut:
    assert rule.left and rule.right and rule.field_name
    field_name = rule.field_name
    label = FIELD_LABELS.get(field_name, field_name)
    left_layer = layers.get(rule.left)
    right_layer = layers.get(rule.right)

    def unavailable(layer: LayerData | None, which: str) -> FindingOut:
        reason = (layer.reason if layer and layer.reason else "source not supplied")
        return FindingOut(
            rule_id=rule.rule_id,
            field_name=field_name,
            status=RuleStatus.REVIEW.value,
            severity=rule.severity,
            explanation=(
                f"{label} could not be cross-checked because {layer_word(which)} is "
                f"unavailable: {reason}"
            ),
            confidence=0.0,
            legal_reference=rule.legal_reference,
        )

    if left_layer is None or not left_layer.available:
        return unavailable(left_layer, rule.left)
    if right_layer is None or not right_layer.available:
        return unavailable(right_layer, rule.right)

    left = left_layer.fields.get(field_name)
    right = right_layer.fields.get(field_name)

    left_present = left is not None and left.present
    right_present = right is not None and right.present

    if not left_present and not right_present:
        # Neither surface declares this field at all. That is not a discrepancy
        # — e.g. a domestically manufactured product has no importer. Presence
        # rules, not cross-source rules, are what catch a missing *mandatory*
        # declaration.
        return FindingOut(
            rule_id=rule.rule_id,
            field_name=field_name,
            status=RuleStatus.NOT_APPLICABLE.value,
            severity=rule.severity,
            explanation=(
                f"Not applicable: {label} is not declared on {layer_word(rule.left)} "
                f"or {layer_word(rule.right)}."
            ),
            confidence=0.0,
            legal_reference=rule.legal_reference,
        )

    missing: list[str] = []
    if not left_present:
        missing.append(layer_word(rule.left))
    if not right_present:
        missing.append(layer_word(rule.right))
    if missing:
        return FindingOut(
            rule_id=rule.rule_id,
            field_name=field_name,
            status=RuleStatus.REVIEW.value,
            severity=rule.severity,
            explanation=(
                f"{label} is not declared on {' and '.join(missing)}, so the two sources "
                "could not be compared."
            ),
            confidence=0.0,
            evidence_ids=_evidence_ids(left, right),
            legal_reference=rule.legal_reference,
        )

    assert left is not None and right is not None
    pair_confidence = round(min(left.confidence, right.confidence), 4)

    if left.norm is None or right.norm is None:
        side = layer_word(rule.left) if left.norm is None else layer_word(rule.right)
        raw = left.raw if left.norm is None else right.raw
        return FindingOut(
            rule_id=rule.rule_id,
            field_name=field_name,
            status=RuleStatus.REVIEW.value,
            severity=rule.severity,
            explanation=(
                f"{label} on {side} could not be interpreted (raw value \"{raw}\"), so "
                "no reliable comparison is possible."
            ),
            confidence=pair_confidence,
            evidence_ids=_evidence_ids(left, right),
            legal_reference=rule.legal_reference,
        )

    if pair_confidence < config.CONFIDENCE_THRESHOLD:
        return FindingOut(
            rule_id=rule.rule_id,
            field_name=field_name,
            status=RuleStatus.REVIEW.value,
            severity=rule.severity,
            explanation=(
                f"{label} comparison is below the confidence threshold "
                f"({pair_confidence:.2f} < {config.CONFIDENCE_THRESHOLD:.2f}). "
                "Routed to review rather than treated as a result."
            ),
            confidence=pair_confidence,
            evidence_ids=_evidence_ids(left, right),
            legal_reference=rule.legal_reference,
        )

    verdict = compare_values(field_name, left.norm, right.norm)

    if verdict is Comparison.EQUAL:
        return FindingOut(
            rule_id=rule.rule_id,
            field_name=field_name,
            status=RuleStatus.PASS.value,
            severity=rule.severity,
            explanation=(
                f"{label} agrees between {layer_word(rule.left)} and "
                f"{layer_word(rule.right)} (\"{left.display(field_name)}\")."
            ),
            confidence=pair_confidence,
            evidence_ids=_evidence_ids(left, right),
            legal_reference=rule.legal_reference,
        )

    if verdict is Comparison.INCOMPARABLE:
        return FindingOut(
            rule_id=rule.rule_id,
            field_name=field_name,
            status=RuleStatus.REVIEW.value,
            severity=rule.severity,
            explanation=(
                f"{label} values are not directly comparable "
                f"(\"{left.display(field_name)}\" vs \"{right.display(field_name)}\"). "
                "Routed to review."
            ),
            confidence=pair_confidence,
            evidence_ids=_evidence_ids(left, right),
            legal_reference=rule.legal_reference,
        )

    # DIFFERENT
    status = (
        RuleStatus.FAIL.value
        if pair_confidence >= config.FAIL_CONFIDENCE_THRESHOLD
        else RuleStatus.REVIEW.value
    )
    explanation = rule.explanation_template.format(
        label=label,
        left_word=layer_word(rule.left),
        right_word=layer_word(rule.right),
        left_value=left.display(field_name),
        right_value=right.display(field_name),
    )
    if status == RuleStatus.REVIEW.value:
        explanation += (
            f" Extraction confidence {pair_confidence:.2f} is below the "
            f"{config.FAIL_CONFIDENCE_THRESHOLD:.2f} threshold required to record a failure."
        )
    return FindingOut(
        rule_id=rule.rule_id,
        field_name=field_name,
        status=status,
        severity=rule.severity,
        explanation=explanation,
        confidence=pair_confidence,
        evidence_ids=_evidence_ids(left, right),
        legal_reference=rule.legal_reference,
    )


def _evaluate_consistency(rule: RuleDef, layers: dict[str, LayerData]) -> FindingOut:
    photo = layers.get(PHOTO)
    na = FindingOut(
        rule_id=rule.rule_id,
        field_name=rule.field_name,
        status=RuleStatus.NOT_APPLICABLE.value,
        severity=rule.severity,
        explanation="Not applicable: the label does not declare both a production date and an expiry date.",
        confidence=0.0,
        legal_reference=rule.legal_reference,
    )
    if photo is None or not photo.available:
        return na

    expiry = photo.fields.get(EXPIRY_DATE)
    production = None
    for name in (MANUFACTURING_DATE, PACKING_DATE):
        candidate = photo.fields.get(name)
        if candidate is not None and candidate.norm is not None:
            production = candidate
            break

    if expiry is None or expiry.norm is None or production is None:
        return na

    try:
        expiry_date = date.fromisoformat(expiry.norm["iso"])
        production_date = date.fromisoformat(production.norm["iso"])
    except (KeyError, TypeError, ValueError):
        return na

    confidence = round(min(expiry.confidence, production.confidence), 4)
    if expiry_date > production_date:
        return FindingOut(
            rule_id=rule.rule_id,
            field_name=rule.field_name,
            status=RuleStatus.PASS.value,
            severity=rule.severity,
            explanation=(
                f"Expiry ({expiry.display(EXPIRY_DATE)}) is later than the production date "
                f"({production.display(MANUFACTURING_DATE)}) on the physical label."
            ),
            confidence=confidence,
            evidence_ids=_evidence_ids(expiry, production),
            legal_reference=rule.legal_reference,
        )

    return FindingOut(
        rule_id=rule.rule_id,
        field_name=rule.field_name,
        status=RuleStatus.FAIL.value,
        severity=rule.severity,
        explanation=(
            f"{rule.explanation_template} Expiry {expiry.display(EXPIRY_DATE)} is not later "
            f"than production date {production.display(MANUFACTURING_DATE)}."
        ),
        confidence=confidence,
        evidence_ids=_evidence_ids(expiry, production),
        legal_reference=rule.legal_reference,
    )


_EVALUATORS = {
    RuleType.PRESENCE: _evaluate_presence,
    RuleType.CROSS_SOURCE: _evaluate_cross,
    RuleType.CONSISTENCY: _evaluate_consistency,
}


# ---------------------------------------------------------------------------
# Field-level triangulation
# ---------------------------------------------------------------------------


def _comparable_pairs() -> dict[str, set[frozenset[str]]]:
    """Which layer pairs an active cross-source rule actually compares."""
    mapping: dict[str, set[frozenset[str]]] = {}
    for rule in CROSS_RULES:
        if rule.active and rule.field_name and rule.left and rule.right:
            mapping.setdefault(rule.field_name, set()).add(
                frozenset((rule.left, rule.right))
            )
    return mapping


COMPARABLE_PAIRS: dict[str, set[frozenset[str]]] = _comparable_pairs()


def _field_outcome(field_name: str, layers: dict[str, LayerData]) -> FieldOutcome:
    """Decide this field's agreement pattern across the three layers.

    Only layer pairs that an active rule actually compares are considered. The
    comparison table must never show a mismatch that no rule fired on — e.g.
    the official registry lists the generic commodity name while the pack
    carries the brand name, and no rule compares those two.
    """
    is_material = field_name in MATERIAL_FIELDS
    allowed = COMPARABLE_PAIRS.get(field_name, set())

    if not allowed:
        return FieldOutcome(
            field_name,
            FieldStatus.NOT_APPLICABLE.value,
            note="No cross-source rule is configured for this field; values are shown for context only.",
            is_material=is_material,
        )

    participating = {layer for pair in allowed for layer in pair}

    usable: dict[str, FieldValue] = {}
    weak: list[str] = []
    for layer_name in (PHOTO, LISTING, OFFICIAL):
        if layer_name not in participating:
            continue
        layer = layers.get(layer_name)
        if layer is None or not layer.available:
            continue
        value = layer.fields.get(field_name)
        if value is None or not value.present:
            continue
        if value.usable:
            usable[layer_name] = value
        else:
            weak.append(layer_name)

    if not usable and not weak:
        return FieldOutcome(field_name, FieldStatus.NOT_APPLICABLE.value, is_material=is_material)

    pairs: dict[tuple[str, str], Comparison] = {}
    for left_name, right_name in ((PHOTO, LISTING), (PHOTO, OFFICIAL), (LISTING, OFFICIAL)):
        if frozenset((left_name, right_name)) not in allowed:
            continue
        if left_name not in usable or right_name not in usable:
            continue
        pairs[(left_name, right_name)] = compare_values(
            field_name, usable[left_name].norm, usable[right_name].norm
        )

    if not pairs:
        note = "Fewer than two sources supplied a usable value, so no comparison was possible."
        if weak:
            note = (
                "A value was found but is below the confidence threshold or could not be "
                "interpreted, so it was not used for comparison."
            )
        return FieldOutcome(
            field_name, FieldStatus.INSUFFICIENT.value, note=note, is_material=is_material
        )

    names = [name for name in (PHOTO, LISTING, OFFICIAL) if name in usable]

    if any(v is Comparison.INCOMPARABLE for v in pairs.values()):
        return FieldOutcome(
            field_name,
            FieldStatus.REVIEW.value,
            note="At least one pair of values is not directly comparable.",
            is_material=is_material,
        )

    if all(v is Comparison.EQUAL for v in pairs.values()):
        return FieldOutcome(field_name, FieldStatus.MATCH.value, is_material=is_material)

    # Something differs — work out which surface is the odd one out.
    signal: str | None = None
    note: str | None = None

    if len(pairs) == 3 and len(names) == 3:
        photo_listing = pairs[(PHOTO, LISTING)]
        photo_official = pairs[(PHOTO, OFFICIAL)]
        listing_official = pairs[(LISTING, OFFICIAL)]
        if photo_official is Comparison.EQUAL and photo_listing is Comparison.DIFFERENT:
            signal = SIGNAL_SELLER
            note = (
                "The physical label and the official record agree; only the seller's "
                "listing differs. The inconsistency sits on the online claim."
            )
        elif photo_listing is Comparison.EQUAL and listing_official is Comparison.DIFFERENT:
            signal = SIGNAL_COUNTERFEIT
            note = (
                "The product and the seller's listing agree with each other but both "
                "differ from the registered declaration. The product as sold does not "
                "match the official record."
            )
        elif listing_official is Comparison.EQUAL and photo_official is Comparison.DIFFERENT:
            signal = SIGNAL_COUNTERFEIT
            note = (
                "The listing matches the official record, but the physical label differs "
                "from both. The physical product is the outlier."
            )
        else:
            signal = SIGNAL_AMBIGUOUS
            note = "All three sources disagree; no single surface explains the discrepancy."
    else:
        differing = [pair for pair, verdict in pairs.items() if verdict is Comparison.DIFFERENT]
        if len(differing) != 1:
            return FieldOutcome(
                field_name,
                FieldStatus.MISMATCH.value,
                note=(
                    "More than one pair of sources disagrees and the third comparison is "
                    "unavailable, so the origin of the discrepancy cannot be isolated."
                ),
                is_material=is_material,
                signal=SIGNAL_AMBIGUOUS,
            )
        pair = differing[0]
        if pair == (PHOTO, OFFICIAL):
            signal = SIGNAL_COUNTERFEIT
            note = (
                "The physical label conflicts with the registered declaration. No seller "
                "listing was available to isolate where the discrepancy originates."
            )
        elif pair == (LISTING, OFFICIAL):
            signal = SIGNAL_SELLER
            note = (
                "The seller's listing conflicts with the registered declaration. No "
                "physical-label reading was available as a third reference."
            )
        else:  # PHOTO vs LISTING with no official reference
            signal = SIGNAL_AMBIGUOUS
            note = (
                "The physical label and the seller's listing disagree, but without the "
                "official record it cannot be determined which one is wrong."
            )

    return FieldOutcome(
        field_name,
        FieldStatus.MISMATCH.value,
        note=note,
        is_material=is_material,
        signal=signal,
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _classify(
    findings: list[FindingOut],
    field_outcomes: dict[str, FieldOutcome],
    layers: dict[str, LayerData],
) -> tuple[str, list[FindingOut], str]:
    """Return (classification, decisive findings, headline).

    Decision order is fixed and documented so the result is explainable:

    1. Material fields carrying both SELLER and COUNTERFEIT signals, or an
       AMBIGUOUS signal, mean no single story explains the evidence.
    2. A COUNTERFEIT signal outranks a SELLER signal when it stands alone.
    3. A SELLER signal alone means the online claim is the outlier.
    4. Any confident FAIL, any REVIEW on a material check, or any missing
       source means the case is not clean and goes to a human.
    5. Only a case with no failures and no unresolved evidence is COMPLIANT.
    """
    material = [o for o in field_outcomes.values() if o.is_material and o.signal]
    seller = [o for o in material if o.signal == SIGNAL_SELLER]
    counterfeit = [o for o in material if o.signal == SIGNAL_COUNTERFEIT]
    ambiguous = [o for o in material if o.signal == SIGNAL_AMBIGUOUS]

    fails = [f for f in findings if f.status == RuleStatus.FAIL.value]
    reviews = [f for f in findings if f.status == RuleStatus.REVIEW.value]
    missing_sources = [
        layer_word(name)
        for name, layer in layers.items()
        if not layer.available
    ]

    def findings_for(outcomes: list[FieldOutcome]) -> list[FindingOut]:
        names = {o.field_name for o in outcomes}
        picked = [f for f in fails if f.field_name in names]
        return picked or [f for f in findings if f.field_name in names]

    def label_of(outcome: FieldOutcome) -> str:
        return FIELD_LABELS.get(outcome.field_name, outcome.field_name)

    if ambiguous or (seller and counterfeit):
        names = ", ".join(sorted({label_of(o) for o in (ambiguous + seller + counterfeit)}))
        return (
            Classification.MANUAL_REVIEW.value,
            findings_for(ambiguous + seller + counterfeit),
            f"Conflicting evidence across all three sources for {names}. "
            "No single explanation fits, so the case is routed to an officer.",
        )

    if counterfeit:
        names = ", ".join(sorted({label_of(o) for o in counterfeit}))
        return (
            Classification.COUNTERFEIT_OR_ILLEGAL_IMPORT.value,
            findings_for(counterfeit),
            f"The physical product conflicts with the registered official declaration on "
            f"{names}. Flagged for enforcement review as a possible counterfeit or "
            "unregistered import.",
        )

    if seller:
        names = ", ".join(sorted({label_of(o) for o in seller}))
        return (
            Classification.SELLER_FRAUD.value,
            findings_for(seller),
            f"The physical label and the official record agree, but the seller's online "
            f"listing differs on {names}. The discrepancy is attributable to the online claim.",
        )

    if fails:
        high = [f for f in fails if f.severity == Severity.HIGH.value]
        chosen = high or fails
        detail = "; ".join(f.rule_id for f in chosen[:3])
        return (
            Classification.MANUAL_REVIEW.value,
            chosen,
            f"{len(fails)} compliance check(s) failed on the package itself "
            f"({detail}). No cross-source pattern explains the issue, so an officer "
            "must decide the action.",
        )

    if missing_sources:
        return (
            Classification.MANUAL_REVIEW.value,
            reviews,
            f"Verification is incomplete because {', '.join(sorted(missing_sources))} "
            "could not be obtained. A missing source is not evidence of compliance.",
        )

    if reviews:
        material_reviews = [f for f in reviews if f.field_name in MATERIAL_FIELDS]
        chosen = material_reviews or reviews
        return (
            Classification.MANUAL_REVIEW.value,
            chosen,
            f"{len(reviews)} check(s) could not be resolved with sufficient confidence. "
            "Unknown is not treated as compliant.",
        )

    passes = [f for f in findings if f.status == RuleStatus.PASS.value]
    return (
        Classification.COMPLIANT.value,
        passes,
        "All configured checks passed and the physical label, the seller's listing and "
        "the official declaration agree on every compared field.",
    )


def _overall_confidence(decisive: list[FindingOut]) -> float:
    """Mean confidence of the findings that determined the outcome.

    Deliberately simple and deterministic. For a MANUAL_REVIEW driven by a
    missing source the decisive findings carry 0.0 confidence, so the number
    reads honestly low rather than manufacturing certainty.
    """
    if not decisive:
        return 0.0
    total = sum(max(0.0, min(1.0, f.confidence)) for f in decisive)
    return round(total / len(decisive), 3)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def reconcile(layers: dict[str, LayerData]) -> VerificationOutcome:
    """Run every active rule, triangulate, and classify."""
    findings: list[FindingOut] = []
    for rule in active_rules():
        evaluator = _EVALUATORS.get(rule.rule_type)
        if evaluator is None:  # pragma: no cover - guarded by RuleType
            continue
        findings.append(evaluator(rule, layers))

    # Stable, demo-friendly ordering: worst first, then by rule id.
    status_rank = {
        RuleStatus.FAIL.value: 0,
        RuleStatus.REVIEW.value: 1,
        RuleStatus.PASS.value: 2,
        RuleStatus.NOT_APPLICABLE.value: 3,
    }
    findings.sort(
        key=lambda f: (
            status_rank.get(f.status, 9),
            -SEVERITY_ORDER.get(f.severity, 0),
            f.rule_id,
        )
    )

    field_outcomes = {name: _field_outcome(name, layers) for name in CANONICAL_FIELDS}

    classification, decisive, headline = _classify(findings, field_outcomes, layers)
    confidence = _overall_confidence(decisive)

    counts = {
        "passed": sum(1 for f in findings if f.status == RuleStatus.PASS.value),
        "failed": sum(1 for f in findings if f.status == RuleStatus.FAIL.value),
        "review": sum(1 for f in findings if f.status == RuleStatus.REVIEW.value),
        "not_applicable": sum(
            1 for f in findings if f.status == RuleStatus.NOT_APPLICABLE.value
        ),
        "high_severity_failures": sum(
            1
            for f in findings
            if f.status == RuleStatus.FAIL.value and f.severity == Severity.HIGH.value
        ),
        "fields_compared": sum(
            1
            for o in field_outcomes.values()
            if o.status in {FieldStatus.MATCH.value, FieldStatus.MISMATCH.value}
        ),
        "fields_mismatched": sum(
            1 for o in field_outcomes.values() if o.status == FieldStatus.MISMATCH.value
        ),
    }

    return VerificationOutcome(
        classification=classification,
        overall_confidence=confidence,
        headline=headline,
        findings=findings,
        field_outcomes=field_outcomes,
        counts=counts,
    )
