# Quick Start Guide

## What I Created

A **minimal** Viam web app that replaces your Flask implementation:

### ✅ What's Different:
- **No Flask server** - Pure TypeScript frontend
- **Same exact UI** - Kept all your styling and design
- **Viam SDK integration** - Connects through Viam's platform
- **Can deploy to viamapplications.com** - Get that URL you wanted!

### ✅ What's the Same:
- **Exact same look and feel**
- **Same file browser functionality**
- **Same expandable passes**
- **Same download buttons**

## File Overview

### Python Module (runs on robot)
- `opencv_webapp/webapp.py` – ~150 lines, just reads the filesystem
- Exposes 2 commands: `list_passes` and `get_file`

### Optional frontend (runs in browser)
- `main.ts`, `index.html`, `style.css` – same UI as before
- Bundle with a tool like esbuild/Vite before deploying

## Next Steps

1. **Test locally first:**
   ```bash
   cd /path/to/opencv-webapp
   npm install
   # Update the JSON block in index.html with your robot credentials and service name
   npm start
   ```

2. **Deploy Python module to robot:**
   - Upload to GitHub
   - Add as module in app.viam.com
   - Configure as shown in example-config.json

3. **Deploy frontend:**
   - Follow Viam app deployment docs
   - Or just run locally for now

4. **Access your webapp:**
   - Locally: http://localhost:8000
   - Or: https://your-app.viamapplications.com (credentials are injected automatically by the Viam portal)

## Total Lines of Code

- Python: ~150 lines (vs ~450 in Flask version)
- TypeScript: ~200 lines
- HTML/CSS: Same as your original

**Much simpler!** ✨
