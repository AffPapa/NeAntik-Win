# Release evidence — 0.8.30-preview

Дата подготовки: 2026-10-16. Preview portable-сборка, не гарантия анонимности.
Chromium 155.0.8059.79 — неизменённое ядро; модификации browser/device
fingerprint нет.

## Источник и артефакт

- Binary-source commit: `09f516f6dc340c126f1d1f8615d68a9f9251b734`.
- Тег `v0.8.30-preview` и GitHub Release на момент подготовки ещё отсутствовали.
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
| Public-source guard | PASS, 231 файл; staged evidence-файл требует финальной сверки после добавления |
| Локальный portable archive verifier | PASS, 1,066 файлов |
| Fresh extraction точного ZIP и packaged `--self-test` | PASS, exit 0; пользовательские Data/Profiles отсутствуют |
| GUI-smoke кандидата 0.8.30 | NOT RUN: отдельное action-time подтверждение для запуска этой сборки не получено |
| Windows 10/ARM64, другая физическая машина и внешние DNS/IPv6/UDP/STUN/TURN | NOT RUN |

GUI-smoke предыдущего кандидата 0.8.29 не переносится на этот бинарник.
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

## Сайт

На момент подготовки публичный Site ещё указывает на 0.8.29-preview. Публикация
сайта допускается только после создания Release, повторного скачивания ZIP и
совпадения SHA-256/размера с этим evidence; затем требуется live-проверка
главной страницы, `/release.json`, `/CHANGELOG.md` и публичного ZIP.
