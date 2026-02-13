"""Example usage of the vectorized novel database."""
import json
import yaml
from qdrant_client import QdrantClient
from utils.embedding_client import EmbeddingClient


def load_config():
    """Load configuration."""
    with open('config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def example_search_by_character():
    """Example: Search scenes by character."""
    print("\n" + "=" * 60)
    print("Example 1: Search by Character")
    print("=" * 60)

    config = load_config()
    client = QdrantClient(path=config['paths']['vector_db_path'])
    collection_name = config['vector_db']['collection_name']

    # Search for scenes with specific character
    character_name = "林风"

    results = client.scroll(
        collection_name=collection_name,
        scroll_filter={
            "must": [
                {
                    "key": "characters",
                    "match": {"any": [character_name]}
                }
            ]
        },
        limit=5,
        with_payload=True,
        with_vectors=False
    )

    print(f"\nFound {len(results[0])} scenes with character '{character_name}':\n")

    for i, point in enumerate(results[0], 1):
        payload = point.payload
        print(f"{i}. [{payload['chapter_title']}] Scene {payload['scene_index']}")
        print(f"   Event: {payload['event_summary']}")
        print(f"   Characters: {', '.join(payload['characters'])}")
        print(f"   Location: {payload['location']}")
        print(f"   Emotion: {payload['emotion_tone']}")
        print()


def example_search_by_location():
    """Example: Search scenes by location."""
    print("\n" + "=" * 60)
    print("Example 2: Search by Location")
    print("=" * 60)

    config = load_config()
    client = QdrantClient(path=config['paths']['vector_db_path'])
    collection_name = config['vector_db']['collection_name']

    # Search for scenes at specific location
    location = "客栈"

    results = client.scroll(
        collection_name=collection_name,
        scroll_filter={
            "must": [
                {
                    "key": "location",
                    "match": {"value": location}
                }
            ]
        },
        limit=10,
        with_payload=True,
        with_vectors=False
    )

    print(f"\nFound {len(results[0])} scenes at location '{location}':\n")

    for i, point in enumerate(results[0], 1):
        payload = point.payload
        print(f"{i}. {payload['event_summary']}")
        print(f"   Chapter: {payload['chapter_title']}")
        print(f"   Characters: {', '.join(payload['characters'])}")
        print()


def example_semantic_search():
    """Example: Semantic search with query vector."""
    print("\n" + "=" * 60)
    print("Example 3: Semantic Search")
    print("=" * 60)

    config = load_config()
    client = QdrantClient(path=config['paths']['vector_db_path'])
    collection_name = config['vector_db']['collection_name']

    # Generate query vector
    embedding_client = EmbeddingClient(config)

    query_text = "林风和沈小姐在藏书楼寻找秘籍"
    print(f"\nQuery: {query_text}\n")

    query_vector = embedding_client.embed([query_text])[0]

    # Search
    results = client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=3
    )

    print(f"Top {len(results)} most relevant scenes:\n")

    for i, result in enumerate(results, 1):
        payload = result.payload
        score = result.score

        print(f"{i}. [Score: {score:.4f}] {payload['chapter_title']}")
        print(f"   Event: {payload['event_summary']}")
        print(f"   Characters: {', '.join(payload['characters'])}")
        print(f"   Location: {payload['location']}")
        print(f"   Text preview: {payload['text'][:100]}...")
        print()


def example_combined_filter():
    """Example: Combined filters (character + plot significance)."""
    print("\n" + "=" * 60)
    print("Example 4: Combined Filters")
    print("=" * 60)

    config = load_config()
    client = QdrantClient(path=config['paths']['vector_db_path'])
    collection_name = config['vector_db']['collection_name']

    # Search for high-significance scenes with specific character
    character = "林风"
    significance = "high"

    results = client.scroll(
        collection_name=collection_name,
        scroll_filter={
            "must": [
                {
                    "key": "characters",
                    "match": {"any": [character]}
                },
                {
                    "key": "plot_significance",
                    "match": {"value": significance}
                }
            ]
        },
        limit=5,
        with_payload=True,
        with_vectors=False
    )

    print(f"\nHigh-significance scenes with '{character}':\n")

    for i, point in enumerate(results[0], 1):
        payload = point.payload
        print(f"{i}. [{payload['chapter_title']}]")
        print(f"   Event: {payload['event_summary']}")
        print(f"   Emotion: {payload['emotion_tone']}")
        if payload.get('key_dialogues'):
            print(f"   Key dialogue: {payload['key_dialogues'][0]}")
        print()


