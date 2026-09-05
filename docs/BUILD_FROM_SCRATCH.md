# Build the M-Pesa Payment Gateway from Scratch

This guide explains the tools, project structure, implementation, testing, containerization, continuous integration and Render deployment.

## Tools and concepts

| Item | Meaning and use |
| --- | --- |
| Git | Tracks source-code changes and sends them to GitHub. |
| GitHub | Hosts the repository and runs the automated CI workflow. |
| VS Code | The editor used to create files, run commands and debug Python. |
| Virtual environment | Isolates this project's Python packages from other projects. |
| FastAPI | Creates validated HTTP API endpoints and automatic Swagger documentation. |
| Uvicorn | Runs the FastAPI application as an ASGI web server. |
| Pydantic | Validates and converts request and response data. |
| SQLite | Stores payment records in a lightweight local database file. |
| httpx | Sends asynchronous HTTPS requests to the Safaricom Daraja API. |
| pytest | Runs repeatable unit and integration tests. |
| Docker | Packages the application and its dependencies into a portable image. |
| GitHub Actions | Automatically tests and builds the project after a push. |
| Render | Builds the Docker image and hosts the public web service. |

## 1. Prepare VS Code and the repository

Install Python 3.12, Git and VS Code. Add the official Python extension in VS Code, then open a terminal with **Terminal > New Terminal**.

```bash
git clone https://github.com/kimtour/mpesa-payment-gateway.git # Download the repository and its history from GitHub.
cd mpesa-payment-gateway # Move the terminal into the downloaded project folder.
code . # Open the current folder as a VS Code workspace.
```

To build an empty project instead, create a folder and initialize Git:

```bash
mkdir mpesa-payment-gateway # Create the project directory.
cd mpesa-payment-gateway # Enter the new directory.
git init # Start a local Git repository in this directory.
mkdir -p app/static tests docs .github/workflows # Create folders for code, browser files, tests, documentation and CI.
touch app/__init__.py # Mark the app directory as a Python package.
```

## 2. Create and activate a virtual environment

```bash
python3 -m venv .venv # Create an isolated Python installation inside .venv.
source .venv/bin/activate # Activate the environment on Linux or macOS.
python -m pip install --upgrade pip # Upgrade the package installer inside the environment.
pip install fastapi uvicorn httpx pydantic pytest pytest-cov # Install runtime and testing packages.
```

On Windows PowerShell, activate it with:

```powershell
.venv\Scripts\Activate.ps1 # Activate the virtual environment in PowerShell.
python -m pip install --upgrade pip # Upgrade pip inside the activated environment.
```

In VS Code, press **Command/Ctrl + Shift + P**, select **Python: Select Interpreter**, and choose the interpreter inside `.venv`.

## 3. Record the dependencies

Create `requirements.txt` for production packages:

```text
fastapi==0.116.1 # Provide the API framework and automatic OpenAPI documentation.
uvicorn[standard]==0.35.0 # Run FastAPI and include production server extras.
httpx==0.28.1 # Send asynchronous requests to the Daraja endpoints.
pydantic==2.11.7 # Validate phone numbers, amounts and response objects.
```

Create `requirements-dev.txt` for development tools:

```text
-r requirements.txt # Install every production dependency first.
pytest==8.4.1 # Discover and run automated tests.
pytest-cov==6.2.1 # Measure how much application code the tests execute.
```

## 4. Understand the project structure

```text
app/ # Contains the application package.
app/main.py # Defines FastAPI routes and business operations.
app/models.py # Defines validated Pydantic request and response models.
app/database.py # Creates the SQLite schema and runs database queries.
app/gateway.py # Encapsulates simulated and real Daraja communication.
app/config.py # Reads configuration from environment variables.
app/static/ # Contains the HTML, CSS and JavaScript dashboard.
tests/ # Contains unit and integration tests.
.github/workflows/ci.yml # Defines the GitHub Actions CI pipeline.
Dockerfile # Describes the deployable container image.
render.yaml # Describes the Render service configuration.
```

