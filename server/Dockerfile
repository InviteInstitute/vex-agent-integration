FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY . ./
# editable install keeps package __file__ at /app/vex_agent, so the bind-mounted
# invite_hub_sync_state.json (compose) lands where fetch_invite_hub_logs reads it.
RUN pip install -e .
EXPOSE 8000
CMD ["uvicorn", "vex_agent.app:app", "--host", "0.0.0.0", "--port", "8000"]
