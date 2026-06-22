import os
import sys
import re
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Reconfigure output to utf-8 to handle Indonesian/Javanese characters in terminal
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Load environment variables relative to this script
script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(script_dir, '../.env'))

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Load local CSV metrics for fallback
METRICS_CSV = os.path.join(script_dir, "../data/dataset_dinasti_final_with_metrics.csv")
ALT_CSV = os.path.join(script_dir, "../data/dataset_dinasti_final.csv")

# Load dataset and cache names for entity extraction
df_metrics = None
people_set = set()
kingdoms_set = set()

if os.path.exists(METRICS_CSV):
    try:
        df_metrics = pd.read_csv(METRICS_CSV, sep=';')
        print(f"[INFO] Loaded local metrics dataset from '{METRICS_CSV}'.")
    except Exception as e:
        print(f"[WARNING] Failed to load '{METRICS_CSV}': {e}. Trying fallback...")
        
if df_metrics is None and os.path.exists(ALT_CSV):
    try:
        df_metrics = pd.read_csv(ALT_CSV, sep=';')
        print(f"[INFO] Loaded fallback dataset from '{ALT_CSV}'. Metrics will default to 0.")
    except Exception as e:
        print(f"[ERROR] Failed to load '{ALT_CSV}': {e}")

if df_metrics is not None:
    # Gather unique names
    if 'orang' in df_metrics.columns:
        people_set = set(df_metrics['orang'].dropna().unique())
    if 'kerajaan' in df_metrics.columns:
        kingdoms_set.update(df_metrics['kerajaan'].dropna().unique())
    if 'namaKerajaan' in df_metrics.columns:
        kingdoms_set.update(df_metrics['namaKerajaan'].dropna().unique())
        
    # Clean up empty or whitespace names
    people_set = {p.strip() for p in people_set if p.strip()}
    kingdoms_set = {k.strip() for k in kingdoms_set if k.strip()}
else:
    print("[WARNING] No dataset found. Entity extraction will rely on database queries only.")

# --- NEO4J CONNECTION CLASS ---
class Neo4jConnector:
    def __init__(self, uri, username, password):
        self.uri = uri
        self.username = username
        self.password = password
        self.driver = None
        self.connect()

    def connect(self):
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
            # Test connection
            self.driver.verify_connectivity()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to connect to Neo4j database: {e}")
            self.driver = None
            return False

    def close(self):
        if self.driver:
            self.driver.close()

    def run_query(self, query, parameters=None):
        if not self.driver:
            return []
        try:
            with self.driver.session() as session:
                result = session.run(query, parameters)
                return [record.data() for record in result]
        except Exception as e:
            print(f"[DATABASE ERROR] Exception running query: {e}")
            return []

# Initialize Neo4j connector
neo4j_conn = Neo4jConnector(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD)



# --- FALLBACK METRICS LOOKUP ---
def get_metrics_from_csv(name, entity_type):
    """Retrieves PageRank and Louvain Cluster from local CSV if they are not stored in Neo4j."""
    if df_metrics is None:
        return {"pagerank": 0.0, "louvain_cluster": -1}
        
    try:
        if entity_type == 'Person':
            match = df_metrics[df_metrics['orang'].str.lower() == name.lower()]
            if not match.empty:
                pr = match.iloc[0].get('orang_PageRank', 0.0)
                cluster = match.iloc[0].get('orang_Louvain_Cluster', -1)
                return {"pagerank": float(pr), "louvain_cluster": int(cluster)}
        elif entity_type == 'Kingdom':
            match = df_metrics[df_metrics['kerajaan'].str.lower() == name.lower()]
            if not match.empty:
                pr = match.iloc[0].get('kerajaan_PageRank', 0.0)
                cluster = match.iloc[0].get('kerajaan_Louvain_Cluster', -1)
                return {"pagerank": float(pr), "louvain_cluster": int(cluster)}
    except Exception as e:
        pass
    return {"pagerank": 0.0, "louvain_cluster": -1}

