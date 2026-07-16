import os
import csv
import math
import requests
import pandas as pd
import xml.etree.ElementTree as ET

from io import StringIO
from datetime import datetime

# ============================================================
# SETTINGS
# ============================================================

CSV_URL = "https://www.gsmnet.ro/csv/feedPriceCustomersDiamond.csv"

MPO_CATEGORY_FILE = "Koub Solutions feed - Sheet1.csv"

HISTORY_FILE = "product_history.csv"

REPORT_FILE = "feed_report.csv"

DISABLED_FILE = "disabled_products.csv"

MIN_EXPECTED_PRODUCTS = 3000

VAT = {
    "RO": 1.00,
    "BG": 1.20,
    "HU": 1.27
}

SHIPPING = {
    "RO": 11.48
}

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def add(parent, tag, value):
    ET.SubElement(parent, tag).text = str(value)


def round99(value):
    return round(math.floor(value) + 0.99, 2)


def today():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# DOWNLOAD GSMNET FEED
# ============================================================

print("Downloading GSMNet feed...")

response = requests.get(CSV_URL, timeout=60)

response.raise_for_status()

response.encoding = "utf-8"

csv_text = response.text

sample = csv_text[:5000]

delimiter = csv.Sniffer().sniff(sample).delimiter

df = pd.read_csv(
    StringIO(csv_text),
    sep=delimiter,
    low_memory=False,
    on_bad_lines="skip"
)

df.columns = [str(c).strip() for c in df.columns]

print(f"GSMNet products: {len(df)}")

# ============================================================
# HEALTH CHECK
# ============================================================

if len(df) < MIN_EXPECTED_PRODUCTS:

    raise Exception(
        f"""
Supplier feed looks incomplete.

Expected at least {MIN_EXPECTED_PRODUCTS} products.

Received {len(df)}.

Feed generation stopped.
"""
    )

print("Supplier feed looks healthy.")

# ============================================================
# LOAD MPO CATEGORY FILE
# ============================================================

print("Loading MPO categories...")

mpo = pd.read_csv(MPO_CATEGORY_FILE)

mpo["identifier"] = mpo["identifier"].astype(str)

category_lookup = dict(
    zip(
        mpo["identifier"],
        mpo["Category_Corectata"]
    )
)

print(
    f"MPO categories loaded: {len(category_lookup)}"
)

# ============================================================
# LOAD PRODUCT HISTORY
# ============================================================

print("Loading product history...")

history_columns = [
    "COD_UNIC",
    "EAN",
    "Name",
    "Brand",
    "Price",
    "Stock",
    "ProductURL",
    "ImageURL",
    "LastSeen",
    "MissingCount"
]

if os.path.exists(HISTORY_FILE):

    history = pd.read_csv(HISTORY_FILE)

    print(
        f"History loaded: {len(history)} products"
    )

else:

    history = pd.DataFrame(
        columns=history_columns
    )

    print(
        "History file not found."
    )

# ============================================================
# CLEAN SUPPLIER DATA
# ============================================================

for col in [
    "EAN",
    "LINK POZA",
    "LINK PRODUS",
    "Disponibilitate",
    "COD_UNIC"
]:

    if col in df.columns:

        df[col] = (
            df[col]
            .astype(str)
            .str.strip()
        )

valid = df[
    df["COD_UNIC"]
    .astype(str)
    .str.match(r"^\d+$", na=False)
].copy()

valid = valid.drop_duplicates(
    subset=["EAN"]
)

valid["Pret Diamond cu TVA"] = pd.to_numeric(
    valid["Pret Diamond cu TVA"]
    .astype(str)
    .str.replace(",", "."),
    errors="coerce"
)

valid = valid[
    (
        valid["EAN"]
        .str.match(r"^\d{8,}$", na=False)
    )
    &
    (
        valid["LINK POZA"]
        .str.lower() != "nan"
    )
    &
    (
        valid["LINK PRODUS"]
        .str.lower() != "nan"
    )
]

print(
    f"Valid products: {len(valid)}"
)

