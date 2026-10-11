# NeVision visual assets

`app-icon-source.svg` is the editable source for the Windows application icon.
`nevision.ico` is the rendered multi-resolution icon used by the packaged executable.
`logo-mark.svg` documents the in-app mark; the Tkinter interface renders the same
geometry natively so controls remain sharp and the application starts without a web
renderer. The line icons in the interface follow the original 24px / 1.8px-stroke
NeVision visual system.

To regenerate `nevision.ico` after changing the source design, run:

```powershell
python -m pip install -r requirements-dev.txt
py -3.12 .\tools\render_brand_icon.py
```
