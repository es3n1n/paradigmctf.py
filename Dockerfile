FROM python:3.13.5-slim

# Set up unprivileged user and install dependencies
# TODO: we need bsdmainutils so we have hexdump so foundry-huff can...
#       generate some random bytes... :/
RUN true && \
    useradd -u 1000 -m user && \
    apt-get update && \
    apt-get install -y curl git socat bsdmainutils && \
    rm -rf /var/cache/apt/lists /var/lib/apt/lists/* && \
    true

# Install Foundry
ENV FOUNDRY_DIR=/opt/foundry

ENV PATH=${FOUNDRY_DIR}/bin/:${PATH}

RUN true && \
    curl -L https://foundry.paradigm.xyz | bash && \
    foundryup && \
    true

# TODO(es3n1n): huff2?
# Install Huff
# ENV HUFF_DIR=/opt/huff

# ENV PATH=${HUFF_DIR}/bin/:${PATH}

# RUN true && \
#     curl -L http://get.huff.sh | bash && \
#     huffup && \
#     true

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install the library
COPY . /tmp/paradigmctf.py
RUN true && \
    uv pip install --system --no-cache-dir /tmp/paradigmctf.py && \
    rm -rf /tmp/paradigmctf.py && \
    true

USER 1000

WORKDIR /home/user