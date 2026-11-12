import asyncio
import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.tools.human_tools import ask_human

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

APP_NAME = "human_pause_test"
USER_ID = "tester"
QUESTION = "Was the authentication token expired?"

agent = Agent(
    name="human_pause_tester",
    model=LiteLlm(model="openai/gpt-4o-mini"),
    description="Asks a human one question, then reports the answer.",
    instruction=(
        "You investigate an HTTP 401 failure.\n"
        "Call ask_human exactly once before you answer.\n"
        f"Use this exact question: {QUESTION}\n"
        "After the human answers, report their answer clearly.\n"
        "Do not guess the cause before the human answers."
    ),
    tools=[ask_human],
)


async def main():
    service = InMemorySessionService()
    session = await service.create_session(app_name=APP_NAME, user_id=USER_ID)
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=service)

    message = types.Content(
        role="user",
        parts=[types.Part(text="Investigate my HTTP 401 failure.")],
    )

    confirmation_call = None

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=message,
    ):
        for call in event.get_function_calls():
            if call.name == "adk_request_confirmation":
                confirmation_call = call

    if confirmation_call is None:
        raise RuntimeError("Agent did not request human input")

    print("ADK PAUSED")
    print(
        "Question:",
        confirmation_call.args["toolConfirmation"]["hint"],
    )

    # Simulate the human answering in React.
    answer = input("Your answer: ").strip()
    if not answer:
        raise ValueError("Answer cannot be empty")

    # Resume the same ADK session.
    response_message = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=confirmation_call.id,
                    name="adk_request_confirmation",
                    response={
                        "confirmed": True,
                        "payload": {"answer": answer},
                    },
                )
            )
        ],
    )

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=response_message,
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts or []:
                if part.text:
                    print("Agent:", part.text)


asyncio.run(main())
