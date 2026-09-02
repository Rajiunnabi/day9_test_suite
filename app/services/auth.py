"""Registration, login, refresh, password change, logout.

Nothing in this file knows it is being called over HTTP. No Request, no
HTTPException, no status codes - it raises AppError subclasses and returns
domain objects. That is what makes it testable with a fake repository and
reusable from a CLI script.

Transaction rule: this service owns the commit. The repository stages work,
the service decides the operation succeeded.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.exceptions import (
    EmailAlreadyExists,
    InvalidCredentials,
    InvalidToken,
    TooManyAttempts,
)
from app.core.enums import UserRole
from app.core.security import (
    TokenPair,
    create_token_pair,
    decode_token,
    dummy_verify,
    hash_password,
    subject_from_claims,
    verify_password,
)
from app.core.throttle import LoginThrottle
from app.db.models.user import User
from app.repositories.user import UserRepository

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self, db: Session, users: UserRepository, throttle: LoginThrottle
    ) -> None:
        # Everything this service needs arrives through the constructor. That is
        # the whole trick behind the unit tests: pass fakes instead of the real
        # session and repository, and no database is involved.
        self.db = db
        self.users = users
        self.throttle = throttle

    # ---------------------------------------------------------- registration

    def register(
        self, email: str, full_name: str, phone: str | None, password: str
    ) -> User:
        """Public sign-up. The role is decided here, never by the caller."""
        if self.users.get_by_email(email) is not None:
            raise EmailAlreadyExists()

        user = User(
            email=email,
            full_name=full_name,
            phone=phone,
            hashed_password=hash_password(password),
            role=UserRole.USER,
        )
        self.users.add(user)
        self.db.commit()
        self.db.refresh(user)  # public_id / created_at come from Postgres

        # Audit: who and what, never the password. public_id rather than email,
        # so the log file doesn't become a list of everyone's addresses.
        logger.info("user registered: %s", user.public_id)
        return user

    # ----------------------------------------------------------------- login

    def login(self, email: str, password: str) -> TokenPair:
        key = email.lower()

        wait = self.throttle.seconds_remaining(key)
        if wait:
            logger.warning("login locked out: %s (%ss left)", key, wait)
            raise TooManyAttempts(f"Too many failed attempts. Try again in {wait}s.")

        user = self.users.get_by_email(key)

        if user is None:
            # Same work as a real check, so timing doesn't reveal which emails
            # are registered.
            dummy_verify()
            self.throttle.record_failure(key)
            raise InvalidCredentials()

        if not verify_password(password, user.hashed_password):
            self.throttle.record_failure(key)
            logger.warning("failed login for user %s", user.public_id)
            raise InvalidCredentials()

        self.throttle.reset(key)
        logger.info("login ok: %s", user.public_id)
        return create_token_pair(user.public_id, user.token_version)

    # --------------------------------------------------------------- tokens

    def user_from_access_token(self, token: str) -> User:
        """Token string -> the live User row it belongs to.

        The dependency in api/deps.py is a two-line wrapper around this. Keeping
        the logic here means "what makes a token valid" is testable without
        starting a web server.
        """
        return self._user_from_token(token, expected_type="access")

    def refresh(self, refresh_token: str) -> TokenPair:
        """Trade a valid refresh token for a fresh pair.

        Both tokens are re-issued (rotation), so a refresh token that leaked
        into a log a week ago is unlikely to still be the current one.
        """
        user = self._user_from_token(refresh_token, expected_type="refresh")
        return create_token_pair(user.public_id, user.token_version)

    def _user_from_token(self, token: str, expected_type: str) -> User:
        claims = decode_token(token, expected_type)  # type: ignore[arg-type]
        public_id = subject_from_claims(claims)

        user = self.users.get_by_public_id(public_id)
        if user is None:
            # Covers deleted accounts too - the repository hides those.
            raise InvalidToken()

        # Revocation. Logout bumps token_version, so every token minted before
        # that moment fails here.
        if claims.get("ver") != user.token_version:
            raise InvalidToken("Token has been revoked, please log in again")

        return user

    # ------------------------------------------------------- password / logout

    def change_password(self, user: User, current: str, new: str) -> None:
        """Re-asking for the current password stops someone who walked up to an
        unlocked laptop from locking the real owner out."""
        if not verify_password(current, user.hashed_password):
            logger.warning("failed password change for %s", user.public_id)
            raise InvalidCredentials("Current password is incorrect")

        user.hashed_password = hash_password(new)
        user.token_version += 1  # a password change must kill every session
        self.db.commit()
        logger.info("password changed for %s", user.public_id)

    def logout(self, user: User) -> None:
        """JWTs are stateless - the server cannot delete one already issued.
        Bumping the version is how you invalidate them all at once."""
        user.token_version += 1
        self.db.commit()
        logger.info("logout: %s", user.public_id)
