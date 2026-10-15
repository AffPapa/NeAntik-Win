# Release evidence — 0.8.30-preview

Дата подготовки: 2026-10-16. Preview portable-сборка, не гарантия анонимности.
Chromium 155.0.8059.79 — неизменённое ядро; модификации browser/device
fingerprint нет.

## Источник и артефакт

- Binary-source commit: `09f516f6dc340c126f1d1f8615d68a9f9251b734`.
- Annotated tag `v0.8.30-preview` и публичный GitHub prerelease опубликованы;
  tag указывает на точный binary-source commit выше. ZIP и sidecar/manifest
  доступны как неизменяемые assets; публичный ZIP был повторно скачан и совпал
  с локальным архивом по размеру и SHA-256.
- Portable ZIP: `NeAntikWin-portable-v0.8.30-preview.zip`, 262,393,616 байт,
  SHA-256 `07766ee6edc251c5d7a512cd056da41e5f2ae8994f63a7cd6c2d724e6bf7be6a`.
- Packaged EXE SHA-256:
  `5e566d7bd6048c2e980957f7fd48257e4c7fbd75dd39b923646cdbf256ec21cd`.
- Архив собран с неизменённым проверенным ядром из предыдущего portable-пакета;
  Chromium повторно не собирался. В manifest `fingerprint_modification=false`.

## Проверки

| Gate | Результат |
| --- | --- |
| Source branch `main`, clean tree, commit `09f516f` | PASS |
| Windows CI для точного source commit `09f516f` (run `38775059588`) | PASS |
| Локальный полный unittest suite | PASS, 301 тест, 3 skipped |
| Тесты storage/path isolation | PASS, 37 тестов |
| Release tooling | PASS, 58 проверок |
| Packaged-style self-test в build-каталоге | PASS, exit 0 |
| Public-source guard | PASS, 231 файл на source commit; staged release evidence после добавления — PASS, 1 файл |
| Локальный portable archive verifier | PASS, 1,066 файлов |
| Fresh extraction точного ZIP и packaged `--self-test` | PASS, exit 0; пользовательские Data/Profiles отсутствуют |
| Public second-host gate (GitHub Actions run `38779333300`) | PASS на отдельном hosted Windows Server 2022 runner: публичный ZIP/source provenance, packaged self-test, synthetic storage 21 assertions / 7 visits; runner commit `ec7c3e50f52e71ffd5417f237f34ce49ef3eb6e6` |
| GUI-smoke кандидата 0.8.30 | NOT RUN: отдельное action-time подтверждение для запуска этой сборки не получено |
| Другая пользовательская Windows-машина/учётная запись; GUI, Windows 10/ARM64 и внешний DNS/IPv6/UDP/STUN/TURN | NOT RUN |

GUI-smoke предыдущего кандидата 0.8.29 не переносится на этот бинарник.
Hosted second-host gate подтверждает только скачивание точного публичного ZIP,
self-test и synthetic storage на отдельной CI-машине; он не заменяет ручной GUI,
cross-account migration, проверку разных CPU/GPU или независимое сетевое
наблюдение.
Проверка junction для `Data`/`Profiles` подтверждает защиту конкретных корневых
путей до открытия SQLite; не заявляется защита от same-user TOCTOU или всех
вложенных ссылок Chromium.

## Ограничения

Изменение 0.8.30 валидирует portable-хранилище (`Data`, `Profiles`, `Backups`,
`Logs`, `Operations`) и файлы SQLite/sidecar от reparse points и неподходящих
типов до подключения базы. Защита не является границей против вредоносного
процесса с теми же правами пользователя. Browser fingerprint не подменяется;
proxy, local-first режим и раздельные профили не гарантируют анонимность или
отсутствие внешних сетевых утечек.

## Сайт после публикации

- Существующий public Site: [nevision-win.mail782861.chatgpt.site](https://nevision-win.mail782861.chatgpt.site/), Sites version 68; audience сохранён.
- Site source commit: `a86d9933eb25d093a1b8cd733a2fa046c36f7631`; deployment status `succeeded`.
- Главная, `/release.json` и `/CHANGELOG.md` — HTTP 200; live release metadata совпадает с версией 0.8.30, binary-source commit, именем/размером/SHA-256 ZIP.
- Публичный GitHub ZIP HEAD — HTTP 200, `Content-Length: 262393616`.
- Сжатый Site deployment archive: `16183229` байт, SHA-256 `17921209f9ef682a7f21f4e20087c2501fb7cd30878bb3ee9a6f780b90f4cd3b`; архив содержит `dist/.openai/hosting.json`, `dist/server/index.js` и проверенный `dist/client/release.json`.
