"""Regression tests for runtime config validation."""
import unittest
from types import SimpleNamespace

from tests.stubs import install_dependency_stubs

install_dependency_stubs()

import main


def _base_config():
    return {
        'llm': {
            'base_url': 'https://api.openai.com/v1',
            'api_key': 'sk-real-llm',
            'model': 'gpt-4o',
            'annotate_model': 'gpt-4o-mini'
        },
        'embedding': {
            'base_url': 'https://api.openai.com/v1',
            'api_key': 'sk-real-emb',
            'model': 'text-embedding-3-small',
            'dimensions': 1536
        },
        'paths': {
            'input_file': 'data/input/示例小说.txt',
            'chapters_dir': 'data/chapters',
            'scenes_dir': 'data/scenes',
            'annotated_dir': 'data/annotated',
            'profiles_dir': 'data/profiles',
            'vector_db_path': 'vector_db',
            'log_dir': 'logs',
        }
    }


class ConfigValidationTests(unittest.TestCase):
    """Test runtime config validation behavior."""

    def test_step1_does_not_require_api_key(self):
        config = _base_config()
        config['llm']['api_key'] = 'sk-xxxxx'
        config['embedding']['api_key'] = 'sk-yyyyy'
        args = SimpleNamespace(step=1, input='data/input/示例小说.txt', config='config.yaml')

        main.validate_config(config, args)
        self.assertEqual(config['paths']['input_file'], 'data/input/示例小说.txt')

    def test_step2_requires_llm_key(self):
        config = _base_config()
        config['llm']['api_key'] = 'sk-xxxxx'
        args = SimpleNamespace(step=2, input='data/input/示例小说.txt', config='config.yaml')

        with self.assertRaises(ValueError):
            main.validate_config(config, args)

    def test_step1_missing_input_file_raises(self):
        config = _base_config()
        args = SimpleNamespace(step=1, input='data/input/不存在.txt', config='config.yaml')

        with self.assertRaises(FileNotFoundError):
            main.validate_config(config, args)

    def test_missing_configured_input_falls_back_to_sample(self):
        config = _base_config()
        config['paths']['input_file'] = 'data/input/不存在.txt'
        args = SimpleNamespace(step=1, input=None, config='config.yaml')

        main.validate_config(config, args)
        self.assertEqual(config['paths']['input_file'], 'data/input/示例小说.txt')

    def test_placeholder_key_detection(self):
        self.assertTrue(main._is_placeholder_api_key('sk-xxxxx'))
        self.assertTrue(main._is_placeholder_api_key('your-llm-api-key'))
        self.assertFalse(main._is_placeholder_api_key('sk-real-key'))


if __name__ == '__main__':
    unittest.main()
