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

client = MultiServerMCPClient(
    {
        "tavily":{
            "transport": "streamable_http",
            "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}",
        }
    }
)

tavily_search_tool = None

async def get_all_tools():
    tools = await client.get_tools()

    for tool in tools:
        print(tool.name)

    return tools


async def get_tavily_search_tool():
    global tavily_search_tool

    if tavily_search_tool is not None:
        return tavily_search_tool

    tools = await client.get_tools()
    print("Available tools:")
    for tool in tools:
        print(tool.name)

    tavily_search_tool = next(tool
                              for tool in tools
                              if tool.name == "tavily_search"
                            )
    return tavily_search_tool


async def tavily_mcp_search(query: str):
    await get_tavily_search_tool()

    result = await tavily_search_tool.ainvoke(
        {
            "query": query
        }
    )
    return format_mcp_result(result)


def format_mcp_result(result) -> str:
    """
    MCP tools return a list of content blocks, e.g.
    [{"type": "text", "text": '{"results": [...]}'}].
    Convert that into a plain, readable string.
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

    if isinstance(data, dict) and "error" in data:
        detail = data.get("detail")
        if isinstance(detail, dict):
            detail = detail.get("error")
        status = data.get("status", "unknown")
        return f"Search failed (status {status}): {detail or data['error']}"

    results = data.get("results", []) if isinstance(data, dict) else []
    if not results:
        return text

    formatted = []

    for i, r in enumerate(results, 1):
        title = r.get("title", "N/A")
        url = r.get("url", "N/A")
        snippet = r.get("content") or r.get("snippet") or "N/A"

        if len(snippet) > 300:
            snippet = snippet[:300].rsplit(" ", 1)[0] + "..."

        formatted.append(f"{i}. {title}\nURL: {url}\nSnippet: {snippet}\n")

    return "\n\n".join(formatted)
    # print(result)



