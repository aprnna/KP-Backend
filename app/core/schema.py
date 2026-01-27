from pydantic import BaseModel
from typing import Any, Optional, Union, List, Dict
from enum import Enum

class StatusEnum(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    WARNING = "warning"

class BaseResponse(BaseModel):
    status: StatusEnum
    message: str
    data: Optional[Union[str, int, float, bool, Dict[str, Any], List[Any], Any]] = None

    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Operation completed successfully",
                "data": None
            }
        }

class SuccessResponse(BaseResponse):
    status: StatusEnum = StatusEnum.SUCCESS

class ErrorResponse(BaseResponse):
    status: StatusEnum = StatusEnum.FAILED

def create_success_response(message: str = "Success", data: Any = None) -> BaseResponse:
    return BaseResponse(
        status=StatusEnum.SUCCESS,
        message=message,
        data=data
    )

def create_error_response(message: str = "An error occurred", data: Any = None) -> BaseResponse:
    return BaseResponse(
        status=StatusEnum.FAILED,
        message=message,
        data=data
    )

def create_warning_response(message: str = "Warning", data: Any = None) -> BaseResponse:
    return BaseResponse(
        status=StatusEnum.WARNING,
        message=message,
        data=data
    )

class DataListResponse(BaseResponse):
    data: Optional[List[Any]] = None

class DataObjectResponse(BaseResponse):
    data: Optional[Dict[str, Any]] = None

class DataStringResponse(BaseResponse):
    data: Optional[str] = None