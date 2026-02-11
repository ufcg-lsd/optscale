#!/usr/bin/env python3
"""
Script to fetch S3 Intelligent Tiering prices from AWS Pricing API
for all AWS regions and all storage classes.

The script automatically uses AWS CLI credentials configured in ~/.aws/credentials
or environment variables AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.

Usage:
    python fetch_s3_it_prices_direct.py

Or with environment variables:
    export AWS_ACCESS_KEY_ID=<KEY>
    export AWS_SECRET_ACCESS_KEY=<SECRET>
    python fetch_s3_it_prices_direct.py
"""

import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List

import boto3
from botocore.exceptions import ClientError, BotoCoreError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)

# Mapping from regionCode to standard region code
REGION_CODE_MAPPING = {
    "us-east-1": "us-east-1",
    "us-east-2": "us-east-2",
    "us-west-1": "us-west-1",
    "us-west-2": "us-west-2",
    "eu-west-1": "eu-west-1",
    "eu-west-2": "eu-west-2",
    "eu-west-3": "eu-west-3",
    "eu-central-1": "eu-central-1",
    "eu-north-1": "eu-north-1",
    "eu-south-1": "eu-south-1",
    "eu-south-2": "eu-south-2",
    "ap-southeast-1": "ap-southeast-1",
    "ap-southeast-2": "ap-southeast-2",
    "ap-southeast-3": "ap-southeast-3",
    "ap-southeast-4": "ap-southeast-4",
    "ap-southeast-5": "ap-southeast-5",
    "ap-northeast-1": "ap-northeast-1",
    "ap-northeast-2": "ap-northeast-2",
    "ap-northeast-3": "ap-northeast-3",
    "ap-south-1": "ap-south-1",
    "ap-south-2": "ap-south-2",
    "ap-east-1": "ap-east-1",
    "ca-central-1": "ca-central-1",
    "sa-east-1": "sa-east-1",
    "af-south-1": "af-south-1",
    "me-south-1": "me-south-1",
    "me-central-1": "me-central-1",
    "il-central-1": "il-central-1",
    "us-gov-east-1": "us-gov-east-1",
    "us-gov-west-1": "us-gov-west-1",
    "cn-north-1": "cn-north-1",
    "cn-northwest-1": "cn-northwest-1",
}


def normalize_storage_class(storage_class: str, usagetype: str = "") -> Optional[str]:
    """
    Normalizes the storage class name to identify the tier.

    Uses regex and pattern matching to identify different variations:
    - Frequent Access / FA
    - Infrequent Access / IA
    - Archive Instant Access / AIA
    - Deep Archive Access / DAA

    Args:
        storage_class: Storage class name (may come in various formats)
        usagetype: AWS usage type (used as fallback)

    Returns:
        Normalized tier code (FA, IA, AIA, DAA) or None
    """
    # Combines storage_class and usagetype for analysis
    text_to_analyze = f"{storage_class or ''} {usagetype or ''}".strip()

    if not text_to_analyze:
        return None

    # Normalizes to lowercase and removes extra spaces/hyphens
    normalized = re.sub(r'[\s\-_]+', '', text_to_analyze.lower())

    # Patterns for Deep Archive Access (must come BEFORE Archive Instant Access)
    if re.search(r'deeparchive|daa|deep.*archive', normalized, re.IGNORECASE):
        return "DAA"

    # Patterns for Archive Instant Access
    if re.search(r'archiveinstant|aia|archive.*instant', normalized, re.IGNORECASE):
        return "AIA"

    # Patterns for Frequent Access
    if re.search(r'frequent|fa(?!a)', normalized, re.IGNORECASE):
        return "FA"

    # Patterns for Infrequent Access (must come after Frequent)
    if re.search(r'infrequent|ia(?!a)', normalized, re.IGNORECASE):
        return "IA"

    # Tries to identify by specific usagetype patterns
    # Examples: IntelligentTieringFAStorage, IntelligentTieringIAStorage, etc.
    if re.search(r'intelligenttieringfastorage|it.*fa', normalized, re.IGNORECASE):
        return "FA"
    if re.search(r'intelligenttieringiastorage|it.*ia(?!a)', normalized, re.IGNORECASE):
        return "IA"
    if re.search(r'intelligenttieringaastorage|it.*aa(?!a)', normalized, re.IGNORECASE):
        return "AIA"
    if re.search(r'intelligenttieringdaastorage|it.*daa', normalized, re.IGNORECASE):
        return "DAA"

    return None


