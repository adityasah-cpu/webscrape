"""
Unit tests for extract_text_from_resume(). PDF/DOCX parsing libraries are
mocked so these tests don't depend on real binary fixture files - only the
dispatch logic (extension validation, error wrapping, empty-file handling)
is under test here. Plain .txt decoding is tested for real since it needs
no external library.
"""
import io

import pytest
from werkzeug.datastructures import FileStorage

import api as api_module


def make_file_storage(content: bytes, filename: str) -> FileStorage:
    return FileStorage(stream=io.BytesIO(content), filename=filename)


class TestOversizedUploadReturnsJson:
    def test_413_response_is_json_not_html(self, client):
        """Regression test: Flask's default 413 response is an HTML error
        page, which breaks the frontend's fetch().json() parsing."""
        api_module.limiter.reset()  # other tests in this session share the in-memory limiter store
        oversized = b"x" * (api_module.MAX_RESUME_SIZE_BYTES + 1)
        data = {"resume": (io.BytesIO(oversized), "resume.txt")}
        res = client.post("/api/match-resume", data=data, content_type="multipart/form-data")
        assert res.status_code == 413
        body = res.get_json()
        assert body["success"] is False
        assert "too large" in body["error"].lower()


class TestExtractTextFromResume:
    def test_txt_file_decoded_directly(self):
        fs = make_file_storage(b"Python developer with 1 year experience.", "resume.txt")
        text = api_module.extract_text_from_resume(fs)
        assert text == "Python developer with 1 year experience."

    def test_unsupported_extension_raises_value_error(self):
        fs = make_file_storage(b"some content", "resume.doc")
        with pytest.raises(ValueError, match="Unsupported file type"):
            api_module.extract_text_from_resume(fs)

    def test_no_extension_raises_value_error(self):
        fs = make_file_storage(b"some content", "resume")
        with pytest.raises(ValueError, match="Unsupported file type"):
            api_module.extract_text_from_resume(fs)

    def test_empty_file_raises_value_error(self):
        fs = make_file_storage(b"", "resume.txt")
        with pytest.raises(ValueError, match="empty"):
            api_module.extract_text_from_resume(fs)

    def test_pdf_dispatches_to_pdfminer(self, mocker):
        mocker.patch.object(
            api_module, "pdf_extract_text",
            return_value="  extracted pdf text long enough to skip the OCR fallback path  ",
        )
        fs = make_file_storage(b"%PDF-1.4 fake bytes", "resume.pdf")
        text = api_module.extract_text_from_resume(fs)
        assert text == "extracted pdf text long enough to skip the OCR fallback path"
        api_module.pdf_extract_text.assert_called_once()

    def test_pdf_with_no_text_layer_falls_back_to_ocr(self, mocker):
        mocker.patch.object(api_module, "pdf_extract_text", return_value="")
        mocker.patch.object(api_module, "_ocr_pdf_bytes", return_value="ocr extracted text")
        fs = make_file_storage(b"%PDF-1.4 scanned, no text layer", "scanned.pdf")
        text = api_module.extract_text_from_resume(fs)
        assert text == "ocr extracted text"
        api_module._ocr_pdf_bytes.assert_called_once()

    def test_image_upload_dispatches_to_ocr(self, mocker):
        mocker.patch.object(api_module, "_ocr_image_bytes", return_value="ocr image text")
        fs = make_file_storage(b"\x89PNG fake bytes", "resume.png")
        text = api_module.extract_text_from_resume(fs)
        assert text == "ocr image text"
        api_module._ocr_image_bytes.assert_called_once()

    def test_docx_dispatches_to_mammoth(self, mocker):
        fake_result = mocker.Mock(value="  extracted docx text  ")
        mocker.patch.object(api_module.mammoth, "extract_raw_text", return_value=fake_result)
        fs = make_file_storage(b"PK fake docx bytes", "resume.docx")
        text = api_module.extract_text_from_resume(fs)
        assert text == "extracted docx text"

    def test_pdf_parser_exception_wrapped_as_value_error(self, mocker):
        mocker.patch.object(api_module, "pdf_extract_text", side_effect=RuntimeError("corrupt stream"))
        fs = make_file_storage(b"broken pdf bytes", "resume.pdf")
        with pytest.raises(ValueError, match="Could not parse this file"):
            api_module.extract_text_from_resume(fs)

    def test_image_upload_rejects_invalid_image_bytes(self):
        fs = make_file_storage(b"not a real image", "resume.png")
        with pytest.raises(ValueError, match="Could not parse this file"):
            api_module.extract_text_from_resume(fs)

    def test_image_upload_rejects_oversized_resolution(self, mocker):
        mocker.patch.object(api_module, "MAX_OCR_IMAGE_PIXELS", 100)  # trivially small cap
        import io as _io
        from PIL import Image
        buf = _io.BytesIO()
        Image.new("RGB", (50, 50), "white").save(buf, format="PNG")  # 2500px > 100px cap
        fs = make_file_storage(buf.getvalue(), "resume.png")
        with pytest.raises(ValueError, match="Could not parse this file"):
            api_module.extract_text_from_resume(fs)

    def test_extension_is_case_insensitive(self, mocker):
        mocker.patch.object(
            api_module, "pdf_extract_text",
            return_value="enough text here to clear the OCR fallback threshold",
        )
        fs = make_file_storage(b"bytes", "Resume.PDF")
        text = api_module.extract_text_from_resume(fs)
        assert text == "enough text here to clear the OCR fallback threshold"


