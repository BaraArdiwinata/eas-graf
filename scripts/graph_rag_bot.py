import os
import sys
import re
import json
import requests
import pandas as pd
import networkx as nx
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

<<<<<<< HEAD

=======
# --- ENTITY EXTRACTION ENGINE ---
def extract_entities(query_text):
    """
    Extracts known historical figure names or kingdoms from the query text.
    Uses exact word/phrase boundary matching to avoid sub-string collisions.
    """
    sorted_people = sorted(list(people_set), key=len, reverse=True)
    sorted_kingdoms = sorted(list(kingdoms_set), key=len, reverse=True)
    
    query_normalized = f" {query_text.lower()} "
    query_normalized = re.sub(r'[^\w\s]', ' ', query_normalized)
    query_normalized = re.sub(r'\s+', ' ', query_normalized)
    
    matched_people = []
    matched_kingdoms = []
    matched_spans = []
    
    # 1. Exact Match
    for person in sorted_people:
        p_clean = person.lower()
        p_clean = re.sub(r'[^\w\s]', ' ', p_clean)
        p_clean = re.sub(r'\s+', ' ', p_clean).strip()
        
        if not p_clean:
            continue
            
        pattern = r'\b' + re.escape(p_clean) + r'\b'
        match = re.search(pattern, query_normalized)
        if match:
            start, end = match.span()
            overlap = False
            for s_start, s_end in matched_spans:
                if not (end <= s_start or start >= s_end):
                    overlap = True
                    break
            if not overlap:
                matched_people.append(person)
                matched_spans.append((start, end))
                
    for kingdom in sorted_kingdoms:
        k_clean = kingdom.lower()
        k_clean = re.sub(r'[^\w\s]', ' ', k_clean)
        k_clean = re.sub(r'\s+', ' ', k_clean).strip()
        
        if not k_clean:
            continue
            
        pattern = r'\b' + re.escape(k_clean) + r'\b'
        match = re.search(pattern, query_normalized)
        if match:
            start, end = match.span()
            overlap = False
            for s_start, s_end in matched_spans:
                if not (end <= s_start or start >= s_end):
                    overlap = True
                    break
            if not overlap:
                matched_kingdoms.append(kingdom)
                matched_spans.append((start, end))
                
    # 2. Heuristic Partial Match if no exact matches found
    if not matched_people and not matched_kingdoms:
        stop_words = {
            "siapa", "dan", "dari", "di", "adalah", "yang", "pada", "tentang", "bagaimana", 
            "apakah", "berapa", "ayah", "ibu", "anak", "istri", "suami", "pasangan", 
            "saudara", "kerabat", "raja", "sultan", "ratu", "patih", "pendahulu", "penerus",
            "silsilah", "hubungan", "kerajaan", "kesultanan", "dinasti", "silsilahnya", "mirip"
        }
        titles_to_ignore = {
            "raden", "sri", "sultan", "dewa", "agung", "raja", "mpu", "patih", "sang", 
            "baginda", "dyah", "ratu", "mas", "gusti", "susuhunan", "panembahan", "prabu",
            "kanjeng", "haryo", "wuryaningrat", "karaeng", "daeng", "datu", "alauddin", 
            "syarif", "sayyid", "sunan"
        }
        
        query_words = re.findall(r'\b\w+\b', query_text.lower())
        query_words = [w for w in query_words if w not in stop_words and w not in titles_to_ignore and len(w) >= 3]
        
        for word in query_words:
            for person in sorted_people:
                person_lower = person.lower()
                person_words = re.findall(r'\b\w+\b', person_lower)
                if word in person_words:
                    matched_people.append(person)
                    break
            if matched_people:
                break
                
            for kingdom in sorted_kingdoms:
                kingdom_lower = kingdom.lower()
                kingdom_words = re.findall(r'\b\w+\b', kingdom_lower)
                if word in kingdom_words:
                    matched_kingdoms.append(kingdom)
                    break
            if matched_kingdoms:
                break
                
    return matched_people, matched_kingdoms
>>>>>>> 2b02bc9d4e24fb81b73f5273c787416e1ba43aee

# --- FALLBACK METRICS LOOKUP ---
def get_metrics_from_csv(name, entity_type):
    """Retrieves PageRank and Louvain Cluster from local CSV."""
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
    except Exception:
        pass
    return {"pagerank": 0.0, "louvain_cluster": -1}

