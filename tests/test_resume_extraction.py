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
