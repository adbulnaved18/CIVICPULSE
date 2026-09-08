from pydantic import BaseModel, EmailStr


class UserSignup(BaseModel):
    name: str
    email: EmailStr
    password: str
    # role is intentionally NOT accepted from the client here.
    # Every public signup becomes a "citizen"; admin accounts are created
    # separately so a regular user can't just request the admin role.


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    token: str | None = None
