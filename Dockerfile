# Use docker image with pre-installed poetry
FROM pfeiffermax/python-poetry:1.12.0-poetry1.8.4-python3.12.7-slim-bookworm

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1

# Install required packages for cade functionality
RUN apt-get update && apt-get install --no-install-recommends -y \
    curl \
    ffmpeg \
    git \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install deno for yt-dlp JS challenges
RUN curl -fsSL https://deno.land/install.sh | sh -s -- -y

# Copy cade folder & dependency info from this repo into the docker container
WORKDIR /cade
COPY poetry.lock pyproject.toml ./
COPY .git ./.git
RUN poetry config virtualenvs.create false
RUN poetry check && poetry install --no-interaction --no-cache --without dev

# Run cade
COPY cade /cade
CMD [ "poetry", "run", "python", "bot.py" ]