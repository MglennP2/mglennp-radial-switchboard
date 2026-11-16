FROM python:3.11-slim

WORKDIR /app

ENV PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RADIAL_USDC_TREASURY_ADDRESS=0x24b1a09b489c67c3e43f7cd1f3023aef544104fd

RUN addgroup --system appgroup && adduser --system --group appuser

COPY . /app/

RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8080

CMD ["python3", "radial_switchboard_v3_standalone.py", "--serve"]
