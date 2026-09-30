"""Format-robustness probes: citation variants a real generator (or a real brief) produces
that the benchmark's own strings under-represent. Each probe is one sentence and the
canonical key(s) a correct extractor should return.

  python robustness.py [--out results/robustness.csv]
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from extractors import EXTRACTORS, canonical

NBSP = " "

PROBES = [
    # (group, variant, sentence, expected canonical keys)
    ("statute", "benchmark form", "Under AS 25.24.150(c), the court weighs the factors.", {"AS 25.24.150(c)"}),
    ("statute", "no subsection", "Consistent with AS 25.20.090, custody is decided on best interests.", {"AS 25.20.090"}),
    ("statute", "non-breaking space (common in Word)", f"Under AS{NBSP}25.24.150(c), the court weighs the factors.", {"AS 25.24.150(c)"}),
    ("statute", "nested subsection", "Under AS 18.66.100(c)(14), the court may order relief.", {"AS 18.66.100(c)(14)"}),
    ("statute", "two subsections joined", "Under AS 25.24.150(c) and (d), the court weighs the factors.", {"AS 25.24.150(c)", "AS 25.24.150(d)"}),
    ("statute", "Bluebook form", "See Alaska Stat. § 25.24.150 (2024).", {"AS 25.24.150"}),
    ("statute", "section range", "See AS 25.24.150-.160.", {"AS 25.24.150", "AS 25.24.160"}),
    ("statute", "space before subsection", "Under AS 25.24.150 (c), the court weighs the factors.", {"AS 25.24.150(c)"}),
    ("rule", "benchmark form", "Under Civil Rule 90.3(a), support is income-based.", {"civ 90.3(a)"}),
    ("rule", "bare Rule", "Under Rule 90.3, support is income-based.", {"civ 90.3"}),
    ("rule", "evidence rule, benchmark form", "Alaska R. Evid. 505(a) governs the privilege.", {"evid 505(a)"}),
    ("rule", "corpus form", "Alaska R. Civ. P. 90.3(a) governs support.", {"civ 90.3(a)"}),
    ("rule", "Evidence Rule N", "Evidence Rule 404(b) bars propensity evidence.", {"evid 404(b)"}),
    ("rule", "Alaska Civil Rule N", "Under Alaska Civil Rule 90.3, support is income-based.", {"civ 90.3"}),
    ("rule", "plural Rules N and M", "Civil Rules 90.3 and 90.4 govern support.", {"civ 90.3", "civ 90.4"}),
    ("rule", "nested subsection", "Under Civil Rule 90.3(a)(1), income is adjusted.", {"civ 90.3(a)(1)"}),
    ("case", "benchmark form", "Dunn v. Jones, 451 P.3d 375 (Alaska 2019).", {"451 P.3d 375"}),
    ("case", "prose prefix (key strings carry these)", "In Dunn v. Jones, 451 P.3d 375 (Alaska 2019), the court held.", {"451 P.3d 375"}),
    ("case", "pin cite", "Dunn v. Jones, 451 P.3d 375, 380 (Alaska 2019).", {"451 P.3d 375"}),
    ("case", "initialized pseudonyms", "Sarah D. v. John D., 352 P.3d 419 (Alaska 2015).", {"352 P.3d 419"}),
    ("case", "In re caption", "In re Adoption of S.K.L.H., 204 P.3d 320 (Alaska 2009).", {"204 P.3d 320"}),
    ("case", "State agency party", "State, Dep't of Revenue, Child Support Servs. Div. v. Kovac, 984 P.2d 1109 (Alaska 1999).", {"984 P.2d 1109"}),
    ("case", "non-breaking space in reporter", f"Dunn v. Jones, 451{NBSP}P.3d{NBSP}375 (Alaska 2019).", {"451 P.3d 375"}),
    ("case", "spaced reporter 'P. 3d'", "Dunn v. Jones, 451 P. 3d 375 (Alaska 2019).", {"451 P.3d 375"}),
    ("case", "string cite, two cases", "See Dunn v. Jones, 451 P.3d 375 (Alaska 2019); Layne v. Niles, 632 P.2d 234 (Alaska 1981).", {"451 P.3d 375", "632 P.2d 234"}),
]


def run():
    rows = []
    for group, variant, text, expected in PROBES:
        row = {"group": group, "variant": variant, "text": text.replace(NBSP, "[nbsp]"), "expected": "; ".join(sorted(expected))}
        for name, fn in EXTRACTORS.items():
            got = {k for m in fn(text) if (k := canonical(m.raw, m.type))}
            found = expected & got
            row[name] = "pass" if found == expected else ("partial" if found else "miss")
            row[f"{name}_got"] = "; ".join(sorted(got))
        rows.append(row)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("results/robustness.csv"))
    args = ap.parse_args()
    rows = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"{r['group']:8} {r['variant']:40} eyecite={r['eyecite']:8} regex={r['alaska_regex']:8} hybrid={r['hybrid']:8} got={r['hybrid_got']}")
