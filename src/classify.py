"""Citation classification from verifier existence output.

Maps the verifier's ``exists`` value ("true" / "false" / "out_of_scope") to a
human-readable label and reason. Used by src/detect.py and
scripts/classify_citations.py.
"""

VALID = "Valid/Verified"
HALLUCINATED = "Hallucinated"
MISMATCHED = "Mismatched Context/Format"
# A case whose reporter cite exists but whose name or year does not match it
# (set by src/detect.py from src.verifier.case_detail_mismatches).
WRONG_CASE_NAME = "Wrong Case Name"
WRONG_YEAR = "Wrong Year"


def classify(exists):
    if exists == "true":
        return VALID

    if exists == "false":
        return HALLUCINATED

    return MISMATCHED


def explain_reason(exists, classification):
    if classification == VALID:
        return "Citation matched an authority in the ground-truth corpus."

    if classification == HALLUCINATED:
        return "Citation did not match an authority in the ground-truth corpus."

    if exists == "out_of_scope":
        return "Citation is known to be real law but is outside the benchmark corpus."

    return "Citation could not be classified from the verifier output."
