# Публикация NeAntik Win 0.8.7-preview — 2026-10-13

Статус: опубликован **prerelease**, а не подтверждение полной анонимности или
закрытия всех выпускных ворот.

- Исходный commit бинарника: `d2e6eac9a50f5edfa474ec72aff9ace64c2e8801`.
  Тег `v0.8.7-preview` указывает на него. GitHub CI для исходного commit и
  последующей документации `67f9fbc4327d8efe7437d523e68ac166102784ff`
  завершился успешно.
- [GitHub Release](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.7-preview)
  помечен Pre-release. Доступны portable ZIP, `.zip.sha256` и standalone
  manifest; GitHub показывает тот же digest ZIP.
- [Публичный portable ZIP](https://github.com/AffPapa/NeAntik-Win/releases/download/v0.8.7-preview/NeAntikWin-portable-v0.8.7-preview.zip)
  скачан повторно: 262 385 442 байта, SHA-256
  `9bf12392f8c8057763024cb88666679e8d9938e73cc050f976e7057b5c5234d1`.
  Архивный verifier: PASS, 1 066 файлов. Извлечённый `NeAntikWin.exe`:
  SHA-256 `e3c97c1623dee5fa2f59d08744b8006d8ca82e2ef3fecf189785688e34bf07eb`;
  `--self-test`: exit 0. Скачанные checksum и manifest совпали с локальными
  побайтно.
- [Публичный Site](https://nevision-win.mail782861.chatgpt.site/)
  обновлён до version 37 из site source commit
  `d29b26b90ab1a4b6ef02c8c0fca6aa4abeeb8966`. Публичные `/`,
  `/CHANGELOG.md` и `/release.json`: HTTP HEAD 200; `/release.json` содержит
  версию, размер, SHA-256 и URL точного ZIP. GET changelog показывает
  `0.8.7-preview` и корректную кириллицу. В Chrome визуально проверены
  главная страница, desktop и мобильный блок скачивания.

Открыто: GUI создание профиля и GUI backup — INCONCLUSIVE из-за ввода
автоматизации; Windows loopback STUN — INCONCLUSIVE, хотя отдельный
WSL-network-namespace контроль на том же Chromium и штатном sandbox прошёл.
Внешние DNS/IPv6/TURN, второй компьютер, полная
защита fingerprint и доказательство анонимности — NOT RUN. Подробный протокол
локального кандидата: `RELEASE_EVIDENCE_0.8.7-preview-candidate-2.md`.

## Сверка Site после раскрытия ограничения — 2026-10-13

Site version 39 опубликован из source commit
`9083baaaf425140daa3294252c0dcccf1163cd7a`. Это изменение документации, а не
новая версия браузера: portable ZIP 0.8.7, его hash, ядро и `release.json` не
менялись. После deploy главная страница и `/CHANGELOG.md` отвечали HTTP 200 и
содержали предупреждение, что ключ Canvas-сессии V4b сейчас передаётся через
аргументы командной строки renderer-процессов. Ограничение сформулировано как
возможность локального чтения средствами диагностики/мониторинга того же
пользователя; не утверждается, что ключ доступен обычным сайтам или что имела
место удалённая компрометация. Deploy Site version 39 завершился успешно.

Исправление включено в P1.2a gate до следующего выпуска браузера; см.
[`MASTER_IMPLEMENTATION_PLAN.md`](MASTER_IMPLEMENTATION_PLAN.md) и
[`FINGERPRINT_SURFACE_MATRIX.md`](FINGERPRINT_SURFACE_MATRIX.md).
