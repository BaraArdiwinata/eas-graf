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

# Load environment variables
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Load local CSV metrics for fallback
METRICS_CSV = "dataset_dinasti_final_with_metrics.csv"
ALT_CSV = "dataset_dinasti_final.csv"

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

# --- ENTITY EXTRACTION ENGINE ---
def extract_entities(query_text):
    """
    Extracts known historical figure names or kingdoms from the query text.
    Uses exact word/phrase boundary matching to avoid sub-string collisions and false positive title matches.
    """
    sorted_people = sorted(list(people_set), key=len, reverse=True)
    sorted_kingdoms = sorted(list(kingdoms_set), key=len, reverse=True)
    
    # Normalize query text to avoid case and punctuation issues
    query_normalized = f" {query_text.lower()} "
    query_normalized = re.sub(r'[^\w\s]', ' ', query_normalized)
    query_normalized = re.sub(r'\s+', ' ', query_normalized)
    
    matched_people = []
    matched_kingdoms = []
    
    # Track character index spans already matched to avoid double-matching
    matched_spans = []
    
    # 1. Exact Dictionary Match with Word Boundaries
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
            # Check overlap
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
                
    # 2. Fallback Stricter Word boundary partial match (only if no exact matches found)
    if not matched_people and not matched_kingdoms:
        # Common stop words in Indonesian
        stop_words = {
            "siapa", "dan", "dari", "di", "adalah", "yang", "pada", "tentang", "bagaimana", 
            "apakah", "berapa", "ayah", "ibu", "anak", "istri", "suami", "pasangan", 
            "saudara", "kerabat", "raja", "sultan", "ratu", "patih", "pendahulu", "penerus",
            "silsilah", "hubungan", "kerajaan", "kesultanan", "dinasti", "silsilahnya"
        }
        # Common honorific titles in Indonesian history to ignore for partial matching
        titles_to_ignore = {
            "raden", "sri", "sultan", "dewa", "agung", "raja", "mpu", "patih", "sang", 
            "baginda", "dyah", "ratu", "mas", "gusti", "susuhunan", "panembahan", "prabu",
            "kanjeng", "haryo", "wuryaningrat", "karaeng", "daeng", "datu", "alauddin", 
            "syarif", "sayyid", "sunan"
        }
        
        query_words = re.findall(r'\b\w+\b', query_text.lower())
        query_words = [w for w in query_words if w not in stop_words and w not in titles_to_ignore and len(w) >= 3]
        
        # Word-by-word search against known entity sets
        for word in query_words:
            # Check people
            for person in sorted_people:
                person_lower = person.lower()
                person_words = re.findall(r'\b\w+\b', person_lower)
                if word in person_words:
                    matched_people.append(person)
                    break
            if matched_people:
                break
                
            # Check kingdoms
            for kingdom in sorted_kingdoms:
                kingdom_lower = kingdom.lower()
                kingdom_words = re.findall(r'\b\w+\b', kingdom_lower)
                if word in kingdom_words:
                    matched_kingdoms.append(kingdom)
                    break
            if matched_kingdoms:
                break
                
    return matched_people, matched_kingdoms

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
def retrieve_graph_context(people, kingdoms):
    """
    Queries Neo4j to retrieve neighborhood subgraphs, node attributes, and paths.
    Converts graph structured relationships and metadata into structured markdown text context.
    """
    context = ""
    
    if not neo4j_conn.driver:
        # Fallback to pure CSV lookup if database is offline
        context += "### [WARNING: DATABASE NEO4J OFFLINE - MENGGUNAKAN FALLBACK DATASET CSV]\n"
        if df_metrics is not None:
            for p in people:
                match = df_metrics[df_metrics['orang'].str.lower() == p.lower()].fillna("")
                if not match.empty:
                    row = match.iloc[0]
                    metrics = get_metrics_from_csv(p, 'Person')
                    context += f"**Tokoh (Person): {p}**\n"
                    context += f"- Peran: {row.get('peran', 'Tidak diketahui')}\n"
                    context += f"- Dinasti: {row.get('dinasti', 'Tidak diketahui')}\n"
                    context += f"- Tanggal Lahir: {row.get('tglLahir', 'Tidak diketahui')}, Wafat: {row.get('tglMati', 'Tidak diketahui')}\n"
                    context += f"- PageRank: {metrics['pagerank']:.6f}, Klaster Louvain: {metrics['louvain_cluster']}\n"
                    context += f"- Silsilah: Ayah: {row.get('ayah')}, Ibu: {row.get('ibu')}, Pasangan: {row.get('pasangan')}, Anak: {row.get('anak')}, Saudara: {row.get('saudara')}, Kerabat: {row.get('kerabat')}\n\n"
            for k in kingdoms:
                match = df_metrics[df_metrics['kerajaan'].str.lower() == k.lower()].fillna("")
                if not match.empty:
                    row = match.iloc[0]
                    metrics = get_metrics_from_csv(k, 'Kingdom')
                    context += f"**Kerajaan (Kingdom): {k}**\n"
                    context += f"- Ibu Kota: {row.get('ibuKota', 'Tidak diketahui')}\n"
                    context += f"- Agama: {row.get('agama', 'Tidak diketahui')}\n"
                    context += f"- Tahun Mulai: {row.get('tahunMulai', 'Tidak diketahui')}\n"
                    context += f"- PageRank: {metrics['pagerank']:.6f}, Klaster Louvain: {metrics['louvain_cluster']}\n\n"
        return context

    # --- Retrieve Shortest Path if two or more people are found ---
    if len(people) >= 2:
        name1 = people[0]
        name2 = people[1]
        shortest_path_query = """
        MATCH (n1 {name: $name1}), (n2 {name: $name2})
        MATCH path = shortestPath((n1)-[*..5]-(n2))
        RETURN [node in nodes(path) | node.name] as node_names, 
               [node in nodes(path) | labels(node)[0]] as node_labels,
               [rel in relationships(path) | type(rel)] as rel_types
        """
        path_res = neo4j_conn.run_query(shortest_path_query, {"name1": name1, "name2": name2})
        if path_res and path_res[0]["node_names"]:
            p_info = path_res[0]
            context += "### [JALUR HUBUNGAN GRAF (SHORTEST PATH)]\n"
            context += "Ditemukan hubungan terpendek dalam graf:\n"
            path_str = ""
            for i in range(len(p_info["node_names"])):
                name = p_info["node_names"][i]
                label = p_info["node_labels"][i]
                path_str += f"{name} ({label})"
                if i < len(p_info["rel_types"]):
                    rel = p_info["rel_types"][i]
                    path_str += f" --[:{rel}]--> "
            context += f"- **Path**: {path_str}\n\n"

    # --- Retrieve Info for Each Matched Person ---
    for person in people:
        # Query node properties
        prop_query = """
        MATCH (p:Person {name: $name})
        RETURN p.name as name, p.role as role, p.birthDate as birthDate, 
               p.deathDate as deathDate, p.wikidataID as wikidataID, p.dynasty as dynasty,
               p.pagerank_score as pagerank, p.louvain_cluster as louvain_cluster
        """
        prop_res = neo4j_conn.run_query(prop_query, {"name": person})
        
        # Get metrics from CSV (or Neo4j if loaded there)
        csv_metrics = get_metrics_from_csv(person, 'Person')
        
        if prop_res:
            p_data = prop_res[0]
            pr = p_data.get("pagerank") or csv_metrics["pagerank"]
            cluster = p_data.get("louvain_cluster") if p_data.get("louvain_cluster") is not None else csv_metrics["louvain_cluster"]
            
            context += f"### [TOKOH: {person}]\n"
            context += f"- **Peran**: {p_data.get('role') or 'Tidak diketahui'}\n"
            context += f"- **Dinasti**: {p_data.get('dynasty') or 'Tidak diketahui'}\n"
            context += f"- **Masa Hidup**: Lahir: {p_data.get('birthDate') or 'Tidak diketahui'}, Wafat: {p_data.get('deathDate') or 'Tidak diketahui'}\n"
            context += f"- **Metrik Jaringan**: PageRank={pr:.6f}, ID Klaster Louvain={cluster}\n"
            context += f"- **Wikidata ID**: {p_data.get('wikidataID') or 'Tidak diketahui'}\n"
        else:
            # Fallback to CSV properties if node not found but extracted
            context += f"### [TOKOH: {person} (Hanya ada di CSV)]\n"
            if df_metrics is not None:
                match = df_metrics[df_metrics['orang'].str.lower() == person.lower()].fillna("")
                if not match.empty:
                    row = match.iloc[0]
                    context += f"- **Peran**: {row.get('peran') or 'Tidak diketahui'}\n"
                    context += f"- **Dinasti**: {row.get('dinasti') or 'Tidak diketahui'}\n"
                    context += f"- **Masa Hidup**: Lahir: {row.get('tglLahir') or 'Tidak diketahui'}, Wafat: {row.get('tglMati') or 'Tidak diketahui'}\n"
                    context += f"- **Metrik Jaringan**: PageRank={csv_metrics['pagerank']:.6f}, ID Klaster Louvain={csv_metrics['louvain_cluster']}\n"
        
        # Query relationships
        rel_query = """
        MATCH (p:Person {name: $name})-[r]-(neighbor)
        RETURN type(r) as relation, startNode(r) = p as is_outgoing, 
               neighbor.name as neighbor_name, labels(neighbor)[0] as neighbor_type
        """
        rel_res = neo4j_conn.run_query(rel_query, {"name": person})
        if rel_res:
            context += "- **Hubungan Graf (Neighborhood)**:\n"
            for rel in rel_res:
                rel_type = rel["relation"]
                is_out = rel["is_outgoing"]
                neighbor_name = rel["neighbor_name"]
                neighbor_type = rel["neighbor_type"]
                
                if rel_type == 'MEMIMPIN_ATAU_TERAFILIASI':
                    context += f"  * Terafiliasi dengan Kerajaan: {neighbor_name}\n"
                elif is_out:
                    context += f"  * Memiliki {rel_type} -> {neighbor_name} ({neighbor_type})\n"
                else:
                    context += f"  * Menjadi {rel_type} dari <- {neighbor_name} ({neighbor_type})\n"
        context += "\n"

    # --- Retrieve Info for Each Matched Kingdom ---
    for kingdom in kingdoms:
        # Query node properties
        prop_query = """
        MATCH (k:Kingdom {name: $name})
        RETURN k.name as name, k.capital as capital, k.religion as religion, 
               k.yearStart as yearStart, k.wikidataID as wikidataID,
               k.pagerank_score as pagerank, k.louvain_cluster as louvain_cluster
        """
        prop_res = neo4j_conn.run_query(prop_query, {"name": kingdom})
        csv_metrics = get_metrics_from_csv(kingdom, 'Kingdom')
        
        if prop_res:
            k_data = prop_res[0]
            pr = k_data.get("pagerank") or csv_metrics["pagerank"]
            cluster = k_data.get("louvain_cluster") if k_data.get("louvain_cluster") is not None else csv_metrics["louvain_cluster"]
            
            context += f"### [KERAJAAN: {kingdom}]\n"
            context += f"- **Ibu Kota**: {k_data.get('capital') or 'Tidak diketahui'}\n"
            context += f"- **Agama Dominan**: {k_data.get('religion') or 'Tidak diketahui'}\n"
            context += f"- **Tahun Berdiri (Perkiraan)**: {k_data.get('yearStart') or 'Tidak diketahui'}\n"
            context += f"- **Metrik Jaringan**: PageRank={pr:.6f}, ID Klaster Louvain={cluster}\n"
            context += f"- **Wikidata ID**: {k_data.get('wikidataID') or 'Tidak diketahui'}\n"
        else:
            context += f"### [KERAJAAN: {kingdom} (Hanya ada di CSV)]\n"
            if df_metrics is not None:
                match = df_metrics[df_metrics['kerajaan'].str.lower() == kingdom.lower()].fillna("")
                if not match.empty:
                    row = match.iloc[0]
                    context += f"- **Ibu Kota**: {row.get('ibuKota') or 'Tidak diketahui'}\n"
                    context += f"- **Agama Dominan**: {row.get('agama') or 'Tidak diketahui'}\n"
                    context += f"- **Tahun Berdiri**: {row.get('tahunMulai') or 'Tidak diketahui'}\n"
                    context += f"- **Metrik Jaringan**: PageRank={csv_metrics['pagerank']:.6f}, ID Klaster Louvain={csv_metrics['louvain_cluster']}\n"
                    
        # Query affiliated members
        member_query = """
        MATCH (p:Person)-[:MEMIMPIN_ATAU_TERAFILIASI]->(k:Kingdom {name: $name})
        RETURN p.name as name, p.role as role
        """
        member_res = neo4j_conn.run_query(member_query, {"name": kingdom})
        if member_res:
            context += "- **Tokoh yang Terafiliasi/Memimpin**:\n"
            for mem in member_res[:10]: # Limit to 10 prominent figures
                role_str = f" ({mem['role']})" if mem['role'] else ""
                context += f"  * {mem['name']}{role_str}\n"
            if len(member_res) > 10:
                context += f"  * ... dan {len(member_res) - 10} tokoh lainnya.\n"
        context += "\n"
        
    return context

