FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY . ./
# The trigger/learner-model engine ships as a git submodule under vendor/; install
# it editable first so vex_agent can import learner_models / log_parser_delta_engine.
# The editable install keeps package __file__ at /app/vex_agent, so the bind-mounted
# invite_hub_sync_state.json (compose) lands where fetch_invite_hub_logs reads it.
RUN pip install -e ./vendor/agent-lm-packages && pip install -e .
EXPOSE 8000
CMD ["uvicorn", "vex_agent.app:app", "--host", "0.0.0.0", "--port", "8000"]
