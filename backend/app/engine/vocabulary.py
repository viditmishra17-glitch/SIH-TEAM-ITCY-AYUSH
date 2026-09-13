"""
Canonical field vocabulary — FROZEN AT H0 (Build Manual section 4).

Changing anything in this module changes the contract between the pipeline,
the engine, the API and the frontend. It requires team agreement.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

# ---------------------------------------------------------------------------
# Canonical field names
# ---------------------------------------------------------------------------

MRP: Final = "mrp"
NET_QUANTITY: Final = "net_quantity"
QUANTITY_UNIT: Final = "quantity_unit"
MANUFACTURING_DATE: Final = "manufacturing_date"
PACKING_DATE: Final = "packing_date"
EXPIRY_DATE: Final = "expiry_date"
MANUFACTURER_NAME: Final = "manufacturer_name"
PACKER_NAME: Final = "packer_name"
IMPORTER_NAME: Final = "importer_name"
CONSUMER_CARE: Final = "consumer_care"
PRODUCT_NAME: Final = "product_name"
BRAND: Final = "brand"
IDENTIFIER: Final = "identifier"

CANONICAL_FIELDS: Final[tuple[str, ...]] = (
    MRP,
    NET_QUANTITY,
    QUANTITY_UNIT,
    MANUFACTURING_DATE,
    PACKING_DATE,
    EXPIRY_DATE,
    MANUFACTURER_NAME,
    PACKER_NAME,
    IMPORTER_NAME,
    CONSUMER_CARE,
    PRODUCT_NAME,
    BRAND,
    IDENTIFIER,
)

#: Human-readable labels used by the UI and the report.
FIELD_LABELS: Final[dict[str, str]] = {
    MRP: "Maximum Retail Price",
    NET_QUANTITY: "Net Quantity",
    QUANTITY_UNIT: "Quantity Unit",
    MANUFACTURING_DATE: "Date of Manufacture",
    PACKING_DATE: "Date of Packing",
    EXPIRY_DATE: "Best Before / Expiry",
    MANUFACTURER_NAME: "Manufacturer",
    PACKER_NAME: "Packer",
    IMPORTER_NAME: "Importer",
    CONSUMER_CARE: "Consumer Care Details",
    PRODUCT_NAME: "Product Name",
    BRAND: "Brand",
    IDENTIFIER: "Product Identifier",
}

#: How each field is normalized. Drives engine/normalize dispatch and comparison.
class ValueKind(str, Enum):
    MONEY = "MONEY"
    QUANTITY = "QUANTITY"
    DATE = "DATE"
    NAME = "NAME"
    TEXT = "TEXT"
    IDENTIFIER = "IDENTIFIER"


FIELD_KINDS: Final[dict[str, ValueKind]] = {
    MRP: ValueKind.MONEY,
    NET_QUANTITY: ValueKind.QUANTITY,
    QUANTITY_UNIT: ValueKind.TEXT,
    MANUFACTURING_DATE: ValueKind.DATE,
    PACKING_DATE: ValueKind.DATE,
    EXPIRY_DATE: ValueKind.DATE,
    MANUFACTURER_NAME: ValueKind.NAME,
    PACKER_NAME: ValueKind.NAME,
    IMPORTER_NAME: ValueKind.NAME,
    CONSUMER_CARE: ValueKind.TEXT,
    PRODUCT_NAME: ValueKind.NAME,
    BRAND: ValueKind.NAME,
    IDENTIFIER: ValueKind.IDENTIFIER,
}

# ---------------------------------------------------------------------------
# Sources / layers
# ---------------------------------------------------------------------------

class SourceType(str, Enum):
    PHOTO = "PHOTO"
    LISTING = "LISTING"
    OFFICIAL = "OFFICIAL"


LAYERS: Final[tuple[str, ...]] = (
    SourceType.PHOTO.value,
    SourceType.LISTING.value,
    SourceType.OFFICIAL.value,
)

# ---------------------------------------------------------------------------
# Rule + comparison states
# ---------------------------------------------------------------------------

class RuleStatus(str, Enum):
    """Build Manual section 7 — rule result states."""

    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FieldStatus(str, Enum):
    """Per-field agreement across the three layers."""

    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    REVIEW = "REVIEW"
    INSUFFICIENT = "INSUFFICIENT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Severity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


SEVERITY_ORDER: Final[dict[str, int]] = {
    Severity.HIGH.value: 3,
    Severity.MEDIUM.value: 2,
    Severity.LOW.value: 1,
    Severity.INFO.value: 0,
}


class Classification(str, Enum):
    """Build Manual section 7 — classification policy.

    NOTE: this is an engineering triage label, not a legal judgment.
    """

    COMPLIANT = "COMPLIANT"
    SELLER_FRAUD = "SELLER_FRAUD"
    COUNTERFEIT_OR_ILLEGAL_IMPORT = "COUNTERFEIT_OR_ILLEGAL_IMPORT"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class CaseStatus(str, Enum):
    CREATED = "CREATED"
    EXTRACTED = "EXTRACTED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Material fields
# ---------------------------------------------------------------------------

#: Fields whose disagreement can, on its own, drive a classification.
MATERIAL_FIELDS: Final[tuple[str, ...]] = (
    MRP,
    NET_QUANTITY,
    MANUFACTURER_NAME,
    IMPORTER_NAME,
    IDENTIFIER,
)

#: Declarations that must be present on the physical label.
#: Grouped tuples mean "at least one of these satisfies the requirement".
MANDATORY_DECLARATIONS: Final[tuple[tuple[str, ...], ...]] = (
    (MRP,),
    (NET_QUANTITY,),
    (MANUFACTURER_NAME, PACKER_NAME, IMPORTER_NAME),
    (CONSUMER_CARE,),
    (MANUFACTURING_DATE, PACKING_DATE),
    (PRODUCT_NAME,),
)
