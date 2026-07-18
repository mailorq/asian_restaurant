from ninja import Field, Schema


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

    @staticmethod
    def resolve_name(obj) -> str:
        return obj.first_name


class MessageOut(Schema):
    detail: str
