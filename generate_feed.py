import pandas as pd
import math
import xml.etree.ElementTree as ET

CSV_URL="https://www.gsmnet.ro/csv/feedPriceCustomersDiamond.csv"

df=pd.read_csv(CSV_URL, low_memory=False)

for c in ['EAN','LINK POZA','LINK PRODUS','Disponibilitate','COD_UNIC']:
    df[c]=df[c].astype(str).str.strip()

df=df[(df["COD_UNIC"]!="")&(df["COD_UNIC"].str.lower()!="nan")]
df=df.drop_duplicates(subset=["EAN"])

df["Pret Diamond cu TVA"]=pd.to_numeric(
    df["Pret Diamond cu TVA"]
    .astype(str)
    .str.replace(",","."),
    errors="coerce"
)

valid=df[
(df["EAN"].str.match(r'^\d{8,}$',na=False))&
(df["LINK POZA"].str.lower()!="nan")&
(df["LINK PRODUS"].str.lower()!="nan")&
(df["Disponibilitate"].str.contains("stoc",case=False,na=False))&
(~df["Disponibilitate"].str.contains("lipsa",case=False,na=False))&
(df["Pret Diamond cu TVA"]>10)
]

def price(c):
    if c<=10:p=c*2
    elif c<=25:p=c*1.8
    elif c<=50:p=c*1.6
    elif c<=100:p=c*1.45
    elif c<=200:p=c*1.35
    else:p=c*1.25

    p*=1.05
    return round(math.floor(p)+0.99,2)

root=ET.Element("products")

for _,r in valid.iterrows():

    prod=ET.SubElement(root,"product")

    fields={
        "id":r["COD_UNIC"],
        "category":r.get("CATEGORIE",""),
        "name":r.get("NUME",""),
        "brand":r.get("MARCA",""),
        "product_code":r.get("COD",""),
        "product_url":r.get("LINK PRODUS",""),
        "image_url":r.get("LINK POZA",""),
        "sale_price":price(r["Pret Diamond cu TVA"]),
        "stock":"10",
        "ean":r.get("EAN","")
    }

    for k,v in fields.items():
        ET.SubElement(prod,k).text=str(v)

ET.ElementTree(root).write(
    "feed.xml",
    encoding="utf-8",
    xml_declaration=True
)

print("Feed generated")
