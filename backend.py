import os
import certifi
from dotenv import load_dotenv
load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from typing import TypedDict, Annotated
import operator
import uuid

import psycopg
from psycopg.rows import dict_row

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    AnyMessage,
)

from langchain_groq import ChatGroq
from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights

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
    itinerary: str
    llm_calls: int

# ==========================
# FLight Agent
# =========================

def flight_agent(state: TravelState):
    query = state["user_query"]
    flight_data = search_flights(query)

    return {
        "flight_results": flight_data,
        "messages": [
            AIMessage(content=f"Flight search results for '{query}':\n\n{flight_data}")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

# ==========================
# Hotel Agent
# =========================

def hotel_agent(state: TravelState):
    query = f"Best hotels for {state['user_query']}"
    hotel_results = tavily_search(query)

    return {
        "hotel_results": hotel_results,
        "messages": [
            AIMessage(content=f"Hotel search results for '{query}':\n\n{hotel_results}")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

# ==========================
# Itinerary Agent
# =========================

def itinerary_agent(state: TravelState):
    itinerary_prompt = f"""
    Based on the following flight and hotel results, create a detailed travel itinerary for the user query '{state['user_query']}'.

    Flight Results:
    {state['flight_results']}

    Hotel Results:
    {state['hotel_results']}
    """

    response = llm.invoke([
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
    final_response_prompt = f"""
    Based on the following flight and hotel results, and the generated itinerary, create a final response for the user query '{state['user_query']}'.

    Flight Results:
    {state['flight_results']}

    Hotel Results:
    {state['hotel_results']}

    Itinerary:
    {state['itinerary']}
    """

    response = llm.invoke([
            SystemMessage(content="You are a expert travel planner."),
            HumanMessage(content=final_response_prompt)
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
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)

# ==========================
# Build a graph
# =========================

DATABASE_URL = get_database_url()

_conn = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)
checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)

def run_travel_agent(user_input: str, thread_id: str | None = None):

    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable":{
            "thread_id": thread_id
        }
    }


    result = travel_graph.invoke(
        {
            "messages":[
                HumanMessage(content=user_input)
            ],
            "user_query": user_input,
            "flight_results": "",
            "hotel_results": "",
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
        "itinerary": result.get("itinerary", ""),
        "llm_calls": result.get("llm_calls", 0)
    }
