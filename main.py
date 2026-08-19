from typing import List
from fastapi import FastAPI, HTTPException, Request, status, Depends, Cookie
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os
import random
from dotenv import load_dotenv

load_dotenv();

DB_URL = os.getenv("DATABASE_URL");
rep1 = os.getenv("READ_DB_URL_1");
rep2 = os.getenv("READ_DB_URL_2");
rep_pool = [rep1, rep2];
randomly_selected_rep = random.choice(rep_pool);
if randomly_selected_rep == rep1:
    print("Replica 1 is being in used");
else:
    print("Replica 2 is being in used");
WRITE_DB_URL = os.getenv("WRITE_DB_URL");

engine = create_engine(DB_URL);
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine);
Base = declarative_base();

write_engine = create_engine(
    WRITE_DB_URL,
    pool_size=10,
    max_overflow=20
);
read_engine = create_engine(
    randomly_selected_rep,
    pool_size=10,
    max_overflow=20
);
WriteSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=write_engine);
ReadSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=read_engine);

class UserDB(Base):
    __tablename__ = "users";
    id = Column(Integer, primary_key=True, index=True);
    firstname = Column(String);
    lastname = Column(String);
    age = Column(Integer);
    nationality = Column(String);
    gender = Column(Integer);
    username = Column(String, unique=True, index=True);
    password = Column(String);

class NotedTasks(Base):
    __tablename__ = "tasks";
    id = Column(Integer, primary_key=True, index=True);
    order_priority = Column(Integer);
    content = Column(String);
    is_done = Column(Integer);
    account_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"));

Base.metadata.create_all(bind=engine);

# Dependency to get DB session
def get_db():
    db = SessionLocal();
    try:
        yield db;
    finally:
        db.close();

def get_writeDB():
    db = WriteSessionLocal();
    try:
        yield db;
    finally:
        db.close();

def get_readDB():
    db = ReadSessionLocal();
    try:
        yield db;
    finally:
        db.close();

app = FastAPI()

clone_user_accs = {
    "users": [
        {"username": "ditcumay", "password": "hahahaha"},
        {"username": "bulontaodi", "password": "cocailon"},
    ]
}


class TaskCreate(BaseModel):
    content: str;
    order_priority: int;
    is_done: int = 0;

class Task(BaseModel):
    id: int;
    content: str;
    order_priority: int;
    is_done: int;
    account_id: int
    
    class Config:
        from_attribute = True;

class LoginRequest(BaseModel):
    username: str
    password: str

class SignupRequest(BaseModel):
    firstname: str
    lastname: str
    age: int
    nationality: str
    gender: int
    username: str
    password: str


tasks: List[Task] = []
task_id_counter = 1

# @app.get("/read-cookie")
# async def read_cookie(session_id: Optional[str] = Cookie(None)):
#     return {"session_id": session_id};

@app.middleware("http")
async def authentication_middleware(request: Request, call_next):
    path = request.url.path
    # Allow login endpoints and the /static directory without authentication
    if (
        path == "/login"
        or path == "/signup"
        or path.startswith("/api/users/login")
        or path.startswith("/api/users/signup")
        or path.startswith("/static")
    ):
        return await call_next(request)

    # Check authentication cookie
    logged_in = request.cookies.get("logged_in")
    if logged_in != "true":
        return RedirectResponse(
            url="/login", status_code=status.HTTP_303_SEE_OTHER
        )
    return await call_next(request)


# Serve explicit HTML pages
@app.get("/")
def serve_index():
    return FileResponse("static/index.html")


@app.get("/login")
def serve_login():
    return FileResponse("static/login.html")

@app.get("/signup")
def serve_signup():
    return FileResponse("static/signup.html");


# Mount static directory to /static so assets (e.g., /static/style.css) bypass auth cleanly
app.mount("/static", StaticFiles(directory="static"), name="static")

def get_current_user_data(request: Request, db: Session):
    username = request.cookies.get("username");
    if not username or username == "":
        raise HTTPException(status_code=401, detail="Not authenticated");
    user = db.query(UserDB).filter(UserDB.username == username).first();
    if not user:
        raise HTTPException(status_code=404, detail="User not found!");
    return {
        "username": user.username,
        "user_id": user.id
    };

@app.get("/api/tasks", response_model=List[Task])
def get_tasks(request: Request, db: Session = Depends(get_readDB)):
    curr_user = get_current_user_data(request, db);
    user_tasks = db.query(NotedTasks).filter(NotedTasks.account_id == curr_user["user_id"]).all(); 
    return user_tasks;


@app.post("/api/tasks", response_model=Task)
def create_task(
    payload: TaskCreate, 
    request: Request, 
    write_db: Session = Depends(get_writeDB),
    read_db: Session = Depends(get_readDB)):
    curr_user = get_current_user_data(request, read_db);
    new_task = TaskCreate(
        content = payload["content"],
        order_priority = int(payload["order_priority"]),
        is_done = int(payload["is_done"]),
        account_id = int(payload["account_id"])
    );
    write_db.add(new_task);
    write_db.commit();
    write_db.refresh(new_task);
    return new_task;

    


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int, request: Request, write_db: Session = Depends(get_writeDB), read_db: Session = Depends(get_readDB)):
    curr_user = get_current_user_data(request, read_db);
    task = write_db.query(NotedTasks).filter(
        NotedTasks.id == task_id,
        NotedTasks.account_id == curr_user["id"]
    );
    if not task:
        raise HTTPException(status_code=404, detail="Desired task is not found!");
    write_db.delete(task);
    write_db.commit();
    return {"status": "deleted"}


@app.post("/api/users/login")
def login(payload: LoginRequest, db: Session = Depends(get_readDB)):
    existing_user = db.query(UserDB).filter(UserDB.username == payload.username).first();
    if not existing_user:
        raise HTTPException(
            status_code=404, detail="User not found"
        );
    if existing_user.password != payload.password:
        raise HTTException(status_code=401, detail="Wrong password!");

    response = RedirectResponse(
        url="/", status_code=status.HTTP_303_SEE_OTHER
    );
    response.set_cookie(
        key="logged_in", value="true", httponly=True
    );
    response.set_cookie(key="username", value=existing_user.username);
    return response;

@app.post("/api/users/signup")
def signup(payload: SignupRequest, db: Session = Depends(get_writeDB)):
    existing_user = db.query(UserDB).filter(UserDB.username == payload.username).first();
    if existing_user:
        raise HTTPException(status_code=400, detail="Username is already exist!");
    
    new_user = UserDB(
        firstname=payload.firstname,
        lastname=payload.lastname,
        age=payload.age,
        nationality=payload.nationality,
        gender=payload.gender,
        username=payload.username,
        password=payload.password
    );

    db.add(new_user);
    db.commit();
    db.refresh(new_user);
    return {"message": "Created a new account!", "userID": new_user.id};

@app.get("/api/users/me")
def get_current_user(request: Request, db: Session = Depends(get_db)):
    username = request.cookies.get("username");
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated");
    user = db.query(UserDB).filter(UserDB.username == username).first();
    if not user:
        raise HTTPException(status_code=404, detail="User not found!");
    return {
        "username": user.username,
        "firstname": user.firstname,
        "lastname": user.lastname
    };

@app.post("/api/users/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER);
    response.delete_cookie("logged_in");
    response.delete_cookie("username");
    return response;

    