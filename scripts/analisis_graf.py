import os
import sys
import pandas as pd
import networkx as nx
import networkx.algorithms.community as nx_comm

# Reconfigure stdout to UTF-8 to handle special Javanese/Balinese names in console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def main():
    print("=== STARTING NUSANTARA DYNASTY GRAPH ANALYSIS ===")
    
    # 1. LOAD DATA
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_file = os.path.join(script_dir, "../data/dataset_dinasti_final.csv")
    if not os.path.exists(csv_file):
        print(f"Error: {csv_file} not found! Please run the pipeline script first.")
        sys.exit(1)
        
    df = pd.read_csv(csv_file, sep=';')
    print(f"Loaded {len(df)} rows from {csv_file}.")

    # 2. COMPILE KNOWN KINGDOMS AND TERMS FOR ACCURATE TYPE CLASSIFICATION
    known_kingdoms = set()
    for _, row in df.iterrows():
        k = row['kerajaan']
        nk = row['namaKerajaan']
        if k and not pd.isna(k) and str(k).strip():
            known_kingdoms.add(str(k).strip().lower())
        if nk and not pd.isna(nk) and str(nk).strip():
            known_kingdoms.add(str(nk).strip().lower())

    # Add extra general kingdom/geographical terms
    kingdom_terms = [
        "kingdom", "sultanate", "empire", "kerajaan", "kesultanan", "daha", 
        "indies", "residency", "presidency", "batavia", "lambri", "pasai", 
        "pidie", "surabaya", "trowulan", "singhasari", "banten", "demak",
        "cirebon", "mataram", "kediri", "sunda", "palembang", "tidore", "kutai"
    ]

    def is_kingdom(name_str):
        name_lower = name_str.lower().strip()
        if name_lower in known_kingdoms:
            return True
        if any(term in name_lower for term in kingdom_terms):
            return True
        return False

    # 3. CONSTRUCT DIRECTED GRAPH
    G = nx.DiGraph()
    node_types = {}
    
    # Iterate rows and populate nodes and edges
    for _, row in df.iterrows():
        person = row['orang']
        kingdom = row['kerajaan']
        
        if not person or pd.isna(person):
            continue
            
        # Add Person node
        G.add_node(person)
        node_types[person] = 'Person'
        
        # Add Kingdom node and link
        if kingdom and not pd.isna(kingdom):
            G.add_node(kingdom)
            node_types[kingdom] = 'Kingdom'
            G.add_edge(person, kingdom, relation='AFFILIATED')
            
        # Helper function to split comma-separated relatives and add edges
        def add_split_relations(col_name, rel_type):
            val = row[col_name]
            if val and not pd.isna(val) and str(val).strip():
                names = [n.strip() for n in str(val).split(',') if n.strip()]
                for name in names:
                    if name == person:
                        continue
                        
                    # Determine node type (Kingdom vs Person)
                    n_type = 'Kingdom' if is_kingdom(name) else 'Person'
                    
                    # For succession lines (Tokoh ke Tokoh), filter out kingdom entities
                    if rel_type in ['MENGGANTIKAN', 'DIGANTIKAN_OLEH'] and n_type == 'Kingdom':
                        continue
                            
                    # Add node if not exists
                    if not G.has_node(name):
                        G.add_node(name)
                        node_types[name] = n_type
                    
                    # Add directed edge representing relationship flow
                    G.add_edge(person, name, relation=rel_type)

        add_split_relations('ayah', 'AYAH')
        add_split_relations('ibu', 'IBU')
        add_split_relations('pasangan', 'PASANGAN')
        add_split_relations('anak', 'ANAK')
        add_split_relations('saudara', 'SAUDARA')
        add_split_relations('kerabat', 'KERABAT')
        add_split_relations('pendahulu', 'MENGGANTIKAN')
        add_split_relations('penerus', 'DIGANTIKAN_OLEH')

    print(f"Graph Construction Complete: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")

    # 4. COMPUTE PAGERANK CENTRALITY
    print("\nCalculating PageRank Centrality...")
    pagerank = nx.pagerank(G, alpha=0.85)
    
    # Sort and split overall, people, and kingdoms
    sorted_nodes = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)
    
    people_pr = [(node, score) for node, score in sorted_nodes if node_types.get(node) == 'Person']
    kingdoms_pr = [(node, score) for node, score in sorted_nodes if node_types.get(node) == 'Kingdom']

    print("\n--- TOP 10 INFLUENTIAL PEOPLE (PAGERANK) ---")
    for i, (name, score) in enumerate(people_pr[:10], 1):
        print(f"{i}. {name:<40} : {score:.5f}")

    print("\n--- TOP 10 INFLUENTIAL KINGDOMS (PAGERANK) ---")
    for i, (name, score) in enumerate(kingdoms_pr[:10], 1):
        print(f"{i}. {name:<40} : {score:.5f}")

    # 5. LOUVAIN COMMUNITY DETECTION
    print("\nCalculating Louvain Communities (Cluster Dinasti)...")
    # Louvain requires undirected graph
    G_undir = G.to_undirected()
    communities = nx_comm.louvain_communities(G_undir, seed=42)
    
    community_map = {}
    for comm_id, comm in enumerate(communities):
        for node in comm:
            community_map[node] = comm_id
            
    print(f"Detected {len(communities)} distinct Louvain communities/dynasty clusters.")

    # 6. ADAMIC-ADAR GRAPH ANALYTICS (STAGE 5)
    print("\nCalculating Genealogy Adamic-Adar Proximity Index...")
    
    # Build mapping from name to master_id (or fallback to cleaned name)
    name_to_master = {}
    for _, row in df.iterrows():
        p = row['orang']
        m_id = row.get('master_id', p)
        if pd.notna(p):
            p_clean = str(p).strip()
            name_to_master[p_clean] = str(m_id).strip() if pd.notna(m_id) and str(m_id).strip() else p_clean

    # Construct the undirected family graph
    G_family = nx.Graph()
    for _, row in df.iterrows():
        p = row['orang']
        if not p or pd.isna(p):
            continue
        p_clean = str(p).strip()
        p_node = name_to_master.get(p_clean, p_clean)
        
        G_family.add_node(p_node)
        
        for col in ['ayah', 'ibu', 'pasangan', 'anak', 'saudara', 'kerabat']:
            val = row[col]
            if val and not pd.isna(val) and str(val).strip():
                relatives = [r.strip() for r in str(val).split(',') if r.strip()]
                for rel in relatives:
                    rel_node = name_to_master.get(rel, rel)
                    if p_node != rel_node:
                        G_family.add_node(rel_node)
                        G_family.add_edge(p_node, rel_node)

    print(f"Family Graph Construction Complete: {G_family.number_of_nodes()} nodes, {G_family.number_of_edges()} edges.")
    
    # Calculate Adamic-Adar for all pairs of nodes in G_family
    nodes_list = list(G_family.nodes())
    pairs = [(nodes_list[i], nodes_list[j]) for i in range(len(nodes_list)) for j in range(i + 1, len(nodes_list))]
    
    aa_results = list(nx.adamic_adar_index(G_family, pairs))
    aa_results = [r for r in aa_results if r[2] > 0]
    aa_sorted = sorted(aa_results, key=lambda x: x[2], reverse=True)
    
    print(f"Analyzed Adamic-Adar proximity for {len(nodes_list)} nodes.")
    print(f"Total pairs with non-zero Adamic-Adar connectivity: {len(aa_sorted)}")
    
    print("\n--- TOP 5 MOST GENEALOGICALLY SIMILAR PAIRS (ADAMIC-ADAR INDEX) ---")
    for i, (p1, p2, score) in enumerate(aa_sorted[:5], 1):
        print(f"{i}. {p1} <-> {p2} (Score: {score:.4f})")

    # 7. EXPORT METRICS BACK TO DATAFRAME
    print("\nMapping metrics back to final dataset...")
    df['orang_PageRank'] = df['orang'].map(lambda x: pagerank.get(x, 0.0) if pd.notna(x) else 0.0)
    df['orang_Louvain_Cluster'] = df['orang'].map(lambda x: community_map.get(x, -1) if pd.notna(x) else -1)
    df['kerajaan_PageRank'] = df['kerajaan'].map(lambda x: pagerank.get(x, 0.0) if pd.notna(x) else 0.0)
    df['kerajaan_Louvain_Cluster'] = df['kerajaan'].map(lambda x: community_map.get(x, -1) if pd.notna(x) else -1)

    output_file = os.path.join(script_dir, "../data/dataset_dinasti_final_with_metrics.csv")
    print(f"Exporting metrics to {output_file}...")
    df.to_csv(output_file, sep=';', index=False, encoding='utf-8')
    print("=== ANALYSIS FINISHED SUCCESSFULLY ===")

if __name__ == "__main__":
    main()
