import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from groq import AsyncGroq, APIError, APIConnectionError
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("SwiggyMCPClient")

load_dotenv(override=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEFAULT_MODEL = "openai/gpt-oss-20b"

if not GROQ_API_KEY:
    logger.error("GROQ_API_KEY is missing! Please set it in your .env file.")

# Official AsyncGroq client — no base_url needed!
llm_client = AsyncGroq(api_key=GROQ_API_KEY)

SERVER_SCRIPT = str(Path(__file__).parent / "mcp_server.py")
SRC_DIR = str(Path(__file__).parent)


def mcp_tools_to_openai(mcp_tools) -> list[dict]:
    """Convert MCP Tool objects into function-calling schema format."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema,
            },
        }
        for tool in mcp_tools
    ]


async def run_agent_query(user_query: str, model: str = DEFAULT_MODEL) -> dict:
    """
    Connects to the Swiggy MCP Server, runs the agentic tool-calling loop,
    and returns structured telemetry with graceful error handling.
    """
    start_time = time.perf_counter()
    tools_called: list[str] = []
    tool_errors: list[str] = []
    total_tokens = 0
    final_answer = ""

    env = os.environ.copy()
    env["PYTHONPATH"] = SRC_DIR

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[SERVER_SCRIPT],
        env=env,
    )

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                tools_response = await session.list_tools()
                openai_tools = mcp_tools_to_openai(tools_response.tools)
                logger.info(f"Connected to MCP Server. Loaded {len(openai_tools)} tools.")

                messages: list[dict] = [
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful Swiggy AI assistant. Use the provided MCP tools to help "
                            "users search food, order Instamart groceries, track/cancel orders, request refunds, "
                            "apply coupons, or message delivery riders. If required info like an order ID is missing, "
                            "ask the user instead of guessing."
                        ),
                    },
                    {"role": "user", "content": user_query},
                ]

                for turn in range(5):
                    try:
                        response = await llm_client.chat.completions.create(
                            model=model,
                            messages=messages,  # type: ignore
                            tools=openai_tools,  # type: ignore
                            tool_choice="auto",
                            temperature=0.0,
                        )
                    except APIError as api_err:
                        logger.error(f"Groq APIError (Status {api_err.status_code}): {api_err.message}")
                        tool_errors.append(f"LLM_API_ERROR ({api_err.status_code}): {api_err.message}")
                        break
                    except APIConnectionError as conn_err:
                        logger.error(f"Groq Connection Error: {conn_err}")
                        tool_errors.append(f"LLM_CONN_ERROR: {conn_err}")
                        break

                    if response.usage:
                        total_tokens += response.usage.total_tokens

                    msg = response.choices[0].message
                    messages.append(msg.model_dump(exclude_none=True))

                    if not msg.tool_calls:
                        final_answer = msg.content or ""
                        break

                    for tc in msg.tool_calls:
                        t_name = tc.function.name
                        t_args = json.loads(tc.function.arguments or "{}")
                        tools_called.append(t_name)
                        logger.info(f"Turn {turn + 1} -> Calling MCP Tool: {t_name}({t_args})")

                        try:
                            result = await session.call_tool(t_name, arguments=t_args)
                            output_text = "\n".join(
                                c.text for c in result.content if hasattr(c, "text")
                            )
                            if result.is_error:
                                logger.warning(f"Tool '{t_name}' returned error: {output_text}")
                                tool_errors.append(f"{t_name}: {output_text}")
                        except Exception as e:
                            logger.exception(f"Unexpected failure executing tool '{t_name}'")
                            output_text = f"MCP Execution Error: {str(e)}"
                            tool_errors.append(f"{t_name}: {str(e)}")

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": output_text,
                        })

    except Exception as session_err:
        logger.exception("Fatal MCP Client/Server transport failure")
        tool_errors.append(f"TRANSPORT_ERROR: {str(session_err)}")

    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

    return {
        "query": user_query,
        "tools_called": tools_called,
        "tool_errors": tool_errors,
        "latency_ms": latency_ms,
        "total_tokens": total_tokens,
        "cost_usd": 0.0,
        "final_answer": final_answer,
    }


if __name__ == "__main__":
    async def main():
        test_queries = [
            "Where is my order SWG-101 right now?",
            "I want something light for an upset stomach under ₹200.",
            "Check order SWG-105. If it is delayed, cancel it.",
        ]
        for q in test_queries:
            print(f"\n🧑 Query: {q}")
            res = await run_agent_query(q)
            print(f"🛠️  Tools Called: {res['tools_called']}")
            if res["tool_errors"]:
                print(f"🚨 Errors: {res['tool_errors']}")
            print(f"⏱️  Latency: {res['latency_ms']} ms | 🪙 Tokens: {res['total_tokens']}")
            print(f"🤖 Answer: {res['final_answer']}")

    asyncio.run(main())