print("Part 1 completed.")

# ============================================================
# PRODUCT CLASS
# ============================================================

class Product:

    def __init__(self, row):

        self.id = str(row["COD_UNIC"])

        self.code = str(row.get("COD", ""))

        self.ean = str(row["EAN"])

        self.name = str(row.get("NUME", ""))

        self.brand = str(row.get("MARCA", ""))

        self.category = str(row.get("CATEGORIE", ""))

        self.product_url = str(row.get("LINK PRODUS", ""))

        self.image_url = str(row.get("LINK POZA", ""))

        self.description = self.name

        self.cost = float(row["Pret Diamond cu TVA"])

        self.status = str(row["Disponibilitate"]).strip().lower()

    @property
    def in_stock(self):

        return (
            self.status == "in stoc"
        )

    @property
    def stock(self):

        return 5 if self.in_stock else 0


# ============================================================
# BUILD PRODUCT LIST
# ============================================================

print("Building product objects...")

products = []

for _, row in valid.iterrows():

    try:

        products.append(
            Product(row)
        )

    except Exception as e:

        print(
            f"Skipping product: {e}"
        )

print(
    f"Products loaded: {len(products)}"
)
# ============================================================
# SAFETY BUFFER
# ============================================================

def safety_buffer(cost):

    if cost <= 25:
        return 1.10

    elif cost <= 100:
        return 1.07

    return 1.05


# ============================================================
# MARKUP
# ============================================================

def markup(cost):

    if cost <= 10:
        return cost * 2.50

    elif cost <= 25:
        return cost * 2.25

    elif cost <= 50:
        return cost * 2.00

    elif cost <= 100:
        return cost * 1.75

    elif cost <= 200:
        return cost * 1.60

    return cost * 1.50


# ============================================================
# PRICING
# ============================================================

def emag_price(product, country):

    p = markup(product.cost)

    p *= safety_buffer(product.cost)

    p *= VAT[country]

    return round99(p)


def trendyol_price(product):

    p = markup(product.cost)

    p += SHIPPING["RO"]

    p *= safety_buffer(product.cost)

    return round99(p)


def trendyol_original(price):

    return round99(price * 1.15)


def mpo_price(product):

    p = markup(product.cost)

    p *= 1.12

    p *= safety_buffer(product.cost)

    return round99(p)
  def mpo_price(product):

    p = markup(product.cost)

    p *= 1.12

    p *= safety_buffer(product.cost)

    return round99(p)
    # ============================================================
# HISTORY ENGINE
# ============================================================

print("Updating product history...")

# Use product ID as key
history_lookup = {}

if len(history) > 0:

    history["COD_UNIC"] = history["COD_UNIC"].astype(str)

    history_lookup = {
        row["COD_UNIC"]: row
        for _, row in history.iterrows()
    }

new_history = []

current_ids = set()

missing_products = []

disabled_products = []

for product in products:

    current_ids.add(product.id)

    if product.id in history_lookup:

        old = history_lookup[product.id]

        missing = 0

    else:

        missing = 0

    new_history.append({

        "COD_UNIC": product.id,

        "EAN": product.ean,

        "Name": product.name,

        "Brand": product.brand,

        "Price": product.cost,

        "Stock": product.stock,

        "ProductURL": product.product_url,

        "ImageURL": product.image_url,

        "LastSeen": today(),

        "MissingCount": missing

    })

# ============================================================
# CHECK PRODUCTS THAT DISAPPEARED
# ============================================================

for _, row in history.iterrows():

    pid = str(row["COD_UNIC"])

    if pid in current_ids:

        continue

    missing = int(row.get("MissingCount", 0))

    missing += 1

    row["MissingCount"] = missing

    if missing >= 2:

        disabled_products.append(pid)

    else:

        missing_products.append(pid)

    new_history.append({

        "COD_UNIC": pid,

        "EAN": row["EAN"],

        "Name": row["Name"],

        "Brand": row["Brand"],

        "Price": row["Price"],

        "Stock": 0,

        "ProductURL": row["ProductURL"],

        "ImageURL": row["ImageURL"],

        "LastSeen": row["LastSeen"],

        "MissingCount": missing

    })