# --- OPENROUTER LLM CLIENT ---
def query_openrouter_llm(query, context):
    """Sends prompt with retrieved context to OpenRouter LLM, implementing fallbacks."""
    if not OPENROUTER_API_KEY:
        return "[Error: API Key OpenRouter tidak ditemukan di berkas .env. Harap masukkan OPENROUTER_API_KEY Anda.]"
        
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/eas-graf/eas-graf",
        "X-Title": "Nusantara Dynasty GraphRAG Chatbot"
    }
    
    def sanitize_json_string(text):
        if not text:
            return ""
        # Standardize newlines to \n
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        # Filter out illegal control characters (ASCII 0-31 except \n and \t)
        text = "".join(ch for ch in text if ch >= ' ' or ch in ('\n', '\t'))
        return text

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
        user_prompt += context
    else:
        user_prompt += "(Konteks kosong - tidak ada kecocokan tokoh/kerajaan langsung di database graf.)"
        
    # Sanitize prompts to avoid invalid control characters in the JSON payload
    system_prompt = sanitize_json_string(system_prompt)
    user_prompt = sanitize_json_string(user_prompt)

    # Model fallbacks hierarchy
    models = [
        "google/gemini-1.5-flash:free",
        "google/gemini-2.5-flash",
        "meta-llama/llama-3.3-70b-instruct:free",
        "openrouter/free"
    ]
    
    for model in models:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 1200,
            "temperature": 0.3
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=45)
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"].strip()
            else:
                # If rate-limit or credit error, try fallback models
                print(f"[LLM LOG] Model '{model}' gagal dengan status kode {response.status_code}. Mencoba model alternatif...")
        except Exception as e:
            print(f"[LLM LOG] Error saat menghubungi model '{model}': {e}")
            
    return "[Error: Semua model OpenRouter gagal memberikan respons. Silakan periksa koneksi internet Anda atau status limit API Key Anda.]"

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
                
            print("Bot: (Sedang menganalisis pertanyaan & mengekstrak entitas...)")
            people, kingdoms = extract_entities(query)
            
            # Print extraction summary for debug/transparency
            if people or kingdoms:
                extracted_str = []
                if people:
                    extracted_str.append(f"Tokoh: {', '.join(people)}")
                if kingdoms:
                    extracted_str.append(f"Kerajaan: {', '.join(kingdoms)}")
                print(f"-> [Entity Matched] {', '.join(extracted_str)}")
            else:
                print("-> [Entity Matched] Tidak ada entitas spesifik terdeteksi (menggunakan modus pencarian umum)")
                
            print("Bot: (Menarik data dari Knowledge Graph...)")
            context = retrieve_graph_context(people, kingdoms)
            
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

if __name__ == "__main__":
    main()
