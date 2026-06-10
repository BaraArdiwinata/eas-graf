# Walkthrough - Data Enrichment Pipeline (Updated)

This document describes the final results of the Nusantara Dynasty Data Enrichment pipeline.

---

## 1. Environment & Setup
The environment contains:
- `pandas`, `requests`, `wikipedia-api`, and `python-dotenv`.
- A local [.env](file:///c:/Kuliah%20Semester%206/Graf%20Pengetahuan/eas-graf/.env) file containing the `OPENROUTER_API_KEY`.

---

## 2. Dynamic Model Fallback & Self-Healing
We updated the OpenRouter completions to handle model deprecation and credit limits:
1. **Model Fallback Hierarchy**: The script tries the user's requested model first (`google/gemini-1.5-flash:free`). If OpenRouter rejects it with 400 (not a valid model ID in 2026), it falls back to the standard `google/gemini-2.5-flash`, and if that fails, to free alternatives (`meta-llama/llama-3.3-70b-instruct:free` or `openrouter/free`).
2. **Explicit Max Tokens**: Explicitly set `"max_tokens": 1000` to prevent credit checks for the default 65k tokens, eliminating **402 credit constraint errors**.
3. **Structured JSON Output**: Enabled `"response_format": {"type": "json_object"}` and a strict system prompt to guarantee valid, clean JSON returned by the models.
4. **Debug Logging**: Added detailed console prints to trace HTTP error codes and exception stacktraces in real-time.

---

## 3. Results & Alignment

Running the pipeline on the original dataset yields the following final results:
1. **SPARQL Endpoint Hits**:
   - **Wikidata**: Successfully fetched 355 records in **3.04 seconds** using direct indexed lookups by name.
   - **DBpedia**: Successfully fetched 411 records in **5.70 seconds**.
2. **Entity Alignment & Merge**:
   - **403 out of 406 rows** in the original CSV were successfully enriched and aligned.
   - New relational and temporal columns were created: `tglLahir`, `tglMati`, `saudara`, `kerabat`, `dinasti`, and `personWikidataID`.
3. **LLM Extraction Fallback**:
   - Identified **108 figures** with completely empty relationships after the SPARQL queries.
   - Scraped Wikipedia summaries and successfully imputed silsilah data for **95 figures** (88% success rate) using `google/gemini-2.5-flash` via OpenRouter.
4. **Data Integrity**: All CP1252/Double-UTF-8 corruptions were resolved (e.g. `Dewa Agung Śakti` and `Cut Nya' Dhien`).

The final enriched graph database CSV is saved to [dataset_dinasti_final.csv](file:///c:/Kuliah%20Semester%206/Graf%20Pengetahuan/eas-graf/dataset_dinasti_final.csv).

---

## 4. Git History Cleanup & Remote Push
To resolve the GitHub Push Protection violation (`GH013`) due to the OpenRouter API key being tracked in the initial commit, the Git history was rewritten as follows:
1. **Resetting local branch**: The local `main` branch pointer was deleted using `git update-ref -d refs/heads/main` to transition the repo to an unborn state.
2. **Unstaging secrets**: The `.env` file was removed from the index using `git rm --cached .env` to ensure it remains locally on disk but is ignored by Git in all commits.
3. **Commit & Push**: All other files were re-added and committed as a single clean commit (`feat: initial project structure without secrets`). The branch was then successfully pushed to the remote repository `https://github.com/BaraArdiwinata/eas-graf.git`.

---

## 5. GraphRAG Chatbot Expansion
We created a new interactive command-line interface chatbot in [graph_rag_bot.py](file:///c:/Kuliah%20Semester%206/Graf%20Pengetahuan/eas-graf/graph_rag_bot.py):
1. **Neo4j & CSV Hybrid Data Retrieval**: Connected to Neo4j via `NEO4J_URI`, `NEO4J_USERNAME`, and `NEO4J_PASSWORD` in `.env`. The retrieval module looks up node details and silsilah (neighborhood subgraphs) from Neo4j, while fallback metrics (PageRank score, Louvain cluster community) are retrieved from [dataset_dinasti_final_with_metrics.csv](file:///c:/Kuliah%20Semester%206/Graf%20Pengetahuan/eas-graf/dataset_dinasti_final_with_metrics.csv) when Neo4j is offline or the properties aren't yet written to nodes.
2. **Shortest Path Query**: If the user asks about the relationship between two or more figures, the bot executes a shortest path Cypher query on Neo4j to find and display the exact connectivity path between them.
3. **Automatic Entity Extraction**: Performs case-insensitive dictionary-based substring matches using names gathered from the dataset, falling back to a Cypher-based `CONTAINS` keyword matching to ensure typos or partial matches are resolved.
4. **LLM Synthesis & Safe Sanitization**: Packages the user query and the retrieved graph context into a highly structured prompt. Uses a dedicated payload sanitizer `clean_prompt_payload` to strip out carriage returns and non-printable control characters, eliminating API JSON encoding errors (Error 400). Restricts context length to 6,000 characters and limits neighborhood queries to 15 records. Uses OpenRouter API with Gemini Flash and dynamic fallback options (Gemini 2.5, Llama 3.3, Qwen 2.5) to return accurate, contextual historical explanations.
5. **Text-to-Cypher Hybrid Routing**: Detects global aggregation/analytical queries (e.g. asking for "centrality terkuat", "pagerank terbesar", "jumlah tokoh", "klaster") and automatically routes the query to generate a Neo4j Cypher query.
   * Runs the query directly against the Neo4j database (supporting case-insensitive role filtering).
   * **Dynamic Fallback/Enrichment**: If the Cypher query returns null values for analytical scores (e.g. because `pagerank_score` or `louvain_cluster` has not been imported into the database nodes), Python intercepts the result, looks up the real metrics from [dataset_dinasti_final_with_metrics.csv](file:///c:/Kuliah%20Semester%206/Graf%20Pengetahuan/eas-graf/dataset_dinasti_final_with_metrics.csv), enriches the rows, sorts them descending, and formats them. If Neo4j is offline entirely, it runs a Pandas aggregation analysis.
6. **Successful Verification**: Run programmatically to test parsing and API synthesis, producing comprehensive, well-structured, factual answers including PageRank and Louvain metric info.



