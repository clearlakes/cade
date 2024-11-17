FROM pfeiffermax/python-poetry:1.12.0-poetry1.8.4-python3.12.7-slim-bookworm

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install --no-install-recommends -y \
    curl \
    ffmpeg \
    git \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /cade
COPY poetry.lock pyproject.toml ./
COPY .git ./.git
RUN poetry config virtualenvs.create false
RUN poetry check && poetry install --no-interaction --no-cache --without dev

COPY cade /cade
CMD [ "poetry", "run", "python", "bot.py" ]