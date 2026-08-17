from typing import List
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()

clone_user_accs = {
    "users": [
        {"username": "ditcumay", "password": "hahahaha"},
        {"username": "bulontaodi", "password": "cocailon"},
    ]
}


class Task(BaseModel):
    id: int
    text: str


class LoginRequest(BaseModel):
    username: str
    password: str


tasks: List[Task] = []
task_id_counter = 1


@app.middleware("http")
async def authentication_middleware(request: Request, call_next):
    path = request.url.path
    # Allow login endpoints and the /static directory without authentication
    if (
        path == "/login"
        or path.startswith("/api/users/login")
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


# Mount static directory to /static so assets (e.g., /static/style.css) bypass auth cleanly
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/api/tasks", response_model=List[Task])
def get_task():
    return tasks


@app.post("/api/tasks", response_model=Task)
def create_task(payload: dict):
    global task_id_counter
    task = Task(id=task_id_counter, text=payload.get("text", ""))
    tasks.append(task)
    task_id_counter += 1
    return task


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    global tasks
    tasks = [t for t in tasks if t.id != task_id]
    return {"status": "deleted"}


@app.post("/api/users/login")
def login(payload: LoginRequest):
    for user in clone_user_accs["users"]:
        if user["username"] == payload.username:
            if user["password"] == payload.password:
                response = RedirectResponse(
                    url="/", status_code=status.HTTP_303_SEE_OTHER
                )
                response.set_cookie(
                    key="logged_in", value="true", httponly=True
                )
                return response
            else:
                raise HTTPException(
                    status_code=401, detail="Wrong password!"
                )

    raise HTTPException(status_code=404, detail="User not found!")