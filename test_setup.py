"""Quick test script to verify the pipeline works."""
import os
import yaml


def check_dependencies():
    """Check if all dependencies are installed."""
    print("Checking dependencies...")

    required = [
        'openai',
        'qdrant_client',
        'yaml',
        'chardet',
        'thefuzz'
    ]

    missing = []

    for package in required:
        try:
            if package == 'yaml':
                import yaml
            elif package == 'thefuzz':
                from thefuzz import fuzz
            elif package == 'qdrant_client':
                from qdrant_client import QdrantClient
            else:
                __import__(package)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ✗ {package} (missing)")
            missing.append(package)

    if missing:
        print(f"\nMissing packages: {', '.join(missing)}")
        print("Install with: pip install -r requirements.txt")
        return False

    print("\nAll dependencies installed!")
    return True


def check_config():
    """Check if config is properly set up."""
    print("\nChecking configuration...")

    if not os.path.exists('config.yaml'):
        print("  ✗ config.yaml not found")
        return False

    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # Check LLM config
    llm_key = config.get('llm', {}).get('api_key', '')
    if llm_key == 'sk-xxxxx' or not llm_key:
        print("  ✗ LLM API key not configured")
        print("    Please edit config.yaml and set your LLM API key")
        return False
    else:
        print(f"  ✓ LLM API configured ({llm_key[:10]}...)")

    # Check embedding config
    emb_key = config.get('embedding', {}).get('api_key', '')
    if emb_key == 'sk-yyyyy' or not emb_key:
        print("  ✗ Embedding API key not configured")
        print("    Please edit config.yaml and set your Embedding API key")
        return False
    else:
        print(f"  ✓ Embedding API configured ({emb_key[:10]}...)")

    print("\nConfiguration looks good!")
    return True


def check_sample_file():
    """Check if sample novel exists."""
    print("\nChecking sample data...")

    sample_file = '/app/data/input/示例小说.txt'
    if os.path.exists(sample_file):
        print(f"  ✓ Sample novel found: {sample_file}")
        return True
    else:
        print(f"  ✗ Sample novel not found: {sample_file}")
        print("    Please add a novel file to /app/data/input/")
        return False


def main():
    """Run all checks."""
    print("=" * 60)
    print("  Novel Vectorization Pipeline - Quick Check")
    print("=" * 60)
    print()

    all_ok = True

    # Check dependencies
    if not check_dependencies():
        all_ok = False

    # Check config
    if not check_config():
        all_ok = False

    # Check sample file
    if not check_sample_file():
        all_ok = False

    print()
    print("=" * 60)

    if all_ok:
        print("  ✓ All checks passed!")
        print()
        print("  Ready to run! Try:")
        print("    python3 main.py --input data/input/示例小说.txt")
    else:
        print("  ✗ Some checks failed")
        print()
        print("  Please fix the issues above before running the pipeline")

    print("=" * 60)


if __name__ == '__main__':
    main()