<<<<<<< HEAD
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
=======
# --- MCP TOOL REGISTRY ---
class MCPToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name, description, parameters):
        def decorator(func):
            self.tools[name] = {
                "func": func,
                "description": description,
                "parameters": parameters
            }
            return func
        return decorator

    def execute(self, tool_name, **kwargs):
        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not found in registry."
        try:
            return self.tools[tool_name]["func"](**kwargs)
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}"

    def get_tool_descriptions(self):
        descriptions = []
        for name, tool in self.tools.items():
            param_desc = []
            for p_name, p_info in tool["parameters"].items():
                p_type = p_info.get("type", "string")
                p_req = "required" if p_info.get("required", False) else "optional"
                p_desc = p_info.get("description", "")
                param_desc.append(f"  - {p_name} ({p_type}, {p_req}): {p_desc}")
            params_str = "\n".join(param_desc)
            descriptions.append(
                f"Tool: {name}\n"
                f"Description: {tool['description']}\n"
                f"Parameters:\n{params_str}"
            )
        return "\n\n".join(descriptions)

registry = MCPToolRegistry()

# Helper to build NetworkX Graph for fallbacks
def build_nx_graph():
    G = nx.Graph()
    name_to_master = {}
    if df_metrics is not None:
        for _, row in df_metrics.iterrows():
            p = row['orang']
            m_id = row.get('master_id', p)
            if pd.notna(p):
                name_to_master[str(p).strip().lower()] = str(m_id).strip()
                
        for _, row in df_metrics.iterrows():
            p = row['orang']
            if not p or pd.isna(p):
                continue
            p_clean = str(p).strip()
            p_node = name_to_master.get(p_clean.lower(), p_clean)
            G.add_node(p_node, label='Person')
            
            k = row.get('kerajaan')
            if k and pd.notna(k) and str(k).strip():
                k_clean = str(k).strip()
                G.add_node(k_clean, label='Kingdom')
                G.add_edge(p_node, k_clean, relation='MEMIMPIN_ATAU_TERAFILIASI')
                
            for col in ['ayah', 'ibu', 'pasangan', 'anak', 'saudara', 'kerabat']:
                val = row[col]
                if val and pd.notna(val) and str(val).strip():
                    relatives = [r.strip() for r in str(val).split(',') if r.strip()]
                    for rel in relatives:
                        rel_node = name_to_master.get(rel.lower(), rel)
                        G.add_node(rel_node, label='Person')
                        G.add_edge(p_node, rel_node, relation=col.upper())
    return G, name_to_master

# --- REGISTRATION OF LIVE TOOLS ---

