import os
import sys

# Ensure workspace and scripts directories are in the Python search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))

from mcp.server.fastmcp import FastMCP
from scripts.graph_rag_bot import (
    Neo4jConnector,
    retrieve_shortest_path as bot_retrieve_shortest_path,
    retrieve_person_info as bot_retrieve_person_info,
    retrieve_person_relationships as bot_retrieve_person_relationships,
    retrieve_kingdom_info as bot_retrieve_kingdom_info,
    retrieve_analytical_query as bot_retrieve_analytical_query,
    neo4j_conn
)

# Initialize the Model Context Protocol Server using FastMCP
mcp = FastMCP("Nusantara Dynasty Graph Server")

@mcp.tool()
def retrieve_shortest_path(name1: str, name2: str) -> dict:
    """
    Queries Neo4j to retrieve the shortest path between two historical figures.
    
    Args:
        name1: The name of the first historical figure.
        name2: The name of the second historical figure.
    """
    try:
        return bot_retrieve_shortest_path(name1, name2)
    except Exception as e:
        return {"status": "error", "message": f"Failed to retrieve shortest path: {str(e)}"}

@mcp.tool()
def retrieve_person_info(person: str) -> dict:
    """
    Retrieves properties and network metrics (PageRank, Louvain Cluster, Betweenness) for a specific historical figure.
    
    Args:
        person: The name of the historical figure.
    """
    try:
        return bot_retrieve_person_info(person)
    except Exception as e:
        return {"status": "error", "message": f"Failed to retrieve person info: {str(e)}"}

@mcp.tool()
def retrieve_person_relationships(person: str) -> list:
    """
    Retrieves the structural neighborhood relationships (family, succession, etc.) of a specific historical figure.
    
    Args:
        person: The name of the historical figure.
    """
    try:
        return bot_retrieve_person_relationships(person)
    except Exception as e:
        return [{"status": "error", "message": f"Failed to retrieve person relationships: {str(e)}"}]

@mcp.tool()
def retrieve_kingdom_info(kingdom: str) -> dict:
    """
    Retrieves properties, network metrics, and list of affiliated members for a kingdom.
    
    Args:
        kingdom: The name of the kingdom.
    """
    try:
        return bot_retrieve_kingdom_info(kingdom)
    except Exception as e:
        return {"status": "error", "message": f"Failed to retrieve kingdom info: {str(e)}"}

@mcp.tool()
def retrieve_analytical_query(natural_language_question: str) -> dict:
    """
    Use this tool ONLY for complex analytical, ranking, aggregate, filtering, or counting questions 
    (e.g., 'top 5 by PageRank', 'count per Louvain cluster', 'average metrics').
    Do NOT use this tool for simple direct entity lookups or relationship paths (use the other 4 tools instead).
    
    Args:
        natural_language_question: The analytical question in natural language.
    """
    try:
        return bot_retrieve_analytical_query(natural_language_question)
    except Exception as e:
        return {"status": "error", "message": f"Failed to run analytical query: {str(e)}"}

if __name__ == "__main__":
    # Start the server using stdio transport (the standard way MCP hosts communicate with servers)
    print("Starting Nusantara Dynasty Graph MCP Server...", file=sys.stderr)
    mcp.run(transport="stdio")
