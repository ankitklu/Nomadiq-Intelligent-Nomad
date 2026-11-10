import os
import json
import asyncio
import certifi 
from dotenv import load_dotenv
load_dotenv()

from langchain_mcp_adapters.client import MultiServerMCPClient

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATIONSTACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")

client = MultiServerMCPClient(
    {
        "tavily":{
            "transport": "streamable_http",
            "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}",
        },
        ## Installing Aviation Stack to Local Machine and then using it
        "aviationstack":{
            "transport": "stdio",
            "command":"uvx",
            "args":[
                "aviationstack-mcp"
            ],
            "env":{
                "AVIATIONSTACK_API_KEY": AVIATIONSTACK_API_KEY
            }
            # "url": f"https://mcp.aviationstack.com/mcp/?aviationstackApiKey={AVIATIONSTACK_API_KEY}",
        }
    }
)

# tavily_search_tool = None
# aviationstack_tool = None

async def get_all_tools():
    tools = await client.get_tools()

    for tool in tools:
        print(tool.name)

    return tools

# AVIATION and TAVILY tools

search_tool = None
aviation_tools = None

async def initialize_mcp():

    global search_tool
    global aviation_tools

    if search_tool is not None and aviation_tools:
        return

    tools = await client.get_tools()

    print("\n Available MCP tools: \n")

    for tool in tools:
        print(tool.name)

    search_tool = next(
        tool
        for tool in tools
        if tool.name == "tavily_search"
    )

    aviation_tools = {
        tool.name: tool
        for tool in tools
        if tool.name != "tavily_search"
    }

def mcp_result_to_text(result) -> str:
    """
    MCP tools return a list of content blocks, e.g.
    [{"type": "text", "text": '{"results": [...]}'}].
    Convert that into a plain, readable string so it can be stored in
    state, put into LLM prompts and rendered by the frontend.
    """

    if isinstance(result, str):
        blocks = [result]
    else:
        blocks = [
            b.get("text", "") if isinstance(b, dict) else str(b)
            for b in result
        ]

    text = "\n".join(blocks).strip()

    try:
        data = json.loads(text)
    except ValueError:
        return text

    if not isinstance(data, dict):
        return text

    # Errors: Tavily -> {"error": ..., "status": 429, "detail": {...}}
    #         AviationStack -> {"ok": false, "error": "..."}
    if "error" in data or data.get("ok") is False:
        detail = data.get("detail")
        if isinstance(detail, dict):
            detail = detail.get("error")
        message = detail or data.get("error") or "unknown error"
        status = data.get("status")
        context = data.get("context")
        prefix = "Request failed"
        if context:
            prefix += f" while {context}"
        if status:
            prefix += f" (status {status})"
        return f"{prefix}: {message}"

    # Tavily search results
    results = data.get("results")
    if isinstance(results, list) and results:
        formatted = []

        for i, r in enumerate(results, 1):
            title = r.get("title", "N/A")
            url = r.get("url", "N/A")
            snippet = r.get("content") or r.get("snippet") or "N/A"

            if len(snippet) > 300:
                snippet = snippet[:300].rsplit(" ", 1)[0] + "..."

            formatted.append(f"{i}. {title}\nURL: {url}\nSnippet: {snippet}\n")

        return "\n\n".join(formatted)

    return text


async def tavily_mcp_search(query: str) -> str:
    await initialize_mcp()
    result = await search_tool.ainvoke(
        {
            "query" : query
        }
    )
    return mcp_result_to_text(result)

async def aviation_mcp_call(
        tool_name: str,
        tool_args: dict= None
    ) -> str:

    # Reuse the tools loaded once by initialize_mcp() instead of listing
    # every MCP server's tools again on each call.
    await initialize_mcp()

    tool = aviation_tools.get(tool_name)

    if tool is None:
        return f"Request failed: MCP tool '{tool_name}' not found."

    result = await tool.ainvoke(
        tool_args or {}
    )

    return mcp_result_to_text(result)