# --- GRAPH RETRIEVAL ENGINE ---
def retrieve_shortest_path(name1: str, name2: str) -> dict:
    """
    Queries Neo4j to retrieve the shortest path between two historical figures.
    Returns a structured dictionary of the path.
    """
    if not neo4j_conn.driver:
        return {
            "status": "offline",
            "message": "Neo4j database offline. Shortest path retrieval unavailable."
        }
        
    shortest_path_query = """
    MATCH (n1 {name: $name1}), (n2 {name: $name2})
    MATCH path = shortestPath((n1)-[*..5]-(n2))
    RETURN [node in nodes(path) | node.name] as node_names, 
           [node in nodes(path) | labels(node)[0]] as node_labels,
           [rel in relationships(path) | type(rel)] as rel_types
    """
    path_res = neo4j_conn.run_query(shortest_path_query, {"name1": name1, "name2": name2})
    if path_res and path_res[0]["node_names"]:
        return {
            "status": "success",
            "node_names": path_res[0]["node_names"],
            "node_labels": path_res[0]["node_labels"],
            "rel_types": path_res[0]["rel_types"]
        }
    return {
        "status": "not_found",
        "message": f"No connection path found between '{name1}' and '{name2}'."
    }

def retrieve_person_info(person: str) -> dict:
    """
    Retrieves properties and network metrics for a specific historical figure.
    Falls back to local CSV if Neo4j is offline.
    """
    csv_metrics = get_metrics_from_csv(person, 'Person')
    
    if not neo4j_conn.driver:
        # Offline CSV Fallback
        if df_metrics is not None:
            match = df_metrics[df_metrics['orang'].str.lower() == person.lower()].fillna("")
            if not match.empty:
                row = match.iloc[0]
                return {
                    "source": "csv_fallback",
                    "name": person,
                    "role": row.get('peran', 'Tidak diketahui'),
                    "dynasty": row.get('dinasti', 'Tidak diketahui'),
                    "birth_date": row.get('tglLahir', 'Tidak diketahui'),
                    "death_date": row.get('tglMati', 'Tidak diketahui'),
                    "pagerank": csv_metrics["pagerank"],
                    "louvain_cluster": csv_metrics["louvain_cluster"]
                }
        return {
            "status": "not_found",
            "message": f"Person '{person}' not found in offline dataset."
        }
        
    prop_query = """
    MATCH (p:Person {name: $name})
    RETURN p.name as name, p.role as role, p.birthDate as birthDate, 
           p.deathDate as deathDate, p.wikidataID as wikidataID, p.dynasty as dynasty,
           p.pagerank_score as pagerank, p.louvain_cluster as louvain_cluster
    """
    prop_res = neo4j_conn.run_query(prop_query, {"name": person})
    
    if prop_res:
        p_data = prop_res[0]
        pr = p_data.get("pagerank") or csv_metrics["pagerank"]
        cluster = p_data.get("louvain_cluster") if p_data.get("louvain_cluster") is not None else csv_metrics["louvain_cluster"]
        return {
            "source": "neo4j",
            "name": p_data.get("name"),
            "role": p_data.get("role") or "Tidak diketahui",
            "dynasty": p_data.get("dynasty") or "Tidak diketahui",
            "birth_date": p_data.get("birthDate") or "Tidak diketahui",
            "death_date": p_data.get("deathDate") or "Tidak diketahui",
            "wikidata_id": p_data.get("wikidataID") or "Tidak diketahui",
            "pagerank": pr,
            "louvain_cluster": cluster
        }
    else:
        # Fallback to CSV properties if node not found but exists in CSV
        if df_metrics is not None:
            match = df_metrics[df_metrics['orang'].str.lower() == person.lower()].fillna("")
            if not match.empty:
                row = match.iloc[0]
                return {
                    "source": "csv_fallback_node_missing",
                    "name": person,
                    "role": row.get('peran') or "Tidak diketahui",
                    "dynasty": row.get('dinasti') or "Tidak diketahui",
                    "birth_date": row.get('tglLahir') or "Tidak diketahui",
                    "death_date": row.get('tglMati') or "Tidak diketahui",
                    "pagerank": csv_metrics["pagerank"],
                    "louvain_cluster": csv_metrics["louvain_cluster"]
                }
                
    return {
        "status": "not_found",
        "message": f"Person '{person}' not found in database or CSV."
    }

