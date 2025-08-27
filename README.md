# paradigmctf.py

Slightly modified/refactored/fixed version of [paradigmctf.py](https://github.com/paradigmxyz/paradigm-ctf-infrastructure/)

### Docker image

[`ghcr.io/es3n1n/paradigmctf.py:latest`](https://github.com/es3n1n/paradigmctf.py/pkgs/container/paradigmctf.py)

### What's changed

- Fixed instance deletion
- A lot of refactoring for PEP8 (mypy, ruff now produce zero errors)
- Added print instance option for the challenge launchers
- Refactored error handling within challenge launchers, no more sensitive info leaks
- Fixed a few race conditions within backends
- Moved web services to uvicorn workers(5 workers per service, editable) for better performance
- Added possibility to deploy multiple contracts per challenge **(you must use [our forge-ctf](https://github.com/es3n1n/forge-ctf))**
- Completely rewrote websocket anvil proxy, now it preserves connection
- Some parts of solvers were rewritten
- Added CTFd integration
- Migrated to uv
- Added API challenge launcher mode, so you can integrate instance spawning in your own CTF platform
- Added support for challenges with "dynamic" fields, which will be asked for user when requesting the flag
- Other improvements, fixes

### Untested features

- Daemons
- SQLite database

### Removed features (because I don't have any use for them yet)

- KOTH challenges/solvers

### Example deployments

There a few examples for deployments that are used for tests, you can reference them 
while deploying your own instance:

- [compose.yml](./compose.yml) - docker backend
- [k8s.yml](./k8s.yml) - k8s backend

### Deployment notes

- You must use [our forge-ctf](https://github.com/es3n1n/forge-ctf)
- Always double-check the amount of workers in the compose/k8s files, they are set to minimal values for testing, but
in production you should set them to a higher value (same goes for k8s resource limits)

### Running tests

To run tests, you will first need to deploy either of the example deployments.

### Todo

- Make database stuff async
- Get rid of blind exception catches
- Migrate from requests to aiohttp fully
- Spawned instances in docker backend aren't fully isolated from each other/orchestrator

paradigm's original todo:

- Huff support is pretty bad, needs the following changes upstream:
- - [huff-language/foundry-huff#47](https://github.com/huff-language/foundry-huff/issues/47)
- - Needs to support broadcasting from specific address
- - Needs to stop using hexdump to generate some random bytes
- Kubernetes support is not complete yet
