import pandas as pd
import requests
import xml.etree.ElementTree as ET
import math
import re

CSV_URL="https://www.gsmnet.ro/csv/feedPriceCustomersDiamond.csv"

response=requests.get(CSV_URL)
open("supplier.csv","wb").write(response.content)

df=pd.read_csv(
    "supplier.csv",
    sep=";",
    low_memory=False
)

# keep only numeric ids
valid=df[
    df["COD_UNIC"]
    .astype(str)
    .str.match(r'^\d+$',na=False)
].copy()

VAT={
    "RO":1.00,
    "BG":1.20,
    "GR":1.24,
    "HU":1.27
}

SHIPPING={
    "RO":11.48,
    "BG":13.03,
    "GR":17.09
}

MARGIN=1.15


def stock_value(status):

    status=str(status).lower()

    if any(x in status for x in
           ["stoc","disponibil","available"]):
        return 5

    return 0


def make_price(base,country):

    try:
        p=float(str(base).replace(",","."))
    except:
        p=0

    if country in SHIPPING:
        p+=SHIPPING[country]

    p*=VAT[country]
    p*=MARGIN

    # x.99 pricing
    p=math.floor(p)+0.99

    return round(p,2)


# eMAG feeds
for country in ["RO","BG","HU"]:

    root=ET.Element("products")

    for _,r in valid.iterrows():

        product=ET.SubElement(
            root,
            "product"
        )

        fields={

            "id":r["COD_UNIC"],
            "category":r.get("CATEGORIE",""),
            "name":r.get("NUME",""),
            "brand":r.get("MARCA",""),
            "product_code":r.get("COD",""),
            "description":r.get("DENUMIRE",""),
            "product_url":r.get("LINK PRODUS",""),
            "image_url":r.get("LINK POZA",""),

            "sale_price":
                make_price(
                    r["Pret Diamond cu TVA"],
                    country
                ),

            "stock":
                stock_value(
                    r["Disponibilitate"]
                ),

            "ean":
                r.get("EAN","")
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


# Trendyol feeds
for country in ["RO","BG","GR"]:

    root=ET.Element("products")

    for _,r in valid.iterrows():

        product=ET.SubElement(
            root,
            "product"
        )

        sale=make_price(
            r["Pret Diamond cu TVA"],
            country
        )

        original=round(
            math.floor(
                sale*1.15
            )+0.99,
            2
        )

        fields={

            "ean":
                r.get("EAN",""),

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
        f"trendyol_{country.lower()}.xml",
        encoding="utf-8",
        xml_declaration=True
    )

print("All feeds generated")