def retrieve_person_relationships(person: str) -> list:
    """
    Retrieves the structural neighborhood relationships of a specific historical figure.
    Falls back to local CSV columns if Neo4j is offline.
    """
    if not neo4j_conn.driver:
        # Offline CSV Fallback
        if df_metrics is not None:
            match = df_metrics[df_metrics['orang'].str.lower() == person.lower()].fillna("")
            if not match.empty:
                row = match.iloc[0]
                rels = []
                # Map CSV columns to relationship records
                for col, rel_type in [
                    ('ayah', 'AYAH'), ('ibu', 'IBU'), ('pasangan', 'PASANGAN'),
                    ('anak', 'ANAK'), ('saudara', 'SAUDARA'), ('kerabat', 'KERABAT')
                ]:
                    val = row.get(col)
                    if val and str(val).strip():
                        names = [n.strip() for n in str(val).split(',') if n.strip()]
                        for name in names:
                            rels.append({
                                "relation": rel_type,
                                "neighbor_name": name,
                                "neighbor_type": "Person"
                            })
                return rels
        return []
        
    rel_query = """
    MATCH (p:Person {name: $name})-[r]-(neighbor)
    RETURN type(r) as relation, startNode(r) = p as is_outgoing, 
           neighbor.name as neighbor_name, labels(neighbor)[0] as neighbor_type
    LIMIT 15
    """
    rel_res = neo4j_conn.run_query(rel_query, {"name": person})
    
    rels = []
    for rel in rel_res:
        rels.append({
            "relation": rel["relation"],
            "is_outgoing": rel["is_outgoing"],
            "neighbor_name": rel["neighbor_name"],
            "neighbor_type": rel["neighbor_type"]
        })
    return rels

