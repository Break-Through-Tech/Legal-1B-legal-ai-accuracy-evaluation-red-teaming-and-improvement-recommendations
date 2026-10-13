import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CITATIONS_FILE = ROOT / "data" / "processed" / "citations.jsonl"
ANSWER_KEY_FILE = ROOT / "data" / "benchmark" / "answer-key.json"
OUTPUT_FILE = ROOT / "data" / "processed" / "existence-results.csv"


def normalize_text(text):
    if text is None:
        return ""

    text = str(text)
    text = text.replace("Alaska Stat.", "AS")
    text = text.replace("Alaska Civil Rule", "Civil Rule")
    text = text.replace("CIVIL RULE", "Civil Rule")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def citation_to_text(citation):
    cite_type = citation.get("type", "")
    
    if cite_type == "statute":
        return f"AS {citation.get('section', '')}{citation.get('subsection', '')}"
    
    if cite_type == "rule":
        family = citation.get("rule_family")
        number = citation.get("number", "")
        subsection = citation.get("subsection", "")
        if family == "civil":
            return f"Civil Rule {number}{subsection}"
        return f"Rule {number}{subsection}"
    
    if cite_type == "case":
        return citation.get("reporter_cite") or citation.get("raw_text", "")
    
    return citation.get("raw_text", "")


def collect_answer_key_citations(obj):
    results = []

    if isinstance(obj, dict):
        if "cite" in obj and "type" in obj:
            results.append({
                "cite": obj.get("cite"),
                "type": obj.get("type"),
                "exists": obj.get("exists"),
                "injected": obj.get("injected"),
            })

        for value in obj.values():
            results.extend(collect_answer_key_citations(value))

    elif isinstance(obj, list):
        for item in obj:
            results.extend(collect_answer_key_citations(item))

    return results


def main():
    with open(ANSWER_KEY_FILE, "r", encoding="utf-8") as f:
        answer_key = json.load(f)

    answer_entries = collect_answer_key_citations(answer_key)

    reference_lookup = {}
    for entry in answer_entries:
        normalized = normalize_text(entry["cite"])
        key = (entry["type"], normalized)
        reference_lookup[key] = entry

    rows = []

    with open(CITATIONS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            doc = json.loads(line)
            doc_id = doc.get("doc_id")

            for citation in doc.get("citations", []):
                citation_type = citation.get("type")
                raw_text = citation.get("raw_text", "")
                normalized_citation = normalize_text(citation_to_text(citation))

                key = (citation_type, normalized_citation)
                match = reference_lookup.get(key)

                if match:
                    exists_in_corpus = bool(match.get("exists"))
                    matched_reference = match.get("cite")
                    match_status = "matched_answer_key"
                else:
                    exists_in_corpus = False
                    matched_reference = ""
                    match_status = "not_found_in_answer_key"

                rows.append({
                    "doc_id": doc_id,
                    "citation_text": raw_text,
                    "citation_type": citation_type,
                    "normalized_citation": normalized_citation,
                    "exists_in_corpus": exists_in_corpus,
                    "matched_reference": matched_reference,
                    "match_status": match_status,
                })

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "doc_id",
                "citation_text",
                "citation_type",
                "normalized_citation",
                "exists_in_corpus",
                "matched_reference",
                "match_status",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Task 1 complete.")
    print(f"Rows written: {len(rows)}")
    print(f"Output file: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()