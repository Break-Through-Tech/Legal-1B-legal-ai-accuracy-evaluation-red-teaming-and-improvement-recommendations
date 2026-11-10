import io
import json
import unittest
from pathlib import Path
from unittest import mock

import docx

from src import detect
from src.detect import Detector

ROOT = Path(__file__).resolve().parent.parent

PARAGRAPHS = [
    "The court divides property under AS 25.24.160 and AS 25.24.999.",
    "Under AS 25.24.160(a), the court may provide \"for the payment by either or both parties of an "
    "amount of money or goods, in gross or installments\" for the children.",
    "Opposing counsel again relies on AS 25.24.999, which does not help them.",
]


def make_docx(paragraphs=PARAGRAPHS) -> bytes:
    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def stable(report):
    """Report without the fields that legitimately differ between calls."""
    return {k: v for k, v in report.items() if k not in ("runtime", "filename")}


class DetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = Detector()
        cls.data = make_docx()
        cls.report = cls.detector.check(cls.data, filename="sample.docx")

    def test_report_is_json_serializable_and_complete(self):
        json.dumps(self.report)
        self.assertEqual(self.report["doc_id"], "sample")
        self.assertEqual(self.report["errors"], [])
        for key in ("risk", "summary", "flags", "runtime", "text", "source_sha256"):
            self.assertIn(key, self.report)

    def test_one_flag_per_citation_with_stage_and_severity(self):
        citations = [f for f in self.report["flags"] if f["stage"] == "existence"]
        self.assertEqual([f["text"] for f in citations],
                         ["AS 25.24.160", "AS 25.24.999", "AS 25.24.160(a)", "AS 25.24.999"])
        for flag in citations:
            fabricated = flag["text"] == "AS 25.24.999"
            self.assertEqual(flag["flagged"], fabricated)
            self.assertEqual(flag["severity"], "high" if fabricated else None)
            self.assertEqual(flag["status"], "Hallucinated" if fabricated else "Valid/Verified")
            self.assertTrue(flag["message"])

    def test_verbatim_quote_is_verified(self):
        quotes = [f for f in self.report["flags"] if f["item_type"] == "quoted"]
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["status"], "verified")
        self.assertFalse(quotes[0]["flagged"])

    def test_repeated_fabrication_counts_once_in_risk(self):
        risk = self.report["risk"]
        self.assertEqual(risk["problems"], 1)
        self.assertEqual(risk["level"], "high")
        self.assertEqual(risk["drivers"], ["1 fabricated citation"])
        self.assertEqual(self.report["summary"]["citations_flagged"], 2)

    def test_path_bytes_and_stream_give_the_same_report(self):
        path = ROOT / "data" / "benchmark" / "documents" / "doc-0001.docx"
        from_path = self.detector.check(path)
        from_bytes = self.detector.check(path.read_bytes(), doc_id="doc-0001")
        from_stream = self.detector.check(io.BytesIO(path.read_bytes()), doc_id="doc-0001")
        self.assertEqual(stable(from_path), stable(from_bytes))
        self.assertEqual(stable(from_path), stable(from_stream))

    def test_unreadable_file_returns_report_instead_of_raising(self):
        report = self.detector.check(b"not a word document", filename="broken.docx")
        self.assertEqual(report["errors"][0]["stage"], "extract")
        self.assertEqual(report["risk"]["level"], "unknown")
        self.assertIsNone(report["risk"]["score"])
        self.assertEqual(report["flags"], [])
        self.assertNotIn("traceback", report["errors"][0])

    def test_failed_stage_keeps_other_stages(self):
        with mock.patch.object(detect, "lookup_citation", side_effect=RuntimeError("corpus down")):
            report = self.detector.check(self.data, filename="sample.docx")
        self.assertEqual([e["stage"] for e in report["errors"]], ["verify"])
        self.assertFalse(any(f["stage"] == "existence" for f in report["flags"]))
        self.assertTrue(any(f["stage"] == "quote_fidelity" for f in report["flags"]))
        self.assertTrue(report["risk"]["incomplete"])

    def test_citation_extraction_failure_still_scores_the_document(self):
        with mock.patch.object(detect, "extract_citations", side_effect=RuntimeError("regex blew up")):
            report = self.detector.check(self.data, filename="sample.docx")
        self.assertEqual([e["stage"] for e in report["errors"]], ["extract_citations"])
        self.assertIsNotNone(report["risk"]["score"])
        self.assertNotEqual(report["risk"]["level"], "unknown")
        self.assertTrue(any(f["stage"] == "quote_fidelity" for f in report["flags"]))

    def test_quote_flag_failure_is_reported_not_raised(self):
        with mock.patch.object(Detector, "_quote_flags", side_effect=KeyError("kind")):
            report = self.detector.check(self.data, filename="sample.docx")
        self.assertEqual([e["stage"] for e in report["errors"]], ["quote_check"])
        self.assertTrue(any(f["stage"] == "existence" for f in report["flags"]))

    def test_real_reporter_cite_under_another_case_name_is_flagged(self):
        data = make_docx(["See Hollister v. Brandt, 449 P.3d 700 (Alaska 2019).",
                          "See Perry v. Perry, 449 P.3d 700 (Alaska 2019).",
                          "See Kyoko Perry v. Adam Perry, 449 P.3d 700 (Alaska 2014)."])
        flags = self.detector.check(data, filename="new.docx")["flags"]
        by_status = [(f["status"], f["flagged"], f["severity"]) for f in flags]
        self.assertEqual(by_status, [("Wrong Case Name", True, "high"),
                                     ("Valid/Verified", False, None),   # short form of the real name
                                     ("Wrong Year", True, "low")])
        self.assertIn("Kyoko Perry v. Adam Perry", flags[0]["message"])
        self.assertEqual(flags[0]["evidence"]["exists"], "true")       # existence rows unchanged


