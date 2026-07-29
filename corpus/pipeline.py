"""
Master pipeline: Corpus → Dataset → (optional) Upload
Run: python pipeline.py [--token HF_TOKEN] [--username HF_USERNAME]
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from build_corpus import build_corpus
from build_dataset import build_dataset

print("=" * 60)
print("📚 Thesaurus Corpus Pipeline")
print("=" * 60)

# Step 1: Corpus
print("\n[1/2] Building raw corpus...")
build_corpus()

# Step 2: Dataset
print("\n[2/2] Building instruction dataset...")
build_dataset()

print("\n" + "=" * 60)
print("✅ Pipeline complete!")
print("=" * 60)
print(f"\nOutput directory: {os.path.join(os.path.dirname(__file__), 'output')}")
print("\nTo upload to HuggingFace:")
print("  python upload_to_hf.py --token YOUR_HF_TOKEN --username YOUR_USERNAME")
