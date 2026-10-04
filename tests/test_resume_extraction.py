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

    def test_extension_is_case_insensitive(self, mocker):
        mocker.patch.object(
            api_module, "pdf_extract_text",
            return_value="enough text here to clear the OCR fallback threshold",
        )
        fs = make_file_storage(b"bytes", "Resume.PDF")
        text = api_module.extract_text_from_resume(fs)
        assert text == "enough text here to clear the OCR fallback threshold"