history = pd.DataFrame(new_history)

print(f"Products in supplier: {len(products)}")

print(f"Missing once: {len(missing_products)}")

print(f"Disabled: {len(disabled_products)}")
# ============================================================
# PRODUCT STATUS
# ============================================================

def is_disabled(product):

    return product.id in disabled_products


def stock_for_marketplace(product):

    if is_disabled(product):

        return 0

    return product.stock


def delivery_time(product):

    if is_disabled(product):

        return "0"

    return "1" if product.in_stock else "0"
  # ============================================================
# eMAG FEEDS
# ============================================================

print("Generating eMAG feeds...")

for country in ["RO", "BG", "HU"]:

    print(f"Creating eMAG {country}...")

    root = ET.Element("products")

    # --------------------------------------------------------
    # Products currently in supplier feed
    # --------------------------------------------------------

    for product in products:

        xml_product = ET.SubElement(root, "product")

        add(xml_product, "id", product.id)
        add(xml_product, "category", product.category)
        add(xml_product, "name", product.name)
        add(xml_product, "brand", product.brand)
        add(xml_product, "product_code", product.code)
        add(xml_product, "product_url", product.product_url)
        add(xml_product, "image_url", product.image_url)

        add(
            xml_product,
            "sale_price",
            emag_price(product, country)
        )

        add(
            xml_product,
            "stock",
            stock_for_marketplace(product)
        )

        add(
            xml_product,
            "ean",
            product.ean
        )

    # --------------------------------------------------------
    # Products missing from supplier feed
    # --------------------------------------------------------

    for _, row in history.iterrows():

        pid = str(row["COD_UNIC"])

        if pid in current_ids:
            continue

        xml_product = ET.SubElement(root, "product")

        add(xml_product, "id", pid)

        add(xml_product, "category", "")

        add(xml_product, "name", row["Name"])

        add(xml_product, "brand", row["Brand"])

        add(xml_product, "product_code", "")

        add(xml_product, "product_url", row["ProductURL"])

        add(xml_product, "image_url", row["ImageURL"])

        add(
            xml_product,
            "sale_price",
            row["Price"]
        )

        # IMPORTANT
        # Missing products always send stock = 0

        add(
            xml_product,
            "stock",
            0
        )

        add(
            xml_product,
            "ean",
            row["EAN"]
        )

    filename = f"feed_{country.lower()}.xml"

    ET.ElementTree(root).write(
        filename,
        encoding="utf-8",
        xml_declaration=True
    )

    print(
        f"{filename} created."
    )

print("eMAG feeds completed.")
# ============================================================
# TRENDYOL FEED
# ============================================================

print("Generating Trendyol feed...")

root = ET.Element("products")

# Products currently in supplier feed
for product in products:

    xml_product = ET.SubElement(root, "product")

    sale_price = trendyol_price(product)

    add(xml_product, "ean", product.ean)

    add(
        xml_product,
        "sale_price",
        sale_price
    )

    add(
        xml_product,
        "original_price",
        trendyol_original(sale_price)
    )

    add(
        xml_product,
        "stock",
        stock_for_marketplace(product)
    )

# Products missing from supplier feed
for _, row in history.iterrows():

    pid = str(row["COD_UNIC"])

    if pid in current_ids:
        continue

    xml_product = ET.SubElement(root, "product")

    add(xml_product, "ean", row["EAN"])

    add(xml_product, "sale_price", row["Price"])

    add(xml_product, "original_price", row["Price"])

    add(xml_product, "stock", 0)

ET.ElementTree(root).write(
    "trendyol_ro.xml",
    encoding="utf-8",
    xml_declaration=True
)

print("trendyol_ro.xml created.")


# ============================================================
# MPO FEED
# ============================================================

print("Generating MPO feed...")

root = ET.Element("products")

