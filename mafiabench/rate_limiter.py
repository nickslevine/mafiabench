"""Rate limiter for controlling API request rates globally."""

import asyncio
import time
from typing import Optional, List, Tuple

# import logging
from loguru import logger

# logger = logging.getLogger(__name__)


class GlobalRateLimiter:
    """A global rate limiter using token bucket algorithm."""

    _instance: Optional["GlobalRateLimiter"] = None

    def __init__(self, requests_per_second: float):
        """Initialize the rate limiter.

        Args:
            requests_per_second: Maximum number of requests allowed per second
        """
        self._semaphore = asyncio.Semaphore(1)  # For thread-safe token updates
        self.requests_per_second = requests_per_second
        self._last_update = time.time()
        self._tokens = requests_per_second  # Start with full bucket

        # Statistics tracking
        self._log_interval = 10.0  # Log every 10 seconds if there's rate limiting
        self._last_log_time = time.time()

        # Rolling window stats tracking
        self._request_history: List[
            Tuple[float, float]
        ] = []  # Explicitly type the list
        self._window_size = 10.0  # Keep 10 seconds of history

    @classmethod
    def initialize(cls, requests_per_second: float) -> "GlobalRateLimiter":
        """Initialize the global rate limiter instance.

        Args:
            requests_per_second: Maximum number of requests allowed per second

        Returns:
            The global rate limiter instance
        """
        if cls._instance is None:
            cls._instance = cls(requests_per_second)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "GlobalRateLimiter":
        """Get the global rate limiter instance.

        Returns:
            The global rate limiter instance

        Raises:
            RuntimeError: If the rate limiter hasn't been initialized
        """
        if cls._instance is None:
            raise RuntimeError("GlobalRateLimiter not initialized")
        return cls._instance

    def _cleanup_old_stats(self, current_time: float) -> None:
        """Remove stats older than the window size."""
        cutoff_time = current_time - self._window_size
        self._request_history = [
            (ts, wait) for ts, wait in self._request_history if ts > cutoff_time
        ]

    def _log_stats_if_needed(self) -> None:
        """Log rate limiting statistics if enough time has passed."""
        current_time = time.time()
        elapsed = current_time - self._last_log_time

        if elapsed >= self._log_interval:
            # Clean up old stats first
            self._cleanup_old_stats(current_time)

            # Calculate stats for the last window_size seconds
            total_requests = len(self._request_history)
            rate_limited_reqs = [
                (ts, wait) for ts, wait in self._request_history if wait > 0
            ]
            rate_limited_count = len(rate_limited_reqs)

            # Only log if there were rate-limited requests in this window
            if rate_limited_count > 0:
                total_wait_time = sum(wait for _, wait in rate_limited_reqs)
                percentage = (rate_limited_count / total_requests) * 100
                avg_wait = total_wait_time / rate_limited_count

                logger.warning(
                    f"Rate Limiting Stats (last {self._window_size:.1f}s):\n"
                    f"  Total Requests: {total_requests}\n"
                    f"  Rate Limited: {rate_limited_count} ({percentage:.1f}%)\n"
                    f"  Total Wait Time: {total_wait_time:.1f}s\n"
                    f"  Avg Wait Time: {avg_wait:.2f}s per limited request\n"
                    f"  Current RPS: {self.requests_per_second}"
                )
            # else:
            #     logger.warning(
            #         f"Rate Limiting Stats (last {self._window_size:.1f}s):\n"
            #         f"  Requests per second: {total_requests / 10.0}\n"
            #         f"  Current RPS: {self.requests_per_second}"
            #     )
            self._last_log_time = current_time

    async def acquire(self) -> None:
        """Acquire permission to make an API request."""
        current_time = time.time()
        wait_time = 0.0

        async with self._semaphore:
            # Add tokens based on elapsed time
            elapsed = current_time - self._last_update
            new_tokens = elapsed * self.requests_per_second
            self._tokens = min(self.requests_per_second, self._tokens + new_tokens)

            # Calculate wait time if needed
            if self._tokens < 1:
                wait_time = (1 - self._tokens) / self.requests_per_second

            # Update token count and timestamp
            self._tokens -= 1
            self._last_update = current_time

        # Record this request in our history
        self._request_history.append((current_time, wait_time))

        # Clean up old stats and log if needed
        self._cleanup_old_stats(current_time)
        self._log_stats_if_needed()

        # Wait if necessary
        if wait_time > 0:
            await asyncio.sleep(wait_time)