def retrieve_kingdom_info(kingdom: str) -> dict:
    """
    Retrieves properties, metrics, and affiliated members for a kingdom.
    Falls back to local CSV if Neo4j is offline.
    """
    csv_metrics = get_metrics_from_csv(kingdom, 'Kingdom')
    
    if not neo4j_conn.driver:
        # Offline CSV Fallback
        if df_metrics is not None:
            match = df_metrics[df_metrics['kerajaan'].str.lower() == kingdom.lower()].fillna("")
            if not match.empty:
                row = match.iloc[0]
                return {
                    "source": "csv_fallback",
                    "name": kingdom,
                    "capital": row.get('ibuKota', 'Tidak diketahui'),
                    "religion": row.get('agama', 'Tidak diketahui'),
                    "year_start": row.get('tahunMulai', 'Tidak diketahui'),
                    "pagerank": csv_metrics["pagerank"],
                    "louvain_cluster": csv_metrics["louvain_cluster"],
                    "members": []  # Cannot fetch members offline
                }
        return {
            "status": "not_found",
            "message": f"Kingdom '{kingdom}' not found in offline dataset."
        }
        
    prop_query = """
    MATCH (k:Kingdom {name: $name})
    RETURN k.name as name, k.capital as capital, k.religion as religion, 
           k.yearStart as yearStart, k.wikidataID as wikidataID,
           k.pagerank_score as pagerank, k.louvain_cluster as louvain_cluster
    """
    prop_res = neo4j_conn.run_query(prop_query, {"name": kingdom})
    
    members_query = """
    MATCH (p:Person)-[:MEMIMPIN_ATAU_TERAFILIASI]->(k:Kingdom {name: $name})
    RETURN p.name as name, p.role as role
    LIMIT 15
    """
    members_res = neo4j_conn.run_query(members_query, {"name": kingdom})
    members = [{"name": m["name"], "role": m["role"] or "Tidak diketahui"} for m in members_res]
    
    if prop_res:
        k_data = prop_res[0]
        pr = k_data.get("pagerank") or csv_metrics["pagerank"]
        cluster = k_data.get("louvain_cluster") if k_data.get("louvain_cluster") is not None else csv_metrics["louvain_cluster"]
        return {
            "source": "neo4j",
            "name": k_data.get("name"),
            "capital": k_data.get("capital") or "Tidak diketahui",
            "religion": k_data.get("religion") or "Tidak diketahui",
            "year_start": k_data.get("yearStart") or "Tidak diketahui",
            "wikidata_id": k_data.get("wikidataID") or "Tidak diketahui",
            "pagerank": pr,
            "louvain_cluster": cluster,
            "members": members
        }
    else:
        # Fallback to CSV properties if node not found but exists in CSV
        if df_metrics is not None:
            match = df_metrics[df_metrics['kerajaan'].str.lower() == kingdom.lower()].fillna("")
            if not match.empty:
                row = match.iloc[0]
                return {
                    "source": "csv_fallback_node_missing",
                    "name": kingdom,
                    "capital": row.get('ibuKota') or "Tidak diketahui",
                    "religion": row.get('agama') or "Tidak diketahui",
                    "year_start": row.get('tahunMulai') or "Tidak diketahui",
                    "pagerank": csv_metrics["pagerank"],
                    "louvain_cluster": csv_metrics["louvain_cluster"],
                    "members": members
                }
                
    return {
        "status": "not_found",
        "message": f"Kingdom '{kingdom}' not found in database or CSV."
    }