@registry.register(
    name="lookup_figure",
    description="Mencari dan menampilkan informasi detail properti simpul dan relasi silsilah langsung (neighborhood) dari seorang tokoh sejarah.",
    parameters={
        "name": {"type": "string", "required": True, "description": "Nama tokoh sejarah yang ingin dicari detailnya."}
    }
)
def lookup_figure(name):
    name_clean = name.strip()
    result_str = f"### [TOOL OUTPUT: lookup_figure untuk '{name_clean}']\n"
    
    csv_metrics = get_metrics_from_csv(name_clean, 'Person')
    
    if neo4j_conn.driver:
        prop_query = """
        MATCH (p:Person) WHERE toLower(p.name) = toLower($name)
        RETURN p.name as name, p.role as role, p.birthDate as birthDate, 
               p.deathDate as deathDate, p.wikidataID as wikidataID, p.dynasty as dynasty,
               p.pagerank_score as pagerank, p.louvain_cluster as louvain_cluster
        """
        prop_res = neo4j_conn.run_query(prop_query, {"name": name_clean})
        if prop_res:
            p_data = prop_res[0]
            pr = p_data.get("pagerank") or csv_metrics["pagerank"]
            cluster = p_data.get("louvain_cluster") if p_data.get("louvain_cluster") is not None else csv_metrics["louvain_cluster"]
            
            result_str += f"- Nama Tokoh: {p_data.get('name')}\n"
            result_str += f"- Peran: {p_data.get('role') or 'Tidak diketahui'}\n"
            result_str += f"- Dinasti: {p_data.get('dynasty') or 'Tidak diketahui'}\n"
            result_str += f"- Masa Hidup: Lahir: {p_data.get('birthDate') or 'Tidak diketahui'}, Wafat: {p_data.get('deathDate') or 'Tidak diketahui'}\n"
            result_str += f"- Metrik Jaringan: PageRank={pr:.6f}, ID Klaster Louvain={cluster}\n"
            result_str += f"- Wikidata ID: {p_data.get('wikidataID') or 'Tidak diketahui'}\n"
        else:
            result_str += "Tokoh tidak ditemukan di Neo4j. Mencari di CSV...\n"
            if df_metrics is not None:
                match = df_metrics[df_metrics['orang'].str.lower() == name_clean.lower()].fillna("")
                if not match.empty:
                    row = match.iloc[0]
                    result_str += f"- Nama Tokoh: {row.get('orang')}\n"
                    result_str += f"- Peran: {row.get('peran') or 'Tidak diketahui'}\n"
                    result_str += f"- Dinasti: {row.get('dinasti') or 'Tidak diketahui'}\n"
                    result_str += f"- Masa Hidup: Lahir: {row.get('tglLahir') or 'Tidak diketahui'}, Wafat: {row.get('tglMati') or 'Tidak diketahui'}\n"
                    result_str += f"- Metrik Jaringan: PageRank={csv_metrics['pagerank']:.6f}, ID Klaster Louvain={csv_metrics['louvain_cluster']}\n"
                else:
                    return f"Tokoh '{name_clean}' tidak ditemukan di database maupun file CSV."
            else:
                return f"Tokoh '{name_clean}' tidak ditemukan di database."
                
        # Query relationships
        rel_query = """
        MATCH (p:Person) WHERE toLower(p.name) = toLower($name)
        MATCH (p)-[r]-(neighbor)
        RETURN type(r) as relation, startNode(r) = p as is_outgoing, 
               neighbor.name as neighbor_name, labels(neighbor)[0] as neighbor_type
        LIMIT 15
        """
        rel_res = neo4j_conn.run_query(rel_query, {"name": name_clean})
        if rel_res:
            result_str += "- Hubungan langsung dalam Graf:\n"
            for rel in rel_res:
                rel_type = rel["relation"]
                is_out = rel["is_outgoing"]
                neighbor_name = rel["neighbor_name"]
                neighbor_type = rel["neighbor_type"]
                if rel_type == 'MEMIMPIN_ATAU_TERAFILIASI':
                    result_str += f"  * Terafiliasi dengan Kerajaan: {neighbor_name}\n"
                elif is_out:
                    result_str += f"  * Memiliki {rel_type} -> {neighbor_name} ({neighbor_type})\n"
                else:
                    result_str += f"  * Menjadi {rel_type} dari <- {neighbor_name} ({neighbor_type})\n"
        return result_str
    else:
        # Fallback CSV
        result_str += "[Database Offline - Menggunakan Fallback CSV]\n"
        if df_metrics is not None:
            match = df_metrics[df_metrics['orang'].str.lower() == name_clean.lower()].fillna("")
            if not match.empty:
                row = match.iloc[0]
                result_str += f"- Nama Tokoh: {row.get('orang')}\n"
                result_str += f"- Peran: {row.get('peran') or 'Tidak diketahui'}\n"
                result_str += f"- Dinasti: {row.get('dinasti') or 'Tidak diketahui'}\n"
                result_str += f"- Masa Hidup: Lahir: {row.get('tglLahir') or 'Tidak diketahui'}, Wafat: {row.get('tglMati') or 'Tidak diketahui'}\n"
                result_str += f"- Metrik Jaringan: PageRank={csv_metrics['pagerank']:.6f}, ID Klaster Louvain={csv_metrics['louvain_cluster']}\n"
                result_str += "- Hubungan Silsilah langsung:\n"
                for col in ['ayah', 'ibu', 'pasangan', 'anak', 'saudara', 'kerabat']:
                    val = row[col]
                    if val and str(val).strip():
                        result_str += f"  * {col.capitalize()}: {val}\n"
                return result_str
        return f"Tokoh '{name_clean}' tidak ditemukan di file CSV."

