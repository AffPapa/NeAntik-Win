# NeAntik Win 0.8.24-preview — publication evidence

Дата проверки: 2026-10-15. Публичный portable prerelease; приложение не меняет browser/device fingerprint и не обещает анонимность.

## Источник и ZIP

- GitHub tag `v0.8.24-preview` указывает на source commit `96da9945be1558fa2fd47b372ea61315e96fbd04`; рабочая ветка `main` чистая и синхронизирована с `origin/main`.
- Windows CI run `38733032956` для этого коммита завершился успешно.
- В release вошёл неизменённый stock Chromium 155.0.8059.79; ZIP — `262386734` байта, SHA-256 `a440ab85d2ac4a8e152ecb3f4069fad870db4c1a19d444a6973f8d82c0380591`.
- Portable archive verifier прошёл для локального ZIP и повторно скачанного GitHub asset: 1 066 файлов. Sidecar SHA-256 и GitHub asset digest совпали. Упакованный EXE `--self-test` завершился с кодом 0.
- `python -m unittest discover -v`: 289 тестов прошли, 3 пропущены. Release-tool suite: 58 проверок PASS. Public-repository guard: 222 файла PASS.
- SHA-256 извлечённого `NeAntikWin.exe`: `a0cceeb1dd37eb5622b94d6e9b040bc835e27c66e5dc734808378c620dcd5909`.

## Изолированный GUI smoke

- Точный `NeAntikWin.exe` из свежей одноразовой QA-распаковки запущен после явного разрешения пользователя.
- Окно `NeAntik Win 0.8.24-preview` успешно отрисовало стартовое локальное рабочее пространство без профилей и пользовательских данных — PASS.
- Создание профиля и ручной сценарий резервного копирования в GUI этим smoke не проверялись; регрессия нового диалога backup покрыта unit/controller tests. Не переносить PASS с source tests на ручной GUI backup.

## Публичный сайт

- Существующий публичный Site сохранён публичным; сохранена версия 58 и выполнен deploy: статус `succeeded`.
- Сайт source commit: `0d129644c5316a25d6db67b32270afb4ac19b1d4`. Пакет содержит актуальный `dist/client/release.json` с browser commit и ZIP SHA выше.
- Живые `/`, `/release.json`, `/CHANGELOG.md` и GitHub ZIP HEAD вернули HTTP 200. В `release.json` версия `0.8.24-preview`, source commit и checksum совпадают; CHANGELOG содержит запись 0.8.24; ZIP `Content-Length` — `262386734`.

## Не закрытые проверки

Внешние proxy/CONNECT, DNS/IPv6/WebRTC/UDP/STUN/TURN, другая Windows-машина, Windows 10/ARM64, физическая клавиатура и screen reader не проверялись. Данные backup не зашифрованы и могут содержать browser cookies, историю и сессии; Proxy Vault пароли в backup не включаются. Fingerprint spoofing отсутствует.