# Products currently in supplier feed
for product in products:

    xml_product = ET.SubElement(root, "product")

    add(xml_product, "identifier", product.id)

    add(xml_product, "manufacturer", product.brand)

    add(xml_product, "name", product.name)

    add(xml_product, "product_url", product.product_url)

    add(
        xml_product,
        "price",
        mpo_price(product)
    )

    add(xml_product, "currency", "RON")

    add(
        xml_product,
        "image_url",
        product.image_url
    )

    add(
        xml_product,
        "category",
        category_lookup.get(
            product.id,
            product.category
        )
    )

    add(
        xml_product,
        "description",
        product.description
    )

    add(
        xml_product,
        "Delivery_Time",
        delivery_time(product)
    )

    add(
        xml_product,
        "Delivery_Cost",
        "20 RON"
    )

    add(
        xml_product,
        "EAN_code",
        product.ean
    )

# Products missing from supplier feed
for _, row in history.iterrows():

    pid = str(row["COD_UNIC"])

    if pid in current_ids:
        continue

    xml_product = ET.SubElement(root, "product")

    add(xml_product, "identifier", pid)

    add(xml_product, "manufacturer", row["Brand"])

    add(xml_product, "name", row["Name"])

    add(xml_product, "product_url", row["ProductURL"])

    add(xml_product, "price", row["Price"])

    add(xml_product, "currency", "RON")

    add(xml_product, "image_url", row["ImageURL"])

    add(
        xml_product,
        "category",
        category_lookup.get(pid, "")
    )

    add(
        xml_product,
        "description",
        row["Name"]
    )

    add(
        xml_product,
        "Delivery_Time",
        "0"
    )

    add(
        xml_product,
        "Delivery_Cost",
        "20 RON"
    )

    add(
        xml_product,
        "EAN_code",
        row["EAN"]
    )

ET.ElementTree(root).write(
    "mpo_feed.xml",
    encoding="utf-8",
    xml_declaration=True
)

print("mpo_feed.xml created.")
# ============================================================
# SAVE HISTORY
# ============================================================

print("Saving product history...")

history = history.sort_values(
    by="COD_UNIC"
)

history.to_csv(
    HISTORY_FILE,
    index=False
)

print(f"{HISTORY_FILE} updated.")

# ============================================================
# DISABLED PRODUCTS
# ============================================================

print("Saving disabled products...")

disabled_df = history[
    history["MissingCount"] >= 2
].copy()

disabled_df.to_csv(
    DISABLED_FILE,
    index=False
)

print(
    f"Disabled products: {len(disabled_df)}"
)

# ============================================================
# REPORT
# ============================================================

print("Creating report...")

report = pd.DataFrame([{

    "RunDate": today(),

    "SupplierProducts": len(df),

    "ValidProducts": len(valid),

    "ProductsInFeeds": len(products),

    "MissingOnce": len(missing_products),

    "DisabledProducts": len(disabled_products),

    "eMAG_RO": len(products) + len(disabled_products),

    "eMAG_BG": len(products) + len(disabled_products),

    "eMAG_HU": len(products) + len(disabled_products),

    "Trendyol": len(products) + len(disabled_products),

    "MPO": len(products) + len(disabled_products)

}])

report.to_csv(
    REPORT_FILE,
    index=False
)

print(f"{REPORT_FILE} created.")

# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 60)
print("FEED GENERATION COMPLETED")
print("=" * 60)

print(f"Supplier products       : {len(df)}")
print(f"Valid products          : {len(valid)}")
print(f"Marketplace products    : {len(products)}")
print(f"Missing once            : {len(missing_products)}")
print(f"Disabled                : {len(disabled_products)}")

print()
print("Generated files:")

print("  feed_ro.xml")
print("  feed_bg.xml")
print("  feed_hu.xml")
print("  trendyol_ro.xml")
print("  mpo_feed.xml")

print()
print("Generated reports:")

print(f"  {HISTORY_FILE}")
print(f"  {REPORT_FILE}")
print(f"  {DISABLED_FILE}")

print()
print("=" * 60)
print("SUCCESS")
print("=" * 60)
