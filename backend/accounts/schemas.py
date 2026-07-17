from ninja import Schema


class RegisterIn(Schema):
    phone: str
    password: str


class LoginIn(Schema):
    phone: str
    password: str


class UserOut(Schema):
    id: int
    phone: str | None = None


class MessageOut(Schema):
    detail: str
