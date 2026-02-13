"""LLM client for OpenAI-compatible API."""
import time
import json
import logging
import threading
from openai import OpenAI


logger = logging.getLogger(__name__)


class _SharedRateLimiter:
    """Thread-safe shared leaky-bucket limiter (start-time pacing).

    We space out *start times* for requests. Multiple requests can still be
    in-flight concurrently when latency exceeds the interval.
    """

    def __init__(self, rate_limit_per_minute):
        self._lock = threading.Lock()
        self._next_allowed_time = 0.0
        self._interval_s = self._calc_interval(rate_limit_per_minute)

    @staticmethod
    def _calc_interval(rate_limit_per_minute):
        if not rate_limit_per_minute:
            return 0.0
        if rate_limit_per_minute <= 0:
            return 0.0
        return 60.0 / float(rate_limit_per_minute)

    def update_rate_limit(self, rate_limit_per_minute):
        """Adopt the strictest (largest) interval seen for this limiter."""
        new_interval = self._calc_interval(rate_limit_per_minute)
        # 0 means "no limiting"; never relax a limiter once set.
        if new_interval <= 0:
            return
        with self._lock:
            if new_interval > self._interval_s:
                self._interval_s = new_interval

    def wait(self):
        interval = self._interval_s
        if interval <= 0:
            return

        with self._lock:
            now = time.time()
            if now < self._next_allowed_time:
                wait_s = self._next_allowed_time - now
                self._next_allowed_time += interval
            else:
                wait_s = 0.0
                self._next_allowed_time = now + interval

        if wait_s > 0:
            time.sleep(wait_s)


class LLMClient:
    """Client for calling LLM API."""
    _global_call_stats = {}
    _global_call_stats_lock = threading.Lock()
    _shared_rate_limiters = {}
    _shared_rate_limiters_lock = threading.Lock()

    def __init__(self, config):
        """Initialize LLM client with config."""
        self.base_url = config['llm']['base_url']
        self.api_key = config['llm']['api_key']
        self.model = config['llm']['model']
        self.annotate_model = config['llm']['annotate_model']
        self.max_retries = config['llm']['max_retries']
        self.retry_delay = config['llm']['retry_delay']
        self.rate_limit = config['llm'].get('rate_limit_per_minute', 30)

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )

        # Call tracking for statistics
        self.call_stats = {}
        self._rate_limiter = self._get_shared_rate_limiter(
            key=(self.base_url, self.api_key),
            rate_limit_per_minute=self.rate_limit,
        )

    @classmethod
    def _get_shared_rate_limiter(cls, key, rate_limit_per_minute):
        with cls._shared_rate_limiters_lock:
            limiter = cls._shared_rate_limiters.get(key)
            if limiter is None:
                limiter = _SharedRateLimiter(rate_limit_per_minute)
                cls._shared_rate_limiters[key] = limiter
            else:
                limiter.update_rate_limit(rate_limit_per_minute)
            return limiter

    def _track_call(self, model, tokens_used):
        """Track API call statistics."""
        if model not in self.call_stats:
            self.call_stats[model] = {
                'calls': 0,
                'tokens': 0
            }

        self.call_stats[model]['calls'] += 1
        self.call_stats[model]['tokens'] += tokens_used

        with LLMClient._global_call_stats_lock:
            if model not in LLMClient._global_call_stats:
                LLMClient._global_call_stats[model] = {
                    'calls': 0,
                    'tokens': 0
                }
            LLMClient._global_call_stats[model]['calls'] += 1
            LLMClient._global_call_stats[model]['tokens'] += tokens_used

    def call(self, prompt, model=None, temperature=0.7, response_format=None, system_prompt=None):
        """
        Call LLM API with retries.

        Args:
            prompt: User prompt
            model: Model to use (defaults to self.model)
            temperature: Sampling temperature
            response_format: Response format (e.g., {"type": "json_object"})
            system_prompt: Optional system prompt

        Returns:
            Response text or dict (if JSON response)
        """
        if model is None:
            model = self.model

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        for attempt in range(self.max_retries):
            try:
                self._rate_limiter.wait()

                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature
                }

                # Some providers don't support response_format
                if response_format:
                    kwargs["response_format"] = response_format

                response = self.client.chat.completions.create(**kwargs)

                content = response.choices[0].message.content

                # Track usage
                tokens_used = response.usage.total_tokens if hasattr(response, 'usage') else 0
                self._track_call(model, tokens_used)

                # Parse JSON if expected
                if response_format and response_format.get('type') == 'json_object':
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON response, attempt {attempt + 1}")
                        if attempt == self.max_retries - 1:
                            # Try to extract JSON from response
                            return self._extract_json(content)
                        continue

                return content

            except Exception as e:
                logger.error(f"LLM call failed (attempt {attempt + 1}): {e}")

                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise

        raise Exception(f"LLM call failed after {self.max_retries} retries")

    def _extract_json(self, text):
        """Try to extract JSON from text response."""
        # Try to find JSON in markdown code blocks
        import re
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass

        # Try to find any JSON object
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except:
                pass

        raise ValueError(f"Could not extract valid JSON from response: {text[:200]}")

    def get_stats(self):
        """Get call statistics."""
        return self.call_stats

    @classmethod
    def get_global_stats(cls):
        """Get call statistics aggregated across all instances."""
        with cls._global_call_stats_lock:
            return dict(cls._global_call_stats)

    @classmethod
    def reset_global_stats(cls):
        """Reset global call statistics."""
        with cls._global_call_stats_lock:
            cls._global_call_stats = {}
