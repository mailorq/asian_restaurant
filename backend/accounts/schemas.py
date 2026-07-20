from ninja import Field, Schema

from employee.permissions import is_employee


class RegisterIn(Schema):
    phone: str
    password: str
    name: str = Field(min_length=1, max_length=150)


class LoginIn(Schema):
    phone: str
    password: str


class UserOut(Schema):
    id: int
    phone: str | None = None
    name: str = ""
    is_employee: bool = False

    @staticmethod
    def resolve_name(obj) -> str:
        return obj.first_name

    @staticmethod
    def resolve_is_employee(obj) -> bool:
        return is_employee(obj)


class MessageOut(Schema):
    detail: str
