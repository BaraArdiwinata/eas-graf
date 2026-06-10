## 📄 Mini-PRD: Pengayaan Data Knowledge Graph Dinasti Nusantara

**1. Latar Belakang & Tujuan (Objective)**
Proyek ini merupakan kelanjutan (ekspansi) dari riset ETS. Tujuan utamanya adalah melakukan *Data Enrichment* untuk mengatasi masalah kekosongan data (*sparsity*) pada relasi silsilah (ayah, ibu, pasangan, anak) tokoh-tokoh kerajaan Nusantara di dataset Wikidata. Data relasional yang utuh dan komprehensif sangat krusial untuk mencegah oversimplifikasi dan meningkatkan akurasi algoritma *Network Analysis* (PageRank, Louvain, Jaccard) di Neo4j.

**2. Ruang Lingkup (Scope)**

* **In Scope:** * Revisi kueri SPARQL (penambahan properti suksesi P1365/P1366, relasi horizontal P3373/P53, dan batasan temporal P569/P570).
* Penyelarasan entitas (*Entity Alignment*) DBpedia secara absolut via `wikidataID`.
* Ekstraksi informasi otomatis berbasis LLM dari teks Wikipedia untuk mengisi data yang *missing* (`NaN`).


* **Out of Scope:** Pembuatan antarmuka pengguna (UI/UX) atau aplikasi *front-end* interaktif; fokus utama adalah *backend data pipeline* dan analitik graf.

**3. Tech Stack & Tools**

* **Database Analitik:** Neo4j (Graph Database) & Cypher Query.
* **Sumber Data Utama:** Wikidata SPARQL Endpoint, DBpedia SPARQL Endpoint, Wikipedia (*Unstructured Text*).
* **Pemrosesan Data:** Python (Pandas untuk *cleaning* & integrasi, `wikipedia-api` untuk *scraping*).
* **AI Engine:** OpenRouter API (LLM *prompting* berformat JSON untuk *Information Extraction*).

**4. Alur Kerja Sistem (Data Pipeline Flow)**

1. **Ekstraksi Dasar:** Eksekusi kueri SPARQL Wikidata dan DBpedia yang sudah diperluas.
2. **Pembersihan & Penyatuan:** Pembersihan *encoding* karakter UTF-8 yang rusak di Python dan proses *Left Join* menggunakan `wikidataID` (menghindari pencocokan *string* manual).
3. **Injeksi AI (Penambalan Data):** Sistem mendeteksi baris dengan nilai `NaN` pada kolom silsilah ➡️ Menarik artikel Wikipedia tokoh tersebut ➡️ Mengirim *prompt* ke LLM untuk mengekstrak entitas keluarga/suksesi ➡️ Mengonversi *output* JSON ke dalam *dataframe*.
4. **Finalisasi Ekspor:** Menghasilkan file `dataset_dinasti_final.csv` yang solid dan siap di-*load* menjadi *nodes* dan *edges* di Neo4j.