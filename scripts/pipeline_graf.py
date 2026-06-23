import os
import sys
import re
import time
import json
import requests
import pandas as pd
import wikipediaapi
from dotenv import load_dotenv
from rapidfuzz import fuzz

# Reconfigure output to utf-8 to handle Indonesian/Javanese characters in terminal
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Load environmental variables from .env relative to script path
script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(script_dir, '../.env'))
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# --- DATA CLEANING FUNCTIONS ---
def clean_encoding(text):
    """
    Fixes double encoding issue (like utf-8 bytes interpreted as cp1252/latin-1).
    For example: 'Ã…Å¡akti' -> 'Śakti', 'Cut NyaÃ¢â‚¬â„¢ Dhien' -> 'Cut Nya' Dhien'.
    """
    if not isinstance(text, str) or pd.isna(text):
        return ""
    
    # Standardize empty representation
    text = text.strip()
    if text.lower() in ['nan', 'none', 'null', '']:
        return ""

    prev = ""
    # Try decoding up to 3 times to handle nested double encoding
    for _ in range(3):
        if prev == text:
            break
        prev = text
        try:
            # Check if there are signs of corrupted chars
            if any(c in text for c in ['Ã', 'Â', 'Å', 'â', '€', '™', 'œ', '¥', '¡', '¢', '„']):
                # Attempt cp1252 to utf-8 conversion
                candidate = text.encode('cp1252', errors='ignore').decode('utf-8', errors='ignore')
                if candidate == text:
                    break
                text = candidate
            else:
                break
        except Exception:
            break
            
    # Clean up double/triple quotes often found in CSV
    text = re.sub(r'^"+|"+$', '', text)
    
    # Normalize common messy characters
    text = text.replace('â‚¬â„¢', "'").replace('â€™', "'").replace('â€', '"')
    text = text.replace('Ã…Å¡', 'Ś').replace('Ã¢â‚¬â„¢', "'")
    
    # Strip spaces
    text = text.strip()
    return text

def clean_uri(uri):
    """Helper to extract clean ID/URI and remove quotes."""
    if not isinstance(uri, str) or pd.isna(uri):
        return ""
    uri = uri.strip().strip('"').strip("'")
    return uri

# --- SPARQL ENDPOINT CLIENT ---
def fetch_sparql(endpoint, query, max_retries=3):
    """Fetches SPARQL query results as a pandas DataFrame."""
    headers = {
        "User-Agent": "NusantaraDinastiBot/1.0 (contact: senior_dev@domain.com)",
        "Accept": "application/sparql-results+json"
    }
    
    # DBpedia sometimes prefers application/json
    if "dbpedia" in endpoint:
        headers["Accept"] = "application/json"

    print(f"Fetching data from {endpoint}...")
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(endpoint, data={"query": query}, headers=headers, timeout=60)
            if response.status_code == 200:
                data = response.json()
                cols = data.get("head", {}).get("vars", [])
                rows = []
                for binding in data.get("results", {}).get("bindings", []):
                    row = {}
                    for col in cols:
                        val = binding.get(col, {})
                        row[col] = val.get("value", None)
                    rows.append(row)
                df = pd.DataFrame(rows, columns=cols)
                print(f"Successfully fetched {len(df)} records from {endpoint}.")
                return df
            else:
                print(f"Attempt {attempt} failed with status code: {response.status_code}")
        except Exception as e:
            print(f"Attempt {attempt} failed with error: {str(e)}")
        
        if attempt < max_retries:
            sleep_time = attempt * 5
            print(f"Sleeping for {sleep_time} seconds before retrying...")
            time.sleep(sleep_time)
            
    print(f"Failed to fetch data from {endpoint} after {max_retries} attempts.")
    return pd.DataFrame()