# --- 5th MCP TOOL: ANALYTICAL CYPHER GENERATOR & EXECUTION ---
def retrieve_analytical_query(natural_language_question: str) -> dict:
    """
    Translates an analytical natural language question into Cypher, validates for read-only safety,
    executes it in the Neo4j database, and returns the serialized JSON results.
    """
    system_prompt = (
        "Anda adalah pakar Neo4j Cypher. Konversikan pertanyaan pengguna berikut ke dalam satu query Cypher read-only.\n\n"
        "Berikut adalah skema database graf kami:\n"
        "Node:\n"
        "- Person: mewakili tokoh sejarah.\n"
        "  Properti:\n"
        "    - name (string)\n"
        "    - role (string)\n"
        "    - birthDate (string)\n"
        "    - deathDate (string)\n"
        "    - wikidataID (string)\n"
        "    - dynasty (string)\n"
        "    - pagerank_score (float, metrik PageRank)\n"
        "    - louvain_cluster (integer, ID klaster Louvain)\n"
        "    - betweenness_score (float, metrik Betweenness Centrality)\n"
        "    - adamic_adar_avg (float, skor rata-rata Adamic-Adar)\n"
        "- Kingdom: mewakili kerajaan prekolonial.\n"
        "  Properti:\n"
        "    - name (string)\n"
        "    - capital (string)\n"
        "    - religion (string)\n"
        "    - yearStart (integer)\n"
        "    - wikidataID (string)\n"
        "    - pagerank_score (float, metrik PageRank)\n"
        "    - louvain_cluster (integer, ID klaster Louvain)\n"
        "    - betweenness_score (float, metrik Betweenness Centrality)\n\n"
        "Relasi:\n"
        "- (p:Person)-[:MEMIMPIN_ATAU_TERAFILIASI]->(k:Kingdom)\n"
        "- (p1:Person)-[:AYAH]->(p2:Person)\n"
        "- (p1:Person)-[:IBU]->(p2:Person)\n"
        "- (p1:Person)-[:PASANGAN]->(p2:Person)\n"
        "- (p1:Person)-[:ANAK]->(p2:Person)\n"
        "- (p1:Person)-[:SAUDARA]->(p2:Person)\n"
        "- (p1:Person)-[:KERABAT]->(p2:Person)\n"
        "- (p1:Person)-[:MENGGANTIKAN]->(p2:Person)\n"
        "- (p1:Person)-[:DIGANTIKAN_OLEH]->(p2:Person)\n\n"
        "Aturan Ketat:\n"
        "1. Kembalikan HANYA kueri Cypher mentah. JANGAN gunakan markdown fences (seperti ```cypher atau ```), penulisan tambahan, penjelasan, atau teks pengantar apapun.\n"
        "2. Kueri harus bersifat read-only (hanya menggunakan MATCH, RETURN, ORDER BY, LIMIT, WHERE, dsb.)."
    )
    
    # 1. Use query_openrouter_raw to convert question into raw Cypher
    cypher_query = query_openrouter_raw(system_prompt, natural_language_question)
    if not cypher_query:
        return {
            "query_generated": "",
            "row_count": 0,
            "results": [],
            "error": "Failed to generate Cypher query from LLM."
        }
        
    # 2. Strip any ```cypher or ``` fences that the model adds anyway
    cypher_query = cypher_query.strip()
    if cypher_query.startswith("```"):
        lines = cypher_query.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cypher_query = "\n".join(lines).strip()
        
    # Remove single line markdown quotes if present
    cypher_query = re.sub(r'^`|`$', '', cypher_query).strip()
    
    # Auto-append LIMIT 25 if missing
    if "limit" not in cypher_query.lower():
        if cypher_query.endswith(";"):
            cypher_query = cypher_query[:-1].strip()
        cypher_query += "\nLIMIT 25"
        
    # 3. Read-only validation
    forbidden_patterns = [
        r"\bCREATE\b", r"\bMERGE\b", r"\bSET\b", r"\bDELETE\b", 
        r"\bREMOVE\b", r"\bDROP\b", r"\bDETACH\b", r"\bLOAD\s+CSV\b", 
        r"apoc\..*write"
    ]
    is_invalid = False
    for pattern in forbidden_patterns:
        if re.search(pattern, cypher_query, re.IGNORECASE):
            is_invalid = True
            break
            
    if is_invalid:
        return {
            "query_generated": cypher_query,
            "row_count": 0,
            "results": [],
            "error": "Query rejected: Only read-only operations are allowed. Write/mutation patterns detected."
        }
        
    # 4. Check if neo4j connection is active
    if not neo4j_conn.driver:
        return {
            "query_generated": cypher_query,
            "row_count": 0,
            "results": [],
            "error": "Neo4j database offline. Query execution unavailable."
        }
        
    # 5. Execute via Neo4jConnector pattern
    print(f"-> [Execute Generated Cypher Query]:\n{cypher_query}\n")
    try:
        with neo4j_conn.driver.session() as session:
            result = session.run(cypher_query)
            raw_results = [record.data() for record in result]
            
        # Recursive serialization to ensure JSON-serializable types
        def make_serializable(data):
            if isinstance(data, dict):
                return {k: make_serializable(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [make_serializable(x) for x in data]
            elif isinstance(data, (set, tuple)):
                return [make_serializable(x) for x in data]
            elif hasattr(data, 'isoformat'):
                return data.isoformat()
            return data
            
        serialized_results = make_serializable(raw_results)
        
        return {
            "query_generated": cypher_query,
            "row_count": len(serialized_results),
            "results": serialized_results,
            "error": None
        }
    except Exception as e:
        return {
            "query_generated": cypher_query,
            "row_count": 0,
            "results": [],
            "error": f"Neo4j execution error: {str(e)}"
        }

# --- CLEAN PROMPT PAYLOAD AND SANITIZE CONTROL CHARS ---
def clean_prompt_payload(text):
    if not text:
        return ""
    # Standardize newlines
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Filter out illegal control characters (ASCII 0-31 except \n and \t)
    cleaned_chars = []
    for char in text:
        codepoint = ord(char)
        if codepoint in (9, 10) or (32 <= codepoint <= 126) or (codepoint >= 160):
            cleaned_chars.append(char)
    return "".join(cleaned_chars)

# --- GENERIC OPENROUTER CLIENT WITH MODEL FALLBACKS ---
def query_openrouter_raw(system_prompt=None, user_prompt=None, messages=None, tools=None):
    if not OPENROUTER_API_KEY:
        return {} if (messages is not None or tools is not None) else ""
        
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/eas-graf/eas-graf",
        "X-Title": "Nusantara Dynasty GraphRAG Chatbot"
    }
    
    if messages is None:
        sys_str = clean_prompt_payload(system_prompt or "")
        usr_str = clean_prompt_payload(user_prompt or "")
        messages = [
            {"role": "system", "content": sys_str},
            {"role": "user", "content": usr_str}
        ]
        temp_system = sys_str
    else:
        # If messages is passed, try to find system prompt content for token/temp heuristics
        temp_system = ""
        for msg in messages:
            if msg.get("role") == "system":
                temp_system = msg.get("content", "")
                break

    # Model fallback hierarchy
    models = [
        "google/gemini-2.5-flash",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "google/gemini-1.5-flash:free",
        "openrouter/free"
    ]
    
    # Heuristics for tokens and temperature
    if tools is not None or (system_prompt is None and user_prompt is None):
        max_tok = 1500
        temp = 0.2
    else:
        max_tok = 1000 if "cypher" in temp_system.lower() else 1200
        temp = 0.1 if "cypher" in temp_system.lower() else 0.3

    for model in models:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tok,
            "temperature": temp
        }
        if tools is not None:
            payload["tools"] = tools
            
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=45)
            if response.status_code == 200:
                result = response.json()
                if tools is not None or (system_prompt is None and user_prompt is None):
                    # Return the full response dictionary/JSON structure
                    return result
                else:
                    # Return only the content string for backward compatibility
                    return result["choices"][0]["message"]["content"].strip()
            else:
                print(f"[LLM LOG] Model '{model}' gagal dengan status kode {response.status_code}. Mencoba model alternatif...", file=sys.stderr)
        except Exception as e:
            print(f"[LLM LOG] Error saat menghubungi model '{model}': {e}", file=sys.stderr)
            
    return {} if (messages is not None or tools is not None) else ""



