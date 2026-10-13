# 0.8.7-preview candidate-2 — локальная проверка, 2026-10-13

Это отчёт о **кандидате**, а не подтверждение публичного релиза или полной
анонимности. Он не переносит автоматически результаты на иной ZIP или EXE.

## Идентичность

- Чистый исходный commit сборки: `d2e6eac9a50f5edfa474ec72aff9ace64c2e8801`.
- Локальный portable ZIP SHA-256:
  `9bf12392f8c8057763024cb88666679e8d9938e73cc050f976e7057b5c5234d1`.
- Извлечённый `NeAntikWin.exe` SHA-256:
  `e3c97c1623dee5fa2f59d08744b8006d8ca82e2ef3fecf189785688e34bf07eb`.
- Встроенный Chromium 155.0.8059.40 `chrome.exe` SHA-256:
  `751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`.
- Windows 11 Pro x64, build 26200. Архивный verifier: PASS, 1 066 файлов;
  shipping `Data/` отсутствует. Бинарный `--self-test`: PASS, exit 0. Он
  создаёт синтетический hardlink на файл вне профиля и требует отказа backup.

## Локальные результаты

- Исходники на commit сборки: 220 unit tests PASS, 3 SKIP; выпускные инструменты:
  55 checks PASS. GitHub CI для этого commit: PASS.
- Packaged browser integration: 21/21 PASS; cookie allow/block: PASS; managed
  downloads: 3/3 PASS. Все профили и серверы одноразовые.
- Packaged launcher: 4 cases PASS; proxy route: 37 assertions / 13 launches
  PASS; HTTPS proxy: 5 cases PASS; WebSocket route: 16 cases PASS. Первый raw
  browser proxy run завершился до assertions без AppContainer read ACL; после
  product-equivalent ACL только на одноразовый `Engine/Chromium` он прошёл.
  Это ошибка подготовки стенда, а не первоначальный PASS сети.
- Upgrade/rollback из заново скачанного публичного ZIP 0.8.6 в candidate-2:
  **PASS** для синтетических профиля, proxy и DPAPI в той же учётной записи;
  старый snapshot не изменился. Отдельный browser-session gate: **PASS** для
  cookie и localStorage на одном loopback origin, старый snapshot сохранён.
  Скрипты получили версии и SHA-256 обоих ZIP явно, вместо старых констант.
- Дополнительный двухсайтовый gate на том же упакованном Chromium: **PASS 7/7**
  для одного одноразового профиля на `127.0.0.1` и `localhost`. Сверены полные
  языковые списки, `Intl`, запрошенные Client Hints и паритет HTTP/JS в шести
  контекстах. Это тест локальной согласованности, не доказательство анонимности
  или отсутствия внешних утечек. Инструмент добавлен после сборки ZIP; он не
  меняет выпущенный бинарник.
- Локальный WebRTC/STUN: **INCONCLUSIVE**. Положительный direct control не был
  принят тестовым STUN sink, хотя NetLog показал отправки; proxy-bound case
  показал ноль отправок. Без рабочего контроля отсутствие утечки не доказано.
  Дополнительный контроль на том же упакованном Chromium и штатном sandbox с
  приёмником в отдельном сетевом пространстве WSL принял 5 direct STUN Binding
  requests; proxy-bound case принял 0 и показал 0 UDP в NetLog. Это **PASS
  только для такого локального маршрута**, не проверка публичной сети или
  отсутствия DNS/IPv6/TURN-утечек. Диагностический запуск без network sandbox
  также доставил direct loopback-пакеты, но не считается выпускным PASS.

## Открытые ворота

- Ручной GUI smoke точного EXE: **PASS** для запуска, первого экрана и
  открытия формы нового профиля на Windows 11 x64 build 26200. Создание
  профиля и GUI backup: **INCONCLUSIVE** — ввод автоматизации не попал в поле,
  а повторная попытка ввела символ русской раскладки. Сценарий остановлен без
  вывода о дефекте продукта. Приложение закрыто; в одноразовой извлечённой
  папке не создано ни профилей, ни backup ZIP. Исходный shipping ZIP не менялся.
- Публичный ZIP 0.8.6 для upgrade повторно скачан, SHA-256 совпал с опубликованным
  `a370e9dfae4ccab89beb036a9a075b5372944aab19bdf151484ed4ace17da1c1`;
  архивный verifier: PASS, 1 066 файлов. Полный GUI update и другие storage
  surfaces всё ещё **NOT RUN**.
- GitHub prerelease, повторное скачивание точного ZIP и обновление Site:
  **PASS**. Публичный ZIP — 262 385 442 байта, SHA-256 совпал с локальным
  кандидатом; архивный verifier — PASS (1 066 файлов), извлечённый EXE имеет
  прежний SHA-256 и завершил `--self-test` с кодом 0. Публичные checksum и
  manifest совпали побайтно с локальными. Site version 37 показывает релиз,
  SHA-256 и доступные ссылки; `/`, `/CHANGELOG.md`, `/release.json` отвечают
  HTTP 200. Кириллица отображается корректно, desktop/mobile блок загрузки
  визуально проверен. Подробности: `RELEASE_PUBLICATION_0.8.7-preview.md`.
- Внешние DNS/IPv6/UDP/TURN, второй Windows-компьютер, Windows 10/ARM64,
  полная согласованность fingerprint и статистическая анонимность: **NOT RUN**.

Сырые отчёты с локальными сетевыми и аппаратными деталями не публикуются.
