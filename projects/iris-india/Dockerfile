FROM python:3.11-slim

WORKDIR /app

# Install dependencies first — separate layer so code changes don't
# invalidate the pip cache on every rebuild.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Default: run the scheduler (continuous scoring loop).
# Override CMD in docker compose to run one-off scripts, e.g.:
#   docker compose run --rm evaluation-runner-iris-india python run_golden_dataset.py
CMD ["python", "scheduler.py"]
