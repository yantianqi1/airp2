"""Test-only dependency stubs for optional third-party packages."""
import sys
import types


def install_dependency_stubs():
    """Install lightweight stubs so tests can import project modules."""
    if 'openai' not in sys.modules:
        openai_module = types.ModuleType('openai')

        class OpenAI:  # pragma: no cover - simple import stub
            def __init__(self, *args, **kwargs):
                pass

        openai_module.OpenAI = OpenAI
        sys.modules['openai'] = openai_module

    if 'thefuzz' not in sys.modules:
        thefuzz_module = types.ModuleType('thefuzz')

        class _Fuzz:  # pragma: no cover - import stub only
            @staticmethod
            def ratio(left, right):
                return 100 if left == right else 0

            @staticmethod
            def partial_ratio(left, right):
                return 100 if left in right or right in left else 0

        thefuzz_module.fuzz = _Fuzz
        sys.modules['thefuzz'] = thefuzz_module

    if 'qdrant_client.models' not in sys.modules:
        models_module = types.ModuleType('qdrant_client.models')

        class Distance:  # pragma: no cover - simple import stub
            COSINE = 'cosine'
            EUCLID = 'euclid'
            DOT = 'dot'

        class VectorParams:  # pragma: no cover
            def __init__(self, size, distance):
                self.size = size
                self.distance = distance

        class PointStruct:  # pragma: no cover
            def __init__(self, id, vector, payload):
                self.id = id
                self.vector = vector
                self.payload = payload

        class PayloadSchemaType:  # pragma: no cover
            KEYWORD = 'keyword'
            INTEGER = 'integer'

        class TextIndexParams:  # pragma: no cover
            pass

        class MatchAny:  # pragma: no cover
            def __init__(self, any):
                self.any = any

        class MatchValue:  # pragma: no cover
            def __init__(self, value):
                self.value = value

        class FieldCondition:  # pragma: no cover
            def __init__(self, key, match=None, range=None):
                self.key = key
                self.match = match
                self.range = range

        class Range:  # pragma: no cover
            def __init__(self, lte=None, gte=None):
                self.lte = lte
                self.gte = gte

        class Filter:  # pragma: no cover
            def __init__(self, must=None, should=None):
                self.must = must or []
                self.should = should or []

        models_module.Distance = Distance
        models_module.VectorParams = VectorParams
        models_module.PointStruct = PointStruct
        models_module.PayloadSchemaType = PayloadSchemaType
        models_module.TextIndexParams = TextIndexParams
        models_module.MatchAny = MatchAny
        models_module.MatchValue = MatchValue
        models_module.FieldCondition = FieldCondition
        models_module.Range = Range
        models_module.Filter = Filter
        sys.modules['qdrant_client.models'] = models_module

    if 'qdrant_client' not in sys.modules:
        qdrant_module = types.ModuleType('qdrant_client')

        class QdrantClient:  # pragma: no cover - import stub only
            def __init__(self, *args, **kwargs):
                pass

        qdrant_module.QdrantClient = QdrantClient
        qdrant_module.models = sys.modules['qdrant_client.models']
        sys.modules['qdrant_client'] = qdrant_module
