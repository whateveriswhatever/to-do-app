from typing import List
from fastapi import FastAPI, HTTPException, Request, status, Depends, Cookie, APIRouter
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os
import random
from dotenv import load_dotenv
from redis_fastapi import FastAPIRedis, AsyncRedisDep
from redis_init_db import redis_client
from redis_cache import CacheService
from redis.asyncio import Redis, ConnectionPool;

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

# Dependency to get Redis and cache
async def get_redis() -> Redis:
    return redis_client.get_client();

async def get_cache(redis: Redis = Depends(get_redis)) -> CacheService:
    return CacheService(redis);

app = FastAPI();
FastAPIRedis(app).lifespan();
router = APIRouter();

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

@router.get("/cache/{key}")
async def get_cached_value(key: str, redis: Redis = Depends(get_redis)):
    value = await redis.get(key);
    return {"key": key, "value": value};

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

async def get_current_user_data(request: Request, db: Session, cache: CacheService = Depends(get_cache)):
    username = request.cookies.get("username");
    if not username or username == '':
        raise HTTPException(status_code=401, detail="Not authenticated");
    async def query_user_data_manually():
        user = db.query(UserDB).filter(UserDB.username == username).first();
        if not user:
            return None;
        return {
            "username": user.username,
            "user_id": user.id
        };
    
    user_data = await cache.remember(f"user:account:{username}", 666, query_user_data_manually);
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found!");
    return user_data;

@app.get("/api/tasks", response_model=List[Task])
async def get_tasks(request: Request, db: Session = Depends(get_readDB), curr_user_data: dict = Depends(get_current_user_data), cache: CacheService = Depends(get_cache)):
    async def query_user_tasks_manually():
        user_tasks = db.query(NotedTasks).filter(NotedTasks.account_id == curr_user_data["user_id"]).all();
        return [
            {
                "id": task.id,
                "content": task.content,
                "order_priority": task.order_priority,
                "is_done": task.is_done,
                "account_id": task.account_id
            }
            for task in user_tasks
        ];
    user_tasks = await cache.remember("user:tasks:{}".format(curr_user_data["user_id"]), 666, query_user_tasks_manually);
    return user_tasks;


@app.post("/api/tasks", response_model=Task)
async def create_task(
        payload: TaskCreate, 
        request: Request, 
        write_db: Session = Depends(get_writeDB),
        read_db: Session = Depends(get_readDB),
        curr_user_data: dict = Depends(get_current_user_data),
        cache: CacheService = Depends(get_cache)):
    new_task = NotedTasks(
        content = payload.content,
        order_priority = payload.order_priority,
        is_done = payload.is_done,
        account_id = curr_user_data["user_id"]
    );
    write_db.add(new_task);
    write_db.commit();
    write_db.refresh(new_task);
    await cache.delete("user:tasks:{}".format(curr_user_data["user_id"]));
    return new_task;


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int, request: Request, write_db: Session = Depends(get_writeDB), read_db: Session = Depends(get_readDB), curr_user_data: dict = Depends(get_current_user_data), cache: CacheService = Depends(get_cache)):
    task = write_db.query(NotedTasks).filter(
        NotedTasks.id == task_id,
        NotedTasks.account_id == curr_user["user_id"]
    ).first();
    if not task:
        raise HTTPException(status_code=404, detail="Desired task is not found!");
    write_db.delete(task);
    write_db.commit();
    await cache.delete("user:tasks:{}".format(current_user_data["user_id"]));
    return {"status": "deleted"}


@app.post("/api/users/login")
async def login(payload: LoginRequest, db: Session = Depends(get_readDB), cache: CacheService = Depends(get_cache)):
    existing_user = db.query(UserDB).filter(UserDB.username == payload.username).first();
    if not existing_user:
        raise HTTPException(
            status_code=404, detail="User not found"
        );
    if existing_user.password != payload.password:
        raise HTTPException(status_code=401, detail="Wrong password!");

    user_data = {
        "username": existing_user.username,
        "user_id": existing_user.id
    };

    user = await cache.set(f"user:account:{existing_user.username}", user_data, 666);
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
async def get_current_user(request: Request, db: Session = Depends(get_db), cache: CacheService = Depends(get_cache)):
    username = request.cookies.get("username");
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated");
    async def query_userData_manually():
        user = db.query(UserDB).filter(UserDB.username == username).first();
        return {
            "username": user.username,
            "user_id": user.id
        };
    
    user = cache.remember("user:account:{}".format(username), 666, query_userData_manually);    
    if not user:
        raise HTTPException(status_code=404, detail="User not found!");
    return user;

@app.post("/api/users/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER);
    response.delete_cookie("logged_in");
    response.delete_cookie("username");
    return response;

    