# --- OPENROUTER LLM CLIENT FOR FINAL ANSWER SYNTHESIS ---
def query_openrouter_llm(query, context):
    """Sends prompt with retrieved context to OpenRouter LLM, implementing fallbacks."""
    system_prompt = (
        "Anda adalah Nusantara Dynasty Knowledge Graph Bot, asisten cerdas berkeahlian ganda sebagai "
        "Senior Historian Sejarah Nusantara dan Senior Data Scientist. Tugas Anda adalah membantu "
        "pengguna memahami relasi silsilah dinasti kerajaan prekolonial di Indonesia menggunakan "
        "data terstruktur dari Neo4j Graph Database dan metrik analisis graf (NetworkX).\n\n"
        "Aturan Penulisan Jawaban:\n"
        "1. Jawab dalam bahasa Indonesia yang mengalir, jelas, natural, dan sangat profesional.\n"
        "2. Manfaatkan informasi dalam KONTEKS GRAF yang disediakan (seperti relasi silsilah, PageRank, "
        "dan Klaster Louvain) untuk memperkuat kredibilitas jawaban Anda.\n"
        "3. PageRank menunjukkan tingkat pengaruh tokoh/kerajaan dalam jaringan (makin tinggi nilainya, "
        "makin banyak relasi/koneksi). Klaster Louvain (ID Klaster) mengelompokkan tokoh-tokoh ke dalam "
        "klaster dinasti/kerabat yang terhubung secara modular.\n"
        "4. Jika informasi tidak ada di dalam KONTEKS GRAF, berikan penjelasan sejarah umum yang Anda ketahui, "
        "namun cantumkan catatan penjelasan singkat (disclaimer) bahwa data tersebut berada di luar "
        "database graf dinasti saat ini.\n"
        "5. Tuliskan jawaban secara komprehensif, terstruktur (gunakan bullet points jika membantu), dan informatif."
    )
    
    user_prompt = f"PERTANYAAN PENGGUNA:\n{query}\n\nKONTEKS GRAF DARI DATABASE:\n"
    if context.strip():
        # Enforce Cap of 6000 characters to avoid huge payloads
        if len(context) > 6000:
            context = context[:6000] + "\n\n[... Konteks dipotong karena batas kapasitas payload ...]"
        user_prompt += context
    else:
        user_prompt += "(Konteks kosong - tidak ada kecocokan tokoh/kerajaan langsung di database graf.)"
        
    res = query_openrouter_raw(system_prompt, user_prompt)
    if not res:
        return "[Error: Semua model OpenRouter gagal memberikan respons. Silakan periksa koneksi internet Anda atau status limit API Key Anda.]"
    return res

