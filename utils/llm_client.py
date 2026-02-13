"""LLM client for OpenAI-compatible API."""
import time
import json
import logging
from openai import OpenAI


logger = logging.getLogger(__name__)


class LLMClient:
    """Client for calling LLM API."""
    _global_call_stats = {}

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
        self.last_call_time = 0
        self.call_interval = 60.0 / self.rate_limit if self.rate_limit > 0 else 0

    def _rate_limit_wait(self):
        """Wait if necessary to respect rate limits."""
        if self.call_interval > 0:
            elapsed = time.time() - self.last_call_time
            if elapsed < self.call_interval:
                time.sleep(self.call_interval - elapsed)
        self.last_call_time = time.time()

    def _track_call(self, model, tokens_used):
        """Track API call statistics."""
        if model not in self.call_stats:
            self.call_stats[model] = {
                'calls': 0,
                'tokens': 0
            }

        self.call_stats[model]['calls'] += 1
        self.call_stats[model]['tokens'] += tokens_used

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
                self._rate_limit_wait()

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
        return cls._global_call_stats

    @classmethod
    def reset_global_stats(cls):
        """Reset global call statistics."""
        cls._global_call_stats = {}