def find_fuzzy_match(name, kingdom, enriched_sources):
    """
    Finds the best matching row in enriched_sources using rapidfuzz token_sort_ratio.
    Auto-merges if similarity score >= 90.0.
    Flags for manual check if 75.0 <= score < 90.0.
    """
    if enriched_sources.empty or not name or pd.isna(name):
        return None, 0.0, False
        
    best_row = None
    best_score = 0.0
    
    name_clean = str(name).lower().strip()
    k_clean = str(kingdom).lower().strip() if (kingdom and not pd.isna(kingdom)) else ""
    
    for _, row in enriched_sources.iterrows():
        label = row.get('orangLabel', '')
        if not label or pd.isna(label):
            continue
        label_clean = str(label).lower().strip()
        
        # Calculate similarity score using token_sort_ratio
        score = fuzz.token_sort_ratio(name_clean, label_clean)
        
        # Boost score slightly if kingdom matches to disambiguate identical/similar names
        if k_clean:
            row_k1 = str(row.get('kerajaanLabel', '')).lower().strip()
            row_k2 = str(row.get('namaKerajaan', '')).lower().strip()
            if k_clean in (row_k1, row_k2) and row_k1:
                score += 5.0
                score = min(score, 100.0)
                
        if score > best_score:
            best_score = score
            best_row = row
            
    if best_score >= 90.0:
        return best_row, best_score, False
    elif 75.0 <= best_score < 90.0:
        return best_row, best_score, True
        
    return None, best_score, False

# --- WIKIPEDIA SCRAPER & LLM PIPELINE ---
def fetch_wikipedia_text(nama_tokoh):
    """Fetches summary and main content of a historical figure from Wikipedia API."""
    user_agent = 'NusantaraDinastiBot/1.0 (contact: senior_dev@domain.com)'
    
    # Try Indonesian Wikipedia first
    wiki_id = wikipediaapi.Wikipedia(user_agent=user_agent, language='id', verify=False)
    page = wiki_id.page(nama_tokoh)
    if page.exists():
        print(f"Found Wikipedia (ID) page for '{nama_tokoh}'.")
        return page.summary + "\n" + page.text[:3000]
        
    # Try English Wikipedia if ID not found
    wiki_en = wikipediaapi.Wikipedia(user_agent=user_agent, language='en', verify=False)
    page = wiki_en.page(nama_tokoh)
    if page.exists():
        print(f"Found Wikipedia (EN) page for '{nama_tokoh}'.")
        return page.summary + "\n" + page.text[:3000]
        
    print(f"No Wikipedia page found for '{nama_tokoh}'.")
    return ""

def impute_missing_with_llm(nama_tokoh, wiki_text, api_key):
    """Asks OpenRouter LLM to extract family relations in structured JSON format."""
    if not api_key:
        return None
    if not wiki_text:
        return {
            "ayah": "",
            "ibu": "",
            "pasangan": "",
            "anak": "",
            "saudara": "",
            "confidence_score": 0.0
        }
        
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/eas-graf/eas-graf",
        "X-Title": "Nusantara Dynasty Graph Enrichment"
    }
    
    # Simple structured user prompt
    prompt = f"Extract family relations for the historical figure '{nama_tokoh}' from the following text.\n\nText:\n{wiki_text}"

    # Get models to try, using env override if present
    custom_model = os.getenv("OPENROUTER_MODEL", "")
    models_to_try = []
    if custom_model:
        models_to_try.append(custom_model)
    # Default list of fallbacks
    models_to_try.extend([
        "google/gemini-1.5-flash:free",
        "google/gemini-2.5-flash",
        "meta-llama/llama-3.3-70b-instruct:free",
        "openrouter/free"
    ])
    
    # Remove duplicates while preserving order
    seen = set()
    models_to_try = [x for x in models_to_try if not (x in seen or seen.add(x))]

    for model in models_to_try:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional historian and data scientist. Extract the father, mother, spouse, children, and siblings of the historical figure. Also estimate a confidence score from 0.0 to 1.0 reflecting how certain you are based on the text. You must respond ONLY with a valid JSON object matching the schema below. Do NOT wrap the response in markdown blocks (e.g. do not use ```json ... ```) or any other text.\n\nJSON Schema:\n{\n  \"ayah\": \"Name of Father\",\n  \"ibu\": \"Name of Mother\",\n  \"pasangan\": \"Name of Spouse(s), comma separated\",\n  \"anak\": \"Name of Children, comma separated\",\n  \"saudara\": \"Name of Siblings, comma separated\",\n  \"confidence_score\": 0.85\n}"
                },
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 1000,
            "temperature": 0.1
        }
        
        print(f"Querying OpenRouter LLM for '{nama_tokoh}' using model '{model}'...")
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"].strip()
                
                # Clean possible markdown block markers if LLM returns them anyway
                content = re.sub(r'^```json\s*|^```\s*|```$', '', content, flags=re.MULTILINE).strip()
                
                parsed = json.loads(content)
                print(f"LLM successfully extracted data for '{nama_tokoh}' (using model '{model}'): {parsed}")
                return parsed
            elif response.status_code in [400, 402, 403, 404]:
                # If error is due to model validation or credits, print and try next model
                print(f"OpenRouter API returned error code {response.status_code} for model '{model}': {response.text}")
                print("Trying next model in fallback hierarchy...")
                continue
            else:
                print(f"OpenRouter API returned error code {response.status_code} for model '{model}': {response.text}")
                break
        except Exception as e:
            print(f"Exception raised while querying OpenRouter LLM for '{nama_tokoh}' using model '{model}': {str(e)}")
            import traceback
            traceback.print_exc()
            print("Trying next model in fallback hierarchy...")
            continue
            
    return None

