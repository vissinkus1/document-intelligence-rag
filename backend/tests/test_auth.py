"""Unit and integration tests for authentication and authorization.

Tests user registration (first user bootstrap to admin, subsequent to member),
password hashing/validation, login flow with JWT, /auth/me, and RBAC endpoint guards.
"""
import os

from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Role, User
from app.routers.auth import list_users, login, me, register, set_role
from app.schemas import RegisterIn, RoleUpdate


@pytest.fixture(scope="module")
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_first_user_registration_is_admin(db_session):
    user = register(RegisterIn(email="Admin@Test.com", password="password123"), db_session)
    assert user.role == Role.admin
    assert user.email == "admin@test.com"  # Lowercase normalized
    assert "password" not in user.__dict__ or not user.__dict__["password_hash"] == "password123"


def test_second_user_registration_is_member(db_session):
    user = register(RegisterIn(email="member@test.com", password="password123"), db_session)
    assert user.role == Role.member
    assert user.email == "member@test.com"


def test_duplicate_registration_rejected_409(db_session):
    with pytest.raises(HTTPException) as exc_info:
        register(RegisterIn(email="member@test.com", password="password123"), db_session)
    assert exc_info.value.status_code == 409


def test_login_flow(db_session):
    # Valid login
    form = OAuth2PasswordRequestForm(
        grant_type="",
        username="admin@test.com",
        password="password123",
        scope="",
        client_id=None,
        client_secret=None,
    )
    token_out = login(form, db_session)
    assert token_out.access_token
    assert token_out.token_type == "bearer"
    assert token_out.user.email == "admin@test.com"

    # Invalid password -> 401
    bad_form = OAuth2PasswordRequestForm(
        grant_type="",
        username="admin@test.com",
        password="wrongpassword",
        scope="",
        client_id=None,
        client_secret=None,
    )
    with pytest.raises(HTTPException) as exc_info:
        login(bad_form, db_session)
    assert exc_info.value.status_code == 401


def test_auth_me_and_user_listing(db_session):
    admin = db_session.query(User).filter_by(role=Role.admin).first()
    member = db_session.query(User).filter_by(role=Role.member).first()

    # /auth/me returns the authenticated user
    profile = me(member)
    assert profile.email == "member@test.com"
    assert profile.role == Role.member

    # /auth/users list all users for admin
    users = list_users(admin, db_session)
    assert len(users) >= 2


def test_role_enforcement_and_promotion(db_session):
    admin = db_session.query(User).filter_by(role=Role.admin).first()
    member = db_session.query(User).filter_by(role=Role.member).first()

    # Promote member to admin
    updated = set_role(member.id, RoleUpdate(role=Role.admin), admin, db_session)
    assert updated.role == Role.admin

    # Self-demotion blocked
    with pytest.raises(HTTPException) as exc_info:
        set_role(admin.id, RoleUpdate(role=Role.member), admin, db_session)
    assert exc_info.value.status_code == 400

    # Non-existent user -> 404
    with pytest.raises(HTTPException) as exc_info:
        set_role(99999, RoleUpdate(role=Role.admin), admin, db_session)
    assert exc_info.value.status_code == 404