def example_get_character_timeline():
    """Example: Get character's timeline."""
    print("\n" + "=" * 60)
    print("Example 5: Character Timeline")
    print("=" * 60)

    config = load_config()
    client = QdrantClient(path=config['paths']['vector_db_path'])
    collection_name = config['vector_db']['collection_name']

    character = "林风"

    # Get all scenes with this character, ordered by chapter and scene
    results = client.scroll(
        collection_name=collection_name,
        scroll_filter={
            "must": [
                {
                    "key": "characters",
                    "match": {"any": [character]}
                }
            ]
        },
        limit=100,
        with_payload=True,
        with_vectors=False
    )

    # Sort by chapter and scene index
    scenes = sorted(
        results[0],
        key=lambda x: (x.payload['chapter'], x.payload['scene_index'])
    )

    print(f"\n{character}'s Timeline ({len(scenes)} scenes):\n")

    for i, point in enumerate(scenes, 1):
        payload = point.payload
        print(f"{i}. [{payload['chapter_title']}] Scene {payload['scene_index']}")
        print(f"   {payload['event_summary']}")
        print()


def example_get_statistics():
    """Example: Get database statistics."""
    print("\n" + "=" * 60)
    print("Example 6: Database Statistics")
    print("=" * 60)

    config = load_config()
    client = QdrantClient(path=config['paths']['vector_db_path'])
    collection_name = config['vector_db']['collection_name']

    # Get collection info
    collection_info = client.get_collection(collection_name)

    print(f"\nCollection: {collection_name}")
    print(f"Total scenes: {collection_info.points_count}")
    print(f"Vector dimensions: {collection_info.config.params.vectors.size}")
    print(f"Distance metric: {collection_info.config.params.vectors.distance}")

    # Sample some scenes to get statistics
    results = client.scroll(
        collection_name=collection_name,
        limit=100,
        with_payload=True,
        with_vectors=False
    )

    # Count characters
    all_characters = set()
    all_locations = set()
    significance_counts = {'high': 0, 'medium': 0, 'low': 0}

    for point in results[0]:
        payload = point.payload
        all_characters.update(payload.get('characters', []))
        all_locations.add(payload.get('location', ''))
        sig = payload.get('plot_significance', 'medium')
        significance_counts[sig] += 1

    print(f"\nUnique characters: {len(all_characters)}")
    print(f"Unique locations: {len(all_locations)}")
    print(f"\nPlot significance distribution:")
    print(f"  High: {significance_counts['high']}")
    print(f"  Medium: {significance_counts['medium']}")
    print(f"  Low: {significance_counts['low']}")

    print(f"\nTop characters: {', '.join(list(all_characters)[:10])}")


def main():
    """Run all examples."""
    print("\n")
    print("=" * 60)
    print("  Novel Vector Database - Usage Examples")
    print("=" * 60)

    try:
        # Check if database exists
        config = load_config()
        db_path = config['paths']['vector_db_path']

        import os
        if not os.path.exists(db_path):
            print("\nError: Vector database not found!")
            print("Please run the pipeline first: python main.py --input /app/data/input/示例小说.txt")
            return

        # Run examples
        example_search_by_character()
        example_search_by_location()
        example_semantic_search()
        example_combined_filter()
        example_get_character_timeline()
        example_get_statistics()

        print("\n" + "=" * 60)
        print("  Examples completed!")
        print("=" * 60)
        print()

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