def is_same_person_llm(name1, name2, api_key):
    """Asks OpenRouter LLM to verify if two names refer to the exact same historical figure."""
    if not api_key:
        return False
        
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/eas-graf/eas-graf",
        "X-Title": "Nusantara Dynasty Entity Disambiguation"
    }
    
    prompt = f"Apakah kedua tokoh sejarah berikut merujuk pada satu individu (orang) yang sama?\n1. {name1}\n2. {name2}\n\nJawab dengan YES atau NO saja."
    
    custom_model = os.getenv("OPENROUTER_MODEL", "")
    models_to_try = []
    if custom_model:
        models_to_try.append(custom_model)
    models_to_try.extend([
        "google/gemini-1.5-flash:free",
        "google/gemini-2.5-flash",
        "meta-llama/llama-3.3-70b-instruct:free",
        "openrouter/free"
    ])
    
    seen = set()
    models_to_try = [x for x in models_to_try if not (x in seen or seen.add(x))]
    
    for model in models_to_try:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional historian of Indonesian precolonial kingdoms. Decide if the two names refer to the exact same historical figure. Respond ONLY with YES or NO."
                },
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 10,
            "temperature": 0.0
        }
        
        try:
            print(f"Querying LLM if '{name1}' and '{name2}' are the same person using model '{model}'...")
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"].strip().upper()
                print(f"LLM Response for '{name1}' vs '{name2}': {content}")
                if "YES" in content:
                    return True
                return False
            elif response.status_code in [400, 402, 403, 404]:
                print(f"OpenRouter API returned error code {response.status_code} for model '{model}': {response.text}")
                continue
            else:
                print(f"OpenRouter API returned error code {response.status_code}: {response.text}")
                break
        except Exception as e:
            print(f"Error querying LLM: {str(e)}")
            continue
            
    return False