@registry.register(
    name="get_genealogy",
    description="Melakukan traversal BFS untuk melacak silsilah keturunan dan kerabat keluarga seorang tokoh sampai kedalaman tertentu.",
    parameters={
        "name": {"type": "string", "required": True, "description": "Nama tokoh sejarah awal."},
        "depth": {"type": "integer", "required": False, "description": "Kedalaman traversal BFS (default: 2)."}
    }
)
def get_genealogy(name, depth=2):
    name_clean = name.strip()
    try:
        depth = int(depth)
    except Exception:
        depth = 2
        
    result_str = f"### [TOOL OUTPUT: get_genealogy untuk '{name_clean}', kedalaman: {depth}]\n"
    
    # Run BFS on family graph
    visited = set()
    queue = [(name_clean, 0)]
    edges = []
    
    # Build Master mapping from CSV
    name_to_master = {}
    if df_metrics is not None:
        for _, row in df_metrics.iterrows():
            p = row['orang']
            m_id = row.get('master_id', p)
            if pd.notna(p):
                name_to_master[str(p).strip().lower()] = str(m_id).strip()
                
    master_name = name_to_master.get(name_clean.lower(), name_clean)
    queue = [(master_name, 0)]
    
    while queue:
        curr, curr_depth = queue.pop(0)
        if curr_depth >= depth:
            continue
        if curr.lower() in visited:
            continue
        visited.add(curr.lower())
        
        relatives = []
        if neo4j_conn.driver:
            query = """
            MATCH (p:Person) WHERE toLower(p.name) = toLower($name)
            MATCH (p)-[r:AYAH|IBU|PASANGAN|ANAK|SAUDARA|KERABAT]-(relative:Person)
            RETURN type(r) as relation, relative.name as relative_name, startNode(r) = p as is_outgoing
            """
            res = neo4j_conn.run_query(query, {"name": curr})
            for row in res:
                rel_master = name_to_master.get(row["relative_name"].lower(), row["relative_name"])
                relatives.append((rel_master, row["relation"], row["is_outgoing"]))
        else:
            if df_metrics is not None:
                match = df_metrics[df_metrics['orang'].str.lower() == curr.lower()]
                for _, row in match.iterrows():
                    for col in ['ayah', 'ibu', 'pasangan', 'anak', 'saudara', 'kerabat']:
                        val = row[col]
                        if val and pd.notna(val) and str(val).strip():
                            names = [n.strip() for n in str(val).split(',') if n.strip()]
                            for n in names:
                                m_n = name_to_master.get(n.lower(), n)
                                relatives.append((m_n, col.upper(), True))
                                
        for rel_name, rel_type, is_out in relatives:
            edges.append({"source": curr, "relation": rel_type, "target": rel_name, "is_outgoing": is_out})
            if rel_name.lower() not in visited:
                queue.append((rel_name, curr_depth + 1))
                
    if not edges:
        return f"Tidak ditemukan relasi silsilah untuk tokoh '{name_clean}'."
        
    for edge in edges:
        if edge["is_outgoing"]:
            result_str += f"- {edge['source']} --[:{edge['relation']}]--> {edge['target']}\n"
        else:
            result_str += f"- {edge['target']} --[:{edge['relation']}]--> {edge['source']}\n"
            
    return result_str

@registry.register(
    name="find_connection_path",
    description="Mencari dan menampilkan jalur hubungan silsilah terpendek (shortest path) antara dua tokoh sejarah.",
    parameters={
        "a": {"type": "string", "required": True, "description": "Nama tokoh pertama."},
        "b": {"type": "string", "required": True, "description": "Nama tokoh kedua."}
    }
)
def find_connection_path(a, b):
    a_clean = a.strip()
    b_clean = b.strip()
    result_str = f"### [TOOL OUTPUT: find_connection_path antara '{a_clean}' dan '{b_clean}']\n"
    
    if neo4j_conn.driver:
        shortest_path_query = """
        MATCH (n1 {name: $a}), (n2 {name: $b})
        MATCH path = shortestPath((n1)-[*..5]-(n2))
        RETURN [node in nodes(path) | node.name] as node_names, 
               [node in nodes(path) | labels(node)[0]] as node_labels,
               [rel in relationships(path) | type(rel)] as rel_types
        """
        path_res = neo4j_conn.run_query(shortest_path_query, {"a": a_clean, "b": b_clean})
        if path_res and path_res[0]["node_names"]:
            p_info = path_res[0]
            path_str = ""
            for i in range(len(p_info["node_names"])):
                name = p_info["node_names"][i]
                label = p_info["node_labels"][i]
                path_str += f"{name} ({label})"
                if i < len(p_info["rel_types"]):
                    rel = p_info["rel_types"][i]
                    path_str += f" --[:{rel}]--> "
            result_str += f"- Path: {path_str}\n"
            return result_str
            
    # Fallback NetworkX
    result_str += "[Menggunakan fallback NetworkX dari CSV]\n"
    G, name_to_master = build_nx_graph()
    
    a_resolved = name_to_master.get(a_clean.lower(), a_clean)
    b_resolved = name_to_master.get(b_clean.lower(), b_clean)
    
    if not G.has_node(a_resolved):
        return f"Tokoh '{a_clean}' tidak ditemukan di graf."
    if not G.has_node(b_resolved):
        return f"Tokoh '{b_clean}' tidak ditemukan di graf."
        
    try:
        path = nx.shortest_path(G, source=a_resolved, target=b_resolved)
        path_str = ""
        for i in range(len(path)):
            node = path[i]
            label = G.nodes[node].get('label', 'Person')
            path_str += f"{node} ({label})"
            if i < len(path) - 1:
                edge_data = G.get_edge_data(path[i], path[i+1])
                rel_type = edge_data.get('relation', 'RELATION')
                path_str += f" --[:{rel_type}]--> "
        result_str += f"- Path: {path_str}\n"
        return result_str
    except Exception:
        return f"Tidak ditemukan hubungan/jalur silsilah terpendek antara '{a_clean}' dan '{b_clean}'."