# --- MAIN TERMINAL CHATBOT LOOP (CLI) ---
def main():
    print("========================================================================")
    print("            NUSANTARA DYNASTY KNOWLEDGE GRAPH - GRAPHRAG BOT            ")
    print("========================================================================")
    print("Selamat datang di CLI Chatbot Graf Silsilah Dinasti Nusantara!")
    print("Bot ini menggabungkan Graph Database Neo4j, Metrik Analitik NetworkX,")
    print("dan OpenRouter LLM untuk memberikan jawaban sejarah yang berbasis fakta.")
    print("------------------------------------------------------------------------")
    print(f"Database URI: {NEO4J_URI}")
    if neo4j_conn.driver:
        print("Status Database: TERHUBUNG (Koneksi Neo4j Aktif)")
    else:
        print("Status Database: OFFLINE (Menggunakan fallback pencarian CSV Lokal)")
    print("Ketik 'exit', 'quit', atau 'keluar' untuk mengakhiri sesi chat.")
    print("========================================================================\n")
    
    while True:
        try:
            query = input("Anda: ").strip()
            if not query:
                continue
                
            if query.lower() in ['exit', 'quit', 'keluar']:
                print("\nTerima kasih telah menggunakan Nusantara Dynasty GraphRAG Bot. Sampai jumpa!")
                break
                
            context = ""
            
            # Match entities against the loaded datasets
            matched_people = [p for p in people_set if p.lower() in query.lower()]
            matched_kingdoms = [k for k in kingdoms_set if k.lower() in query.lower()]
            
            if matched_people or matched_kingdoms:
                extracted_str = []
                if matched_people:
                    extracted_str.append(f"Tokoh: {', '.join(matched_people)}")
                if matched_kingdoms:
                    extracted_str.append(f"Kerajaan: {', '.join(matched_kingdoms)}")
                print(f"-> [Entity Matched] {', '.join(extracted_str)}")
            else:
                print("-> [Entity Matched] Tidak ada entitas spesifik terdeteksi (menggunakan modus pencarian umum)")
                
            print("Bot: (Menarik data dari Knowledge Graph...)")
            structured_context = {
                "offline_warning": not neo4j_conn.driver,
                "shortest_paths": [],
                "people_info": [],
                "kingdoms_info": []
            }
            
            if len(matched_people) >= 2:
                sp_result = retrieve_shortest_path(matched_people[0], matched_people[1])
                if sp_result.get("status") == "success":
                    structured_context["shortest_paths"].append(sp_result)
                    
            for p in matched_people:
                p_info = retrieve_person_info(p)
                p_rels = retrieve_person_relationships(p)
                if p_info.get("status") != "not_found":
                    structured_context["people_info"].append({
                        "info": p_info,
                        "relationships": p_rels
                    })
                    
            for k in matched_kingdoms:
                k_info = retrieve_kingdom_info(k)
                if k_info.get("status") != "not_found":
                    structured_context["kingdoms_info"].append(k_info)
                    
            context = json.dumps(structured_context, indent=2, ensure_ascii=False)
            
            # 3. LLM Synthesis
            print("Bot: (Mensintesis jawaban dengan AI...)")
            answer = query_openrouter_llm(query, context)
            
            print("\n------------------------------ JAWABAN BOT ------------------------------")
            print(answer)
            print("-------------------------------------------------------------------------\n")
            
        except KeyboardInterrupt:
            print("\nSesi chat dihentikan oleh pengguna. Sampai jumpa!")
            break
        except Exception as e:
            print(f"\n[ERROR] Terjadi kesalahan dalam loop chat: {e}\n")
            
    # Clean up Neo4j driver
    neo4j_conn.close()

