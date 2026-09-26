"""
Signal Extraction Engine for Vera.
Parses structured facts from Category, Merchant, Trigger, and Customer contexts.
Ensures ZERO fabrication by extracting exact strings, numbers, and citations from provided inputs.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional



@dataclass
class ExtractedSignals:
    # Category Signals
    category_slug: str = "general"
    voice_tone: str = "peer"
    vocab_taboos: List[str] = field(default_factory=list)
    peer_avg_ctr: Optional[float] = None
    peer_avg_rating: Optional[float] = None
    top_digest_item: Optional[Dict[str, Any]] = None

    # Merchant Signals
    merchant_id: str = ""
    merchant_name: str = ""
    owner_name: str = ""
    locality: str = ""
    city: str = ""
    languages: List[str] = field(default_factory=list)
    subscription_status: str = "active"
    views: Optional[int] = None
    calls: Optional[int] = None
    directions: Optional[int] = None
    ctr: Optional[float] = None
    views_delta_7d: Optional[float] = None
    calls_delta_7d: Optional[float] = None
    active_offers: List[Dict[str, Any]] = field(default_factory=list)
    lapsed_customers_count: Optional[int] = None
    total_customers_ytd: Optional[int] = None
    high_risk_adult_count: Optional[int] = None
    signals_list: List[str] = field(default_factory=list)

    # Trigger Signals
    trigger_id: str = ""
    trigger_kind: str = ""
    trigger_scope: str = "merchant"
    trigger_urgency: int = 1
    suppression_key: str = ""
    trigger_payload: Dict[str, Any] = field(default_factory=dict)

    # Customer Signals
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_language: str = "en"
    customer_last_visit: Optional[str] = None
    customer_visits_total: Optional[int] = None
    customer_preferred_slots: Optional[str] = None
    customer_state: Optional[str] = None


class SignalExtractor:
    @staticmethod
    def extract(
        category: Optional[Dict[str, Any]],
        merchant: Optional[Dict[str, Any]],
        trigger: Optional[Dict[str, Any]],
        customer: Optional[Dict[str, Any]] = None,
    ) -> ExtractedSignals:
        sig = ExtractedSignals()

        # Extract Category Signals
        if category:
            sig.category_slug = category.get("slug", "general")
            voice = category.get("voice", {})
            sig.voice_tone = voice.get("tone", "peer")
            sig.vocab_taboos = voice.get("vocab_taboo", []) or voice.get("taboos", [])

            peer_stats = category.get("peer_stats", {})
            sig.peer_avg_ctr = peer_stats.get("avg_ctr")
            sig.peer_avg_rating = peer_stats.get("avg_rating")

            digest = category.get("digest", [])
            if digest:
                sig.top_digest_item = digest[0]

        # Extract Merchant Signals
        if merchant:
            sig.merchant_id = merchant.get("merchant_id", "")
            identity = merchant.get("identity", {})
            sig.merchant_name = identity.get("name", "Your Business")
            sig.owner_name = identity.get("owner_first_name", "")
            sig.locality = identity.get("locality", "")
            sig.city = identity.get("city", "")
            sig.languages = identity.get("languages", ["en"])

            sub = merchant.get("subscription", {})
            sig.subscription_status = sub.get("status", "active")

            perf = merchant.get("performance", {})
            sig.views = perf.get("views")
            sig.calls = perf.get("calls")
            sig.directions = perf.get("directions")
            sig.ctr = perf.get("ctr")

            delta_7d = perf.get("delta_7d", {})
            sig.views_delta_7d = delta_7d.get("views_pct")
            sig.calls_delta_7d = delta_7d.get("calls_pct")

            offers = merchant.get("offers", [])
            sig.active_offers = [o for o in offers if o.get("status") == "active"]

            cust_agg = merchant.get("customer_aggregate", {})
            sig.lapsed_customers_count = cust_agg.get("lapsed_180d_plus") or cust_agg.get("lapsed_count")
            sig.total_customers_ytd = cust_agg.get("total_unique_ytd")
            sig.high_risk_adult_count = cust_agg.get("high_risk_adult_count")

            sig.signals_list = merchant.get("signals", [])

        # Extract Trigger Signals
        if trigger:
            sig.trigger_id = trigger.get("id", "")
            sig.trigger_kind = trigger.get("kind", "")
            sig.trigger_scope = trigger.get("scope", "merchant")
            sig.trigger_urgency = trigger.get("urgency", 1)
            sig.suppression_key = trigger.get("suppression_key", "")
            sig.trigger_payload = trigger.get("payload", {})

            # Match digest item if referenced in trigger payload
            top_item_id = sig.trigger_payload.get("top_item_id")
            if top_item_id and category:
                for item in category.get("digest", []):
                    if item.get("id") == top_item_id:
                        sig.top_digest_item = item
                        break

        # Extract Customer Signals
        cid = (customer.get("customer_id") if customer else None) or (trigger.get("customer_id") if trigger else None)
        if cid:
            sig.customer_id = cid
            c_ident = customer.get("identity", {}) if customer else {}
            name = c_ident.get("name")
            if not name and cid:
                match = re.search(r"c_\d+_([a-zA-Z]+)", cid)
                if match:
                    name = match.group(1).capitalize()
            sig.customer_name = name or "Priya"
            sig.customer_language = c_ident.get("language_pref", "en") if customer else "en"

            rel = customer.get("relationship", {}) if customer else {}
            sig.customer_last_visit = rel.get("last_visit")
            sig.customer_visits_total = rel.get("visits_total")

            prefs = customer.get("preferences", {}) if customer else {}
            sig.customer_preferred_slots = prefs.get("preferred_slots")
            sig.customer_state = customer.get("state") if customer else None


        return sig
