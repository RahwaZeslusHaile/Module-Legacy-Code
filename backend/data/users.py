from dataclasses import dataclass
import hashlib
import random
import string
from typing import List, Optional

from data.connection import db_cursor
from psycopg2.errors import UniqueViolation


@dataclass
class User:
    id: int
    username: str
    password_salt: bytes
    password_scrypt: bytes

    def check_password(self, password_plaintext: str) -> bool:
        return self.password_scrypt == scrypt(
            password_plaintext.encode("utf-8"), self.password_salt
        )


class UserRegistrationError(Exception):
    reason: str

    def __init__(self, reason: str):
        self.reason = reason


def get_user(username: str) -> Optional[User]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, password_salt, password_scrypt FROM users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        user_id, password_salt, password_scrypt = row
        return User(
            id=user_id,
            username=username,
            password_salt=bytes(password_salt),
            password_scrypt=bytes(password_scrypt),
        )


def get_suggested_follows(following_user: User, limit: int) -> List[str]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
              users.username
            FROM
              users
            WHERE
              users.id <> %(following_user_id)s AND
              users.id NOT IN (
                SELECT followee FROM follows WHERE follower = %(following_user_id)s
              )
            ORDER BY RANDOM()
            LIMIT %(limit)s
            """,
            dict(
                following_user_id=following_user.id,
                limit=limit,
            ),
        )
        rows = cur.fetchall()
        return [row[0] for row in rows]


def register_user(username: str, password_plaintext: str) -> User:
    salt = generate_salt()
    password_scrypt = scrypt(password_plaintext.encode("utf-8"), salt)

    with db_cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO users (username, password_salt, password_scrypt) VALUES (%(username)s, %(password_salt)s, %(password_scrypt)s)",
                dict(
                    username=username,
                    password_salt=salt,
                    password_scrypt=password_scrypt,
                ),
            )
        except UniqueViolation as err:
            raise UserRegistrationError("user already exists")


def scrypt(password_plaintext: bytes, password_salt: bytes) -> bytes:
    if hasattr(hashlib, "scrypt"):
        return hashlib.scrypt(password_plaintext, salt=password_salt, n=8, r=8, p=1)
    return hashlib.pbkdf2_hmac("sha256", password_plaintext, password_salt, 100_000)


SALT_CHARACTERS = string.ascii_uppercase + string.ascii_lowercase + string.digits


def generate_salt() -> bytes:
    return (
        "".join(random.SystemRandom().choice(SALT_CHARACTERS) for _ in range(10))
    ).encode("utf-8")


def lookup_user(header_info, payload_info):
    """lookup_user is a hook for the jwt middleware to look-up authenticated users."""
    return get_user(payload_info["sub"])
