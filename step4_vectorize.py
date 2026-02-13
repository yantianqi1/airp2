"""Step 4: Vectorize scenes and store in Qdrant."""
import os
import json
import logging
import uuid
import re
from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams, PointStruct
from utils.embedding_client import EmbeddingClient


logger = logging.getLogger(__name__)


def should_run_step4(status, force=False):
    """Decide whether step4 should process a chapter."""
    if force:
        return status in {'annotated_done', 'vectorized', 'vectorize_failed'}

    return status == 'annotated_done'


class SceneVectorizer:
    """Vectorize scenes and store in vector database."""

    def __init__(self, config):
        """Initialize with config."""
        self.config = config
        self.embedding_client = EmbeddingClient(config)

        self.vector_db_path = config['paths']['vector_db_path']
        self.collection_name = config['vector_db']['collection_name']
        self.distance_metric = config['vector_db']['distance_metric']
        self.dimensions = config['embedding']['dimensions']

        # Initialize Qdrant client (local file mode)
        self.qdrant_client = QdrantClient(path=self.vector_db_path)

        # Create collection if not exists
        self._ensure_collection()

    def _ensure_collection(self):
        """Create collection if missing, or recreate when vector config changed."""
        collections = self.qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]

        distance_map = {
            'Cosine': Distance.COSINE,
            'Euclidean': Distance.EUCLID,
            'Dot': Distance.DOT
        }
        target_distance = distance_map.get(self.distance_metric, Distance.COSINE)

        if self.collection_name not in collection_names:
            logger.info(f"Creating collection: {self.collection_name}")
            self._create_collection(target_distance)
            return

        info = self.qdrant_client.get_collection(self.collection_name)
        vector_params = info.config.params.vectors
        current_size = getattr(vector_params, 'size', None)
        current_distance = getattr(vector_params, 'distance', None)

        if current_size != self.dimensions or current_distance != target_distance:
            logger.warning(
                "Collection %s config mismatch (size=%s, distance=%s), expected "
                "(size=%s, distance=%s). Recreating collection.",
                self.collection_name,
                current_size,
                current_distance,
                self.dimensions,
                target_distance,
            )
            self.qdrant_client.delete_collection(self.collection_name)
            self._create_collection(target_distance)
        else:
            logger.info(f"Collection {self.collection_name} already exists")
            self._create_indexes()

    def _create_collection(self, distance):
        """Create collection and payload indexes."""
        self.qdrant_client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.dimensions,
                distance=distance
            )
        )
        # Create payload indexes for filtering
        self._create_indexes()

    def _create_indexes(self):
        """Create payload indexes for efficient filtering."""
        from qdrant_client.models import PayloadSchemaType

        # Index for characters (keyword index)
        self._safe_create_payload_index(
            collection_name=self.collection_name,
            field_name="characters",
            field_schema=PayloadSchemaType.KEYWORD
        )

        # Index for location
        self._safe_create_payload_index(
            collection_name=self.collection_name,
            field_name="location",
            field_schema=PayloadSchemaType.KEYWORD
        )

        # Index for chapter
        self._safe_create_payload_index(
            collection_name=self.collection_name,
            field_name="chapter",
            field_schema=PayloadSchemaType.KEYWORD
        )

        # Numeric chapter index for spoiler filtering and range operations.
        self._safe_create_payload_index(
            collection_name=self.collection_name,
            field_name="chapter_no",
            field_schema=PayloadSchemaType.INTEGER
        )

        # Index for plot_significance
        self._safe_create_payload_index(
            collection_name=self.collection_name,
            field_name="plot_significance",
            field_schema=PayloadSchemaType.KEYWORD
        )

        # Entity tags used by filter retrieval channel in RP query.
        self._safe_create_payload_index(
            collection_name=self.collection_name,
            field_name="entity_tags",
            field_schema=PayloadSchemaType.KEYWORD
        )

        logger.info("Payload indexes created")

    def _safe_create_payload_index(self, **kwargs):
        """Create payload index and ignore duplicate definition failures."""
        try:
            self.qdrant_client.create_payload_index(**kwargs)
        except Exception as exc:
            field_name = kwargs.get("field_name", "unknown")
            logger.warning("Create payload index skipped for '%s': %s", field_name, exc)

    def vectorize_chapter(self, annotated_file):
        """
        Vectorize all scenes in an annotated chapter.

        Returns:
            Number of scenes processed
        """
        # Load annotated data
        with open(annotated_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        chapter_id = data['chapter_id']
        chapter_title = data['chapter_title']
        scenes = data['scenes']

        logger.info(f"Vectorizing {len(scenes)} scenes from {chapter_id}")

        # Prepare augmented texts for embedding
        augmented_texts = []
        for scene in scenes:
            augmented_text = self._create_augmented_text(scene)
            augmented_texts.append(augmented_text)

        # Generate embeddings in batches
        embeddings = self.embedding_client.embed(augmented_texts)

        if len(embeddings) != len(scenes):
            logger.error(f"Embedding count mismatch: {len(embeddings)} != {len(scenes)}")
            return 0

        # Reprocessing a chapter should replace previous chapter points instead
        # of appending duplicated vectors.
        self._delete_chapter_points(chapter_id)

        # Prepare points for Qdrant
        points = []
        for i, (scene, embedding) in enumerate(zip(scenes, embeddings)):
            scene_index = scene.get('scene_index', i)
            point = self._create_point(
                point_id=self._build_point_id(chapter_id, scene_index),
                scene=scene,
                embedding=embedding,
                chapter_id=chapter_id,
                chapter_title=chapter_title
            )
            points.append(point)

        # Upload to Qdrant
        self.qdrant_client.upsert(
            collection_name=self.collection_name,
            points=points
        )

        logger.info(f"Uploaded {len(points)} points to collection")

        return len(points)

    def _build_point_id(self, chapter_id, scene_index):
        """Build stable point id for deterministic upsert."""
        try:
            scene_index_int = int(scene_index)
        except (TypeError, ValueError):
            scene_index_int = 0
        raw_key = f"{chapter_id}:{scene_index_int:06d}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, raw_key))

    def _delete_chapter_points(self, chapter_id):
        """Delete existing points belonging to a chapter before re-upsert."""
        chapter_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="chapter",
                    match=models.MatchValue(value=chapter_id)
                )
            ]
        )
        self.qdrant_client.delete(
            collection_name=self.collection_name,
            points_selector=chapter_filter
        )
        logger.info(f"Cleared existing points for chapter: {chapter_id}")

    def _create_augmented_text(self, scene):
        """Create augmented text for better embedding."""
        metadata = scene.get('metadata', {})

        # Combine key information with original text
        parts = []

        # Add event summary
        if metadata.get('event_summary'):
            parts.append(metadata['event_summary'])

        # Add characters
        if metadata.get('characters'):
            parts.append(' '.join(metadata['characters']))

        # Add location
        if metadata.get('location'):
            parts.append(metadata['location'])

        # Add original text
        parts.append(scene['text'])

        return '\n'.join(parts)

    def _create_point(self, point_id, scene, embedding, chapter_id, chapter_title):
        """Create a Qdrant point from scene data."""
        metadata = scene.get('metadata', {})
        chapter_no = self._extract_chapter_no(chapter_id)
        entity_tags = self._infer_entity_tags(metadata, scene.get('text', ''))

        payload = {
            'text': scene['text'],
            'chapter': chapter_id,
            'chapter_no': chapter_no,
            'chapter_title': chapter_title,
            'scene_index': scene.get('scene_index', 0),
            'scene_summary': scene.get('scene_summary', ''),
            'char_count': scene.get('char_count', 0),

            # Metadata fields
            'characters': metadata.get('characters', []),
            'location': metadata.get('location', ''),
            'time_description': metadata.get('time_description', ''),
            'event_summary': metadata.get('event_summary', ''),
            'emotion_tone': metadata.get('emotion_tone', ''),
            'key_dialogues': metadata.get('key_dialogues', []),
            'character_relations': metadata.get('character_relations', []),
            'plot_significance': metadata.get('plot_significance', 'medium'),
            'aliases': metadata.get('characters', []),
            'entity_tags': entity_tags,
            'spoiler_level': chapter_no,
        }

        return PointStruct(
            id=point_id,
            vector=embedding,
            payload=payload
        )

    def _extract_chapter_no(self, chapter_id):
        """Extract numeric chapter index from chapter id."""
        matched = re.search(r'(\\d+)', str(chapter_id))
        if not matched:
            return 0
        try:
            return int(matched.group(1))
        except ValueError:
            return 0

    def _infer_entity_tags(self, metadata, scene_text):
        """Infer coarse tags for filter retrieval and analytics."""
        tags = set()

        text = f"{metadata.get('event_summary', '')} {metadata.get('scene_summary', '')} {scene_text}"
        if any(keyword in text for keyword in ['案', '捕', '审', '衙门', '查']):
            tags.add('办案')
        if any(keyword in text for keyword in ['朝', '帝', '官', '奏', '殿', '京城']):
            tags.add('朝堂')
        if any(keyword in text for keyword in ['修行', '功法', '元神', '佛门', '道门', '气机']):
            tags.add('修行')
        if any(keyword in text for keyword in ['战', '军', '兵', '杀']):
            tags.add('战斗')

        if not tags:
            tags.add('剧情')

        return sorted(tags)

    def get_stats(self):
        """Get vectorization statistics."""
        collection_info = self.qdrant_client.get_collection(self.collection_name)

        return {
            'collection_name': self.collection_name,
            'total_points': collection_info.points_count,
            'vector_dimensions': self.dimensions
        }


