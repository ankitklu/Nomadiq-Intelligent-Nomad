import os
import certifi
from dotenv import load_dotenv
load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from typing import TypedDict, Annotated
import asyncio
import json
import operator
import uuid

from mcp_client import tavily_mcp_search, aviation_mcp_call, extract_destination, forecast_mcp_search, weather_mcp_search

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    AnyMessage,
)

from langchain_groq import ChatGroq
# from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights
from mcp_client import tavily_mcp_search, aviation_mcp_call

def get_database_url():

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set.")

    if "sslmode" not in database_url:
        separator= "&" if "?" in database_url else "?"
        database_url += f"{separator}sslmode=require"

    return database_url

# url = get_database_url()
# print(url)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set.")


# ==========================
# LLM
# =========================

llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model="openai/gpt-oss-20b",
    temperature=0.7,
)

# ==========================
# State
# =========================

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    flight_results: str
    hotel_results: str
    weather_results: str
    itinerary: str
    llm_calls: int

# ==========================
# FLight Agent
# =========================

# async def flight_agent(state: TravelState):
#     query = state["user_query"]
#     flight_data = await search_flights(query)

#     return {
#         "flight_results": flight_data,
#         "messages": [
#             AIMessage(content=f"Flight search results for '{query}':\n\n{flight_data}")
#         ],
#         "llm_calls": state.get("llm_calls", 0) + 1
#     }

# Normalises free-form requests into a route the flight tool's parser understands
FLIGHT_ROUTE_PROMPT = """
Rewrite this travel request as a single flight route line, in exactly this form:

flights from <origin city> to <destination city>

Rules:
- Use the city that has the main international airport (e.g. Bali -> Denpasar, India -> Delhi, Japan -> Tokyo).
- If the request has no origin, return: flights to <destination city>
- Return only that one line, nothing else.

Request:
{query}
"""

# Flight Tool Router Prompt
FLIGHT_AGENT_PROMPT = """
You are a travel flight expert.

User Query:
{query}

Live Flight Data (AviationStack, today's flights; no fares):
{live_flights}

Use the live flight data where it is relevant. If it has no flights for this
route, say so briefly and recommend common connecting routes instead.

Generate:

1. Likely departure airport
2. Likely arrival airport
3. Airlines serving this route
4. Typical flight duration
5. Estimated airfare range
6. Peak season pricing warning
7. Booking advice

Return concise travel guidance.
"""

