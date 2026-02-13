"""Embedding client for OpenAI-compatible API."""
import time
import logging
from typing import List
from openai import OpenAI


logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Client for calling Embedding API."""
    _global_stats = {}

    def __init__(self, config):
        """Initialize Embedding client with config."""
        self.base_url = config['embedding']['base_url']
        self.api_key = config['embedding']['api_key']
        self.model = config['embedding']['model']
        self.dimensions = config['embedding']['dimensions']
        self.batch_size = config['embedding']['batch_size']
        self.max_retries = config['embedding']['max_retries']
        self.retry_delay = config['embedding']['retry_delay']

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )

        # Call tracking for statistics
        self.total_texts = 0
        self.total_calls = 0

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        all_embeddings = []

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_embeddings = self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a single batch with retries."""
        for attempt in range(self.max_retries):
            try:
                kwargs = {
                    "model": self.model,
                    "input": texts
                }

                # Some providers support dimensions parameter
                if self.dimensions:
                    kwargs["dimensions"] = self.dimensions

                response = self.client.embeddings.create(**kwargs)

                # Extract embeddings in correct order
                embeddings = [item.embedding for item in response.data]

                # Validate dimensions
                if embeddings and len(embeddings[0]) != self.dimensions:
                    logger.warning(
                        f"Expected {self.dimensions} dimensions, got {len(embeddings[0])}"
                    )

                # Track statistics
                self.total_texts += len(texts)
                self.total_calls += 1
                self._track_global_stats(len(texts))

                return embeddings

            except Exception as e:
                logger.error(f"Embedding call failed (attempt {attempt + 1}): {e}")

                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise

        raise Exception(f"Embedding call failed after {self.max_retries} retries")

    def get_stats(self):
        """Get call statistics."""
        return {
            'model': self.model,
            'total_calls': self.total_calls,
            'total_texts': self.total_texts
        }

    def _track_global_stats(self, text_count):
        """Track statistics aggregated across all instances."""
        if self.model not in EmbeddingClient._global_stats:
            EmbeddingClient._global_stats[self.model] = {
                'total_calls': 0,
                'total_texts': 0
            }

        EmbeddingClient._global_stats[self.model]['total_calls'] += 1
        EmbeddingClient._global_stats[self.model]['total_texts'] += text_count

    @classmethod
    def get_global_stats(cls):
        """Get statistics aggregated across all instances."""
        total_calls = 0
        total_texts = 0

        for stats in cls._global_stats.values():
            total_calls += stats['total_calls']
            total_texts += stats['total_texts']

        return {
            'models': cls._global_stats,
            'total_calls': total_calls,
            'total_texts': total_texts
        }

    @classmethod
    def reset_global_stats(cls):
        """Reset global embedding statistics."""
        cls._global_stats = {}