class TestEvaluateAtsScore:
    """evaluate_ats_score() talks to an external service (CUTM AI Gateway).
    These tests cover both the confirmed-live response shape (ats_score,
    summary, critical_issues, actionable_recommendations, missing_keywords)
    and the older guessed-field fallbacks kept for robustness, plus every
    failure mode turning into a clear ValueError rather than a crash."""

    def _mock_response(self, mocker, status_code=200, json_data=None, json_raises=False):
        resp = mocker.Mock()
        resp.status_code = status_code
        if json_raises:
            resp.json.side_effect = ValueError("not json")
        else:
            resp.json.return_value = json_data or {}
        return resp

    def test_success_with_score_and_feedback_keys(self, mocker):
        mocker.patch.object(
            api_module.requests, "post",
            return_value=self._mock_response(mocker, json_data={"score": 82, "feedback": "Add metrics."})
        )
        result = api_module.evaluate_ats_score("resume.pdf", b"bytes")
        assert result == {"score": 82.0, "feedback": "Add metrics."}

    def test_success_with_alternate_key_names(self, mocker):
        mocker.patch.object(
            api_module.requests, "post",
            return_value=self._mock_response(mocker, json_data={"ats_score": "65.3", "suggestions": ["Use action verbs", "Add a skills section"]})
        )
        result = api_module.evaluate_ats_score("resume.pdf", b"bytes")
        assert result["score"] == 65.3
        assert "action verbs" in result["feedback"]
        assert "skills section" in result["feedback"]

    def test_success_with_confirmed_live_response_shape(self, mocker):
        """Regression test: the real service returns ats_score plus
        several separate improvement-guidance fields, not a single
        "feedback" key - this used to silently fall back to the generic
        'No improvement suggestions provided.' message for every real
        response because none of the guessed key names matched."""
        mocker.patch.object(
            api_module.requests, "post",
            return_value=self._mock_response(mocker, json_data={
                "ats_score": 85, "match_percentage": 95, "rating": "Strong Match",
                "summary": "Strong backend engineer with solid metrics.",
                "critical_issues": ["Missing GitHub/portfolio link"],
                "actionable_recommendations": ["Include a GitHub link", "Add AWS services to skills"],
                "missing_keywords": ["AWS Services", "Testing Frameworks"],
            })
        )
        result = api_module.evaluate_ats_score("resume.pdf", b"bytes")
        assert result["score"] == 85.0  # ats_score preferred over match_percentage
        assert "Strong backend engineer" in result["feedback"]
        assert "Missing GitHub/portfolio link" in result["feedback"]
        assert "Include a GitHub link" in result["feedback"]
        assert "AWS Services" in result["feedback"]
        assert result["feedback"] != "No improvement suggestions provided."

    def test_missing_score_raises_value_error(self, mocker):
        mocker.patch.object(
            api_module.requests, "post",
            return_value=self._mock_response(mocker, json_data={"feedback": "looks fine"})
        )
        with pytest.raises(ValueError, match="did not include a score"):
            api_module.evaluate_ats_score("resume.pdf", b"bytes")

    def test_non_numeric_score_raises_value_error(self, mocker):
        mocker.patch.object(
            api_module.requests, "post",
            return_value=self._mock_response(mocker, json_data={"score": "not-a-number"})
        )
        with pytest.raises(ValueError, match="non-numeric score"):
            api_module.evaluate_ats_score("resume.pdf", b"bytes")

    def test_non_200_status_raises_value_error(self, mocker):
        mocker.patch.object(
            api_module.requests, "post",
            return_value=self._mock_response(mocker, status_code=404)
        )
        with pytest.raises(ValueError, match="HTTP 404"):
            api_module.evaluate_ats_score("resume.pdf", b"bytes")

    def test_unparseable_json_raises_value_error(self, mocker):
        mocker.patch.object(
            api_module.requests, "post",
            return_value=self._mock_response(mocker, json_raises=True)
        )
        with pytest.raises(ValueError, match="unreadable response"):
            api_module.evaluate_ats_score("resume.pdf", b"bytes")

    def test_timeout_raises_value_error(self, mocker):
        mocker.patch.object(
            api_module.requests, "post",
            side_effect=api_module.requests.exceptions.Timeout()
        )
        with pytest.raises(ValueError, match="timed out"):
            api_module.evaluate_ats_score("resume.pdf", b"bytes")

    def test_connection_error_raises_value_error(self, mocker):
        mocker.patch.object(
            api_module.requests, "post",
            side_effect=api_module.requests.exceptions.ConnectionError()
        )
        with pytest.raises(ValueError, match="unreachable"):
            api_module.evaluate_ats_score("resume.pdf", b"bytes")

    def test_missing_feedback_falls_back_to_default_message(self, mocker):
        mocker.patch.object(
            api_module.requests, "post",
            return_value=self._mock_response(mocker, json_data={"score": 50})
        )
        result = api_module.evaluate_ats_score("resume.pdf", b"bytes")
        assert result["feedback"] == "No improvement suggestions provided."


