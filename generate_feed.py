import pandas as pd
import requests
import xml.etree.ElementTree as ET
import math
import csv
from io import StringIO

CSV_URL="https://www.gsmnet.ro/csv/feedPriceCustomersDiamond.csv"

VAT={
    "RO":1.00,
    "BG":1.20,
    "HU":1.27
}

SHIPPING={
    "RO":11.48
}

response=requests.get(CSV_URL)
response.encoding="utf-8"

csv_text=response.text

sample=csv_text[:5000]
delimiter=csv.Sniffer().sniff(sample).delimiter

df=pd.read_csv(
    StringIO(csv_text),
    sep=delimiter,
    low_memory=False,
    on_bad_lines="skip"
)

df.columns=[str(c).strip() for c in df.columns]

for c in [
    "EAN",
    "LINK POZA",
    "LINK PRODUS",
    "Disponibilitate",
    "COD_UNIC"
]:
    if c in df.columns:
        df[c]=df[c].astype(str).str.strip()

# keep only numeric IDs
valid=df[
    df["COD_UNIC"]
    .astype(str)
    .str.match(r"^\d+$",na=False)
].copy()

# remove duplicate EAN
valid=valid.drop_duplicates(
    subset=["EAN"]
)

# convert price
valid["Pret Diamond cu TVA"]=pd.to_numeric(
    valid["Pret Diamond cu TVA"]
    .astype(str)
    .str.replace(",","."),
    errors="coerce"
)

# required fields
valid=valid[
(valid["EAN"].str.match(r"^\d{8,}$",na=False))&
(valid["LINK POZA"].str.lower()!="nan")&
(valid["LINK PRODUS"].str.lower()!="nan")
]

def stock_value(status):

    status=str(status).lower()

    if (
        "stoc" in status
        and
        "lipsa" not in status
    ):
        return 5

    return 0


def markup(cost):

    if cost<=10:
        return cost*2.50

    elif cost<=25:
        return cost*2.25

    elif cost<=50:
        return cost*2.00

    elif cost<=100:
        return cost*1.75

    elif cost<=200:
        return cost*1.60

    return cost*1.50


def emag_price(cost,country):

    cost=float(cost)

    p=markup(cost)

    # safety buffer
    p*=1.05

    p*=VAT[country]

    return round(
        math.floor(p)+0.99,
        2
    )


def trendyol_price(cost,country):

    cost=float(cost)

    p=markup(cost)

    # shipping cost
    p+=SHIPPING[country]

    # safety buffer
    p*=1.05

    return round(
        math.floor(p)+0.99,
        2
    )


def mpo_price(cost):

    cost=float(cost)

    p=markup(cost)

    # MPO commission
    p*=1.12

    # safety buffer
    p*=1.05

    return round(
        math.floor(p)+0.99,
        2
    )


# =========================
# eMAG feeds
# =========================

for country in ["RO","BG","HU"]:

    root=ET.Element("products")

    for _,r in valid.iterrows():

        product=ET.SubElement(
            root,
            "product"
        )

        fields={

            "id":
                r["COD_UNIC"],

            "category":
                r.get(
                    "CATEGORIE",
                    ""
                ),

            "name":
                r.get(
                    "NUME",
                    ""
                ),

            "brand":
                r.get(
                    "MARCA",
                    ""
                ),

            "product_code":
                r.get(
                    "COD",
                    ""
                ),

            "product_url":
                r.get(
                    "LINK PRODUS",
                    ""
                ),

            "image_url":
                r.get(
                    "LINK POZA",
                    ""
                ),

            "sale_price":
                emag_price(
                    r["Pret Diamond cu TVA"],
                    country
                ),

            "stock":
                stock_value(
                    r["Disponibilitate"]
                ),

            "ean":
                r["EAN"]

        }

        for k,v in fields.items():

            ET.SubElement(
                product,
                k
            ).text=str(v)

    ET.ElementTree(root).write(
        f"feed_{country.lower()}.xml",
        encoding="utf-8",
        xml_declaration=True
    )


# =========================
# Trendyol RO
# =========================

root=ET.Element("products")

for _,r in valid.iterrows():

    product=ET.SubElement(
        root,
        "product"
    )

    sale=trendyol_price(
        r["Pret Diamond cu TVA"],
        "RO"
    )

    original=round(
        math.floor(
            sale*1.15
        )+0.99,
        2
    )

    fields={

        "ean":
            r["EAN"],

        "sale_price":
            sale,

        "stock":
            stock_value(
                r["Disponibilitate"]
            ),

        "original_price":
            original
    }

    for k,v in fields.items():

        ET.SubElement(
            product,
            k
        ).text=str(v)

ET.ElementTree(root).write(
    "trendyol_ro.xml",
    encoding="utf-8",
    xml_declaration=True
)


# =========================
# MPO Feed
# =========================

root=ET.Element("products")

for _,r in valid.iterrows():

    product=ET.SubElement(
        root,
        "product"
    )

    price=mpo_price(
        r["Pret Diamond cu TVA"]
    )

    fields={

        "identifier":
            r["COD_UNIC"],

        "manufacturer":
            r.get(
                "MARCA",
                ""
            ),

        "name":
            r.get(
                "NUME",
                ""
            ),

        "product_url":
            r.get(
                "LINK PRODUS",
                ""
            ),

        "price":
            price,

        "currency":
            "RON",

        "image_url":
            r.get(
                "LINK POZA",
                ""
            ),

        "category":
            r.get(
                "CATEGORIE",
                ""
            ),

         "description":
             r.get(
                  "NUME",
                 ""
            ),

        "Delivery_Time":
    "1" if stock_value(
        r["Disponibilitate"]
    ) > 0 else "0",

        "Delivery_Cost":
            "20 RON",

        "EAN_code":
            r.get(
                "EAN",
                ""
            )
    }

    for k,v in fields.items():

        ET.SubElement(
            product,
            k
        ).text=str(v)

ET.ElementTree(root).write(
    "mpo_feed.xml",
    encoding="utf-8",
    xml_declaration=True
)

print("All feeds generated successfully")