def normalize_region_code(region_code: str) -> Optional[str]:
    """
    Normalizes the region code to standard format.

    Args:
        region_code: AWS region code (may vary)

    Returns:
        Normalized region code or None
    """
    if not region_code:
        return None

    # Normalizes to lowercase
    normalized = region_code.lower().strip()

    # Returns if already in mapping
    if normalized in REGION_CODE_MAPPING:
        return normalized

    # Tries to find partial match
    for key, value in REGION_CODE_MAPPING.items():
        if key.startswith(normalized) or normalized.startswith(key):
            return value

    return normalized  # Returns original value if no match found


def filter_pricing_item(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Filters an AWS pricing item to extract relevant information.

    Args:
        raw: Raw product data returned by the API

    Returns:
        List of filtered items with price information
    """
    product = raw.get("product", {})
    attrs = product.get("attributes", {})
    filtered_items = []
    terms = raw.get("terms", {}).get("OnDemand", {})
    for term in terms.values():
        effective_date = term.get("effectiveDate")

        for dim in term.get("priceDimensions", {}).values():
            # Filters only items with GB-Mo unit (GB per month)
            # Accepts variations like "GB-Month", "GB-Mo", etc.
            unit = dim.get("unit", "")
            if not unit or "GB" not in unit.upper() or "MO" not in unit.upper():
                continue

            price = dim.get("pricePerUnit", {}).get("USD")
            if not price:
                continue

            # Extracts product information
            region_code = attrs.get("regionCode")
            region_name = attrs.get("location")
            storage_class = attrs.get("storageClass")
            usagetype = attrs.get("usagetype", "")

            # Normalizes storage class to identify tier
            # Passes both storage_class and usagetype for better identification
            tier = normalize_storage_class(storage_class or "", usagetype)

            # Normalizes region code
            normalized_region = normalize_region_code(region_code) if region_code else None

            filtered_items.append({
                "region_code": normalized_region or region_code,
                "region_name": region_name,
                "storage_class": storage_class,
                "usagetype": usagetype,
                "tier": tier,  # Normalized tier (FA, IA, AIA, DAA)
                "unit": dim.get("unit"),
                "price_per_unit_usd": float(price),
                "sku": product.get("sku"),
                "description": dim.get("description"),
                "effective_date": effective_date
            })

    return filtered_items


def fetch_all_prices() -> Dict[str, Dict[str, Any]]:
    """
    Fetches all S3 Intelligent Tiering prices from AWS Pricing API.

    Returns:
        Dict organized by region and tier: {
            "us-east-1": {
                "FA": {"price": 0.023, "sku": "...", ...},
                "IA": {"price": 0.0125, ...},
                ...
            },
            ...
        }
    """
    LOG.info("Creating AWS Pricing client...")
    pricing = boto3.client("pricing", region_name="us-east-1")

    filters = [
        {
            "Type": "TERM_MATCH",
            "Field": "servicecode",
            "Value": "AmazonS3",
        },
        {
            "Type": "TERM_MATCH",
            "Field": "storageClass",
            "Value": "Intelligent-Tiering",
        },
    ]

    LOG.info("Fetching products from AWS Pricing API...")
    paginator = pricing.get_paginator("get_products")
    page_iterator = paginator.paginate(
        ServiceCode="AmazonS3",
        Filters=filters,
        FormatVersion="aws_v1"
    )

    # Organizes prices by region and tier
    prices_by_region_tier: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    total_items = 0
    processed_items = 0
    items_without_tier = []
    items_without_region = []
    sample_raw_items = []  # For debugging
    for page_num, page in enumerate(page_iterator, 1):
        LOG.debug(f"Processing page {page_num}...")

        for price_item in page["PriceList"]:
            total_items += 1
            try:
                raw = json.loads(price_item)
                # Saves first raw items for debugging
                if total_items <= 5:
                    attrs = raw.get("product", {}).get("attributes", {})
                    sample_raw_items.append({
                        "item_num": total_items,
                        "storageClass": attrs.get("storageClass"),
                        "usagetype": attrs.get("usagetype"),
                        "regionCode": attrs.get("regionCode"),
                        "location": attrs.get("location"),
                        "units": [
                            d.get("unit")
                            for term in raw.get("terms", {}).get("OnDemand", {}).values()
                            for d in term.get("priceDimensions", {}).values()
                        ]
                    })
                filtered = filter_pricing_item(raw)
                if not filtered:
                    # Logs first items without filters for debugging
                    if total_items <= 5:
                        attrs = raw.get("product", {}).get("attributes", {})
                        units = []
                        for term in raw.get("terms", {}).get("OnDemand", {}).values():
                            for d in term.get("priceDimensions", {}).values():
                                units.append(d.get("unit"))
                        LOG.warning(
                            f"Item {total_items} without filters - "
                            f"storageClass: '{attrs.get('storageClass')}', "
                            f"usagetype: '{attrs.get('usagetype')}', "
                            f"regionCode: '{attrs.get('regionCode')}', "
                            f"location: '{attrs.get('location')}', "
                            f"units: {units}"
                        )
                    continue

                for item in filtered:
                    region = item.get("region_code")
                    tier = item.get("tier")
                    # Logs all filtered items for debugging (first 10)
                    if total_items <= 10:
                        LOG.info(
                            f"Filtered item {total_items}: region='{region}', tier='{tier}', "
                            f"storage_class='{item.get('storage_class')}', "
                            f"usagetype='{item.get('usagetype')}', "
                            f"price=${item.get('price_per_unit_usd')}"
                        )

                    if region and tier:
                        prices_by_region_tier[region][tier].append(item)
                        processed_items += 1

                        if processed_items <= 5:  # Logs first 5 valid items
                            LOG.info(
                                f"✓ Valid price: {region} - {tier} = "
                                f"${item['price_per_unit_usd']:.6f} per GB/month"
                            )
                    else:
                        if not tier:
                            items_without_tier.append(
                                {
                                    "region": region,
                                    "storage_class": item.get("storage_class"),
                                    "usagetype": item.get("usagetype"),
                                    "price": item.get("price_per_unit_usd"),
                                }
                            )
                        if not region:
                            items_without_region.append(
                                {
                                    "tier": tier,
                                    "storage_class": item.get("storage_class"),
                                    "usagetype": item.get("usagetype"),
                                    "region_code_raw": raw.get(
                                        "product", {}
                                    ).get("attributes", {}).get("regionCode"),
                                    "location": raw.get(
                                        "product", {}
                                    ).get("attributes", {}).get("location"),
                                    "price": item.get("price_per_unit_usd"),
                                }
                            )

            except Exception as exc:
                LOG.warning(f"Error processing item {total_items}: {exc}", exc_info=True)
                continue

    # Logs debug statistics
    if items_without_tier:
        LOG.warning(
            "Found %d items without identified tier",
            len(items_without_tier),
        )
        # Shows unique examples
        unique_examples = {}
        for item in items_without_tier[:10]:
            key = (item.get("storage_class"), item.get("usagetype"))
            if key not in unique_examples:
                unique_examples[key] = item
        for example in unique_examples.values():
            LOG.warning(
                "  Example without tier: storage_class='%s', usagetype='%s'",
                example.get("storage_class"),
                example.get("usagetype"),
            )

    if items_without_region:
        LOG.warning(
            "Found %d items without identified region",
            len(items_without_region),
        )
        for example in items_without_region[:5]:
            LOG.warning(
                "  Example without region: tier=%s, region_code_raw='%s'",
                example.get("tier"),
                example.get("region_code_raw"),
            )

    LOG.info(
        "Processed %d valid items out of %d total",
        processed_items,
        total_items,
    )

    # Logs examples of raw items for debugging
    if sample_raw_items:
        LOG.info("Examples of raw items from API:")
        for sample in sample_raw_items[:3]:
            LOG.info(
                f"  Item {sample['item_num']}: "
                f"storageClass='{sample['storageClass']}', "
                f"usagetype='{sample['usagetype']}', "
                f"regionCode='{sample['regionCode']}', "
                f"units={sample['units']}"
            )

    # Organizes data more cleanly, taking the most recent price per region/tier
    organized_prices: Dict[str, Dict[str, Any]] = {}

    for region, tiers in prices_by_region_tier.items():
        organized_prices[region] = {}

        for tier, items in tiers.items():
            # If there are multiple items, takes the most recent (by effective_date)
            if items:
                # Sorts by effective_date (most recent first)
                sorted_items = sorted(
                    items,
                    key=lambda x: x.get("effective_date", ""),
                    reverse=True
                )
                # Takes the first (most recent)
                latest_item = sorted_items[0]

                organized_prices[region][tier] = {
                    "price_per_unit_usd": latest_item["price_per_unit_usd"],
                    "sku": latest_item["sku"],
                    "description": latest_item["description"],
                    "effective_date": latest_item["effective_date"],
                    "region_name": latest_item["region_name"],
                    "storage_class": latest_item["storage_class"],
                    "usagetype": latest_item["usagetype"],
                    # Includes all found items for reference
                    "all_items_count": len(items)
                }

    LOG.info(
        f"Prices organized for {len(organized_prices)} regions with "
        f"{sum(len(tiers) for tiers in organized_prices.values())} region/tier combinations"
    )

    return organized_prices


def save_prices(
    prices_by_region: Dict[str, Dict[str, Any]],
    output_file: Path
):
    """
    Saves prices to a structured JSON file.

    Args:
        prices_by_region: Dict organized by region and tier
        output_file: Output file path
    """
    # Calculates default prices (average of found values) for fallback
    default_prices = {}
    tier_counts = defaultdict(int)
    tier_sums = defaultdict(float)

    for region_prices in prices_by_region.values():
        for tier, data in region_prices.items():
            if isinstance(data, dict) and "price_per_unit_usd" in data:
                tier_sums[tier] += data["price_per_unit_usd"]
                tier_counts[tier] += 1

    for tier in tier_sums:
        if tier_counts[tier] > 0:
            default_prices[tier] = tier_sums[tier] / tier_counts[tier]

    # Creates simplified structure for compatibility with existing code
    simplified_prices = {}
    detailed_prices = {}

    for region, tiers in prices_by_region.items():
        simplified_prices[region] = {}
        detailed_prices[region] = {}

        for tier, data in tiers.items():
            if isinstance(data, dict) and "price_per_unit_usd" in data:
                simplified_prices[region][tier] = data["price_per_unit_usd"]
                detailed_prices[region][tier] = data

    output_data = {
        "description": "S3 Intelligent Tiering prices from AWS by region (obtained via AWS Pricing API)",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "prices_by_region": simplified_prices,  # Simplified format for compatibility
        "detailed_prices_by_region": detailed_prices,  # Detailed format with metadata
        "default_prices": default_prices,
        "tier_mappings": {
            "FA": "Frequent Access",
            "IA": "Infrequent Access",
            "AIA": "Archive Instant Access",
            "DAA": "Deep Archive Access",
        },
        "access_tier_to_price_tier": {
            "frequent": "FA",
            "infrequent": "IA",
            "archive": "AIA"
        },
        "statistics": {
            "total_regions": len(prices_by_region),
            "total_tier_prices": sum(len(tiers) for tiers in prices_by_region.values()),
            "tiers_found": list(set(
                tier for region_prices in prices_by_region.values()
                for tier in region_prices.keys()
            ))
        }
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    LOG.info(f"Prices saved to {output_file}")


def main():
    """Main function of the script."""
    try:
        LOG.info("=" * 60)
        LOG.info("Starting S3 Intelligent Tiering price fetch")
        LOG.info("=" * 60)

        prices_by_region = fetch_all_prices()

        # Defines output file
        script_dir = Path(__file__).parent
        output_file = script_dir / "s3_it_prices_all_regions.json"

        save_prices(prices_by_region, output_file)

        LOG.info("=" * 60)
        LOG.info("Prices fetched successfully!")
        LOG.info(f"Total regions processed: {len(prices_by_region)}")

        # Shows some examples
        regions_with_prices = [
            r for r, prices in prices_by_region.items()
            if prices
        ]

        if regions_with_prices:
            LOG.info(f"\nRegions with prices found: {len(regions_with_prices)}")
            sample_regions = regions_with_prices[:5]

            for region in sample_regions:
                if prices_by_region[region]:
                    LOG.info(f"\nExample - {region}:")
                    for tier, data in prices_by_region[region].items():
                        if isinstance(data, dict) and "price_per_unit_usd" in data:
                            price = data["price_per_unit_usd"]
                            storage_class = data.get("storage_class", "N/A")
                            LOG.info(
                                f"  {tier} ({storage_class}): "
                                f"${price:.6f} per GB/month"
                            )
        else:
            LOG.warning("No prices found for any region")

        LOG.info("=" * 60)
        LOG.info(f"File saved to: {output_file}")

    except Exception as exc:
        LOG.error(f"Error fetching prices: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