class TestAnalyzeResumeCategories:
    """analyze_resume_categories() is the local, rule-based scoring
    breakdown (Content/Sections/ATS Essentials/HR Red Flags/
    Discrimination/Seniority/Tailoring), computed entirely in this
    codebase with no external API call."""

    STRONG_RESUME = """
    Ravi Kumar Sharma
    Email: ravi.sharma@example.com | Phone: +91-9123456780

    SUMMARY
    Backend Engineer with 3 years of experience.

    EXPERIENCE
    Software Engineer, TechCorp
    Jan 2023 - Present
    - Led migration of 50,000 users to a new payment system, reducing errors by 40%
    - Built and deployed REST APIs serving 1 million requests per day
    - Increased test coverage from 60% to 95% by implementing CI/CD pipelines

    EDUCATION
    B.Tech in Computer Science, VIT Bangalore, 2021

    SKILLS
    Python, Flask, MySQL, AWS, Docker, machine learning, TensorFlow
    """

    WEAK_RESUME = """
    John Smith
    I am a hardworking team player and a detail-oriented self-starter.
    I was responsible for various duties included in my previous role.
    """

    def test_returns_overall_score_and_all_seven_categories(self):
        result = api_module.analyze_resume_categories(self.STRONG_RESUME)
        assert 0 <= result["overall_score"] <= 100
        assert set(result["categories"].keys()) == {
            "content", "sections", "ats_essentials", "hr_red_flags",
            "discrimination", "seniority", "tailoring",
        }
        for cat in result["categories"].values():
            assert 0 <= cat["score"] <= 100
            assert isinstance(cat["findings"], list) and cat["findings"]

    def test_strong_resume_scores_higher_on_content_than_weak_resume(self):
        strong = api_module.analyze_resume_categories(self.STRONG_RESUME)
        weak = api_module.analyze_resume_categories(self.WEAK_RESUME)
        assert strong["categories"]["content"]["score"] > weak["categories"]["content"]["score"]

    def test_cliche_phrases_are_flagged_and_lower_content_score(self):
        result = api_module.analyze_resume_categories(self.WEAK_RESUME)
        findings_text = " ".join(result["categories"]["content"]["findings"])
        assert "hard worker" in findings_text or "team player" in findings_text

    def test_missing_sections_are_flagged(self):
        result = api_module.analyze_resume_categories(self.WEAK_RESUME)
        findings_text = " ".join(result["categories"]["sections"]["findings"])
        assert "Missing" in findings_text

    def test_missing_contact_info_lowers_ats_essentials_score(self):
        result = api_module.analyze_resume_categories("Just some text with no contact details at all.")
        assert result["categories"]["ats_essentials"]["score"] < 100

    def test_bias_disclosures_are_flagged_and_lower_discrimination_score(self):
        text_with_disclosure = self.STRONG_RESUME + "\nMarital Status: Married\nReligion: Hindu"
        result = api_module.analyze_resume_categories(text_with_disclosure)
        assert result["categories"]["discrimination"]["score"] < 100
        findings_text = " ".join(result["categories"]["discrimination"]["findings"])
        assert "Marital status" in findings_text

    def test_clean_resume_has_perfect_discrimination_score(self):
        result = api_module.analyze_resume_categories(self.STRONG_RESUME)
        assert result["categories"]["discrimination"]["score"] == 100

    def test_seniority_mismatch_is_flagged(self):
        # Claims "Senior"/years of seniority language with almost no
        # detectable experience from date ranges.
        text = "Senior Software Engineer\nSkills: Python\nNo dated experience listed."
        result = api_module.analyze_resume_categories(text)
        findings_text = " ".join(result["categories"]["seniority"]["findings"])
        assert "senior-level language" in findings_text.lower() or result["categories"]["seniority"]["score"] < 100

    def test_tailoring_detects_domain_focus(self):
        result = api_module.analyze_resume_categories(self.STRONG_RESUME)
        findings_text = " ".join(result["categories"]["tailoring"]["findings"])
        assert "AIML" in findings_text or "Data Analytics" in findings_text

    def test_empty_text_does_not_crash(self):
        result = api_module.analyze_resume_categories("")
        assert result["overall_score"] >= 0
        assert len(result["categories"]) == 7