def apply_entity_disambiguation(df, api_key):
    """Groups duplicate entities in 'orang' column based on fuzzy matching and LLM verification."""
    print("\n=== STARTING ENTITY DISAMBIGUATION (STAGE 3) ===")
    if not api_key:
        print("WARNING: OPENROUTER_API_KEY not set. Skipping LLM entity disambiguation. Setting master_id = orang.")
        df['master_id'] = df['orang']
        return df
        
    names = df['orang'].dropna().unique()
    names = [str(n).strip() for n in names if str(n).strip()]
    
    # DSU (Disjoint Set Union) Structure
    parent = {name: name for name in names}
    
    def find(n):
        path = []
        while parent[n] != n:
            path.append(n)
            n = parent[n]
        for node in path:
            parent[node] = n
        return n
        
    def union(n1, n2):
        r1 = find(n1)
        r2 = find(n2)
        if r1 != r2:
            parent[r1] = r2

    n_names = len(names)
    checked_pairs = 0
    merged_count = 0
    
    for i in range(n_names):
        for j in range(i + 1, n_names):
            name1 = names[i]
            name2 = names[j]
            
            # Skip if already merged
            if find(name1) == find(name2):
                continue
                
            ratio = fuzz.token_set_ratio(name1, name2)
            if ratio >= 85:
                checked_pairs += 1
                is_same = is_same_person_llm(name1, name2, api_key)
                if is_same:
                    union(name1, name2)
                    merged_count += 1
                    print(f"SUCCESS: Merged '{name1}' and '{name2}' as the same individual.")
                else:
                    print(f"INFO: Kept '{name1}' and '{name2}' separate.")
                    
    print(f"Disambiguation complete. Checked {checked_pairs} candidate pairs. Merged {merged_count} groups.")
    
    # Apply master_id mapping to dataframe
    master_map = {name: find(name) for name in names}
    df['master_id'] = df['orang'].map(lambda x: master_map.get(str(x).strip(), x) if pd.notna(x) else "")
    return df

