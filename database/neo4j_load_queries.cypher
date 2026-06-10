// ============================================================================
// NEO4J IMPORT QUERIES - MENAUTKAN BENANG MERAH DINASTI NUSANTARA
// ============================================================================
// File ini berisi kueri Cypher untuk memuat data dari 'dataset_dinasti_final.csv'
// ke dalam Neo4j Graph Database.
//
// CATATAN PENTING:
// 1. Letakkan berkas 'dataset_dinasti_final.csv' di direktori 'import' Neo4j Anda.
// 2. CSV menggunakan pemisah titik koma (;), sehingga kueri menggunakan `FIELDTERMINATOR ';'`.
// ============================================================================

// ----------------------------------------------------------------------------
// TAHAP 1: PEMBUATAN CONSTRAINT & INDEX (Jalankan ini terlebih dahulu!)
// ----------------------------------------------------------------------------

// Membuat constraint agar nama kerajaan unik (menghindari duplikasi)
CREATE CONSTRAINT kingdom_name_unique IF NOT EXISTS
FOR (k:Kingdom) REQUIRE k.name IS UNIQUE;

// Membuat constraint agar nama tokoh unik (menghindari duplikasi)
CREATE CONSTRAINT person_name_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.name IS UNIQUE;

// Membuat indeks tambahan pada properti peran untuk optimasi query pencarian
CREATE INDEX person_role_index IF NOT EXISTS
FOR (p:Person) ON (p.role);

// ----------------------------------------------------------------------------
// TAHAP 2: IMPORT NODE KERAJAAN (KINGDOM) & TOKOH (PERSON)
// ----------------------------------------------------------------------------

// 1. Memuat Node Kerajaan (Kingdom)
LOAD CSV WITH HEADERS FROM "file:///dataset_dinasti_final.csv" AS row
FIELDTERMINATOR ';'
WITH row WHERE row.kerajaan IS NOT NULL AND row.kerajaan <> ""
MERGE (k:Kingdom {name: row.kerajaan})
ON CREATE SET 
  k.capital = row.ibuKota,
  k.religion = row.agama,
  k.yearStart = toInteger(row.tahunMulai),
  k.wikidataID = row.wikidataID
ON MATCH SET
  k.capital = coalesce(k.capital, row.ibuKota),
  k.religion = coalesce(k.religion, row.agama),
  k.yearStart = coalesce(k.yearStart, toInteger(row.tahunMulai)),
  k.wikidataID = coalesce(k.wikidataID, row.wikidataID);

// 2. Memuat Node Tokoh (Person)
LOAD CSV WITH HEADERS FROM "file:///dataset_dinasti_final.csv" AS row
FIELDTERMINATOR ';'
WITH row WHERE row.orang IS NOT NULL AND row.orang <> ""
MERGE (p:Person {name: row.orang})
ON CREATE SET 
  p.role = row.peran,
  p.birthDate = row.tglLahir,
  p.deathDate = row.tglMati,
  p.wikidataID = row.personWikidataID,
  p.dynasty = row.dinasti
ON MATCH SET
  p.role = coalesce(p.role, row.peran),
  p.birthDate = coalesce(p.birthDate, row.tglLahir),
  p.deathDate = coalesce(p.deathDate, row.tglMati),
  p.wikidataID = coalesce(p.wikidataID, row.personWikidataID),
  p.dynasty = coalesce(p.dynasty, row.dinasti);

// ----------------------------------------------------------------------------
// TAHAP 3: IMPORT RELASI AFILIASI KERAJAAN
// ----------------------------------------------------------------------------

// Relasi Tokoh ke Kerajaan: (:Person)-[:MEMIMPIN_ATAU_TERAFILIASI]->(:Kingdom)
LOAD CSV WITH HEADERS FROM "file:///dataset_dinasti_final.csv" AS row
FIELDTERMINATOR ';'
WITH row WHERE row.orang IS NOT NULL AND row.orang <> "" AND row.kerajaan IS NOT NULL AND row.kerajaan <> ""
MATCH (p:Person {name: row.orang})
MATCH (k:Kingdom {name: row.kerajaan})
MERGE (p)-[:MEMIMPIN_ATAU_TERAFILIASI]->(k);

// ----------------------------------------------------------------------------
// TAHAP 4: IMPORT RELASI SILSILAH KELUARGA (Tokoh ke Tokoh)
// ----------------------------------------------------------------------------
// Relasi-relasi di bawah ini menggunakan UNWIND dan split() karena kolom relasi
// bisa berisi lebih dari satu nama yang dipisahkan dengan koma (,).

// 1. Relasi AYAH
LOAD CSV WITH HEADERS FROM "file:///dataset_dinasti_final.csv" AS row
FIELDTERMINATOR ';'
WITH row WHERE row.orang IS NOT NULL AND row.orang <> "" AND row.ayah IS NOT NULL AND row.ayah <> ""
MATCH (p:Person {name: row.orang})
UNWIND split(row.ayah, ",") AS fatherName
WITH p, trim(fatherName) AS cleanFather
WHERE cleanFather <> ""
MERGE (f:Person {name: cleanFather})
MERGE (p)-[:AYAH]->(f);

