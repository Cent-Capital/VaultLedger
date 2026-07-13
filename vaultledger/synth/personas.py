"""The synthetic cast: personas, organizations, merchants, and their intended
relationships (SPEC.md 8.3).

Entity richness is a *requirement* here, not an accident — GraphRAG (Track D,
Phase 15) is only worth building if genuine cross-document relationships exist.
So the structural identities (who banks where, who employs whom, who invoices
whom) are hand-fixed in this module rather than drawn from Faker. Amounts and
dates are randomized downstream from the seed; the *relationships* are pinned.

Everything here is obviously synthetic. No real PII.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Value objects ---------------------------------------------------------


@dataclass(frozen=True)
class Address:
    street: str
    city: str
    state: str
    zip: str

    def oneline(self) -> str:
        return f"{self.street}, {self.city}, {self.state} {self.zip}"


@dataclass(frozen=True)
class Account:
    label: str  # "checking" | "savings"
    last4: str  # synthetic account tail, e.g. "4021"


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    address: Address
    accounts: tuple[Account, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Org:
    id: str
    name: str
    kind: str  # "employer" | "client"
    address: Address
    ein_last4: str


# --- The cast (fixed; the relationships below depend on these identities) ---

NIMBUS = Org(
    id="nimbus",
    name="Nimbus Analytics LLC",
    kind="employer",
    address=Address("900 Innovation Pkwy Suite 400", "Jersey City", "NJ", "07302"),
    ein_last4="8841",
)
HALCYON = Org(
    id="halcyon",
    name="Halcyon Retail Group",
    kind="client",
    address=Address("1200 Commerce Blvd", "Columbus", "OH", "43215"),
    ein_last4="2093",
)
CEDAR_GROVE = Org(
    id="cedargrove",
    name="Cedar Grove Media",
    kind="client",
    address=Address("77 Media Row", "Burbank", "CA", "91502"),
    ein_last4="5510",
)

ORGS: tuple[Org, ...] = (NIMBUS, HALCYON, CEDAR_GROVE)

MARCUS = Persona(
    id="marcus",
    name="Marcus Chen",
    address=Address("218 Larkspur Lane", "Astoria", "NY", "11106"),
    # Two accounts under one person -> the aggregation / "combine my accounts" test.
    accounts=(Account("checking", "4021"), Account("savings", "7788")),
)
PRIYA = Persona(
    id="priya",
    name="Priya Raman",
    address=Address("55 Kingfisher Ct", "Somerville", "MA", "02144"),
    accounts=(Account("checking", "3390"),),
)
DAVID = Persona(
    id="david",
    name="David Okafor",
    address=Address("4127 Maple Hollow Dr", "Austin", "TX", "78745"),
    accounts=(Account("checking", "5567"),),
)

PERSONAS: tuple[Persona, ...] = (MARCUS, PRIYA, DAVID)

# Merchants that must recur across a persona's monthly statements so that
# "recurring merchant" is a real, extractable relationship (GraphRAG signal).
# Order is fixed for deterministic output.
RECURRING_MERCHANTS: tuple[str, ...] = (
    "Whole Foods Market",
    "Con Edison",
    "Verizon Wireless",
    "Netflix",
    "Blue Bottle Coffee",
)
# Occasional merchants sprinkled in to vary each statement.
OCCASIONAL_MERCHANTS: tuple[str, ...] = (
    "Shell Gas",
    "Amazon Marketplace",
    "CVS Pharmacy",
    "Delta Air Lines",
    "The Home Depot",
    "Trader Joe's",
    "Spotify",
    "Uber",
)


def personas_by_id() -> dict[str, Persona]:
    return {p.id: p for p in PERSONAS}


def orgs_by_id() -> dict[str, Org]:
    return {o.id: o for o in ORGS}