# --- MAIN EXECUTION PIPELINE ---
def main():
    print("=== STARTING NUSANTARA DYNASTY DATA ENRICHMENT PIPELINE ===")
    
    # 1. LOAD AND PRE-CLEAN ORIGINAL CSV
    print("Loading and cleaning original CSV...")
    csv_input = os.path.join(script_dir, '../data/dataset_gabungan_uts_graf.csv')
    if not os.path.exists(csv_input):
        print(f"Error: {csv_input} not found in workspace!")
        sys.exit(1)
        
    df_orig = pd.read_csv(csv_input, sep=';')
    
    # Clean encoding for the entire original dataset
    for col in df_orig.columns:
        df_orig[col] = df_orig[col].apply(clean_encoding)

    # Standardize kingdom IDs in original CSV if they are URIs
    df_orig['wikidataID_clean'] = df_orig['wikidataID'].apply(clean_uri)

    # Get unique list of people to query Wikidata directly by name
    names = df_orig['orang'].dropna().unique()
    clean_names = []
    for name in names:
        cleaned = clean_encoding(name)
        if cleaned and len(cleaned) > 2 and cleaned not in clean_names:
            clean_names.append(cleaned)
            
    print(f"Extracted {len(clean_names)} unique person names from CSV.")

    # 2. CONSTRUCT AND RUN OPTIMIZED WIKIDATA SPARQL QUERY
    # Format names for indexed VALUES lookup (supporting both ID and EN labels)
    values_items = []
    for name in clean_names:
        escaped_name = name.replace('"', '\\"')
        values_items.append(f'"{escaped_name}"@id')
        values_items.append(f'"{escaped_name}"@en')

    values_str = "\n    ".join(values_items)

    wikidata_query = f"""
SELECT DISTINCT ?orang ?orangLabel ?kerajaan ?kerajaanLabel ?ayahLabel ?ibuLabel ?pasanganLabel ?anakLabel ?saudaraLabel ?kerabatLabel ?dinastiLabel ?menggantikanLabel ?digantikan_olehLabel ?tglLahir ?tglMati
WHERE {{
  {{
    # 1. Cari berdasarkan kecocokan label nama langsung dari CSV
    VALUES ?label {{
      {values_str}
    }}
    ?orang rdfs:label ?label .
    ?orang wdt:P31 wd:Q5 . # Must be human
    
    OPTIONAL {{
      ?orang (wdt:P17|wdt:P27|wdt:P108|wdt:P53|wdt:P1441|wdt:P1080|wdt:P4878|wdt:P361|wdt:P39) ?kerajaan .
    }}
  }}
  UNION
  {{
    # 2. Cari secara dinamis semua tokoh yang terhubung ke kerajaan sejarah di Indonesia
    ?kerajaan wdt:P31/wdt:P279* wd:Q3024240 ; # historical state
              wdt:P17 wd:Q252 .               # Indonesia
              
    ?orang wdt:P31 wd:Q5 . # Must be human
    {{
      ?orang (wdt:P17|wdt:P27|wdt:P108|wdt:P53|wdt:P1441|wdt:P1080|wdt:P4878|wdt:P361|wdt:P39) ?kerajaan .
    }}
    UNION
    {{
      ?orang p:P39 [ ps:P39 ?jabatan ; pq:P642 ?kerajaan ] .
    }}
  }}

  # Silsilah dan Meta data tambahan
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

    # 3. RUN DBpedia SPARQL QUERY
    dbpedia_query = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dbp: <http://dbpedia.org/property/>
PREFIX dbc: <http://dbpedia.org/resource/Category:>

SELECT DISTINCT ?namaKerajaan ?ibuKota ?agama ?pendahulu ?penerus ?tahunMulai ?wikidataID
WHERE {
  ?s dct:subject dbc:Precolonial_states_of_Indonesia ;
     rdfs:label ?namaKerajaan .

  OPTIONAL { ?s dbo:capital ?cap. ?cap rdfs:label ?ibuKota. FILTER (lang(?ibuKota) = "en") }
  OPTIONAL { ?s dbo:religion ?rel. ?rel rdfs:label ?agama. FILTER (lang(?agama) = "en") }
  OPTIONAL { ?s dbp:p ?pendahulu } 
  OPTIONAL { ?s dbp:s ?penerus } 
  OPTIONAL { ?s dbp:yearStart ?tahunMulai }

  OPTIONAL { ?s owl:sameAs ?wikidataID. FILTER (REGEX(STR(?wikidataID), "wikidata.org")) }

  FILTER (lang(?namaKerajaan) = "en")
}
ORDER BY ?tahunMulai
"""

    # Execute SPARQL Queries
    df_wiki = fetch_sparql("https://query.wikidata.org/sparql", wikidata_query)
    df_db = fetch_sparql("https://dbpedia.org/sparql", dbpedia_query)
    
    if df_wiki.empty:
        print("Warning: Wikidata returned empty results.")
    if df_db.empty:
        print("Warning: DBpedia returned empty results.")

    # 4. CLEAN SPARQL DATA AND EXTRACT ABSOLUTE IDs
    print("Cleaning SPARQL Dataframes...")
    for df in [df_wiki, df_db]:
        if not df.empty:
            for col in df.columns:
                df[col] = df[col].apply(clean_encoding)
                
    # Standardize URIs/IDs for Left Join
    if not df_wiki.empty:
        df_wiki['kerajaan_clean'] = df_wiki['kerajaan'].apply(clean_uri)
    else:
        df_wiki['kerajaan_clean'] = []
        
    if not df_db.empty:
        df_db['wikidataID_clean'] = df_db['wikidataID'].apply(clean_uri)
    else:
        df_db['wikidataID_clean'] = []

    # 5. AGGREGATE SPARQL RESULTS
    # Aggregating Wikidata records per person to combine multi-value relationship rows (e.g. multiple children/spouses)
    df_wiki_agg = pd.DataFrame()
    if not df_wiki.empty:
        print("Aggregating Wikidata records per person...")
        agg_funcs = {
            'orangLabel': 'first',
            'kerajaan': 'first',
            'kerajaanLabel': 'first',
            'ayahLabel': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'ibuLabel': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'pasanganLabel': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'anakLabel': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'saudaraLabel': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'kerabatLabel': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'dinastiLabel': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'menggantikanLabel': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'digantikan_olehLabel': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'tglLahir': 'first',
            'tglMati': 'first',
            'kerajaan_clean': 'first'
        }
        agg_funcs = {k: v for k, v in agg_funcs.items() if k in df_wiki.columns}
        df_wiki_agg = df_wiki.groupby('orang').agg(agg_funcs).reset_index()

    # Aggregating DBpedia records per kingdom
    df_db_agg = pd.DataFrame()
    if not df_db.empty:
        print("Aggregating DBpedia records per kingdom...")
        agg_funcs_db = {
            'namaKerajaan': 'first',
            'ibuKota': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'agama': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'pendahulu': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'penerus': lambda x: ', '.join(sorted(list(set(x.dropna())))) if x.dropna().any() else '',
            'tahunMulai': 'first'
        }
        df_db_agg = df_db.groupby('wikidataID_clean').agg(agg_funcs_db).reset_index()

    # 6. MERGE SPARQL DATASETS (Entity Alignment via Absolute ID)
    df_enriched_sources = pd.DataFrame()
    if not df_wiki_agg.empty and not df_db_agg.empty:
        print("Performing Left Join between Wikidata and DBpedia on Kingdom ID...")
        df_enriched_sources = pd.merge(
            df_wiki_agg, 
            df_db_agg, 
            left_on='kerajaan_clean', 
            right_on='wikidataID_clean', 
            how='left'
        )
    elif not df_wiki_agg.empty:
        df_enriched_sources = df_wiki_agg
        print("Using Wikidata as the sole enriched source (DBpedia empty).")
    elif not df_db_agg.empty:
        print("Wikidata is empty, cannot align genealogy. Proceeding with original CSV only.")

    # 7. MAP AND PATCH ORIGINAL CSV
    # Add new metadata, temporal, tracking, and manual validation columns to original CSV if not exist
    new_cols = ['tglLahir', 'tglMati', 'saudara', 'kerabat', 'dinasti', 'personWikidataID', 'source', 'confidence_score', 'manual_check']
    for c in new_cols:
        if c not in df_orig.columns:
            if c == 'confidence_score':
                df_orig[c] = 1.0
            elif c == 'manual_check':
                df_orig[c] = False
            elif c == 'source':
                df_orig[c] = "original"
            else:
                df_orig[c] = ""

    # Perform alignment update
    count_enriched_sparql = 0
    
    print("Performing fuzzy entity disambiguation and mapping...")
    for idx, row in df_orig.iterrows():
        name = row['orang']
        k = row['kerajaan']
        
        if not name or pd.isna(name):
            continue
            
        # Call entity disambiguation (fuzzy matching)
        match_row, match_score, needs_manual = find_fuzzy_match(name, k, df_enriched_sources)
        
        if match_row is not None:
            count_enriched_sparql += 1
            df_orig.at[idx, 'source'] = 'wikidata'
            df_orig.at[idx, 'confidence_score'] = round(float(match_score) / 100.0, 2)
            df_orig.at[idx, 'manual_check'] = needs_manual
            
            # Patch family relationships if missing
            if not row['ayah']:
                df_orig.at[idx, 'ayah'] = match_row.get('ayahLabel', '')
            if not row['ibu']:
                df_orig.at[idx, 'ibu'] = match_row.get('ibuLabel', '')
            if not row['pasangan']:
                df_orig.at[idx, 'pasangan'] = match_row.get('pasanganLabel', '')
            if not row['anak']:
                df_orig.at[idx, 'anak'] = match_row.get('anakLabel', '')
                
            # Kingdom details
            if not row['ibuKota']:
                df_orig.at[idx, 'ibuKota'] = match_row.get('ibuKota', '')
            if not row['agama']:
                df_orig.at[idx, 'agama'] = match_row.get('agama', '')
            if not row['pendahulu']:
                df_orig.at[idx, 'pendahulu'] = match_row.get('menggantikanLabel', '') or match_row.get('pendahulu', '')
            if not row['penerus']:
                df_orig.at[idx, 'penerus'] = match_row.get('digantikan_olehLabel', '') or match_row.get('penerus', '')
            if not row['tahunMulai']:
                df_orig.at[idx, 'tahunMulai'] = match_row.get('tahunMulai', '')
                
            # Add new columns
            df_orig.at[idx, 'tglLahir'] = match_row.get('tglLahir', '')
            df_orig.at[idx, 'tglMati'] = match_row.get('tglMati', '')
            df_orig.at[idx, 'saudara'] = match_row.get('saudaraLabel', '')
            df_orig.at[idx, 'kerabat'] = match_row.get('kerabatLabel', '')
            df_orig.at[idx, 'dinasti'] = match_row.get('dinastiLabel', '')
            df_orig.at[idx, 'personWikidataID'] = match_row.get('orang', '')

    print(f"Enriched {count_enriched_sparql} rows using SPARQL endpoints.")

    # Clean temporary match columns
    df_orig.drop(columns=['wikidataID_clean'], inplace=True, errors='ignore')

    # 8. WIKIPEDIA + LLM EXTRACTOR PIPELINE (FOR REMAINING NaN VALUES)
    print("Checking for rows with missing genealogy relationships to patch via LLM...")
    
    # We target rows where all silsilah (ayah, ibu, pasangan, anak) are empty/missing
    missing_mask = (
        (df_orig['ayah'].apply(lambda x: str(x).strip() == "")) &
        (df_orig['ibu'].apply(lambda x: str(x).strip() == "")) &
        (df_orig['pasangan'].apply(lambda x: str(x).strip() == "")) &
        (df_orig['anak'].apply(lambda x: str(x).strip() == ""))
    )
    
    df_to_impute = df_orig[missing_mask].copy()
    print(f"Found {len(df_to_impute)} rows with empty genealogy relationships.")
    
    if not OPENROUTER_API_KEY:
        print("\n" + "="*50)
        print("WARNING: OPENROUTER_API_KEY not set in environment or .env file.")
        print("LLM extraction step will be SKIPPED.")
        print("To run the LLM extraction, please fill OPENROUTER_API_KEY in the '.env' file.")
        print("="*50 + "\n")
    else:
        print(f"Starting LLM impute pipeline for {len(df_to_impute)} rows...")
        imputed_count = 0
        cache_extracted = {}
        
        for idx, row in df_to_impute.iterrows():
            nama_tokoh = row['orang']
            if not nama_tokoh or str(nama_tokoh).strip() == "":
                continue
                
            if nama_tokoh in cache_extracted:
                extracted = cache_extracted[nama_tokoh]
            else:
                print(f"\nProcessing '{nama_tokoh}'...")
                # Scrape wikipedia
                wiki_text = fetch_wikipedia_text(nama_tokoh)
                if not wiki_text:
                    cache_extracted[nama_tokoh] = None
                    continue
                    
                # Call OpenRouter API
                extracted = impute_missing_with_llm(nama_tokoh, wiki_text, OPENROUTER_API_KEY)
                cache_extracted[nama_tokoh] = extracted
                # Rate limiting safety sleep only when calling API
                time.sleep(2)
            
            if extracted:
                imputed_count += 1
                df_orig.at[idx, 'source'] = 'llm_imputed'
                df_orig.at[idx, 'confidence_score'] = 0.80
                
                # Impute the extracted values
                if extracted.get("ayah"):
                    df_orig.at[idx, 'ayah'] = clean_encoding(extracted["ayah"])
                if extracted.get("ibu"):
                    df_orig.at[idx, 'ibu'] = clean_encoding(extracted["ibu"])
                if extracted.get("pasangan"):
                    df_orig.at[idx, 'pasangan'] = clean_encoding(extracted["pasangan"])
                if extracted.get("anak"):
                    df_orig.at[idx, 'anak'] = clean_encoding(extracted["anak"])
                if extracted.get("saudara"):
                    df_orig.at[idx, 'saudara'] = clean_encoding(extracted["saudara"])
                
                # Write metadata
                conf = extracted.get("confidence_score", 0.85)
                try:
                    conf = float(conf)
                except (ValueError, TypeError):
                    conf = 0.85
                df_orig.at[idx, 'confidence_score'] = conf
                df_orig.at[idx, 'data_source'] = "Wikipedia Scrape"
            
        print(f"\nSuccessfully imputed silsilah data for {imputed_count} figures using LLM pipeline.")

    # Apply Entity Disambiguation (Stage 3) before exporting
    df_orig = apply_entity_disambiguation(df_orig, OPENROUTER_API_KEY)

    # 9. EXPORT ENRICHED DATASET
    output_filename = os.path.join(script_dir, '../data/dataset_dinasti_final.csv')
    print(f"Exporting final enriched dataset to '{output_filename}'...")
    
    df_orig.to_csv(output_filename, sep=';', index=False, encoding='utf-8')
    print("=== PIPELINE RUN FINISHED SUCCESSFULLY ===")

if __name__ == "__main__":
    main()