class TestAtsScoreEndpointLocalAnalysis:
    def test_ats_score_includes_local_analysis(self, client, mocker):
        mocker.patch.object(
            api_module, "evaluate_ats_score",
            return_value={"score": 78.5, "feedback": "Looks good."}
        )
        data = {"resume": (io.BytesIO(b"Python Flask MySQL experience with metrics: increased sales by 20%"), "resume.txt")}
        res = client.post("/api/ats-score", data=data, content_type="multipart/form-data")
        assert res.status_code == 200
        body = res.get_json()
        assert body["local_analysis"] is not None
        assert "categories" in body["local_analysis"]
        assert "overall_score" in body["local_analysis"]

    def test_ats_score_local_analysis_failure_does_not_break_the_response(self, client, mocker):
        """A bug in the local analyzer must never take down the whole
        endpoint when the external score itself succeeded."""
        mocker.patch.object(
            api_module, "evaluate_ats_score",
            return_value={"score": 60, "feedback": "ok"}
        )
        mocker.patch.object(
            api_module, "analyze_resume_categories",
            side_effect=RuntimeError("boom")
        )
        data = {"resume": (io.BytesIO(b"some resume text"), "resume.txt")}
        res = client.post("/api/ats-score", data=data, content_type="multipart/form-data")
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        assert body["score"] == 60
        assert body["local_analysis"] is None
