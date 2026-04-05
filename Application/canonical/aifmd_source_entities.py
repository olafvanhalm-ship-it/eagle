"""Source Canonical entity models for AIFMD regulatory reporting.

This module defines the first layer of a two-layer canonical architecture
for AIFMD regulatory reporting. The Source Canonical stores rich domain data
(funds, managers, positions, etc.) that can be reused across multiple report
types. The second layer (Report Canonical, stored in model.py) stores the
340 ESMA-specific report fields.

Every field is stored as an Optional[FieldValue], wrapping the actual value
with source, priority, confidence, and timestamp metadata. This enables
multi-source merge, audit trails, and interactive correction workflows.

Architecture:
- SourceEntity: Base class with provenance-aware get/set methods
- Scalar entities: ManagerStatic, FundStatic, FundDynamic (one per fund/manager)
- Collection entities: Position, Transaction, Instrument, etc. (multiple per fund)
- SourceCanonical: Top-level container holding all entities for one filing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .provenance import FieldValue, SourcePriority

__all__ = [
    "SourceEntity",
    "ManagerStatic",
    "FundStatic",
    "FundDynamic",
    "Position",
    "Transaction",
    "Instrument",
    "ShareClass",
    "Counterparty",
    "Strategy",
    "Investor",
    "RiskMeasure",
    "MonthlyData",
    "BorrowingSource",
    "ControlledCompany",
    "ControlledStructure",
    "SourceCanonical",
]


# ============================================================================
# Base Class
# ============================================================================

class SourceEntity:
    """Base class for all source canonical entities.

    Provides provenance-aware field management:
    - set(): Store field value with priority-based merge
    - get(): Retrieve raw value
    - get_field(): Retrieve FieldValue with metadata
    - set_bulk(): Set multiple fields from same source
    """

    _FIELD_NAMES: tuple[str, ...] = ()

    def __init__(self):
        """Initialize empty field storage."""
        self._fields: dict[str, FieldValue] = {}

    def set(
        self,
        field_name: str,
        value: Any,
        source: str,
        priority: SourcePriority = SourcePriority.IMPORTED,
        confidence: float = 1.0,
        source_ref: Optional[str] = None,
        note: Optional[str] = None,
    ) -> None:
        """Set a field value with provenance, using priority-based merge.

        If the field already exists, the new value wins only if it has higher
        priority, or equal priority but higher confidence, or equal priority
        and confidence but newer timestamp.

        Args:
            field_name: Name of the field
            value: The actual value (str, int, float, bool, None)
            source: Identifier of the adapter/process (e.g. "m_adapter", "ai_extract")
            priority: Source priority level (default: IMPORTED)
            confidence: Confidence score 0.0-1.0 (default: 1.0)
            source_ref: Optional reference to source location (e.g. cell address)
            note: Optional human-readable note
        """
        fv = FieldValue(
            value=value,
            source=source,
            priority=priority,
            confidence=confidence,
            source_ref=source_ref,
            note=note,
        )
        existing = self._fields.get(field_name)
        if existing is None or fv.beats(existing):
            self._fields[field_name] = fv

    def get(self, field_name: str, default: Any = None) -> Any:
        """Get raw value of a field.

        Args:
            field_name: Name of the field
            default: Value to return if field not set

        Returns:
            The raw field value, or default if not set
        """
        fv = self._fields.get(field_name)
        return fv.value if fv is not None else default

    def get_field(self, field_name: str) -> Optional[FieldValue]:
        """Get FieldValue with full provenance metadata.

        Args:
            field_name: Name of the field

        Returns:
            FieldValue object if set, None otherwise
        """
        return self._fields.get(field_name)

    def has(self, field_name: str) -> bool:
        """Check if field has been set.

        Args:
            field_name: Name of the field

        Returns:
            True if field is set, False otherwise
        """
        return field_name in self._fields

    @property
    def fields(self) -> dict[str, FieldValue]:
        """Return a copy of all fields with their FieldValue objects."""
        return dict(self._fields)

    def to_dict(self) -> dict:
        """Serialize entity to a JSON-compatible dict.

        Returns:
            Dict mapping field names to FieldValue.to_dict() representations
        """
        return {name: fv.to_dict() for name, fv in self._fields.items()}

    @classmethod
    def from_dict(cls, data: dict) -> SourceEntity:
        """Deserialize entity from a JSON-compatible dict.

        Args:
            data: Dict mapping field names to FieldValue dicts

        Returns:
            Entity instance with fields restored
        """
        entity = cls()
        for name, fv_data in data.items():
            entity._fields[name] = FieldValue.from_dict(fv_data)
        return entity

    def set_bulk(
        self,
        values: dict[str, Any],
        source: str,
        priority: SourcePriority = SourcePriority.IMPORTED,
    ) -> None:
        """Set multiple fields at once from the same source.

        Skips None values and empty strings. Useful for batch imports.

        Args:
            values: Dict mapping field names to values
            source: Identifier of the source
            priority: Source priority level (default: IMPORTED)
        """
        for name, value in values.items():
            if value is not None and str(value).strip():
                self.set(name, value, source=source, priority=priority)

    def __repr__(self) -> str:
        """Return a concise representation showing field count."""
        return f"{self.__class__.__name__}(fields={len(self._fields)})"


# ============================================================================
# Scalar Entities (one per fund/manager)
# ============================================================================

@dataclass
class ManagerStatic(SourceEntity):
    """AIFM identity and NCA registration data.

    Attributes (all stored as Optional[FieldValue]):
        name: Manager name
        jurisdiction: Jurisdiction of the manager
        national_code: National code identifier
        lei: Legal Entity Identifier
        bic: Bank Identifier Code
        eea_flag: Whether manager is in EEA
        nca_content_type: NCA registration content type
        nca_period_type: NCA registration period type
        nca_reporting_code: NCA registration reporting code
        nca_sender_id: NCA registration sender ID
        nca_old_rms: Previous RMS identifier
        nca_old_national_code: Previous national code
    """

    _FIELD_NAMES = (
        "name",
        "jurisdiction",
        "national_code",
        "lei",
        "bic",
        "eea_flag",
        "nca_content_type",
        "nca_period_type",
        "nca_reporting_code",
        "nca_sender_id",
        "nca_old_rms",
        "nca_old_national_code",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class FundStatic(SourceEntity):
    """Semi-permanent fund properties.

    Attributes (all stored as Optional[FieldValue]):
        name: Fund name
        eea_flag: Whether fund is in EEA
        domicile: Fund domicile country
        inception_date: Fund inception date
        lei: Legal Entity Identifier
        isin: ISIN code
        cusip: CUSIP code
        sedol: SEDOL code
        bloomberg_code: Bloomberg identifier
        reuters_code: Reuters identifier
        ecb_code: ECB identifier
        share_class_flag: Whether fund has share classes
        base_currency: Fund base currency
        predominant_type: Predominant asset type
        master_feeder_status: Master/feeder fund status
        master_aif_name: Master AIF name (if feeder)
        master_aif_rms: Master AIF RMS identifier
        master_aif_national_code: Master AIF national code
        funding_source_country_1: Primary funding source country
        funding_source_country_2: Secondary funding source country
        funding_source_country_3: Tertiary funding source country
        withdrawal_rights_flag: Whether fund has withdrawal rights
        redemption_frequency: Redemption frequency
        redemption_notice_period: Redemption notice period
        redemption_lock_up_period: Lock-up period for redemptions
        nca_rms: NCA RMS identifier
        nca_national_code: NCA national code
        nca_content_type: NCA content type
        nca_period_type: NCA period type
        nca_reporting_code: NCA reporting code
        nca_old_rms: Previous NCA RMS identifier
        nca_old_national_code: Previous NCA national code
        nca_inception_date: NCA inception date
    """

    _FIELD_NAMES = (
        "name",
        "eea_flag",
        "domicile",
        "inception_date",
        "lei",
        "isin",
        "cusip",
        "sedol",
        "bloomberg_code",
        "reuters_code",
        "ecb_code",
        "share_class_flag",
        "base_currency",
        "predominant_type",
        "master_feeder_status",
        "master_aif_name",
        "master_aif_rms",
        "master_aif_national_code",
        "funding_source_country_1",
        "funding_source_country_2",
        "funding_source_country_3",
        "withdrawal_rights_flag",
        "redemption_frequency",
        "redemption_notice_period",
        "redemption_lock_up_period",
        "nca_rms",
        "nca_national_code",
        "nca_content_type",
        "nca_period_type",
        "nca_reporting_code",
        "nca_old_rms",
        "nca_old_national_code",
        "nca_inception_date",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class FundDynamic(SourceEntity):
    """Per-period fund data (updates each reporting period).

    Attributes (all stored as Optional[FieldValue]):
        hft_transaction_count: High-frequency trading transaction count
        hft_market_value: HFT market value
        position_size_type: Position size categorization
        top5_beneficial_pct: Percentage held by top 5 beneficial owners
        expected_annual_return: Expected annual return
        pct_securities_exchange: % traded on securities exchange
        pct_securities_otc: % traded OTC securities
        pct_derivatives_exchange: % derivatives on exchange
        pct_derivatives_otc: % derivatives OTC
        pct_derivatives_ccp: % derivatives cleared via CCP
        pct_derivatives_bilateral: % derivatives bilateral
        pct_repos_ccp: % repos via CCP
        pct_repos_bilateral: % repos bilateral
        pct_repos_triparty: % repos triparty
        collateral_cash: Cash collateral amount
        collateral_securities: Securities collateral amount
        collateral_other: Other collateral amount
        direct_clearing_flag: Whether fund has direct clearing
        portfolio_liq_0_1d: Portfolio liquidity 0-1 days
        portfolio_liq_2_7d: Portfolio liquidity 2-7 days
        portfolio_liq_8_30d: Portfolio liquidity 8-30 days
        portfolio_liq_31_90d: Portfolio liquidity 31-90 days
        portfolio_liq_91_180d: Portfolio liquidity 91-180 days
        portfolio_liq_181_365d: Portfolio liquidity 181-365 days
        portfolio_liq_gt_365d: Portfolio liquidity >365 days
        unencumbered_cash: Unencumbered cash amount
        investor_liq_0_1d: Investor liquidity 0-1 days
        investor_liq_2_7d: Investor liquidity 2-7 days
        investor_liq_8_30d: Investor liquidity 8-30 days
        investor_liq_31_90d: Investor liquidity 31-90 days
        investor_liq_91_180d: Investor liquidity 91-180 days
        investor_liq_181_365d: Investor liquidity 181-365 days
        investor_liq_gt_365d: Investor liquidity >365 days
        side_pocket_pct: Percentage in side pockets
        gates_pct: Percentage subject to gates
        dealing_suspension_pct: Percentage subject to dealing suspension
        other_arrangement_type: Type of other liquidity arrangements
        other_arrangement_pct: Percentage in other arrangements
        total_arrangement_pct: Total % in arrangements
        preferential_treatment_flag: Whether preferential treatment exists
        disclosure_pref_flag: Disclosure of preferential treatment
        liquidity_pref_flag: Liquidity preferential treatment
        fee_pref_flag: Fee preferential treatment
        other_pref_flag: Other preferential treatment
        available_financing: Available financing amount
        financing_liq_0_1d: Financing liquidity 0-1 days
        financing_liq_2_7d: Financing liquidity 2-7 days
        financing_liq_8_30d: Financing liquidity 8-30 days
        financing_liq_31_90d: Financing liquidity 31-90 days
        financing_liq_91_180d: Financing liquidity 91-180 days
        financing_liq_181_365d: Financing liquidity 181-365 days
        financing_liq_gt_365d: Financing liquidity >365 days
        stress_test_art15: Stress test result (Article 15)
        stress_test_art16: Stress test result (Article 16)
        rehypothecation_flag: Whether fund allows rehypothecation
        rehypothecation_pct: Percentage of assets rehypothecated
        unsecured_borrowing: Unsecured borrowing amount
        secured_prime_broker: Secured borrowing via prime broker
        secured_reverse_repo: Secured borrowing via reverse repo
        secured_other: Other secured borrowing
        etd_exposure: Exchange-traded derivatives exposure
        otc_exposure: OTC derivatives exposure
        short_position_value: Short position value
    """

    _FIELD_NAMES = (
        "hft_transaction_count",
        "hft_market_value",
        "position_size_type",
        "top5_beneficial_pct",
        "expected_annual_return",
        "pct_securities_exchange",
        "pct_securities_otc",
        "pct_derivatives_exchange",
        "pct_derivatives_otc",
        "pct_derivatives_ccp",
        "pct_derivatives_bilateral",
        "pct_repos_ccp",
        "pct_repos_bilateral",
        "pct_repos_triparty",
        "collateral_cash",
        "collateral_securities",
        "collateral_other",
        "direct_clearing_flag",
        "portfolio_liq_0_1d",
        "portfolio_liq_2_7d",
        "portfolio_liq_8_30d",
        "portfolio_liq_31_90d",
        "portfolio_liq_91_180d",
        "portfolio_liq_181_365d",
        "portfolio_liq_gt_365d",
        "unencumbered_cash",
        "investor_liq_0_1d",
        "investor_liq_2_7d",
        "investor_liq_8_30d",
        "investor_liq_31_90d",
        "investor_liq_91_180d",
        "investor_liq_181_365d",
        "investor_liq_gt_365d",
        "side_pocket_pct",
        "gates_pct",
        "dealing_suspension_pct",
        "other_arrangement_type",
        "other_arrangement_pct",
        "total_arrangement_pct",
        "preferential_treatment_flag",
        "disclosure_pref_flag",
        "liquidity_pref_flag",
        "fee_pref_flag",
        "other_pref_flag",
        "available_financing",
        "financing_liq_0_1d",
        "financing_liq_2_7d",
        "financing_liq_8_30d",
        "financing_liq_31_90d",
        "financing_liq_91_180d",
        "financing_liq_181_365d",
        "financing_liq_gt_365d",
        "stress_test_art15",
        "stress_test_art16",
        "rehypothecation_flag",
        "rehypothecation_pct",
        "unsecured_borrowing",
        "secured_prime_broker",
        "secured_reverse_repo",
        "secured_other",
        "etd_exposure",
        "otc_exposure",
        "short_position_value",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


# ============================================================================
# Collection Entities (multiple per fund)
# ============================================================================

@dataclass
class Position(SourceEntity):
    """A single portfolio position within a fund.

    Attributes (all stored as Optional[FieldValue]):
        aif_id: Fund identifier
        instrument_name: Instrument name
        isin: ISIN code
        sub_asset_type: Sub-asset type classification
        asset_type: Main asset type classification
        market_type: Market type (exchange, OTC, etc.)
        mic_code: MIC code for exchange
        counterparty_type: Counterparty type (broker, issuer, etc.)
        counterparty_name: Counterparty name
        counterparty_lei: Counterparty LEI
        currency: Position currency
        market_value: Market value of position
        notional_value: Notional value
        volume: Volume/quantity
        region: Geographic region
        short_long: Whether position is short or long
        position_type: Type of position (equity, bond, derivative, etc.)
    """

    _FIELD_NAMES = (
        "aif_id",
        "instrument_name",
        "isin",
        "sub_asset_type",
        "asset_type",
        "market_type",
        "mic_code",
        "counterparty_type",
        "counterparty_name",
        "counterparty_lei",
        "currency",
        "market_value",
        "notional_value",
        "volume",
        "region",
        "short_long",
        "position_type",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class Transaction(SourceEntity):
    """A single transaction (trade) executed by the fund.

    Attributes (all stored as Optional[FieldValue]):
        aif_id: Fund identifier
        sub_asset_type: Sub-asset type classification
        instrument_name: Instrument name
        market_value: Market value of transaction
        notional_value: Notional value
        volume: Volume/quantity traded
        date: Transaction date
    """

    _FIELD_NAMES = (
        "aif_id",
        "sub_asset_type",
        "instrument_name",
        "market_value",
        "notional_value",
        "volume",
        "date",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class Instrument(SourceEntity):
    """An instrument that may be traded across multiple positions.

    Attributes (all stored as Optional[FieldValue]):
        name: Instrument name
        isin: ISIN code
        sub_asset_type: Sub-asset type classification
        market_type: Market type (exchange, OTC, etc.)
        mic_code: MIC code for exchange
        counterparty_type: Counterparty type (issuer, etc.)
        counterparty_name: Counterparty name
        counterparty_lei: Counterparty LEI
        currency: Instrument currency
        region: Geographic region
    """

    _FIELD_NAMES = (
        "name",
        "isin",
        "sub_asset_type",
        "market_type",
        "mic_code",
        "counterparty_type",
        "counterparty_name",
        "counterparty_lei",
        "currency",
        "region",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class ShareClass(SourceEntity):
    """A share class within a fund.

    Attributes (all stored as Optional[FieldValue]):
        aif_id: Fund identifier
        share_class_name: Share class name
        share_class_isin: Share class ISIN
        nav: Net Asset Value of the share class
        share_class_identifier: Additional identifier
    """

    _FIELD_NAMES = (
        "aif_id",
        "share_class_name",
        "share_class_isin",
        "nav",
        "share_class_identifier",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class Counterparty(SourceEntity):
    """A counterparty with exposure to the fund.

    Attributes (all stored as Optional[FieldValue]):
        aif_id: Fund identifier
        name: Counterparty name
        lei: Legal Entity Identifier
        exposure_type: Type of exposure (prime broker, issuer, etc.)
        exposure_value: Exposure value in fund currency
        exposure_pct: Exposure as percentage of AuM
    """

    _FIELD_NAMES = (
        "aif_id",
        "name",
        "lei",
        "exposure_type",
        "exposure_value",
        "exposure_pct",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class Strategy(SourceEntity):
    """An investment strategy used by the fund.

    Attributes (all stored as Optional[FieldValue]):
        aif_id: Fund identifier
        strategy_code: Strategy code/identifier
        strategy_name: Strategy name
        nav_pct: Percentage of fund NAV in this strategy
        gross_pct: Gross exposure as percentage
    """

    _FIELD_NAMES = (
        "aif_id",
        "strategy_code",
        "strategy_name",
        "nav_pct",
        "gross_pct",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class Investor(SourceEntity):
    """An investor in the fund.

    Attributes (all stored as Optional[FieldValue]):
        aif_id: Fund identifier
        investor_type: Type of investor (individual, institution, etc.)
        investor_pct: Percentage of fund held by investor
    """

    _FIELD_NAMES = (
        "aif_id",
        "investor_type",
        "investor_pct",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class RiskMeasure(SourceEntity):
    """A risk measurement for the fund.

    Attributes (all stored as Optional[FieldValue]):
        aif_id: Fund identifier
        risk_type: Type of risk (VaR, leverage, etc.)
        risk_description: Description of the risk measure
        risk_value: Numerical value of the risk metric
        risk_date: Date of the measurement
    """

    _FIELD_NAMES = (
        "aif_id",
        "risk_type",
        "risk_description",
        "risk_value",
        "risk_date",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class MonthlyData(SourceEntity):
    """Monthly performance and flow data for the fund.

    Attributes (all stored as Optional[FieldValue]):
        aif_id: Fund identifier
        month: Month/period identifier
        gross_return: Gross return for the month
        net_return: Net return for the month
        nav_change: Change in NAV for the month
        subscriptions: Subscriptions during the month
        redemptions: Redemptions during the month
    """

    _FIELD_NAMES = (
        "aif_id",
        "month",
        "gross_return",
        "net_return",
        "nav_change",
        "subscriptions",
        "redemptions",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class BorrowingSource(SourceEntity):
    """A source of borrowing/financing for the fund.

    Attributes (all stored as Optional[FieldValue]):
        aif_id: Fund identifier
        source_type: Type of borrowing source (prime broker, bank, etc.)
        amount: Amount borrowed
        leverage_type: Type of leverage (secured, unsecured, etc.)
        collateral_type: Type of collateral pledged
        collateral_value: Value of collateral
    """

    _FIELD_NAMES = (
        "aif_id",
        "source_type",
        "amount",
        "leverage_type",
        "collateral_type",
        "collateral_value",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class ControlledCompany(SourceEntity):
    """A company controlled or significantly influenced by the fund.

    Attributes (all stored as Optional[FieldValue]):
        aif_id: Fund identifier
        company_name: Name of the controlled company
        domicile: Company domicile/jurisdiction
        transaction_type: Type of transaction/control (acquisition, etc.)
        voting_pct: Percentage of voting rights held
        ownership_pct: Percentage of ownership/economic interest held
        strategy_code: Associated strategy code
    """

    _FIELD_NAMES = (
        "aif_id",
        "company_name",
        "domicile",
        "transaction_type",
        "voting_pct",
        "ownership_pct",
        "strategy_code",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


@dataclass
class ControlledStructure(SourceEntity):
    """A securitized structure or vehicle controlled by the fund.

    Attributes (all stored as Optional[FieldValue]):
        aif_id: Fund identifier
        issuer_name: Name of the issuer/structure
        securitised_assets: Description of assets in the structure
        sponsored_flag: Whether fund sponsored the structure
    """

    _FIELD_NAMES = (
        "aif_id",
        "issuer_name",
        "securitised_assets",
        "sponsored_flag",
    )

    def __post_init__(self):
        """Initialize parent class."""
        super().__init__()


# ============================================================================
# Top-Level Container
# ============================================================================

@dataclass
class SourceCanonical:
    """Two-layer canonical: source domain layer.

    Contains rich, reusable domain entities that can project to multiple
    report formats (AIFMD, UCITS, etc.). Serves as the rich source of truth
    that feeds into the Report Canonical (model.py) for AIFMD Annex IV.

    Attributes:
        manager: AIFM identity and NCA registration data
        fund_static: Semi-permanent fund properties
        fund_dynamic: Per-period fund data
        positions: List of portfolio positions
        transactions: List of trades executed
        instruments: List of instruments available for trading
        share_classes: List of fund share classes
        counterparties: List of counterparties with exposure
        strategies: List of investment strategies
        investors: List of fund investors
        risk_measures: List of risk measurements
        monthly_data: List of monthly performance data
        borrowing_sources: List of financing/borrowing sources
        controlled_companies: List of controlled companies
        controlled_structures: List of securitized structures
        source_adapter: Identifier of adapter that created this canonical
        created_at: Timestamp of creation (UTC)
    """

    manager: ManagerStatic = field(default_factory=ManagerStatic)
    fund_static: FundStatic = field(default_factory=FundStatic)
    fund_dynamic: FundDynamic = field(default_factory=FundDynamic)

    positions: list[Position] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)
    instruments: list[Instrument] = field(default_factory=list)
    share_classes: list[ShareClass] = field(default_factory=list)
    counterparties: list[Counterparty] = field(default_factory=list)
    strategies: list[Strategy] = field(default_factory=list)
    investors: list[Investor] = field(default_factory=list)
    risk_measures: list[RiskMeasure] = field(default_factory=list)
    monthly_data: list[MonthlyData] = field(default_factory=list)
    borrowing_sources: list[BorrowingSource] = field(default_factory=list)
    controlled_companies: list[ControlledCompany] = field(default_factory=list)
    controlled_structures: list[ControlledStructure] = field(default_factory=list)

    source_adapter: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Serialize the entire canonical to a JSON-compatible dict.

        Returns:
            Dict containing all scalar entities, collection entities, and metadata.
            Each FieldValue is serialized via FieldValue.to_dict().
        """
        return {
            "manager": self.manager.to_dict(),
            "fund_static": self.fund_static.to_dict(),
            "fund_dynamic": self.fund_dynamic.to_dict(),
            "positions": [p.to_dict() for p in self.positions],
            "transactions": [t.to_dict() for t in self.transactions],
            "instruments": [i.to_dict() for i in self.instruments],
            "share_classes": [sc.to_dict() for sc in self.share_classes],
            "counterparties": [c.to_dict() for c in self.counterparties],
            "strategies": [s.to_dict() for s in self.strategies],
            "investors": [inv.to_dict() for inv in self.investors],
            "risk_measures": [rm.to_dict() for rm in self.risk_measures],
            "monthly_data": [md.to_dict() for md in self.monthly_data],
            "borrowing_sources": [bs.to_dict() for bs in self.borrowing_sources],
            "controlled_companies": [cc.to_dict() for cc in self.controlled_companies],
            "controlled_structures": [cs.to_dict() for cs in self.controlled_structures],
            "source_adapter": self.source_adapter,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> SourceCanonical:
        """Deserialize a SourceCanonical from a JSON-compatible dict.

        Args:
            data: Dict as produced by to_dict()

        Returns:
            SourceCanonical instance with all entities restored
        """
        return cls(
            manager=ManagerStatic.from_dict(data.get("manager", {})),
            fund_static=FundStatic.from_dict(data.get("fund_static", {})),
            fund_dynamic=FundDynamic.from_dict(data.get("fund_dynamic", {})),
            positions=[Position.from_dict(p) for p in data.get("positions", [])],
            transactions=[Transaction.from_dict(t) for t in data.get("transactions", [])],
            instruments=[Instrument.from_dict(i) for i in data.get("instruments", [])],
            share_classes=[ShareClass.from_dict(sc) for sc in data.get("share_classes", [])],
            counterparties=[Counterparty.from_dict(c) for c in data.get("counterparties", [])],
            strategies=[Strategy.from_dict(s) for s in data.get("strategies", [])],
            investors=[Investor.from_dict(inv) for inv in data.get("investors", [])],
            risk_measures=[RiskMeasure.from_dict(rm) for rm in data.get("risk_measures", [])],
            monthly_data=[MonthlyData.from_dict(md) for md in data.get("monthly_data", [])],
            borrowing_sources=[BorrowingSource.from_dict(bs) for bs in data.get("borrowing_sources", [])],
            controlled_companies=[ControlledCompany.from_dict(cc) for cc in data.get("controlled_companies", [])],
            controlled_structures=[ControlledStructure.from_dict(cs) for cs in data.get("controlled_structures", [])],
            source_adapter=data.get("source_adapter", ""),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now(timezone.utc).isoformat())),
        )

    def summary(self) -> dict:
        """Return a summary of entity counts and key information.

        Returns:
            Dict with entity counts, fund name, manager name, and metadata
        """
        return {
            "source_adapter": self.source_adapter,
            "created_at": self.created_at.isoformat(),
            "manager_name": self.manager.get("name"),
            "fund_name": self.fund_static.get("name"),
            "entity_counts": {
                "positions": len(self.positions),
                "transactions": len(self.transactions),
                "instruments": len(self.instruments),
                "share_classes": len(self.share_classes),
                "counterparties": len(self.counterparties),
                "strategies": len(self.strategies),
                "investors": len(self.investors),
                "risk_measures": len(self.risk_measures),
                "monthly_data": len(self.monthly_data),
                "borrowing_sources": len(self.borrowing_sources),
                "controlled_companies": len(self.controlled_companies),
                "controlled_structures": len(self.controlled_structures),
            },
        }

    def __repr__(self) -> str:
        """Return a concise representation."""
        return (
            f"SourceCanonical(manager={self.manager.get('name')!r}, "
            f"fund={self.fund_static.get('name')!r}, "
            f"positions={len(self.positions)}, transactions={len(self.transactions)})"
        )