## 5. Create validated request data

A small version of `app/models.py` looks as follows:

```python
from decimal import Decimal  # Import an exact numeric type suitable for money.
from pydantic import BaseModel, Field  # Import the base schema and validation rules.

class PaymentRequest(BaseModel):  # Define the JSON structure accepted by the API.
    phone_number: str  # Require a phone number string.
    amount: Decimal = Field(gt=0, le=150000)  # Accept positive amounts up to KES 150,000.
    account_reference: str = Field(min_length=1, max_length=32)  # Limit the reference length.
```

Pydantic returns an HTTP 422 response automatically when supplied JSON violates these rules.

## 6. Create the FastAPI application

A minimal `app/main.py` can start with:

```python
from fastapi import FastAPI  # Import the FastAPI application class.
from app.models import PaymentRequest  # Import the validated request model.

app = FastAPI(title="M-Pesa Payment Gateway")  # Create the application and set its Swagger title.

@app.get("/api/health")  # Register a GET endpoint for monitoring.
def health() -> dict:  # Define a synchronous health-check function.
    return {"status": "healthy"}  # Return JSON confirming that the process is responding.

@app.post("/api/payments/stk-push", status_code=201)  # Register a payment-creation endpoint.
async def create_payment(request: PaymentRequest) -> dict:  # Validate JSON before running the function.
    return {"phone": request.phone_number, "status": "PENDING"}  # Return a simplified pending payment.
```

Run the API locally:

```bash
uvicorn app.main:app --reload # Import app from app/main.py and restart when source files change.
```

Open `http://127.0.0.1:8000/docs` to view Swagger UI.

## 7. Store records with SQLite

SQLite is included with Python, so it needs no separate server. Parameter placeholders protect values from SQL injection.

```python
import sqlite3  # Import Python's standard SQLite driver.

connection = sqlite3.connect("payments.db")  # Open or create the database file.
connection.execute("CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY, status TEXT NOT NULL)")  # Create the table once.
connection.execute("INSERT INTO payments (id, status) VALUES (?, ?)", ("payment-1", "PENDING"))  # Insert values safely with placeholders.
connection.commit()  # Persist the transaction to disk.
connection.close()  # Release the database connection.
```

The full project also stores amount, phone number, reference, provider IDs, receipt, idempotency key and timestamps.

## 8. Call Daraja with httpx

The real integration obtains an OAuth token and submits an STK Push over HTTPS.

```python
import httpx  # Import the asynchronous HTTP client.

async with httpx.AsyncClient(timeout=15) as client:  # Open a client that stops waiting after 15 seconds.
    response = await client.post(url, json=payload, headers=headers)  # Send the STK Push JSON and authorization header.
    response.raise_for_status()  # Raise an exception when Daraja returns an error status.
    provider_data = response.json()  # Convert the successful JSON response into a Python dictionary.
```

Keep the consumer key, consumer secret and passkey in environment variables, never in GitHub.

## 9. Add idempotency and callbacks

An idempotency key identifies one intended payment request. When the same key arrives twice, return the original record instead of creating a duplicate. The callback endpoint later changes the saved status from `PENDING` to `COMPLETED` or `FAILED`.

```python
existing = get_payment_by_idempotency_key(idempotency_key)  # Search for an earlier request with the same key.
if existing:  # Check whether that request already exists.
    return existing  # Return the saved transaction without initiating another STK Push.
```

## 10. Write automated tests

Create `tests/test_api.py`:

```python
def test_health(client):  # Define one independently repeatable test.
    response = client.get("/api/health")  # Send a request through FastAPI's in-process test client.
    assert response.status_code == 200  # Confirm that the endpoint succeeded.
    assert response.json()["status"] == "healthy"  # Confirm the response content.
```

Run the full test suite and enforce coverage:

