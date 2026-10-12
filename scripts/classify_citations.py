import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = ROOT / "data" / "processed" / "existence-results.csv"
OUTPUT_FILE = ROOT / "data" / "processed" / "task2-classified-citations.csv"


def parse_bool(value):
    return str(value).strip().lower() == "true"


def classify(row):
    exists = parse_bool(row.get("exists_in_corpus", ""))
    match_status = row.get("match_status", "").strip()

    if match_status == "matched_answer_key" and exists:
        return "Valid/Verified"

    if match_status == "matched_answer_key" and not exists:
        return "Hallucinated"

    return "Mismatched Context/Format"


def explain_reason(row, classification):
    if classification == "Valid/Verified":
        return "Citation matched the answer key and exists in the benchmark reference."

    if classification == "Hallucinated":
        return "Citation matched the answer key, but the benchmark marks it as not existing."

    return "Citation was not found in the answer key, so it needs review for formatting, context, or extraction mismatch."


def main():
    rows = []

    with open(INPUT_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            classification = classify(row)
            row["classification"] = classification
            row["reason"] = explain_reason(row, classification)
            rows.append(row)

    fieldnames = list(rows[0].keys())

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("Task 2 complete.")
    print(f"Rows written: {len(rows)}")
    print(f"Output file: {OUTPUT_FILE}")

    counts = {}
    for row in rows:
        label = row["classification"]
        counts[label] = counts.get(label, 0) + 1

    print("Classification summary:")
    for label, count in counts.items():
        print(f"{label}: {count}")


if __name__ == "__main__":
    main()