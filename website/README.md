# NeAntik Win website source

Source snapshot of https://nevision-win.mail782861.chatgpt.site/, renamed from
NeVision to NeAntik. It keeps the existing Vinext/React template; the desktop
launcher itself remains Python/Tk and does not use this framework.

Run `npm ci`, then `npm run dev` or `npm run build` in this directory. Node 24 was
used for the published build. The public Markdown routes explicitly use UTF-8.

Excluded intentionally: hosting identity, Git metadata, credentials, caches,
node_modules, build output and downloadable executable archives. Deployment
needs your own hosting configuration. Download URLs and release.json currently
describe the older verified NeVision release; they are not a new native release.

After each verified release update the main page, CHANGELOG.md, release.json and
download links together. Preserve old versioned archives; do not overwrite their
bytes or invent checksums. Native Chromium bundles are too large for the current
site asset limit and should use a verified GitHub Release asset URL.
