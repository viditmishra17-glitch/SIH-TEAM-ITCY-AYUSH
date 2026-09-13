"""
The deterministic rule set (Build Manual sections 6 & 7).

Explicitly small and explainable line by line. Every rule is data, not code:
a rule has an id, a field, a type, a severity and an explanation template, so
a judge can read the list and a future rule set can be versioned.

Nothing here calls a model. AI extracts; rules decide.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.vocabulary import (
    BRAND,
    CONSUMER_CARE,
    EXPIRY_DATE,
    FIELD_LABELS,
    IDENTIFIER,
    IMPORTER_NAME,
    MANDATORY_DECLARATIONS,
    MANUFACTURER_NAME,
    MANUFACTURING_DATE,
    MRP,
    NET_QUANTITY,
    PACKER_NAME,
    PACKING_DATE,
    PRODUCT_NAME,
    Severity,
    SourceType,
)


class RuleType:
    """What a rule actually checks."""

    #: The declaration must be readable on the physical label.
    PRESENCE = "PRESENCE"
    #: Two named layers must agree on a field.
    CROSS_SOURCE = "CROSS_SOURCE"
    #: Internal sanity of a single layer (e.g. expiry after manufacture).
    CONSISTENCY = "CONSISTENCY"


@dataclass(frozen=True)
class RuleDef:
    rule_id: str
    rule_type: str
    field_name: str | None
    severity: str
    explanation_template: str
    #: For CROSS_SOURCE rules: which two layers to compare.
    left: str | None = None
    right: str | None = None
    #: For PRESENCE rules: any one of these fields satisfies the requirement.
    any_of: tuple[str, ...] = ()
    legal_reference: str | None = None
    active: bool = True

    @property
    def label(self) -> str:
        if self.field_name:
            return FIELD_LABELS.get(self.field_name, self.field_name)
        return self.rule_id


PHOTO = SourceType.PHOTO.value
LISTING = SourceType.LISTING.value
OFFICIAL = SourceType.OFFICIAL.value

_LAYER_WORDS = {
    PHOTO: "the physical label",
    LISTING: "the seller's online listing",
    OFFICIAL: "the registered official declaration",
}


def layer_word(layer: str) -> str:
    return _LAYER_WORDS.get(layer, layer.lower())


# ---------------------------------------------------------------------------
# Presence rules — mandatory declarations on the pack
# ---------------------------------------------------------------------------

_PRESENCE_SPECS: list[tuple[str, tuple[str, ...], str, str]] = [
    (
        "DECL-001",
        (MRP,),
        Severity.HIGH.value,
        "Retail sale price (MRP) must be declared on the package.",
    ),
    (
        "DECL-002",
        (NET_QUANTITY,),
        Severity.HIGH.value,
        "Net quantity must be declared on the package.",
    ),
    (
        "DECL-003",
        (MANUFACTURER_NAME, PACKER_NAME, IMPORTER_NAME),
        Severity.HIGH.value,
        "Name and address of the manufacturer, packer or importer must be declared.",
    ),
    (
        "DECL-004",
        (CONSUMER_CARE,),
        Severity.MEDIUM.value,
        "Consumer care contact details must be declared on the package.",
    ),
    (
        "DECL-005",
        (MANUFACTURING_DATE, PACKING_DATE),
        Severity.MEDIUM.value,
        "Date of manufacture, pre-packing or import must be declared.",
    ),
    (
        "DECL-006",
        (PRODUCT_NAME,),
        Severity.LOW.value,
        "The common or generic name of the commodity must be declared.",
    ),
]

PRESENCE_RULES: list[RuleDef] = [
    RuleDef(
        rule_id=rule_id,
        rule_type=RuleType.PRESENCE,
        field_name=fields[0],
        any_of=fields,
        severity=severity,
        explanation_template=template,
        legal_reference="Legal Metrology (Packaged Commodities) Rules, 2011 — mandatory declarations",
    )
    for rule_id, fields, severity, template in _PRESENCE_SPECS
]


# ---------------------------------------------------------------------------
# Cross-source rules — the pairwise comparison matrix
# ---------------------------------------------------------------------------

_CROSS_SPECS: list[tuple[str, str, str]] = [
    # (field, id prefix, severity)
    (MRP, "MRP", Severity.HIGH.value),
    (NET_QUANTITY, "QTY", Severity.HIGH.value),
    (MANUFACTURER_NAME, "MFR", Severity.HIGH.value),
    (IMPORTER_NAME, "IMP", Severity.MEDIUM.value),
    (IDENTIFIER, "IDN", Severity.MEDIUM.value),
    (NET_QUANTITY, "QTY", Severity.HIGH.value),
]

_PAIRS: tuple[tuple[str, str, str], ...] = (
    (PHOTO, LISTING, "001"),
    (PHOTO, OFFICIAL, "002"),
    (LISTING, OFFICIAL, "003"),
)


def _build_cross_rules() -> list[RuleDef]:
    rules: list[RuleDef] = []
    seen: set[str] = set()
    for field_name, prefix, severity in _CROSS_SPECS:
        for left, right, suffix in _PAIRS:
            rule_id = f"{prefix}-{suffix}"
            if rule_id in seen:
                continue
            seen.add(rule_id)
            rules.append(
                RuleDef(
                    rule_id=rule_id,
                    rule_type=RuleType.CROSS_SOURCE,
                    field_name=field_name,
                    left=left,
                    right=right,
                    severity=severity,
                    explanation_template=(
                        "{label} on {left_word} ({left_value}) does not match "
                        "{label} on {right_word} ({right_value})."
                    ),
                    legal_reference=(
                        "Cross-verification check — declared value consistency"
                    ),
                )
            )
    return rules


CROSS_RULES: list[RuleDef] = _build_cross_rules()


# Extra cross rules for softer fields, MEDIUM/LOW severity.
CROSS_RULES += [
    RuleDef(
        rule_id="BRD-003",
        rule_type=RuleType.CROSS_SOURCE,
        field_name=BRAND,
        left=LISTING,
        right=OFFICIAL,
        severity=Severity.LOW.value,
        explanation_template=(
            "{label} on {left_word} ({left_value}) does not match "
            "{label} on {right_word} ({right_value})."
        ),
    ),
    RuleDef(
        rule_id="PRD-001",
        rule_type=RuleType.CROSS_SOURCE,
        field_name=PRODUCT_NAME,
        left=PHOTO,
        right=LISTING,
        severity=Severity.LOW.value,
        explanation_template=(
            "{label} on {left_word} ({left_value}) does not match "
            "{label} on {right_word} ({right_value})."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Consistency rules — internal sanity of the physical label
# ---------------------------------------------------------------------------

CONSISTENCY_RULES: list[RuleDef] = [
    RuleDef(
        rule_id="DATE-001",
        rule_type=RuleType.CONSISTENCY,
        field_name=EXPIRY_DATE,
        severity=Severity.MEDIUM.value,
        explanation_template=(
            "Best-before/expiry date is not later than the manufacturing or "
            "packing date on the physical label."
        ),
    ),
]


ALL_RULES: list[RuleDef] = PRESENCE_RULES + CROSS_RULES + CONSISTENCY_RULES

RULES_BY_ID: dict[str, RuleDef] = {rule.rule_id: rule for rule in ALL_RULES}


def active_rules() -> list[RuleDef]:
    return [rule for rule in ALL_RULES if rule.active]


def mandatory_declaration_groups() -> tuple[tuple[str, ...], ...]:
    return MANDATORY_DECLARATIONS
