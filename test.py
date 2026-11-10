import asyncio

from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights
from backend import run_travel_agent, close_travel_agent

# from mcp_client_test import get_all_tools
from mcp_client import get_all_tools


# async def main():
 

#     # res = await search_flights("Plan a 7 days Nepal Trip from India")
#     # print(res)

#     # user_input = input("Enter your travel query: ")

#     # response = await run_travel_agent(
#     #     user_input=user_input,
#     #     thread_id = "test_user"
#     # )

#     # print("\n Final Response: \n")
#     # print(response["answer"])

#     await close_travel_agent()


if __name__ == "__main__":
    # asyncio.run(get_all_tools())

    # tavily_search
    # tavily_extract
    # tavily_crawl
    # tavily_map
    # tavily_research

    # asyncio.run(run_mcp_search("Latest News on NVDIA CEO"))

    asyncio.run(get_all_tools())
