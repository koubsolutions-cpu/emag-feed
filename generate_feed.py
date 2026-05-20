import pandas as pd
import math
import xml.etree.ElementTree as ET
import csv
import requests
from io import StringIO

CSV_URL = "https://www.gsmnet.ro/csv/feedPriceCustomersDiamond.csv"

# Download supplier CSV
response = requests.get(CSV_URL)
response.encoding = "utf-8"

csv_text = response.text

# Detect CSV separator automatically
sample = csv_text[:5000]
delimiter = csv.Sniffer().sniff(sample).delimiter

df = pd.read_csv(
    StringIO(csv_text),
    sep=delimiter,
    low_memory=False,
    on_bad_lines='skip'
)

# Clean column names
df.columns = [str(c).strip() for c in df.columns]

# Clean fields
for c in ['EAN', 'LINK POZA', 'LINK PRODUS', 'Disponibilitate', 'COD_UNIC']:
    if c in df.columns:
        df[c] = df[c].astype(str).str.strip()

# Keep valid IDs
df = df[
    (df["COD_UNIC"] != "") &
    (df["COD_UNIC"].str.lower() != "nan")
]

# Remove duplicate EAN
df = df.drop_duplicates(subset=["EAN"])

# Price conversion
df["Pret Diamond cu TVA"] = pd.to_numeric(
    df["Pret Diamond cu TVA"]
    .astype(str)
    .str.replace(",", "."),
    errors="coerce"
)

# Required filters
valid = df[
    (df["EAN"].str.match(r'^\d{8,}$', na=False)) &
    (df["LINK POZA"].str.lower() != "nan") &
    (df["LINK PRODUS"].str.lower() != "nan") &
    (df["Pret Diamond cu TVA"] > 10)
]

# Stock rule
def stock_value(status):
    status = str(status).lower()

    if "stoc" in status and "lipsa" not in status:
        return 5

    return 0

# Pricing rule
def price(cost):

    if cost <= 10:
        p = cost * 2

    elif cost <= 25:
        p = cost * 1.8

    elif cost <= 50:
        p = cost * 1.6

    elif cost <= 100:
        p = cost * 1.45

    elif cost <= 200:
        p = cost * 1.35

    else:
        p = cost * 1.25

    # eMAG fee protection
    p *= 1.05

    # X.99 pricing
    return round(math.floor(p) + 0.99, 2)

# Create XML
root = ET.Element("products")

for _, r in valid.iterrows():

    product = ET.SubElement(root, "product")

    fields = {

        "id": r["COD_UNIC"],
        "category": r.get("CATEGORIE", ""),
        "name": r.get("NUME", ""),
        "brand": r.get("MARCA", ""),
        "product_code": r.get("COD", ""),
        "product_url": r.get("LINK PRODUS", ""),
        "image_url": r.get("LINK POZA", ""),
        "sale_price": price(r["Pret Diamond cu TVA"]),
        "stock": stock_value(r["Disponibilitate"]),
        "ean": r.get("EAN", "")
    }

    for key, value in fields.items():
        ET.SubElement(product, key).text = str(value)

# Save XML
ET.ElementTree(root).write(
    "feed.xml",
    encoding="utf-8",
    xml_declaration=True
)

print("Feed generated successfully")