@registry.register(
    name="get_influential",
    description="Menampilkan tokoh-tokoh paling berpengaruh (berdasarkan skor PageRank tertinggi) di kerajaan tertentu.",
    parameters={
        "kingdom": {"type": "string", "required": True, "description": "Nama kerajaan/kesultanan."}
    }
)
def get_influential(kingdom):
    k_clean = kingdom.strip()
    result_str = f"### [TOOL OUTPUT: get_influential untuk '{k_clean}']\n"
    
    if neo4j_conn.driver:
        query = """
        MATCH (p:Person)-[:MEMIMPIN_ATAU_TERAFILIASI]->(k:Kingdom)
        WHERE toLower(k.name) CONTAINS toLower($kingdom) OR toLower(p.dynasty) CONTAINS toLower($kingdom)
        RETURN p.name as name, p.role as role, p.pagerank_score as pagerank
        ORDER BY p.pagerank_score DESC LIMIT 10
        """
        res = neo4j_conn.run_query(query, {"kingdom": k_clean})
        if res:
            for idx, row in enumerate(res, 1):
                role_str = f" ({row['role']})" if row['role'] else ""
                pr = row['pagerank'] or 0.0
                result_str += f"{idx}. {row['name']}{role_str} - PageRank: {pr:.6f}\n"
            return result_str
            
    # Fallback CSV
    result_str += "[Menggunakan fallback CSV]\n"
    if df_metrics is not None:
        match_k = df_metrics[(df_metrics['kerajaan'].str.lower().str.contains(k_clean.lower(), na=False)) | 
                             (df_metrics['namaKerajaan'].str.lower().str.contains(k_clean.lower(), na=False)) |
                             (df_metrics['dinasti'].str.lower().str.contains(k_clean.lower(), na=False))]
        if not match_k.empty:
            top_p = match_k[['orang', 'peran', 'orang_PageRank']].dropna().drop_duplicates(subset=['orang'])
            top_p = top_p.sort_values(by='orang_PageRank', ascending=False).head(10)
            for idx, (_, r) in enumerate(top_p.iterrows(), 1):
                role_str = f" ({r['peran']})" if r['peran'] else ""
                result_str += f"{idx}. {r['orang']}{role_str} - PageRank: {r['orang_PageRank']:.6f}\n"
            return result_str
    return f"Kerajaan '{k_clean}' tidak ditemukan atau tidak memiliki data tokoh."

@registry.register(
    name="get_community",
    description="Menampilkan daftar tokoh yang berada dalam kelompok komunitas/dinasti yang sama (berdasarkan ID Klaster Louvain).",
    parameters={
        "cluster_id": {"type": "integer", "required": True, "description": "ID Klaster Louvain (misal: 0, 1, 2, dst)."}
    }
)
def get_community(cluster_id):
    try:
        c_id = int(cluster_id)
    except Exception:
        return "ID Klaster Louvain harus berupa angka integer."
        
    result_str = f"### [TOOL OUTPUT: get_community untuk klaster: {c_id}]\n"
    
    if neo4j_conn.driver:
        query = """
        MATCH (p:Person)
        WHERE p.louvain_cluster = $cluster_id
        RETURN p.name as name, p.role as role, p.pagerank_score as pagerank
        ORDER BY p.pagerank_score DESC LIMIT 20
        """
        res = neo4j_conn.run_query(query, {"cluster_id": c_id})
        if res:
            for idx, row in enumerate(res, 1):
                role_str = f" ({row['role']})" if row['role'] else ""
                pr = row['pagerank'] or 0.0
                result_str += f"{idx}. {row['name']}{role_str} - PageRank: {pr:.6f}\n"
            return result_str
            
    # Fallback CSV
    result_str += "[Menggunakan fallback CSV]\n"
    if df_metrics is not None:
        match_c = df_metrics[df_metrics['orang_Louvain_Cluster'] == c_id]
        if not match_c.empty:
            top_p = match_c[['orang', 'peran', 'orang_PageRank']].dropna().drop_duplicates(subset=['orang'])
            top_p = top_p.sort_values(by='orang_PageRank', ascending=False).head(20)
            for idx, (_, r) in enumerate(top_p.iterrows(), 1):
                role_str = f" ({r['peran']})" if r['peran'] else ""
                result_str += f"{idx}. {r['orang']}{role_str} - PageRank: {r['orang_PageRank']:.6f}\n"
            return result_str
    return f"Komunitas dengan ID Klaster {c_id} tidak ditemukan."

