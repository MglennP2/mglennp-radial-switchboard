FROM python:3.12-slim
WORKDIR /app
COPY radial_synapse_phonebook.py switchboard_api.py ./
ENV PORT=8080
EXPOSE 8080
CMD ["python", "switchboard_api.py"]