def run_analytical_tests():
    print("=== STARTING MANUAL TESTS FOR RETRIEVE_ANALYTICAL_QUERY ===")
    
    questions = [
        "Siapa 5 tokoh dengan PageRank tertinggi di Kerajaan Pajajaran?",
        "Berapa banyak tokoh di setiap klaster Louvain?",
        "Tuliskan kueri Cypher untuk menghapus semua tokoh dari Kerajaan Majapahit menggunakan DETACH DELETE"
    ]
    
    for i, q in enumerate(questions, 1):
        print(f"\n--- TEST {i}: {q} ---")
        res = retrieve_analytical_query(q)
        print(f"Generated Cypher Query:\n{res.get('query_generated')}")
        print(f"Row Count: {res.get('row_count')}")
        print(f"Error: {res.get('error')}")
        print(f"Results Sample: {res.get('results')[:3] if res.get('results') else []}")
        
    print("\n--- TEST 4: Direct Write Cypher Bypass Test (SET command) ---")
    direct_test_query = "MATCH (p:Person {name: 'Mpu Tantular'}) SET p.role = 'Super Mahapatih' RETURN p"
    print(f"Testing direct write query: {direct_test_query}")
    
    forbidden_patterns = [
        r"\bCREATE\b", r"\bMERGE\b", r"\bSET\b", r"\bDELETE\b", 
        r"\bREMOVE\b", r"\bDROP\b", r"\bDETACH\b", r"\bLOAD\s+CSV\b", 
        r"apoc\..*write"
    ]
    is_invalid = False
    for pattern in forbidden_patterns:
        if re.search(pattern, direct_test_query, re.IGNORECASE):
            is_invalid = True
            break
    if is_invalid:
        print("Guard Status: BLOCKED (Correctly identified write/mutation pattern)")
        print("Error: Query rejected: Only read-only operations are allowed. Write/mutation patterns detected.")
    else:
        print("Guard Status: PASSED (Failed to block)")
        
    print("\n--- TEST 5: Word-Boundary Collision Edge Cases ('Setyawati', 'Asset') ---")
    safe_test_queries = [
        "MATCH (p:Person {name: 'Setyawati'}) RETURN p",
        "MATCH (p:Person) WHERE p.name CONTAINS 'Asset' RETURN p"
    ]
    for q in safe_test_queries:
        is_invalid_safe = False
        for pattern in forbidden_patterns:
            if re.search(pattern, q, re.IGNORECASE):
                is_invalid_safe = True
                break
        if is_invalid_safe:
            print(f"Query: '{q}' -> Guard Status: BLOCKED (FAILED - collided with substring)")
        else:
            print(f"Query: '{q}' -> Guard Status: PASSED (SUCCESS - ignored substring)")
            
    print("\n=== MANUAL TESTS COMPLETED ===")
    
    # Close Neo4j connector after test
    neo4j_conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test-analytical":
        run_analytical_tests()
    else:
        main()
