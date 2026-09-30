FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN pip install --user --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install --user -r requirements.txt
COPY --chown=user gridalpha ./gridalpha
COPY --chown=user pyproject.toml start.sh ./
ENV GRIDALPHA_DATA_MODE=synthetic \
    GRIDALPHA_DATA_DIR=/home/user/app/data \
    GRIDALPHA_ARTIFACTS_DIR=/home/user/app/artifacts
EXPOSE 7860
CMD ["bash", "start.sh"]