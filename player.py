from mafia import PlayerName, Role
from openai import AsyncOpenAI
from rate_limiter import GlobalRateLimiter
import time
from loguru import logger
import os
from typing import List
from openai.types.chat import ChatCompletionMessageParam


def setup_async_openai_api() -> AsyncOpenAI:
    """Set up and return the AsyncOpenAI client configured for OpenRouter."""
    api_key = os.environ.get("OPEN_ROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OPEN_ROUTER_API_KEY environment variable not set. "
            "Please set it before running the program."
        )

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    return client


class Player:
    def __init__(
        self, name: PlayerName, role: Role, model: str, temperature: float = 0.7
    ):
        self.name: PlayerName = name
        self.role = role
        self.model = model
        self.temperature = temperature
        self.client = setup_async_openai_api()
        self.alive = True
        self.total_response_time = 0.0
        self.message_count = 0
        self.invalid_response_count = 0
        self.knowledge_base = ""

    def __str__(self) -> str:
        return f"{self.name} (role: {self.role}, model={self.model})"

    def __repr__(self) -> str:
        return self.__str__()

    async def get_response(
        self, prompt: str, max_tokens: int = 1000, retry_count: int = 3
    ) -> str:
        """
        Get a response from the LLM API asynchronously.

        Args:
            prompt: The prompt to send to the model
            max_tokens: Maximum tokens in the response
            retry_count: Number of retries on API failure

        Returns:
            The model's response as a string
        """
        attempts = 0
        rate_limiter = GlobalRateLimiter.get_instance()

        while attempts < retry_count:
            try:
                start_time = time.time()

                # Acquire rate limit before making the request
                await rate_limiter.acquire()

                msgs: List[ChatCompletionMessageParam] = [
                    {
                        "role": "system",
                        "content": f"You are player {self.name} in a game of Mafia. Your role is {self.role or 'not yet assigned'}. Always identify as {self.name} when making decisions.",
                    },
                    {"role": "user", "content": prompt},
                ]

                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=msgs,
                    max_tokens=max_tokens,
                    temperature=self.temperature,
                )
                self.total_response_time += time.time() - start_time
                self.message_count += 1
                if len(response.choices) == 0:
                    logger.error(f"Failed response: {response}")
                content = response.choices[0].message.content
                return content.strip() if content else ""
            except Exception as e:
                logger.error(f"API call failed: {str(e)}")
                attempts += 1
                if attempts == retry_count:
                    logger.error("Max retries reached. Returning generic response.")
                    return "I pass my turn."

        return "I pass my turn."  # Fallback response

    def update_knowledge_base(self, knowledge_base: str) -> None:
        self.knowledge_base = knowledge_base
