import os
import sys
import json
import asyncio
from datetime import timedelta
from dotenv import load_dotenv

# Ensure workspace and scripts folders are in the Python search path to avoid ModuleNotFoundError
workspace_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(workspace_dir)
sys.path.append(os.path.join(workspace_dir, 'scripts'))

# Load environment variables
load_dotenv(os.path.join(workspace_dir, '.env'))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from scripts.graph_rag_bot import OPENROUTER_API_KEY, query_openrouter_raw

# System prompt for the agent to behave like an expert historian and data scientist
SYSTEM_PROMPT = (
    "Anda adalah Nusantara Dynasty Knowledge Graph Bot, asisten cerdas berkeahlian ganda sebagai "
    "Senior Historian Sejarah Nusantara dan Senior Data Scientist. Tugas Anda adalah membantu "
    "pengguna memahami relasi silsilah dinasti kerajaan prekolonial di Indonesia.\n\n"
    "Aturan Penulisan Jawaban:\n"
    "1. Jawab dalam bahasa Indonesia yang mengalir, jelas, natural, dan sangat profesional.\n"
    "2. Gunakan tools graf yang tersedia (seperti retrieve_person_info, retrieve_person_relationships, "
    "retrieve_kingdom_info, retrieve_shortest_path) untuk mencari data silsilah, PageRank, dan Klaster Louvain.\n"
    "3. Selalu panggil tool yang relevan sebelum menjawab pertanyaan sejarah jika nama tokoh atau kerajaan disebutkan.\n"
    "4. Tuliskan jawaban secara komprehensif, terstruktur (gunakan bullet points jika membantu), dan informatif berdasarkan hasil panggilan tools."
)

async def main():
    # Define parameters to launch mcp_server.py as a stdio subprocess using absolute path
    server_script = os.path.join(workspace_dir, "mcp_server.py")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
        env=os.environ.copy()
    )
    
    print("========================================================================")
    print("        NUSANTARA DYNASTY KNOWLEDGE GRAPH - MCP AGENT CLIENT            ")
    print("========================================================================")
    print("Menghubungkan ke server MCP...")
    
    try:
        # Spawn the stdio server process
        async with stdio_client(server_params) as (read, write):
            # Establish the client session with an explicit 60-second read timeout
            # to handle slow startup/booting times on Windows environments.
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=60.0)) as session:
                print("Menginisialisasi sesi komunikasi MCP...")
                await session.initialize()
                
                # Fetch registered tools from the server
                mcp_tools = await session.list_tools()
                print(f"Koneksi sukses! Berhasil memuat {len(mcp_tools.tools)} tools dari mcp_server.py.")
                
                # Map MCP tools schema to standard OpenAI tools format
                openai_tools = []
                for tool in mcp_tools.tools:
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema
                        }
                    })
                
                print("Ketik 'exit', 'quit', atau 'keluar' untuk mengakhiri sesi chat.")
                print("========================================================================\n")
                
                while True:
                    try:
                        # Non-blocking input retrieval
                        query = await asyncio.to_thread(input, "Anda: ")
                        query = query.strip()
                        
                        if not query:
                            continue
                            
                        if query.lower() in ['exit', 'quit', 'keluar']:
                            print("\nTerima kasih telah menggunakan Nusantara Dynasty Agent. Sampai jumpa!")
                            break
                            
                        # Build context history for this turn
                        messages = [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": query}
                        ]
                        
                        # Loop to process reasoning and tool calls
                        while True:
                            response_json = query_openrouter_raw(messages=messages, tools=openai_tools)
                            if not response_json or "choices" not in response_json:
                                print("Bot: Maaf, terjadi kesalahan saat menghubungi AI.")
                                break
                                
                            choice = response_json["choices"][0]
                            message = choice["message"]
                            messages.append(message)
                            
                            # Check if the model requests one or more tool calls
                            if "tool_calls" in message and message["tool_calls"]:
                                print("Bot: (Memanggil tools graf...)")
                                tool_calls = message["tool_calls"]
                                for tool_call in tool_calls:
                                    tool_name = tool_call["function"]["name"]
                                    tool_args_str = tool_call["function"]["arguments"]
                                    tool_call_id = tool_call["id"]
                                    
                                    try:
                                        tool_args = json.loads(tool_args_str)
                                    except Exception as e:
                                        tool_args = {}
                                        print(f"[ERROR] Gagal mem-parse argumen tool: {e}", file=sys.stderr)
                                        
                                    print(f"-> [Execute Tool] {tool_name} dengan argumen: {tool_args}")
                                    
                                    try:
                                        # Request tool execution from the server
                                        result = await session.call_tool(tool_name, tool_args)
                                        content_str = ""
                                        if hasattr(result, "content"):
                                            content_str = "".join([c.text for c in result.content if hasattr(c, 'text')])
                                        elif isinstance(result, (dict, list)):
                                            content_str = json.dumps(result, ensure_ascii=False)
                                        else:
                                            content_str = str(result)
                                    except Exception as e:
                                        content_str = json.dumps({"status": "error", "message": f"Error executing tool: {str(e)}"})
                                        print(f"[ERROR] Gagal mengeksekusi tool '{tool_name}': {e}", file=sys.stderr)
                                        
                                    # Append tool execution result back to messages history
                                    messages.append({
                                        "role": "tool",
                                        "name": tool_name,
                                        "tool_call_id": tool_call_id,
                                        "content": content_str
                                    })
                                
                                # Re-run reasoning loop with the tool outputs
                                continue
                            else:
                                # Output the final synthesized answer
                                print("\n------------------------------ JAWABAN BOT ------------------------------")
                                print(message.get("content", ""))
                                print("-------------------------------------------------------------------------\n")
                                break
                                
                    except KeyboardInterrupt:
                        print("\nSesi chat dihentikan oleh pengguna.")
                        break
                    except Exception as e:
                        print(f"\n[ERROR] Terjadi kesalahan dalam loop chat: {e}\n")
                        
    except Exception as e:
        print(f"[CRITICAL ERROR] Gagal menghubungkan ke server MCP: {e}", file=sys.stderr)

if __name__ == "__main__":
    # Run the main asynchronous client process
    asyncio.run(main())
