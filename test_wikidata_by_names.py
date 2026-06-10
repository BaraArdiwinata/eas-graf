import requests
import pandas as pd
import time
import re

def clean_encoding(text):
    if not isinstance(text, str) or pd.isna(text):
        return ""
    text = text.strip()
    if text.lower() in ['nan', 'none', 'null', '']:
        return ""
    prev = ""
    for _ in range(3):
        if prev == text:
            break
        prev = text
        try:
            if any(c in text for c in ['Ã', 'Â', 'Å', 'â', '€', '™', 'œ', '¥', '¡', '¢', '„']):
                candidate = text.encode('cp1252', errors='ignore').decode('utf-8', errors='ignore')
                if candidate == text:
                    break
                text = candidate
            else:
                break
        except Exception:
            break
    text = re.sub(r'^"+|"+$', '', text)
    text = text.replace('â‚¬â„¢', "'").replace('â€™', "'").replace('â€', '"')
    text = text.replace('Ã…Å¡', 'Ś').replace('Ã¢â‚¬â„¢', "'")
    return text.strip()

# Load unique names from original CSV and clean them
df_orig = pd.read_csv('dataset_gabungan_uts_graf.csv', sep=';')
names = df_orig['orang'].dropna().unique()
clean_names = []
for name in names:
    cleaned = clean_encoding(name)
    # Exclude names that are too generic or empty
    if cleaned and len(cleaned) > 2 and cleaned not in clean_names:
        clean_names.append(cleaned)

print(f"Loaded {len(clean_names)} unique names from CSV.")

# Format names for VALUES block with both @id and @en tags
values_items = []
for name in clean_names:
    # Escape quotes inside name if any
    escaped_name = name.replace('"', '\\"')
    values_items.append(f'"{escaped_name}"@id')
    values_items.append(f'"{escaped_name}"@en')

values_str = "\n    ".join(values_items)

query = f"""
SELECT DISTINCT ?orang ?orangLabel ?kerajaan ?kerajaanLabel ?ayahLabel ?ibuLabel ?pasanganLabel ?anakLabel ?saudaraLabel ?kerabatLabel ?dinastiLabel ?menggantikanLabel ?digantikan_olehLabel ?tglLahir ?tglMati
WHERE {{
  VALUES ?label {{
    {values_str}
  }}
  
  ?orang rdfs:label ?label .
  ?orang wdt:P31 wd:Q5 . # Must be human
  
  # Optional kingdom link
  OPTIONAL {{
    ?orang (wdt:P17|wdt:P27|wdt:P108|wdt:P53|wdt:P1441|wdt:P1080|wdt:P4878|wdt:P361|wdt:P39) ?kerajaan .
  }}

  # Optional family relationships
  OPTIONAL {{ ?orang wdt:P22 ?ayah . }}
  OPTIONAL {{ ?orang wdt:P25 ?ibu . }}
  OPTIONAL {{ ?orang wdt:P26 ?pasangan . }}
  OPTIONAL {{ ?orang wdt:P40 ?anak . }}
  OPTIONAL {{ ?orang wdt:P3373 ?saudara . }} 
  OPTIONAL {{ ?orang wdt:P1038 ?kerabat . }} 
  OPTIONAL {{ ?orang wdt:P53 ?dinasti . }}   
  OPTIONAL {{ ?orang wdt:P569 ?tglLahir . }}
  OPTIONAL {{ ?orang wdt:P570 ?tglMati . }}
  
  # succession
  OPTIONAL {{ ?orang wdt:P1365 ?menggantikan . }}
  OPTIONAL {{ ?orang wdt:P1366 ?digantikan_oleh . }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "id,en" . }}
}}
"""

url = "https://query.wikidata.org/sparql"
headers = {
    "User-Agent": "NusantaraDinastiBot/1.0 (contact: senior_dev@domain.com)",
    "Accept": "application/sparql-results+json"
}

print("Running lookup-by-name query with VALUES (direct index match)...")
start = time.time()
try:
    response = requests.post(url, data={"query": query}, headers=headers, timeout=60)
    print(f"Status Code: {response.status_code}")
    print(f"Time taken: {time.time() - start:.2f}s")
    if response.status_code == 200:
        data = response.json()
        bindings = data.get("results", {}).get("bindings", [])
        print("Success! Number of results:", len(bindings))
        if bindings:
            print("Sample result:")
            for b in bindings[:10]:
                print(f"Name: {b.get('orangLabel', {}).get('value')} | Father: {b.get('ayahLabel', {}).get('value')} | Children: {b.get('anakLabel', {}).get('value')}")
    else:
        print("Error content:", response.text[:500])
except Exception as e:
    print(f"Exception: {str(e)}")
