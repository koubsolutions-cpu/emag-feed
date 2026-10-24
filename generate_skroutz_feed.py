
import csv
import os
import sys
import requests
import pandas as pd
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from pathlib import Path


# ============================================================
# SKROUTZ SETTINGS
# ============================================================

SUPPLIER_CSV_URL = (
    "https://www.gsmnet.ro/csv/feedPriceCustomersDiamond.csv"
)

COMMISSION_FILE = "skroutz_commissions.csv"
CATEGORY_MAPPING_FILE = "skroutz_category_mapping.csv"

OUTPUT_XML = "skroutz_feed.xml"
OUTPUT_REPORT = "skroutz_feed_report.csv"

TRANSPORT_EUR = Decimal("2.00")
GREEK_VAT_RATE = Decimal("24.00")

# Use the existing marketplace markup tiers as the starting
# selling-price basis, then account separately for Skroutz
# commission and transport.
#
# Commission must be a percentage, e.g. 12.5 means 12.5%.


# ============================================================
# HELPERS
# ============================================================

def money(value):
    return Decimal(str(value)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def round99(value):
    """Round upwards to a price ending in .99."""
    value = Decimal(str(value))
    whole = value.quantize(
        Decimal("1"), rounding=ROUND_CEILING
    )
    result = whole - Decimal("0.01")
    if result < value:
        result += Decimal("1")
    return result.quantize(Decimal("0.01"))


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def get_eur_ron_rate():
    """Get the latest EUR/RON reference rate from the ECB."""
    url = (
        "https://www.ecb.europa.eu/stats/eurofxref/"
        "eurofxref-daily.xml"
    )
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)

    for element in root.iter():
        if element.attrib.get("currency") == "RON":
            return Decimal(element.attrib["rate"])

    raise RuntimeError("Could not find RON in ECB exchange-rate data.")


def markup(cost_ron):
    """Existing GSMNet markup tiers."""
    cost = Decimal(str(cost_ron))

    if cost <= 10:
        return cost * Decimal("2.50")
    elif cost <= 25:
        return cost * Decimal("2.25")
    elif cost <= 50:
        return cost * Decimal("2.00")
    elif cost <= 100:
        return cost * Decimal("1.75")
    elif cost <= 200:
        return cost * Decimal("1.60")
    return cost * Decimal("1.50")


def safety_buffer(cost_ron):
    cost = Decimal(str(cost_ron))

    if cost <= 25:
        return Decimal("1.10")
    elif cost <= 100:
        return Decimal("1.07")
    return Decimal("1.05")


def calculate_prices(cost_ron, commission_pct, eur_ron):
    """
    Return net selling price, VAT amount and final gross price.

    The existing markup tiers establish the base selling price.
    The EUR 2 transport charge and Skroutz commission are then
    accounted for separately.
    """
    cost_ron = Decimal(str(cost_ron))
    commission_pct = Decimal(str(commission_pct))

    if cost_ron <= 0:
        raise ValueError("Supplier cost must be greater than zero.")

    commission = commission_pct / Decimal("100")

    if commission < 0 or commission >= 1:
        raise ValueError("Invalid commission percentage.")

    base_price_ron = (
        markup(cost_ron) * safety_buffer(cost_ron)
    )
    base_price_eur = base_price_ron / eur_ron

    # Add transport, then account for marketplace commission.
    net_price = (
        base_price_eur + TRANSPORT_EUR
    ) / (Decimal("1") - commission)

    net_price = round99(net_price)
    vat_amount = money(
        net_price * GREEK_VAT_RATE / Decimal("100")
    )
    gross_price = money(net_price + vat_amount)

    return net_price, vat_amount, gross_price


# ============================================================
# LOAD CATEGORY RULES
# ============================================================


def load_category_rules():
    for filename in (COMMISSION_FILE, CATEGORY_MAPPING_FILE):
        if not Path(filename).exists():
            raise FileNotFoundError(
                f"Required file missing: {filename}"
            )

    commissions = pd.read_csv(
        COMMISSION_FILE, dtype=str
    ).fillna("")

    mapping = pd.read_csv(
        CATEGORY_MAPPING_FILE, dtype=str
    ).fillna("")

    required_commission = {
        "category", "commission_percent"
    }
    required_mapping = {
        "gsmnet_category",
        "skroutz_category",
        "commission_category",
    }

    if not required_commission.issubset(commissions.columns):
        raise ValueError(
            f"{COMMISSION_FILE} must have columns: "
            "category, commission_percent"
        )

    if not required_mapping.issubset(mapping.columns):
        raise ValueError(
            f"{CATEGORY_MAPPING_FILE} must have columns: "
            "gsmnet_category, skroutz_category, "
            "commission_category"
        )

    commission_lookup = {}

    for _, row in commissions.iterrows():
        category = clean(row["category"])
        percentage = clean(row["commission_percent"])

        if not category or not percentage:
            continue

        percentage = percentage.replace("%", "").replace(",", ".")

        try:
            rate = Decimal(percentage)
        except Exception:
            continue

        if rate < 0 or rate >= 100:
            continue

        commission_lookup[category.casefold()] = rate

    mapping_lookup = {}
    skipped = []

    for _, row in mapping.iterrows():
        gsm_category = clean(row["gsmnet_category"])
        skroutz_category = clean(row["skroutz_category"])
        commission_category = clean(row["commission_category"])

        if not gsm_category or not skroutz_category:
            continue

        commission_key = commission_category.casefold()

        if not commission_category:
            skipped.append(gsm_category)
            continue

        if commission_key not in commission_lookup:
            skipped.append(
                f"{gsm_category} (commission not found: "
                f"{commission_category})"
            )
            continue

        mapping_lookup[gsm_category.casefold()] = {
            "skroutz_category": skroutz_category,
            "commission": commission_lookup[commission_key],
        }

    print(
        f"Loaded {len(mapping_lookup)} approved category rules; "
        f"skipped {len(skipped)} incomplete or unmatched mappings."
    )

    if skipped:
        print("Categories needing review:")
        for category in skipped:
            print(f"  - {category}")

    if not mapping_lookup:
        raise ValueError(
            "No valid category rules loaded. Check the "
            "commission categories in skroutz_category_mapping.csv."
        )

    return mapping_lookup

