from tavily import TavilyClient
import os

from dotenv import load_dotenv

load_dotenv()

client = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)


def tavily_search(query: str):
    """
    Search for a location using the Tavily API.

    Args:
        query (str): The search query (e.g., city name, airport code).
    """

    response = client.search(
        query=query,
        max_results=5,  # You can adjust the number of results as needed

    )

    results = []

    for i, r in enumerate(response["results"],1):
        title = r.get("title", "N/A")
        url = r.get("url", "N/A")
        snippet = r.get("snippet", "N/A")

        if(len(snippet) > 300):
            snippet = snippet[:300].rsplit(' ', 1)[0] + "..."

        results.append(f"{i}. {title}\nURL: {url}\nSnippet: {snippet}\n")

    return "\n\n".join(results)

