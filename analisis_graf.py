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
    csv_file = "dataset_dinasti_final.csv"
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

    # 6. JACCARD SIMILARITY FOR GENEALOGY SETS
    print("\nCalculating Genealogy Jaccard Similarity...")
    
    # Build consolidated family sets from all columns for each person
    family_sets = {}
    
    for _, row in df.iterrows():
        person = row['orang']
        if not person or pd.isna(person):
            continue
            
        family = set()
        for col in ['ayah', 'ibu', 'pasangan', 'anak', 'saudara', 'kerabat']:
            val = row[col]
            if val and not pd.isna(val) and str(val).strip():
                names = [n.strip() for n in str(val).split(',') if n.strip()]
                family.update(names)
                
        if person not in family_sets:
            family_sets[person] = set()
        family_sets[person].update(family)

    # Filter out empty family sets
    active_people = {k: v for k, v in family_sets.items() if len(v) > 0}
    people_list = list(active_people.keys())
    n = len(people_list)
    
    jaccard_results = []
    perfect_matches = 0
    total_pairs_with_overlap = 0
    sum_similarity = 0.0

    for i in range(n):
        for j in range(i + 1, n):
            p1 = people_list[i]
            p2 = people_list[j]
            s1 = active_people[p1]
            s2 = active_people[p2]
            
            intersection = s1.intersection(s2)
            union = s1.union(s2)
            
            if len(union) > 0:
                sim = len(intersection) / len(union)
                if sim > 0:
                    total_pairs_with_overlap += 1
                    sum_similarity += sim
                    if sim == 1.0:
                        perfect_matches += 1
                    jaccard_results.append((p1, p2, sim))

    print(f"Analyzed {n} figures with non-empty family relationships.")
    print(f"Pairs with family overlapping: {total_pairs_with_overlap}")
    if total_pairs_with_overlap > 0:
        avg_sim = sum_similarity / total_pairs_with_overlap
        print(f"Average Jaccard Similarity for overlapping pairs: {avg_sim:.4f}")
        print(f"Pairs with 100% duplicate genealogy: {perfect_matches} ({perfect_matches / total_pairs_with_overlap * 100:.2f}%)")
    else:
        print("No overlapping family members found between different individuals.")

    # Sort and show top 5 high-similarity pairs (excluding 100% duplicates for diversity)
    jaccard_sorted = sorted([r for r in jaccard_results if r[2] < 1.0], key=lambda x: x[2], reverse=True)
    print("\n--- TOP 5 MOST GENEALOGICALLY SIMILAR PAIRS (Jaccard Similarity < 100%) ---")
    for i, (p1, p2, sim) in enumerate(jaccard_sorted[:5], 1):
        print(f"{i}. {p1} <-> {p2} (Jaccard: {sim:.2f})")

    # 7. EXPORT METRICS BACK TO DATAFRAME
    print("\nMapping metrics back to final dataset...")
    df['orang_PageRank'] = df['orang'].map(lambda x: pagerank.get(x, 0.0) if pd.notna(x) else 0.0)
    df['orang_Louvain_Cluster'] = df['orang'].map(lambda x: community_map.get(x, -1) if pd.notna(x) else -1)
    df['kerajaan_PageRank'] = df['kerajaan'].map(lambda x: pagerank.get(x, 0.0) if pd.notna(x) else 0.0)
    df['kerajaan_Louvain_Cluster'] = df['kerajaan'].map(lambda x: community_map.get(x, -1) if pd.notna(x) else -1)

    output_file = "dataset_dinasti_final_with_metrics.csv"
    print(f"Exporting metrics to {output_file}...")
    df.to_csv(output_file, sep=';', index=False, encoding='utf-8')
    print("=== ANALYSIS FINISHED SUCCESSFULLY ===")

if __name__ == "__main__":
    main()
