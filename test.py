from fastapi import FastAPI, HTTPException, status, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from pydantic import BaseModel
from typing import List

app = FastAPI();

clone_user_accs = {
    "users": [
        {"username": "ditcumay", "password": "hahahaha"},
        {"username": "bulontaodi", "password": "cocailon"}
    ]
};

class Task(BaseModel):
    id: int;
    text: str;

class LoginRequest(BaseModel):
    username: str;
    password: str;

tasks: List[Task] = [];
task_id_counter = 1;

@app.middleware("http")
async def authentication_middleware(request: Request, call_next):
    path = request.url.path;
    if (
        path == "/login" 
        or path.startswith("/api/users/login")
        or path.startswith("/static")
    ):
        return await call_next(request);
    # Checking authentication
    logged_in = request.cookies.get("logged_in");
    if logged_in != "true":
        return RedirectResponse(
            url="/login",
            status_code=status.HTTP_303_SEE_OTHER
        );
    return await call_next(request);

# Explicitly serve HTML files
@app.get("/")
def serve_index():
    return FileResponse("static/index.html");

@app.get("/login")
def server_login():
    return FileResponse("static/login.html");

@app.get("/api/tasks", response_model=List[Task])
def get_task():
    return tasks;

@app.post("/api/tasks", response_model=Task)
def create_task(payload: dict):
    global task_id_counter;
    task = Task(id=task_id_counter, text=payload.get("text", ""));
    tasks.append(task);
    task_id_counter += 1;
    return task;

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    global tasks;
    tasks = [t for t in tasks if t.id != task_id];
    return {"status": "deleted"};

@app.post("/api/users/login")
def login(payload: LoginRequest):
    for user in clone_user_accs["users"]:
        if user["username"] == payload.username:
            isCorrectPassword = True if user["password"] == payload.password else False;
            if isCorrectPassword:
                # Redirect user to the homepage
                print("Correct!");
                response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER);
                response.set_cookie(
                    key="logged_in",
                    value="true",
                    httponly=True
                );
                return response;
            else:
                # Keeping user to the current page
                print("Wrong password!");
                raise HTTPException(status_code=401, detail="Wrong password!");
    
    print("Account is not found!");
    raise HTTPException(status_code=404, detail="User not found!");

# Serve the HTML frontend
app.mount("/static", StaticFiles(directory="static", html=True), name="static");