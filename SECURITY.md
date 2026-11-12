# Security

## Reporting a problem

Please report security problems privately, not in a public issue or pull request.

Use GitHub's private vulnerability reporting: on the repository, go to **Security** →
**Report a vulnerability**
(<https://github.com/pbexiga/solum-builder/security/advisories/new>).

Say what you found, how to reproduce it, and what you think it allows. You'll get a reply as soon
as I can manage; this is a one-person project, so allow a few days.

## Scope

Solum Builder is a single-user app that runs on your own machine or in a local container. It has
no accounts and no cloud service. Problems that matter most: anything that lets a crafted circuit,
library or model file run code or read or write files outside `DATA_DIR` and `CACHE_DIR`, and
anything that exposes the app to other machines by default.

## Supported versions

Only the latest release gets fixes.
