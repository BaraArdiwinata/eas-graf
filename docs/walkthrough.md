# Walkthrough: Pembaruan Analisis Graf, Refactoring Bot, & Peningkatan Pipeline Data

Dokumen ini mendokumentasikan pembaruan yang telah berhasil diimplementasikan pada proyek Knowledge Graph Dinasti Nusantara.

---

## 1. Pembaruan Metrik Graf di `analisis_graf.py`

Kami telah memperbarui naskah analisis graf [analisis_graf.py](file:///c:/Users/shiho/Downloads/eas-graf/scripts/analisis_graf.py) dengan perubahan berikut:

* **Betweenness Centrality**:
  * Menghitung nilai perantaraan untuk mendeteksi tokoh/kerajaan jembatan antar-dinasti pada graf tidak berarah (`G_undir`).
  * Mengekspor kolom `orang_Betweenness` & `kerajaan_Betweenness` ke berkas dataset.
  * Hasil pengujian menunjukkan **Sunan Gunung Jati** sebagai tokoh jembatan tertinggi (`0.04796`) dan **Majapahit** sebagai kerajaan jembatan tertinggi (`0.05988`).

* **Adamic-Adar Index**:
  * Menggantikan *Jaccard Similarity* berbasis atribut untuk menghitung kemiripan silsilah secara langsung berdasarkan topologi graf (bobot tetangga mutual).
  * Mengekspor kolom `orang_AdamicAdar_Avg` ke berkas dataset.
  * Hasil pengujian mendeteksi pasangan **Rara Santang <-> Pangeran Walangsungsang** sebagai pasangan dengan tingkat kemiripan struktural tertinggi (`2.2529`).

Semua hasil metrik ini diekspor ke [dataset_dinasti_final_with_metrics.csv](file:///c:/Users/shiho/Downloads/eas-graf/data/dataset_dinasti_final_with_metrics.csv).

---

## 2. Refactoring `graph_rag_bot.py` (Struktur Baru untuk MCP)

Kami telah merefaktor [graph_rag_bot.py](file:///c:/Users/shiho/Downloads/eas-graf/scripts/graph_rag_bot.py) untuk mempersiapkannya sebagai tool-calling di sistem MCP:

* **Penghapusan Fungsi Dead-Weight**:
  * Menghapus fungsi ekstraksi entitas manual `extract_entities()`.
  * Menghapus seluruh fungsi translasi dan routing kueri Cypher (`needs_cypher_routing()`, `generate_cypher_query()`, `execute_and_format_cypher()`, serta `run_pandas_fallback()`).

* **Dekomposisi Fungsi `retrieve_graph_context()` Menjadi 4 Fungsi Modular**:
  1. `retrieve_shortest_path(name1, name2)`: Mengembalikan data structured dict berisi node, label, dan tipe relasi dari jalur terpendek antara dua tokoh.
  2. `retrieve_person_info(person)`: Mengembalikan data structured dict berisi atribut tokoh dan metrik jaringannya (mendukung fallback ke CSV).
  3. `retrieve_person_relationships(person)`: Mengembalikan structured list berisi semua hubungan tetangga/keluarga dari tokoh tersebut.
  4. `retrieve_kingdom_info(kingdom)`: Mengembalikan structured dict berisi properti kerajaan, metrik jaringan, dan daftar pemimpin/anggota terafiliasi.

---

## 3. Peningkatan Pipeline Data di `pipeline_graf.py` (Fuzzy Matching & Data Tracking)

Kami telah meningkatkan data pipeline di [pipeline_graf.py](file:///c:/Users/shiho/Downloads/eas-graf/scripts/pipeline_graf.py) dengan fitur-fitur berikut:

* **SPARQL Query Optimization (Combined Names & Kingdoms UNION)**:
  * Menggabungkan pencarian berbasis label nama persis dari CSV (untuk menangkap tokoh independen/religius) dan pencarian berbasis kerajaan (untuk menangkap tokoh dengan variasi ejaan melalui fuzzy matching di Python).
  * Menggunakan kueri dinamis untuk mencari seluruh kerajaan sejarah di Indonesia (`wd:Q3024240` dengan lokasi geografis `wdt:P17 wd:Q252`) secara real-time tanpa perlu mendaftarkan daftar ID secara manual (*hardcode*).
  * Perubahan ini berhasil memperkaya data pada **83 baris** dalam dataset akhir (misal: melengkapi informasi `ibuKota`, `agama`, `tahunMulai` untuk *Adam dari Banjar* dan relasi `saudara` untuk *Mpu Tantular*).

* **Entity Disambiguation via Fuzzy Matching (rapidfuzz)**:
  * Mengganti pencocokan string eksak dengan pencocokan fuzzy (`fuzz.token_sort_ratio`) pada `find_fuzzy_match()`.
  * **Auto-Merge**: Jika skor kemiripan fuzzy antara nama tokoh di CSV asli dan data SPARQL $\ge 90\%$, data akan otomatis digabungkan (*merged*).
  * **Manual Check Flag**: Jika skor kemiripan berada di rentang $75\% - 89\%$, properti akan digabungkan namun diberi tanda `manual_check = True` untuk verifikasi pengguna lebih lanjut.

* **Data Tracking & Kredibilitas Data (Confidence Score)**:
  * Menambahkan kolom `source` pada dataset untuk melacak sumber asal dari masing-masing data properti tokoh/kerajaan.
  * Menambahkan kolom `confidence_score` untuk mengukur tingkat kepercayaan/akurasi data:
    * Data yang bersumber dari SPARQL Wikidata/DBpedia dilacak sebagai `source: 'wikidata'` dengan `confidence_score` dinamis berkisar dari `0.75` hingga `1.0` (berdasarkan skor kemiripan fuzzy).
    * Data yang bersumber dari model bahasa besar dilacak sebagai `source: 'llm_imputed'` dengan `confidence_score` statis sebesar `0.80`.
    * Data asli yang tidak mengalami perubahan dilacak sebagai `source: 'original'` dengan `confidence_score` default `1.0`.

---

## 4. Pembangunan Server MCP (`mcp_server.py`)

Kami telah membuat berkas baru [mcp_server.py](file:///c:/Users/shiho/Downloads/eas-graf/mcp_server.py) di direktori utama proyek sebagai server MCP resmi untuk sistem Knowledge Graph ini:

* **Model Context Protocol SDK (FastMCP)**:
  * Memanfaatkan pustaka resmi Python MCP SDK (`mcp`) dan `FastMCP` wrapper untuk mendefinisikan server.
  * Menggunakan transport komunikasi standar **stdio (Standard Input/Output)** yang merupakan standar de-facto untuk integrasi dengan klien MCP (seperti Claude Desktop).

* **Registrasi Tool**:
  * Mendaftarkan 4 fungsi modular baru dari `graph_rag_bot.py` sebagai tools resmi server MCP yang dapat secara otomatis diekstraksi skemanya oleh model AI:
    * `retrieve_shortest_path`
    * `retrieve_person_info`
    * `retrieve_person_relationships`
    * `retrieve_kingdom_info`
  * Setiap tool dilengkapi penjelasan parameter (*args typehint*) dan *docstring* yang lengkap untuk membantu LLM memahami fungsi tool tersebut pada saat kueri.

---

## 5. Pembangunan & Refinement Klien Agen MCP (`mcp_agent.py`)

Sebagai langkah final, kami telah merancang dan menyempurnakan berkas klien agen [mcp_agent.py](file:///c:/Users/shiho/Downloads/eas-graf/mcp_agent.py) di direktori utama proyek dengan ketahanan tingkat tinggi:

* **Penyelarasan Reasoning Engine (`query_openrouter_raw`)**:
  * Fungsi `query_openrouter_raw` di [graph_rag_bot.py](file:///c:/Users/shiho/Downloads/eas-graf/scripts/graph_rag_bot.py) direfaktor agar sepenuhnya generik.
  * Fungsi ini mendukung pemanggilan tradisional (membuat payload dari `system_prompt` dan `user_prompt`) sekaligus mendukung pemanggilan berbasis riwayat pesan (`messages` list) dan deklarasi `tools` JSON-schema.
  * Ketika `tools` aktif, fungsi mengembalikan struktur respons JSON lengkap dari OpenRouter API secara utuh, bukan hanya teks string jawaban biasa.

* **Standard Client Spawning & Robust Pathing**:
  * Menggunakan `stdio_client` dari `mcp.client.stdio` untuk meluncurkan `mcp_server.py` secara otomatis sebagai subprocess stdio.
  * Menambahkan modifikasi dinamis pada `sys.path` untuk mencegah isu `ModuleNotFoundError` saat `mcp_agent.py` dipanggil dari luar root direktori.
  * Menggunakan jalur absolut berkas (`server_script`) saat melakukan spawn untuk menjamin validitas lokasi target script server.

* **Windows Startup Resilience (Read Timeout)**:
  * Mengonfigurasi `ClientSession` dari `mcp.client.session` secara eksplisit dengan parameter `read_timeout_seconds=timedelta(seconds=60.0)`.
  * Penambahan toleransi timeout 60 detik ini bertujuan mengantisipasi latensi booting awal sub-proses server Python pada lingkungan Windows.

* **Loop Integrasi Tool-Calling dengan LLM**:
  * Meneruskan kueri pengguna beserta definisi skema JSON-schema tools graf ke OpenRouter (mencakup fallback cerdas dari `google/gemini-2.5-flash` ke model free lainnya).
  * Menangani pemanggilan tool berganda (*multiple tool calls*) secara berurutan, mengeksekusi fungsi tools graf pada server MCP menggunakan `session.call_tool()`, menyajikan hasil output JSON terstruktur, lalu mengirimkannya kembali ke LLM (`role: "tool"`).
  * LLM pada akhirnya menyintesis hasil relasi dinasti prekolonial tersebut menjadi informasi sejarah dalam Bahasa Indonesia yang mengalir, akurat, dan profesional.

* **CLI Interaktif**:
  * Menyediakan CLI chat interaktif berbasis asinkron via `asyncio.run(main())` and `asyncio.to_thread(input, ...)` untuk kenyamanan pengujian silsilah dinasti secara live.

---

## 6. Penambahan Tool MCP Ke-5: `retrieve_analytical_query`

Untuk mendukung pertanyaan analitis, agregasi, perhitungan (counting), atau pemfilteran peringkat yang tidak dapat ditangani oleh 4 tool dasar sebelumnya, kami telah menambahkan tool ke-5:

* **Fungsi Modular `retrieve_analytical_query`**:
  * Ditambahkan di [graph_rag_bot.py](file:///c:/Users/shiho/Downloads/eas-graf/scripts/graph_rag_bot.py) dan didaftarkan sebagai `@mcp.tool()` di [mcp_server.py](file:///c:/Users/shiho/Downloads/eas-graf/mcp_server.py).
  * **Text-to-Cypher Translation**: Menggunakan `query_openrouter_raw()` dengan system prompt khusus yang memuat skema node/relasi graf lengkap untuk menerjemahkan pertanyaan bahasa alami secara langsung menjadi kueri Cypher.
  * **Sanitisasi & Batasan**: Membersihkan tag/fences markdown kueri (seperti ` ```cypher `) dan secara otomatis menyematkan klausa `LIMIT 25` jika tidak didefinisikan oleh LLM.

* **Proteksi Write/Mutation (Read-Only Guard)**:
  * Dilengkapi sistem validasi ketat (case-insensitive) menggunakan regex dengan batas kata (`\b`) untuk menolak kueri yang mengandung perintah mutasi database: `CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`, `DROP`, `DETACH`, `LOAD CSV`, atau fungsi penulisan APOC (`apoc.*write*`).
  * Desain batas kata ini memastikan substring dari kata-kata seperti **"Setyawati"** (nama tokoh) atau **"Asset"** tidak terblokir secara keliru, melainkan hanya literal instruksi mutasi.
  * Jika kueri mengandung kata-kata berbahaya tersebut, eksekusi dibatalkan sebelum dikirim ke database, dan tool langsung mengembalikan informasi penolakan error yang aman.

* **Penanganan Error & Serialisasi**:
  * Mengeksekusi kueri langsung via driver Neo4j dan menangkap jika terjadi *syntax error* dari kueri yang dihasilkan LLM agar tidak menyebabkan crash pada server.
  * Hasil dibaca secara rekursif dan diserialisasikan ke format JSON standar (memastikan tidak ada objek Graph Node/Relationship mentah).

* **Blok Pengujian Mandiri (Manual Test Block)**:
  * Menyediakan blok pengujian mandiri yang dapat dipanggil dengan flag `--test-analytical`:
    ```powershell
    python scripts/graph_rag_bot.py --test-analytical
    ```

* **Hasil Pengujian Mandiri Aktual (`--test-analytical`)**:
  Berikut adalah output asli dari eksekusi `python scripts/graph_rag_bot.py --test-analytical`:

  ```
  [INFO] Loaded local metrics dataset from 'C:\Users\shiho\Downloads\eas-graf\scripts\../data/dataset_dinasti_final_with_metrics.csv'.
  === STARTING MANUAL TESTS FOR RETRIEVE_ANALYTICAL_QUERY ===

  --- TEST 1: Siapa 5 tokoh dengan PageRank tertinggi di Kerajaan Pajajaran? ---
  -> [Execute Generated Cypher Query]:
  MATCH (p:Person)-[:MEMIMPIN_ATAU_TERAFILIASI]->(k:Kingdom)
  WHERE k.name = 'Kerajaan Pajajaran'
  RETURN p.name AS Person, p.pagerank_score AS PageRank
  ORDER BY p.pagerank_score DESC
  LIMIT 5

  Generated Cypher Query:
  MATCH (p:Person)-[:MEMIMPIN_ATAU_TERAFILIASI]->(k:Kingdom)
  WHERE k.name = 'Kerajaan Pajajaran'
  RETURN p.name AS Person, p.pagerank_score AS PageRank
  ORDER BY p.pagerank_score DESC
  LIMIT 5
  Row Count: 0
  Error: None
  Results Sample: []

  --- TEST 2: Berapa banyak tokoh di setiap klaster Louvain? ---
  -> [Execute Generated Cypher Query]:
  MATCH (p:Person)
  RETURN p.louvain_cluster AS LouvainCluster, COUNT(p) AS NumberOfPeople
  ORDER BY NumberOfPeople DESC
  LIMIT 25

  Generated Cypher Query:
  MATCH (p:Person)
  RETURN p.louvain_cluster AS LouvainCluster, COUNT(p) AS NumberOfPeople
  ORDER BY NumberOfPeople DESC
  LIMIT 25
  Row Count: 25
  Error: None
  Results Sample: [{'LouvainCluster': None, 'NumberOfPeople': 174}, {'LouvainCluster': 13, 'NumberOfPeople': 38}, {'LouvainCluster': 8, 'NumberOfPeople': 18}]

  --- TEST 3: Tuliskan kueri Cypher untuk menghapus semua tokoh dari Kerajaan Majapahit menggunakan DETACH DELETE ---
  Generated Cypher Query:
  MATCH (p:Person)-[:MEMIMPIN_ATAU_TERAFILIASI]->(k:Kingdom) WHERE k.name = 'Majapahit' DETACH DELETE p
  LIMIT 25
  Row Count: 0
  Error: Query rejected: Only read-only operations are allowed. Write/mutation patterns detected.
  Results Sample: []

  --- TEST 4: Direct Write Cypher Bypass Test (SET command) ---
  Testing direct write query: MATCH (p:Person {name: 'Mpu Tantular'}) SET p.role = 'Super Mahapatih' RETURN p
  Guard Status: BLOCKED (Correctly identified write/mutation pattern)
  Error: Query rejected: Only read-only operations are allowed. Write/mutation patterns detected.

  --- TEST 5: Word-Boundary Collision Edge Cases ('Setyawati', 'Asset') ---
  Query: 'MATCH (p:Person {name: 'Setyawati'}) RETURN p' -> Guard Status: PASSED (SUCCESS - ignored substring)
  Query: 'MATCH (p:Person) WHERE p.name CONTAINS 'Asset' RETURN p' -> Guard Status: PASSED (SUCCESS - ignored substring)

  === MANUAL TESTS COMPLETED ===
  ```