async def flight_agent(state: TravelState):
    print("\nINSIDE FLIGHT AGENT\n")

    query = state["user_query"]

    try:

        # The free AviationStack plan blocks the MCP reference endpoints
        # (list_airports / list_airlines), so use the live /flights endpoint instead
        route = await llm.ainvoke(FLIGHT_ROUTE_PROMPT.format(query=query))
        route_query = route.content.strip().splitlines()[0]

        print("\nFLIGHT ROUTE:", route_query)

        live_flights = await search_flights(route_query, limit=5)

        prompt = FLIGHT_AGENT_PROMPT.format(
            query=query,
            live_flights=live_flights[:4000]
        )

        response = await llm.ainvoke([
            SystemMessage(
                content="You are an expert travel flight planner."
            ),
            HumanMessage(content=prompt)
        ])

        flight_data = response.content

    except Exception as e:

        flight_data = f"Flight information unavailable: {str(e)}"

    return {
        "flight_results": flight_data,
        "messages": [
            AIMessage(
                content="Flight recommendations generated"
            )
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

# ==========================
# Hotel Agent
# =========================

def format_tavily_results(raw: str) -> str:
    """Turn Tavily MCP's JSON text into the numbered list the old tavily_tool produced."""

    try:
        results = json.loads(raw).get("results", [])
    except (ValueError, AttributeError):
        return raw

    if not results:
        return raw

    formatted = []

    for i, r in enumerate(results, 1):
        title = r.get("title", "N/A")
        url = r.get("url", "N/A")
        snippet = (r.get("content") or "N/A").strip()

        if len(snippet) > 300:
            snippet = snippet[:300].rsplit(" ", 1)[0] + "..."

        formatted.append(f"{i}. {title}\nURL: {url}\nSnippet: {snippet}\n")

    return "\n\n".join(formatted)


async def hotel_agent(state: TravelState):
    query = f"Best hotels for {state['user_query']}"

    try:
        hotel_results = format_tavily_results(await tavily_mcp_search(query))
    except Exception as e:
        hotel_results = f"Hotel information unavailable: {str(e)}"

    return {
        "hotel_results": hotel_results,
        "messages": [
            AIMessage(content=f"Hotel search results for '{query}':\n\n{hotel_results}")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

# =========================
# Weather Agent
# =========================

async def weather_agent(state: TravelState):

    try:

        city = await asyncio.to_thread(extract_destination, state["user_query"])

        weather_data, forecast_data = await asyncio.gather(
            weather_mcp_search(city),
            forecast_mcp_search(city),
        )

        weather_results = f"""
        Current Weather:
        {weather_data}

        Forecast:
        {forecast_data}
        """

    except Exception as e:

        weather_results = f"Weather information unavailable: {str(e)}"

    return {
        "weather_results": weather_results,
        "messages": [
            AIMessage(
                content="Weather information fetched"
            )
        ]
    }


# ==========================
# Itinerary Agent
# =========================

async def itinerary_agent(state: TravelState):
    itinerary_prompt = f"""
    Based on the following flight and hotel results, create a detailed travel itinerary for the user query '{state['user_query']}'.

    Flight Results:
    {state['flight_results']}

    Hotel Results:
    {state['hotel_results']}
    """

    response = await llm.ainvoke([
            SystemMessage(content="You are a expert travel planner."),
            HumanMessage(content=itinerary_prompt)
        ])

    return {
        "itinerary": response.content,
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

# ==========================
# Final Response Agent
# =========================

def final_agent(state: TravelState):
    final_prompt = f"""
Generate the final travel response for the user.

User Request:
{state['user_query']}

Flights:
{state['flight_results']}

Hotels:
{state['hotel_results']}

Weather:
{state['weather_results']}

Itinerary:
{state['itinerary']}

Format the final answer beautifully using these sections:

1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Weather Information
5. Day-by-Day Itinerary
6. Estimated Budget
7. Final Recommendations


Important:
- Be clear and practical.
- Mention that live flight API may not provide ticket prices if pricing is unavailable.
- Include weather-based travel advice.
- Keep the response useful for real travel planning.
"""

    response = llm.invoke([
        SystemMessage(content="You are a professional AI travel booking assistant."),
        HumanMessage(content=final_prompt)
    ])

    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

# ==========================
# Build a graph
# =========================

graph = StateGraph(TravelState)

graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("weather_agent", weather_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "weather_agent")
graph.add_edge("weather_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)

# ==========================
# Checkpointer / compiled graph
# =========================

DATABASE_URL = get_database_url()

# The async pool and checkpointer must be created inside a running event loop,
# so they are set up by init_travel_agent() (called from the FastAPI lifespan)
# rather than at import time.
_pool: AsyncConnectionPool | None = None
travel_graph = None
_init_lock = asyncio.Lock()


async def init_travel_agent():
    global _pool, travel_graph

    async with _init_lock:
        if travel_graph is not None:
            return

        _pool = AsyncConnectionPool(
            conninfo=DATABASE_URL,
            max_size=10,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
                "prepare_threshold": 0,
            },
            open=False,
        )
        await _pool.open()

        checkpointer = AsyncPostgresSaver(_pool)
        await checkpointer.setup()

        travel_graph = graph.compile(checkpointer=checkpointer)


async def close_travel_agent():
    global _pool, travel_graph

    if _pool is not None:
        await _pool.close()

    _pool = None
    travel_graph = None


async def run_travel_agent(user_input: str, thread_id: str | None = None):

    if travel_graph is None:
        await init_travel_agent()

    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable":{
            "thread_id": thread_id
        }
    }


    result = await travel_graph.ainvoke(
        {
            "messages":[
                HumanMessage(content=user_input)
            ],
            "user_query": user_input,
            "flight_results": "",
            "hotel_results": "",
            "weather_results":"",
            "itinerary": "",
            "llm_calls": 0
        },
        config = config
    )

    final_answer = result["messages"][-1].content

    return {
        "thread_id": thread_id,
        "answer": final_answer,
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather_results": result.get("weather_results",""),
        "itinerary": result.get("itinerary", ""),
        "llm_calls": result.get("llm_calls", 0)
    }