@registry.register(
    name="find_similar",
    description="Menemukan tokoh-tokoh paling mirip/memiliki kedekatan silsilah terdekat menggunakan perhitungan Adamic-Adar live.",
    parameters={
        "name": {"type": "string", "required": True, "description": "Nama tokoh sejarah awal."},
        "n": {"type": "integer", "required": False, "description": "Jumlah rekomendasi tokoh mirip (default: 5)."}
    }
)
def find_similar(name, n=5):
    name_clean = name.strip()
    try:
        n = int(n)
    except Exception:
        n = 5
        
    result_str = f"### [TOOL OUTPUT: find_similar untuk '{name_clean}', limit: {n}]\n"
    
    # Compute live Adamic-Adar from df_metrics family graph
    G_family, name_to_master = build_nx_graph()
    
    # Filter nodes that are strictly figures
    master_name = name_to_master.get(name_clean.lower(), name_clean)
    if not G_family.has_node(master_name):
        return f"Tokoh '{name_clean}' tidak ditemukan di graf silsilah."
        
    other_nodes = [node for node in G_family.nodes() if node != master_name]
    # Filter out kingdom nodes from G_family to compute only figure similarities
    figure_nodes = []
    for node in other_nodes:
        # Check if node is in master mapping keys/values or just labeled Person
        node_lbl = G_family.nodes[node].get('label', 'Person')
        if node_lbl == 'Person':
            figure_nodes.append(node)
            
    pairs = [(master_name, other) for other in figure_nodes]
    
    try:
        aa_results = list(nx.adamic_adar_index(G_family, pairs))
        aa_results = [r for r in aa_results if r[2] > 0]
        aa_sorted = sorted(aa_results, key=lambda x: x[2], reverse=True)
        
        if not aa_sorted:
            return f"Tidak ditemukan tokoh yang berbagi koneksi silsilah (Adamic-Adar > 0) dengan '{name_clean}'."
            
        for idx, (source, target, score) in enumerate(aa_sorted[:n], 1):
            result_str += f"{idx}. {target} - Skor Kedekatan Adamic-Adar: {score:.4f}\n"
        return result_str
    except Exception as e:
        return f"Error saat menghitung Adamic-Adar index: {e}"

>>>>>>> 2b02bc9d4e24fb81b73f5273c787416e1ba43aee

# --- CLEAN PROMPT PAYLOAD AND SANITIZE CONTROL CHARS ---
def clean_prompt_payload(text):
    if not text:
        return ""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    cleaned_chars = []
    for char in text:
        codepoint = ord(char)
        if codepoint in (9, 10) or (32 <= codepoint <= 126) or (codepoint >= 160):
            cleaned_chars.append(char)
    return "".join(cleaned_chars)

# --- GENERIC OPENROUTER CLIENT WITH MODEL FALLBACKS ---
<<<<<<< HEAD
def query_openrouter_raw(system_prompt=None, user_prompt=None, messages=None, tools=None):
=======
def query_openrouter_raw(system_prompt, user_prompt, temperature=0.3, response_format=None):
>>>>>>> 2b02bc9d4e24fb81b73f5273c787416e1ba43aee
    if not OPENROUTER_API_KEY:
        return {} if (messages is not None or tools is not None) else ""
        
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/eas-graf/eas-graf",
        "X-Title": "Nusantara Dynasty GraphRAG Chatbot"
    }
    
<<<<<<< HEAD
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
=======
    system_prompt = clean_prompt_payload(system_prompt)
    user_prompt = clean_prompt_payload(user_prompt)
    
