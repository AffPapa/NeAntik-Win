# Release evidence — 0.8.29-preview

Дата публикации: 2026-10-15. Это тестовая portable-сборка, не гарантия
анонимности. Chromium 155.0.8059.79 — неизменённое ядро; модификации
browser/device fingerprint нет.

## Источник и артефакт

- Annotated tag и GitHub prerelease: [`v0.8.29-preview`](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.29-preview).
- Binary-source commit: `c6f46c50b92ac3931d9ba6a7bd066d5793b5342b`; provenance внутри архива указывает clean source state.
- Portable ZIP: `NeAntikWin-portable-v0.8.29-preview.zip`, 262,392,554 байта, SHA-256 `c14d4b9295d9daf1bfe490a02043bd6f62781612dddc3f332ae1bc868f506d84`.
- Packaged EXE SHA-256: `235824ffb3751f83efaeaa0ea59f0e0e7e86f72a3c6afb3bd8c3861a55b1df86`.
- GitHub также содержит `.zip.sha256` (106 байт; asset digest `8c22061eb7c877d176c1fba9c1579521ff34dd954955582463fb72c038fd8069`) и `.manifest.json` (197,132 байта; asset digest `c5fb0347db739db61e9b1ed426dec65c81d3d3fc291a6a1d42d165ccbb9def05`).

## Проверки

| Gate | Результат |
| --- | --- |
| Windows CI для binary-source `c6f46c5` (run `38768683580`) | PASS |
| Windows CI для commit, записавшего публикационные ворота `294e3fa` (run `38772867354`) | PASS |
| Public-source guard после добавления этого evidence-файла | PASS, 231 файл |
| Локальный архив verifier | PASS, 1,066 файлов |
| Упакованный EXE `--self-test` | PASS, exit 0 |
| Публичный ZIP повторно скачан, SHA и длина сравнены, archive verifier запущен на скачанном файле | PASS, совпадение |
| GUI-smoke точного кандидата: inline warning, consent перед действием расширений, отказ отменяет запуск и сохраняет профиль готовым | PASS |
| Ввод имени профиля в диалоге создания через UI bridge | INCONCLUSIVE после одной повторной попытки; форма закрыта без сохранения, это не доказывает дефект продукта |
| Полная keyboard-only форма, UIA/MSAA/NVDA, Windows 10/ARM64, другая физическая машина и внешние DNS/IPv6/UDP/STUN/TURN | NOT RUN |

GUI-проверка использовала отдельный QA-профиль в изолированной распакованной
сборке. Пользовательская portable Data не открывалась; Chromium не запускался.

## Сайт

- Существующий публичный Site сохранён без смены доступа: [nevision-win.mail782861.chatgpt.site](https://nevision-win.mail782861.chatgpt.site/).
- Sites version 67, source commit `6a9fa352edf277b71253a5fb2a9e473221eb1bec`.
- Главная, `/release.json` и `/CHANGELOG.md` ответили HTTP 200; live release metadata совпала с binary-source commit, ZIP URL, длиной и SHA-256. Публичный GitHub ZIP HEAD — HTTP 200, `Content-Length: 262392554`.

Предупреждение о расширениях объясняет возможное изменение видимых сайтам
параметров и доступ к данным профиля согласно разрешениям расширений. Это не
изолирует расширения и не означает fingerprint-защиту. Proxy, раздельные
профили и local-first режим не гарантируют анонимность или отсутствие сетевых
утечек.