class BatchTests(unittest.TestCase):
    def test_batch_run_writes_reports_and_run_log(self):
        import tempfile
        with tempfile.TemporaryDirectory() as out:
            with mock.patch.object(detect, "LOG_DIR", Path(out) / "logs"):
                code = detect.main(["doc-0001", "doc-0136", "--out", out, "--strict"])
            self.assertEqual(code, 0)
            reports = [json.loads(line) for line in (Path(out) / "reports.jsonl").read_text().splitlines()]
            run_log = json.loads((Path(out) / "run-log.json").read_text())
        self.assertEqual([r["doc_id"] for r in reports], ["doc-0001", "doc-0136"])
        self.assertEqual(run_log["documents"], {"total": 2, "ok": 2, "failed": 0})
        self.assertIn("p95", run_log["runtime"]["per_doc_ms"])

    def test_evaluate_on_a_subset_scores_only_those_documents(self):
        import tempfile
        with tempfile.TemporaryDirectory() as out:
            with mock.patch.object(detect, "LOG_DIR", Path(out) / "logs"):
                detect.main(["doc-0001", "doc-0136", "--out", out, "--evaluate"])
            card = json.loads((Path(out) / "scorecard.json").read_text())
        self.assertEqual(card["meta"]["documents"], 2)
        self.assertFalse(card["meta"]["full_benchmark"])

    def test_positional_docx_path_checks_a_new_document(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "My new brief.docx"
            path.write_bytes(make_docx())
            with mock.patch.object(detect, "LOG_DIR", Path(tmp) / "logs"):
                detect.main([str(path), "--out", str(Path(tmp) / "out"), "--show"])
            report = json.loads((Path(tmp) / "out" / "reports.jsonl").read_text())
        self.assertEqual(report["doc_id"], "My new brief")
        self.assertEqual(report["risk"]["level"], "high")

    def test_folder_of_other_documents_runs_and_skips_evaluation(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            folder, out = Path(tmp) / "in", Path(tmp) / "out"
            folder.mkdir()
            (folder / "notes.DOCX").write_bytes(make_docx(["Lunch at noon."]))
            (folder / "doc-0001.docx").write_bytes(make_docx())   # benchmark name, different file
            (folder / "broken.docx").write_bytes(b"not a word document")
            (folder / "~$lock.docx").write_bytes(b"word lock file")
            with mock.patch.object(detect, "LOG_DIR", Path(tmp) / "logs"):
                detect.main(["--input", str(folder), "--out", str(out), "--evaluate"])
            ids = [json.loads(line)["doc_id"] for line in (out / "reports.jsonl").read_text().splitlines()]
            self.assertEqual(ids, ["broken", "doc-0001", "notes"])
            self.assertFalse((out / "scorecard.json").exists())

            # A renamed copy of a benchmark document is recognised by its hash and scored.
            shutil.copy(ROOT / "data" / "benchmark" / "documents" / "doc-0002.docx", folder / "upload.docx")
            with mock.patch.object(detect, "LOG_DIR", Path(tmp) / "logs"):
                detect.main(["--input", str(folder), "--out", str(out), "--evaluate"])
            card = json.loads((out / "scorecard.json").read_text())
        self.assertEqual(card["meta"]["documents"], 1)
        self.assertEqual(card["meta"]["unscored_documents"], ["broken", "doc-0001", "notes"])


if __name__ == "__main__":
    unittest.main()