// 2. Relasi IBU
LOAD CSV WITH HEADERS FROM "file:///dataset_dinasti_final.csv" AS row
FIELDTERMINATOR ';'
WITH row WHERE row.orang IS NOT NULL AND row.orang <> "" AND row.ibu IS NOT NULL AND row.ibu <> ""
MATCH (p:Person {name: row.orang})
UNWIND split(row.ibu, ",") AS motherName
WITH p, trim(motherName) AS cleanMother
WHERE cleanMother <> ""
MERGE (m:Person {name: cleanMother})
MERGE (p)-[:IBU]->(m);

// 3. Relasi PASANGAN
LOAD CSV WITH HEADERS FROM "file:///dataset_dinasti_final.csv" AS row
FIELDTERMINATOR ';'
WITH row WHERE row.orang IS NOT NULL AND row.orang <> "" AND row.pasangan IS NOT NULL AND row.pasangan <> ""
MATCH (p:Person {name: row.orang})
UNWIND split(row.pasangan, ",") AS spouseName
WITH p, trim(spouseName) AS cleanSpouse
WHERE cleanSpouse <> ""
MERGE (s:Person {name: cleanSpouse})
MERGE (p)-[:PASANGAN]->(s);

// 4. Relasi ANAK
LOAD CSV WITH HEADERS FROM "file:///dataset_dinasti_final.csv" AS row
FIELDTERMINATOR ';'
WITH row WHERE row.orang IS NOT NULL AND row.orang <> "" AND row.anak IS NOT NULL AND row.anak <> ""
MATCH (p:Person {name: row.orang})
UNWIND split(row.anak, ",") AS childName
WITH p, trim(childName) AS cleanChild
WHERE cleanChild <> ""
MERGE (c:Person {name: cleanChild})
MERGE (p)-[:ANAK]->(c);

// 5. Relasi SAUDARA
LOAD CSV WITH HEADERS FROM "file:///dataset_dinasti_final.csv" AS row
FIELDTERMINATOR ';'
WITH row WHERE row.orang IS NOT NULL AND row.orang <> "" AND row.saudara IS NOT NULL AND row.saudara <> ""
MATCH (p:Person {name: row.orang})
UNWIND split(row.saudara, ",") AS siblingName
WITH p, trim(siblingName) AS cleanSibling
WHERE cleanSibling <> ""
MERGE (s:Person {name: cleanSibling})
MERGE (p)-[:SAUDARA]->(s);

// 6. Relasi KERABAT
LOAD CSV WITH HEADERS FROM "file:///dataset_dinasti_final.csv" AS row
FIELDTERMINATOR ';'
WITH row WHERE row.orang IS NOT NULL AND row.orang <> "" AND row.kerabat IS NOT NULL AND row.kerabat <> ""
MATCH (p:Person {name: row.orang})
UNWIND split(row.kerabat, ",") AS relativeName
WITH p, trim(relativeName) AS cleanRelative
WHERE cleanRelative <> ""
MERGE (r:Person {name: cleanRelative})
MERGE (p)-[:KERABAT]->(r);

// ----------------------------------------------------------------------------
// TAHAP 5: IMPORT RELASI SUKSESI TAKHTA (Tokoh ke Tokoh)
// ----------------------------------------------------------------------------

// 1. Relasi MENGGANTIKAN (Pendahulu)
// Catatan: Kueri memfilter agar pendahulu bukan nama kerajaan (seperti "Singhasari" atau "Demak Sultanate")
// yang tidak sengaja ter-import ke kolom pendahulu dari DBpedia.
LOAD CSV WITH HEADERS FROM "file:///dataset_dinasti_final.csv" AS row
FIELDTERMINATOR ';'
WITH row WHERE row.orang IS NOT NULL AND row.orang <> "" AND row.pendahulu IS NOT NULL AND row.pendahulu <> ""
MATCH (p:Person {name: row.orang})
UNWIND split(row.pendahulu, ",") AS predName
WITH p, trim(predName) AS cleanPred
WHERE cleanPred <> "" AND NOT cleanPred CONTAINS "Kingdom" AND NOT cleanPred CONTAINS "Sultanate" AND NOT cleanPred CONTAINS "Empire"
MERGE (pred:Person {name: cleanPred})
MERGE (p)-[:MENGGANTIKAN]->(pred);

// 2. Relasi DIGANTIKAN_OLEH (Penerus)
LOAD CSV WITH HEADERS FROM "file:///dataset_dinasti_final.csv" AS row
FIELDTERMINATOR ';'
WITH row WHERE row.orang IS NOT NULL AND row.orang <> "" AND row.penerus IS NOT NULL AND row.penerus <> ""
MATCH (p:Person {name: row.orang})
UNWIND split(row.penerus, ",") AS succName
WITH p, trim(succName) AS cleanSucc
WHERE cleanSucc <> "" AND NOT cleanSucc CONTAINS "Kingdom" AND NOT cleanSucc CONTAINS "Sultanate" AND NOT cleanSucc CONTAINS "Empire"
MERGE (succ:Person {name: cleanSucc})
MERGE (p)-[:DIGANTIKAN_OLEH]->(succ);
