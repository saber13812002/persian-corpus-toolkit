"""
Phase 3: HuggingFace Upload Script
Uploads the corpus and dataset to HuggingFace Hub.
Run: python upload_to_hf.py --token YOUR_HF_TOKEN
"""

import os, sys, json, argparse
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / 'output'


def upload(token, username=None, repo_name="thesaurus-rational-sciences"):
    """Upload corpus and dataset files to HuggingFace Hub."""
    
    try:
        from huggingface_hub import HfApi, create_repo, upload_file, upload_folder
    except ImportError:
        print("❌ huggingface_hub not installed.")
        print("   Install: pip install huggingface_hub")
        return False
    
    api = HfApi(token=token)
    
    # ── Create repo ──
    repo_id = f"{username}/{repo_name}" if username else repo_name
    
    print(f"Creating/connecting to repo: {repo_id}")
    try:
        create_repo(repo_id, token=token, exist_ok=True, repo_type="dataset")
        print(f"  ✅ Repo ready")
    except Exception as e:
        print(f"  ⚠️ Repo creation: {e}")
    
    # ── Upload files ──
    files_to_upload = [
        "thesaurus_raw_corpus.txt",
        "thesaurus_corpus.jsonl",
        "thesaurus_terms.txt",
        "thesaurus_dataset_chatml.jsonl",
        "thesaurus_dataset_alpaca.jsonl",
        "thesaurus_dataset_completion.jsonl",
        "README.md",
    ]
    
    uploaded = 0
    for filename in files_to_upload:
        filepath = OUTPUT_DIR / filename
        if not filepath.exists():
            print(f"  ⚠️ {filename}: not found, skipping")
            continue
        
        try:
            upload_file(
                path_or_fileobj=str(filepath),
                path_in_repo=filename,
                repo_id=repo_id,
                token=token,
                repo_type="dataset",
            )
            print(f"  ✅ Uploaded: {filename}")
            uploaded += 1
        except Exception as e:
            print(f"  ❌ {filename}: {e}")
    
    print(f"\n{'='*50}")
    print(f"Upload complete: {uploaded}/{len(files_to_upload)} files")
    print(f"Dataset URL: https://huggingface.co/datasets/{repo_id}")
    
    return uploaded > 0


def main():
    parser = argparse.ArgumentParser(description="Upload thesaurus corpus to HuggingFace")
    parser.add_argument("--token", required=True, help="HuggingFace API token")
    parser.add_argument("--username", help="HuggingFace username (optional, uses token owner)")
    parser.add_argument("--repo", default="thesaurus-rational-sciences", help="Repository name")
    
    args = parser.parse_args()
    
    # Check if corpus exists
    required_files = [
        OUTPUT_DIR / "thesaurus_raw_corpus.txt",
        OUTPUT_DIR / "thesaurus_dataset_chatml.jsonl",
    ]
    missing = [f for f in required_files if not f.exists()]
    if missing:
        print("❌ Corpus files not found. Run build_corpus.py and build_dataset.py first.")
        print(f"   Missing: {missing}")
        sys.exit(1)
    
    upload(args.token, args.username, args.repo)


if __name__ == '__main__':
    main()