def run_step4(config, force=False):
    """Run step 4: vectorization."""
    chapters_dir = config['paths']['chapters_dir']
    annotated_dir = config['paths']['annotated_dir']
    index_file = os.path.join(chapters_dir, 'chapter_index.json')

    if not os.path.exists(index_file):
        logger.error("Chapter index not found. Run previous steps first.")
        return

    # Load chapter index
    with open(index_file, 'r', encoding='utf-8') as f:
        index_data = json.load(f)

    vectorizer = SceneVectorizer(config)

    total_scenes = 0
    total_chars = 0

    # Process each chapter
    chapters = index_data['chapters']
    for chapter_info in chapters:
        chapter_id = chapter_info['chapter_id']
        status = chapter_info.get('status')

        if status == 'vectorized' and not force:
            logger.info(f"Chapter {chapter_id} already vectorized, skipping")
            continue

        if not should_run_step4(status, force=force):
            logger.warning(f"Chapter {chapter_id} not annotated, skipping")
            continue

        # Process chapter
        annotated_file = os.path.join(
            annotated_dir,
            chapter_info.get('annotated_file', '')
        )

        if not os.path.exists(annotated_file):
            logger.error(f"Annotated file not found: {annotated_file}")
            continue

        try:
            num_scenes = vectorizer.vectorize_chapter(annotated_file)

            # Update status
            chapter_info['status'] = 'vectorized'
            total_scenes += num_scenes

            # Read file to get char count
            with open(annotated_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for scene in data['scenes']:
                    total_chars += scene.get('char_count', 0)

        except Exception as e:
            logger.error(f"Failed to vectorize chapter {chapter_id}: {e}")
            chapter_info['status'] = 'vectorize_failed'

    # Save updated index
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    # Print statistics
    stats = vectorizer.get_stats()
    avg_length = total_chars / total_scenes if total_scenes > 0 else 0

    logger.info("=" * 50)
    logger.info("Vectorization Complete")
    logger.info(f"Total scenes: {total_scenes}")
    logger.info(f"Total characters: {total_chars:,}")
    logger.info(f"Average scene length: {avg_length:.0f} characters")
    logger.info(f"Collection: {stats['collection_name']}")
    logger.info(f"Total points in DB: {stats['total_points']}")
    logger.info("=" * 50)

    return stats


if __name__ == '__main__':
    import yaml

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    run_step4(config, force=True)