# ============================================================
# GENERATE XML
# ============================================================

def main():
    print("Loading category commissions and mappings...")
    category_rules = load_category_rules()

    print("Getting EUR/RON exchange rate from ECB...")
    eur_ron = get_eur_ron_rate()
    print(f"1 EUR = {eur_ron} RON")

    print("Downloading GSMNet supplier CSV...")
    response = requests.get(SUPPLIER_CSV_URL, timeout=120)
    response.raise_for_status()

    from io import BytesIO

    # Detect the supplier CSV delimiter instead of assuming commas or semicolons.
    sample = response.content[:65536].decode("utf-8-sig", errors="replace")
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ";"

    df = pd.read_csv(
        BytesIO(response.content),
        sep=delimiter,
        dtype=str,
        encoding="utf-8-sig",
        engine="python",
        on_bad_lines="error",
    )

    df.columns = [
        str(column).replace("\ufeff", "").strip()
        for column in df.columns
    ]

    required_columns = {
        "COD_UNIC", "CATEGORIE", "MARCA", "NUME",
        "EAN", "Pret Diamond cu TVA", "Disponibilitate",
        "LINK PRODUS", "LINK POZA", "PN",
    }

    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(
            "Supplier CSV is missing columns: "
            + ", ".join(sorted(missing))
        )

    df["Pret Diamond cu TVA"] = pd.to_numeric(
        df["Pret Diamond cu TVA"]
        .astype(str)
        .str.replace(",", ".", regex=False),
        errors="coerce",
    )

    # Only in-stock products with valid supplier prices.
    df = df[
        df["Disponibilitate"]
        .astype(str).str.strip().str.casefold().eq("in stoc")
        & df["Pret Diamond cu TVA"].notna()
        & (df["Pret Diamond cu TVA"] > 0)
    ].copy()

    # Keep one record per supplier product ID.
    df = df.drop_duplicates(subset=["COD_UNIC"])

    root = ET.Element("store")
    ET.SubElement(root, "created_at").text = (
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    )
    products_node = ET.SubElement(root, "products")

    report = []
    skipped = 0

    for _, row in df.iterrows():
        uid = clean(row["COD_UNIC"])
        name = clean(row["NUME"])
        brand = clean(row["MARCA"]) or "OEM"
        ean = clean(row["EAN"])
        mpn = clean(row["PN"]) or uid
        product_url = clean(row["LINK PRODUS"])
        image_url = clean(row["LINK POZA"])
        gsm_category = clean(row["CATEGORIE"])

        # Skroutz requires EAN and manufacturer part number.
        if not (
            uid and name and ean.isdigit()
            and len(ean) in (8, 12, 13, 14)
            and mpn and product_url.startswith("https://")
            and image_url.startswith("https://")
        ):
            skipped += 1
            continue

        rule = category_rules.get(gsm_category.casefold())
        if not rule:
            print(f"Skipping unmapped category: {gsm_category}")
            skipped += 1
            continue

        try:
            net, vat_amount, gross = calculate_prices(
                row["Pret Diamond cu TVA"],
                rule["commission"],
                eur_ron,
            )
        except Exception as exc:
            print(f"Skipping product {uid}: {exc}")
            skipped += 1
            continue

        product = ET.SubElement(products_node, "product")

        fields = {
            "uid": uid,
            "name": name[:300],
            "link": product_url,
            "image": image_url,
            "price": f"{net:.2f}",
            "price_with_vat": f"{gross:.2f}",
            "vat": f"{GREEK_VAT_RATE:.2f}",
            "category": rule["skroutz_category"],
            "manufacturer": brand[:100],
            "mpn": mpn[:80],
            "ean": ean,
            "availability": "In stock",
            "instock": "Y",
            "quantity": "5",
            "description": name,
        }

        for tag, value in fields.items():
            ET.SubElement(product, tag).text = str(value)

        report.append({
            "Product_ID": uid,
            "EAN": ean,
            "Name": name,
            "GSMNet_Category": gsm_category,
            "Skroutz_Category": rule["skroutz_category"],
            "Supplier_Cost_RON": row["Pret Diamond cu TVA"],
            "Commission_Percent": str(rule["commission"]),
            "Transport_EUR": str(TRANSPORT_EUR),
            "Net_Price_EUR": f"{net:.2f}",
            "VAT_Rate": str(GREEK_VAT_RATE),
            "VAT_Amount_EUR": f"{vat_amount:.2f}",
            "Gross_Price_EUR": f"{gross:.2f}",
        })

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(
        OUTPUT_XML,
        encoding="utf-8",
        xml_declaration=True,
    )

    pd.DataFrame(report).to_csv(
        OUTPUT_REPORT, index=False, encoding="utf-8-sig"
    )

    print(f"Products included: {len(report)}")
    print(f"Products skipped: {skipped}")
    print(f"Created {OUTPUT_XML}")
    print(f"Created {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()
