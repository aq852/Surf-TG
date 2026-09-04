# ----------------------------------------------------------------------
# Stage 1: Build Stage (Only includes tools necessary for installation)
# ----------------------------------------------------------------------
FROM python:3.12-alpine AS builder

# Install build dependencies (for compiling C extensions like tgcrypto) and 'bash'.
# NOTE: We DO NOT install 'git' here.
RUN apk add --no-cache \
        bash \
        build-base \
        libffi-dev \
        openssl-dev

# Set the working directory
WORKDIR /app

# Copy requirement file first to leverage Docker layer caching
COPY requirements.txt .

# Install pip and uv
RUN pip install -U pip uv

# Install Python dependencies.
RUN uv pip install --system --no-cache-dir -r requirements.txt

# Copy the rest of the application source code
COPY . /app

# ----------------------------------------------------------------------
# Stage 2: Final Stage (Minimal Runtime Image)
# ----------------------------------------------------------------------
FROM python:3.12-alpine

# Set the working directory
WORKDIR /app

# Install necessary runtime system dependencies:
# Runtime contains only the libraries required by the application.
RUN apk add --no-cache libstdc++

# Copy the installed Python dependencies from the 'builder' stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copy the application source code
COPY --from=builder /app /app

RUN chown -R nobody:nogroup /app

# Command to run when the container starts
USER nobody
CMD ["python3", "-m", "bot"]
