"""
Script to generate submission.jsonl for the 30 canonical test pairs in dataset/expanded/test_pairs.json.
"""

from __future__ import annotations
import json
from pathlib import Path
from bot import compose


def generate_submission(dataset_dir: Path, output_file: Path):
    test_pairs_path = dataset_dir / "test_pairs.json"
    if not test_pairs_path.exists():
        print(f"Error: {test_pairs_path} not found.")
        return

    with open(test_pairs_path) as f:
        pairs = json.load(f).get("pairs", [])

    categories = {}
    for cat_file in (dataset_dir / "categories").glob("*.json"):
        with open(cat_file) as f:
            data = json.load(f)
            categories[data["slug"]] = data

    merchants = {}
    for m_file in (dataset_dir / "merchants").glob("*.json"):
        with open(m_file) as f:
            data = json.load(f)
            merchants[data["merchant_id"]] = data

    customers = {}
    if (dataset_dir / "customers").exists():
        for c_file in (dataset_dir / "customers").glob("*.json"):
            with open(c_file) as f:
                data = json.load(f)
                customers[data["customer_id"]] = data

    triggers = {}
    for t_file in (dataset_dir / "triggers").glob("*.json"):
        with open(t_file) as f:
            data = json.load(f)
            triggers[data["id"]] = data

    results = []
    for pair in pairs:
        test_id = pair["test_id"]
        trg_id = pair["trigger_id"]
        m_id = pair["merchant_id"]
        c_id = pair.get("customer_id")

        trg = triggers.get(trg_id, {})
        m = merchants.get(m_id, {})
        cat_slug = m.get("category_slug", "dentists")
        cat = categories.get(cat_slug, {})
        c = customers.get(c_id) if c_id else None

        composed = compose(cat, m, trg, c)
        results.append({
            "test_id": test_id,
            "body": composed["body"],
            "cta": composed["cta"],
            "send_as": composed["send_as"],
            "suppression_key": composed["suppression_key"],
            "rationale": composed["rationale"],
        })

    with open(output_file, "w") as f:
        for res in results:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")

    print(f"Successfully generated {len(results)} submission lines in {output_file}")


if __name__ == "__main__":
    dataset_dir = Path("./dataset/expanded")
    output_file = Path("./submission.jsonl")
    generate_submission(dataset_dir, output_file)
