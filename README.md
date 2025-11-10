# OpenCV Calibration WebApp Module

This repository contains a small Viam module that exposes calibration files
stored on the robot filesystem. The service implements the Generic service API
and accepts two `do_command` calls:

| Command     | Payload                                    | Description                          |
|-------------|---------------------------------------------|--------------------------------------|
| `list_passes` | `{ "command": "list_passes" }`              | Returns all pass folders and files.  |
| `get_file`  | `{ "command": "get_file", "pass_id": "...", "filename": "..." }` | Returns one file (base64 encoded). |

The repository also includes static assets (`index.html`, `style.css`,
`main.ts`) that you can bundle into a separate Viam application if you want a
hosted UI. They are not required for the module itself.

## Repository layout

```
opencv-webapp/
├── opencv_webapp/
│   ├── __init__.py
│   └── webapp.py                # Generic service implementation
├── example-config.json          # Sample robot configuration snippet
├── index.html / style.css / main.ts  # Optional frontend assets
├── meta.json                    # Module manifest (build + entrypoint)
├── requirements.txt             # Python dependencies
├── run.sh                       # Entrypoint used by viam-server
└── Makefile                     # Helper targets for packaging
```

## Packaging & build

The module vendors its Python dependencies into a local `lib/` directory during
build. The `Makefile` hides the details:

```bash
make build        # installs deps into lib/ and creates module.tar.gz
make clean        # removes lib/ and the tarball
```

`meta.json` references these targets so `viam module reload --cloud-build`
works out of the box.

## Deploying to a robot

1. Push this repository to a git host the Viam builder can access.
2. In the Viam console, add a **Module → Local** entry pointing to this repo.
3. Add a Generic service resource:

   ```json
   {
     "name": "webapp",
     "type": "generic",
     "namespace": "viam",
     "model": "viam:opencv-webapp:webapp",
     "attributes": {
       "assets_dir": "./module-data/calibration-passes"
     }
   }
   ```

   Change `assets_dir` if your passes live elsewhere.

4. After deployment, the service responds to `do_command` from any Viam SDK
client (including the optional frontend in this repo).

## Local testing

```bash
# Create some fake data
mkdir -p module-data/calibration-passes/test-pass
echo "example" > module-data/calibration-passes/test-pass/data.txt
touch module-data/calibration-passes/test-pass/.complete

# Invoke service locally
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python - <<'PY'
from opencv_webapp.webapp import WebApp
import asyncio

async def main():
    svc = WebApp("./module-data/calibration-passes")
    print(await svc.do_command({"command": "list_passes"}))

asyncio.run(main())
PY
```

## Optional frontend

`index.html`, `style.css`, and `main.ts` can be bundled (for example with
esbuild or Vite) and hosted via Viam Applications.

The frontend now discovers credentials automatically:

- When deployed through Viam Applications, the runtime injects
  `window.__VIAM_WEB_APP__`; the script reads the machine host, service name,
  and any referenced secrets from there.
- For local development, edit the JSON block inside
  `index.html`’s `<script id="viam-web-app-config">…</script>` tag. Replace the
  placeholder host/API key with your real values before building.
- Ensure the `serviceName` matches the Generic service name configured on your
  machine (for example `webapp` or `calibration-service`).

## License

Apache-2.0