>>>>>>> 2b02bc9d4e24fb81b73f5273c787416e1ba43aee
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
<<<<<<< HEAD
            "messages": messages,
            "max_tokens": max_tok,
            "temperature": temp
        }
        if tools is not None:
            payload["tools"] = tools
=======
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 1200,
            "temperature": temperature
        }
        if response_format:
            payload["response_format"] = response_format
>>>>>>> 2b02bc9d4e24fb81b73f5273c787416e1ba43aee
            
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

<<<<<<< HEAD

=======
# --- HEURISTIC TOOL ROUTER FALLBACK ---
def heuristic_tool_router(query_text):
    query_lower = query_text.lower()
    people, kingdoms = extract_entities(query_text)
    
    # 1. Shortest Path
    if any(kw in query_lower for kw in ["hubungan", "jalur", "path", "koneksi", "terhubung", "rute"]):
        if len(people) >= 2:
            return {"tool": "find_connection_path", "parameters": {"a": people[0], "b": people[1]}}
            
    # 2. Similarity
    if any(kw in query_lower for kw in ["mirip", "kemiripan", "adamic", "adar", "similar", "dekat"]):
        if people:
            return {"tool": "find_similar", "parameters": {"name": people[0]}}
            
    # 3. Genealogy / BFS
    if any(kw in query_lower for kw in ["silsilah", "keturunan", "bfs", "traversal", "silsilahnya"]):
        if people:
            return {"tool": "get_genealogy", "parameters": {"name": people[0], "depth": 2}}
            
    # 4. Influential
    if any(kw in query_lower for kw in ["berpengaruh", "pagerank", "terkuat", "tertinggi", "terbesar", "dominan"]):
        k = kingdoms[0] if kingdoms else (people[0] if people else "Majapahit")
        return {"tool": "get_influential", "parameters": {"kingdom": k}}
        
    # 5. Community
    if any(kw in query_lower for kw in ["klaster", "komunitas", "louvain", "cluster"]):
        nums = re.findall(r'\d+', query_text)
        cluster_id = int(nums[0]) if nums else 0
        return {"tool": "get_community", "parameters": {"cluster_id": cluster_id}}
        
    # 6. Lookup Figure
    if people:
        return {"tool": "lookup_figure", "parameters": {"name": people[0]}}
        
    return {"direct_response": "Saya tidak menemukan entitas tokoh atau kerajaan spesifik dari pertanyaan Anda. Ada yang bisa saya bantu terkait silsilah dinasti Nusantara?"}

# --- MCP AGENTIC ROUTER ---
def determine_tool_call(query_text):
    if not OPENROUTER_API_KEY:
        return heuristic_tool_router(query_text)
        
    system_prompt = (
        "You are the Router Agent for Nusantara Dynasty Knowledge Graph.\n"
        "Your task is to analyze the user's natural language input and decide which tool from the registry is best to retrieve context "
        "to answer the user's question.\n\n"
        f"{registry.get_tool_descriptions()}\n\n"
        "Instructions:\n"
        "1. You must respond ONLY with a valid JSON object matching one of the schemas below. Do NOT wrap it in markdown fences (do not use ```json ... ```).\n"
        "2. If you choose a tool, return exactly:\n"
        "{\n"
        "  \"tool\": \"tool_name\",\n"
        "  \"parameters\": {\"param_name\": \"value\"}\n"
        "}\n\n"
        "3. If no tool is needed (e.g. greetings, simple chit-chat, general questions that don't need historical lookup), return exactly:\n"
        "{\n"
        "  \"direct_response\": \"Your direct greeting or response\"\n"
        "}\n"
        "4. Be accurate with name parameters. Match names exactly as in the user query."
    )
    
    content_raw = query_openrouter_raw(
        system_prompt=system_prompt,
        user_prompt=f"User query: {query_text}",
        temperature=0.0,
        response_format={"type": "json_object"}
    )
    
    if not content_raw:
        return heuristic_tool_router(query_text)
        
    try:
        content_clean = content_raw.strip()
        content_clean = re.sub(r'^```json\s*|^```\s*|```$', '', content_clean, flags=re.MULTILINE).strip()
        parsed = json.loads(content_clean)
        if "tool" in parsed or "direct_response" in parsed:
            return parsed
    except Exception as e:
        print(f"[ROUTER ERROR] Failed parsing router JSON: {e}. Falling back to heuristic router.")
        
    return heuristic_tool_router(query_text)
>>>>>>> 2b02bc9d4e24fb81b73f5273c787416e1ba43aee