```bash
pytest --cov=app --cov-report=term-missing --cov-fail-under=80 # Run tests, list uncovered lines and fail below 80 percent.
```

## 11. Build the Docker image

The repository's `Dockerfile` packages the application:

```dockerfile
FROM python:3.12-slim # Start from a compact official Python image.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 # Disable cache files and show logs immediately.
WORKDIR /app # Make /app the working directory inside the container.
COPY requirements.txt . # Copy dependency definitions before source code for better build caching.
RUN pip install --no-cache-dir -r requirements.txt # Install production packages without retaining the download cache.
COPY app ./app # Copy the application package into the image.
EXPOSE 8000 # Document the port used by Uvicorn.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] # Start the API and accept external container traffic.
```

Build and run it locally:

```bash
docker build -t mpesa-payment-gateway . # Build an image and assign it a readable local name.
docker run --rm -p 8000:8000 -e SIMULATION_MODE=true mpesa-payment-gateway # Run the container and map its port to the computer.
```

## 12. Add GitHub Actions CI

Create `.github/workflows/ci.yml`:

```yaml
name: CI # Display this workflow as CI in GitHub Actions.
on: [push, pull_request] # Run after pushes and pull-request updates.
jobs: # Begin the collection of automated jobs.
  test: # Name the verification job test.
    runs-on: ubuntu-latest # Use GitHub's current Ubuntu runner.
    steps: # List the job operations in execution order.
      - uses: actions/checkout@v4 # Download the repository onto the runner.
      - uses: actions/setup-python@v5 # Install the requested Python runtime.
        with: # Supply configuration to the Python setup action.
          python-version: "3.12" # Match the application's supported Python version.
      - run: pip install -r requirements-dev.txt # Install application and test dependencies.
      - run: pytest --cov=app --cov-fail-under=80 # Run tests and enforce the coverage threshold.
      - run: docker build -t mpesa-payment-gateway . # Prove that the deployment image builds.
```

## 13. Configure Render

The root `render.yaml` makes the deployment repeatable:

```yaml
services: # Begin the list of Render resources.
  - type: web # Create a public HTTP web service.
    name: mpesa-payment-gateway # Assign the service and subdomain name.
    runtime: docker # Build and run the repository's Dockerfile.
    branch: main # Deploy source code from the main branch.
    region: frankfurt # Host the service in Render's Frankfurt region.
    plan: free # Use the free compute plan.
    healthCheckPath: /api/health # Ask Render to monitor the dedicated health endpoint.
    envVars: # Define non-secret deployment configuration.
      - key: SIMULATION_MODE # Name the switch that disables real Daraja requests.
        value: "true" # Keep the public demonstration in safe simulation mode.
      - key: DATABASE_PATH # Name the SQLite file-location setting.
        value: /tmp/payments.db # Store disposable demo records in the writable temporary directory.
```

In Render, choose **New > Blueprint**, connect the GitHub repository, select the free plan and apply the Blueprint. The public service exposes the dashboard at `/` and Swagger at `/docs`.

## 14. Push your work to GitHub

```bash
git status # Review every file that is new or changed.
git add . # Stage the reviewed project files for the next commit.
git commit -m "Build M-Pesa payment gateway" # Save a named snapshot in local Git history.
git branch -M main # Name the primary branch main.
git remote add origin https://github.com/YOUR_USERNAME/mpesa-payment-gateway.git # Link the local repository to GitHub.
git push -u origin main # Upload the branch and remember its upstream destination.
```

## Verification checklist

- Run the pytest command and confirm every test passes.
- Open the dashboard and confirm the health badge becomes green.
- Submit one payment and confirm it appears as `PENDING`.
- Complete, cancel and refund the appropriate transactions.
- Filter by status, search by reference and download the CSV export.
- Open Swagger and confirm all documented endpoints appear.
- Confirm GitHub Actions succeeds and the Render service is live.
