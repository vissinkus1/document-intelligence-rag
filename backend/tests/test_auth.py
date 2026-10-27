from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import User

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
User.__table__.create(engine)
Session = sessionmaker(bind=engine, expire_on_commit=False)

def override():
    db = Session()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override
c = TestClient(app)

def login(email, pw):
    return c.post("/auth/login", data={"username": email, "password": pw})

def auth(tok): return {"Authorization": f"Bearer {tok}"}

# register
r = c.post("/auth/register", json={"email": "Admin@Test.com", "password": "password123"})
assert r.status_code == 201 and r.json()["role"] == "admin", r.text   # first user = admin
r = c.post("/auth/register", json={"email": "emp@test.com", "password": "password123"})
assert r.status_code == 201 and r.json()["role"] == "member", r.text
assert "password" not in r.text and "hash" not in r.text               # no secrets leaked
print("register: first user admin, second member, no hash in response")

assert c.post("/auth/register", json={"email": "emp@test.com", "password": "password123"}).status_code == 409
assert c.post("/auth/register", json={"email": "x@test.com", "password": "short"}).status_code == 422
assert c.post("/auth/register", json={"email": "x@test.com", "password": "a"*80}).status_code == 422
assert c.post("/auth/register", json={"email": "not-an-email", "password": "password123"}).status_code == 422
print("validation: duplicate, short pw, >72 byte pw, bad email all rejected")

# login
assert login("admin@test.com", "wrongpass1").status_code == 401
assert login("nobody@test.com", "password123").status_code == 401
a = login("ADMIN@test.com", "password123"); assert a.status_code == 200
m = login("emp@test.com", "password123"); assert m.status_code == 200
at, mt = a.json()["access_token"], m.json()["access_token"]
print("login: wrong pw / unknown user -> 401, email case-insensitive OK")

# protected routes
assert c.get("/auth/me").status_code == 401
assert c.get("/auth/me", headers=auth("garbage")).status_code == 401
assert c.get("/auth/me", headers=auth(mt)).json()["email"] == "emp@test.com"
print("/auth/me: no token / bad token -> 401, valid token OK")

# role enforcement
assert c.get("/auth/users", headers=auth(mt)).status_code == 403
assert len(c.get("/auth/users", headers=auth(at)).json()) == 2
assert c.patch("/auth/users/2/role", json={"role": "admin"}, headers=auth(mt)).status_code == 403
assert c.patch("/auth/users/2/role", json={"role": "admin"}, headers=auth(at)).json()["role"] == "admin"
assert c.patch("/auth/users/1/role", json={"role": "member"}, headers=auth(at)).status_code == 400
assert c.patch("/auth/users/99/role", json={"role": "admin"}, headers=auth(at)).status_code == 404
print("roles: member blocked (403), admin can list/promote, self-demote blocked, 404 on missing user")
print("\nALL AUTH TESTS PASSED")