# --- OPENROUTER LLM CLIENT FOR FINAL ANSWER SYNTHESIS ---
def query_openrouter_llm(query, context):
    """Sends prompt with retrieved context to OpenRouter LLM, implementing fallbacks."""
    system_prompt = (
        "Anda adalah Nusantara Dynasty Knowledge Graph Bot, asisten cerdas berkeahlian ganda sebagai "
        "Senior Historian Sejarah Nusantara dan Senior Data Scientist. Tugas Anda adalah membantu "
        "pengguna memahami relasi silsilah dinasti kerajaan prekolonial di Indonesia menggunakan "
        "data terstruktur dari Neo4j Graph Database dan metrik analisis graf (NetworkX) yang dikumpulkan lewat Tool Registry.\n\n"
        "Aturan Penulisan Jawaban:\n"
        "1. Jawab dalam bahasa Indonesia yang mengalir, jelas, natural, dan sangat profesional.\n"
        "2. Manfaatkan informasi dalam KONTEKS / OUTPUT TOOL yang disediakan untuk memperkuat kredibilitas jawaban Anda.\n"
        "3. PageRank menunjukkan tingkat pengaruh tokoh/kerajaan dalam jaringan. Klaster Louvain mengelompokkan tokoh ke dalam komunitas silsilah secara modular.\n"
        "4. Skor Adamic-Adar yang tinggi antara dua tokoh menunjukkan kedekatan hubungan kekeluargaan riil mereka berdasarkan irisan relasi keluarga.\n"
        "5. Tuliskan jawaban secara komprehensif, terstruktur, dan informatif."
    )
    
    user_prompt = f"PERTANYAAN PENGGUNA:\n{query}\n\nKONTEKS / OUTPUT DARI TOOL REGISTRY:\n"
    if context.strip():
        if len(context) > 6000:
            context = context[:6000] + "\n\n[... Konteks dipotong karena batas kapasitas payload ...]"
        user_prompt += context
    else:
        user_prompt += "(Konteks kosong - tidak ada data yang ditemukan lewat tool registry.)"
        
    res = query_openrouter_raw(system_prompt, user_prompt)
    if not res:
        return "[Error: Semua model OpenRouter gagal memberikan respons. Silakan periksa koneksi internet Anda atau status limit API Key Anda.]"
    return res

# --- MAIN TERMINAL CHATBOT LOOP (CLI) ---
def main():
    print("========================================================================")
    print("      NUSANTARA DYNASTY KNOWLEDGE GRAPH - AGENTIC MCP GRAPHRAG BOT      ")
    print("========================================================================")
    print("Selamat datang di CLI Chatbot Agentic Graf Dinasti Nusantara!")
    print("Bot ini ditenagai Agentic AI Tool Registry berbasis Model Context Protocol (MCP).")
    print("------------------------------------------------------------------------")
    print(f"Database URI: {NEO4J_URI}")
    if neo4j_conn.driver:
        print("Status Database: TERHUBUNG (Koneksi Neo4j Aktif)")
    else:
        print("Status Database: OFFLINE (Menggunakan fallback CSV & NetworkX)")
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
                
            print("Bot: (Menganalisis pertanyaan dan merencanakan eksekusi...)")
            routing_decision = determine_tool_call(query)
            
<<<<<<< HEAD
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
=======
            tool_output = ""
            if "tool" in routing_decision:
                tool_name = routing_decision["tool"]
                params = routing_decision.get("parameters", {})
                print(f"-> [Agent Call Tool] Mengaktifkan Live Tool: '{tool_name}' dengan parameter {params}")
                
                # Execute tool
                print("Bot: (Mengeksekusi kueri live pada registry...)")
                tool_output = registry.execute(tool_name, **params)
            else:
                tool_output = routing_decision.get("direct_response", "")
                print("-> [Agent Call Tool] Tidak memerlukan live query (menjawab langsung)")
                
            # Synthesize final answer
            print("Bot: (Mensintesis jawaban akhir dengan AI...)")
            answer = query_openrouter_llm(query, tool_output)
>>>>>>> 2b02bc9d4e24fb81b73f5273c787416e1ba43aee
            
            print("\n------------------------------ JAWABAN BOT ------------------------------")
            print(answer)
            print("-------------------------------------------------------------------------\n")
            
        except KeyboardInterrupt:
            print("\nSesi chat dihentikan oleh pengguna. Sampai jumpa!")
            break
        except Exception as e:
            print(f"\n[ERROR] Terjadi kesalahan dalam loop chat: {e}\n")
            
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
