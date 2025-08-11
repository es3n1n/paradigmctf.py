FROM ghcr.io/foundry-rs/foundry:latest AS builder

# Running as root to have access to /artifacts/
USER root
ENV FOUNDRY_DISABLE_NIGHTLY_WARNING=1

COPY project /project
RUN cd /project && \
    forge build --out /artifacts/out --cache-path /artifacts/cache

FROM ghcr.io/es3n1n/paradigmctf.py:latest

COPY --from=es3n1n/pow-proxy:latest /app/main /app/pow
COPY --chown=user:user . /challenge

COPY --from=builder --chown=user:user /artifacts /artifacts
RUN chmod +x /challenge/challenge.py
RUN chmod +x /challenge/entrypoint.sh

# To enable POW, set POW_DIFFICULTY to a value greater than 0
ENV LISTEN_PORT=1337 FORWARD_PORT=1338 POW_DIFFICULTY=0 CONN_LIFETIME_MS=30000
CMD /challenge/entrypoint.sh
