# Running on a NAS or home server

Any machine that runs Docker (or Podman) runs Solum Builder: the image builds on x86-64 and on ARM64 (checked on Apple Silicon). A built image runs only on the kind of processor it was built on, so copy one (A) only from a machine of the same kind as the NAS; otherwise build it on the NAS (B).

## A. Copy a built image
On your computer, in the repo:
```sh
make image-tar        # writes dist/solum-builder-image.tar.gz (~70 MB)
```
Copy `dist/solum-builder-image.tar.gz` and `compose.yaml` to a folder on the NAS, e.g. `/path/to/solum/`, over an SMB share or `scp`:
```sh
scp dist/solum-builder-image.tar.gz compose.yaml <user>@<nas-ip>:/path/to/solum/
```
Then on the NAS (SSH in; use `sudo` unless your user is in the `docker` group):
```sh
cd /path/to/solum
sudo docker load -i solum-builder-image.tar.gz
sudo docker compose run --rm solum-builder solum bench
```
The bench prints timings as JSON in about 10–30 s, a quick check that the simulator runs there.

## B. Build on the NAS
Copy the whole repo to the NAS (or `git clone` it there), then:
```sh
cd /path/to/solum
sudo docker compose build
sudo docker compose run --rm solum-builder solum bench
```
Needs internet access on the NAS (Debian packages and PyPI); the build takes a few minutes.

## Serving the app
```sh
cp .env.example .env    # optional: edit DATA_DIR (a share you back up) and CACHE_DIR (local disk)
sudo docker compose up -d
```
Open `http://<nas-ip>:8000`. `http://<nas-ip>:8000/api/health` should show `"engine": "native"`.

## Memory
Solum Builder is designed to stay within 8 GB (D-031). In use it takes well under 100 MB.
