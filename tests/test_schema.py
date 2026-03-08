"""
Unit tests for app.core.schema — response helpers and Pydantic models.
No database or network connections required.
"""

from app.core.schema import (
    BaseResponse,
    StatusEnum,
    create_success_response,
    create_error_response,
    create_warning_response,
)


class TestStatusEnum:
    def test_values_are_strings(self):
        assert StatusEnum.SUCCESS == "success"
        assert StatusEnum.FAILED == "failed"
        assert StatusEnum.ERROR == "error"
        assert StatusEnum.WARNING == "warning"


class TestCreateSuccessResponse:
    def test_default_message(self):
        resp = create_success_response()
        assert resp.status == StatusEnum.SUCCESS
        assert resp.message == "Success"
        assert resp.data is None

    def test_custom_message_and_data(self):
        resp = create_success_response(message="Done", data={"key": "value"})
        assert resp.status == StatusEnum.SUCCESS
        assert resp.message == "Done"
        assert resp.data == {"key": "value"}

    def test_returns_base_response(self):
        resp = create_success_response()
        assert isinstance(resp, BaseResponse)


class TestCreateErrorResponse:
    def test_default_message(self):
        resp = create_error_response()
        assert resp.status == StatusEnum.FAILED
        assert resp.message == "An error occurred"
        assert resp.data is None

    def test_custom_message(self):
        resp = create_error_response(message="Not found")
        assert resp.status == StatusEnum.FAILED
        assert resp.message == "Not found"

    def test_with_data_payload(self):
        resp = create_error_response(message="Oops", data={"detail": "missing field"})
        assert resp.data == {"detail": "missing field"}


class TestCreateWarningResponse:
    def test_default_message(self):
        resp = create_warning_response()
        assert resp.status == StatusEnum.WARNING
        assert resp.message == "Warning"

    def test_custom_message(self):
        resp = create_warning_response(message="Rate limit approaching")
        assert resp.message == "Rate limit approaching"


class TestBaseResponseModel:
    def test_serialise_to_dict(self):
        resp = create_success_response(message="OK", data=42)
        d = resp.model_dump()
        assert d["status"] == "success"
        assert d["message"] == "OK"
        assert d["data"] == 42

    def test_list_data(self):
        resp = create_success_response(data=[1, 2, 3])
        assert resp.data == [1, 2, 3]
