# Публикация NeAntik Win 0.8.7-preview — 2026-10-13

Статус: опубликован **prerelease**, а не подтверждение полной анонимности или
закрытия всех выпускных ворот.

- Исходный commit бинарника: `d2e6eac9a50f5edfa474ec72aff9ace64c2e8801`.
  Тег `v0.8.7-preview` указывает на него. GitHub CI для исходного commit и
  последующей документации `ab7eb1daee2d283424e0cbd9004beeaa324f5c03`
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
автоматизации; локальный STUN — INCONCLUSIVE из-за отсутствующего
положительного контроля. Внешние DNS/IPv6/TURN, второй компьютер, полная
защита fingerprint и доказательство анонимности — NOT RUN. Подробный протокол
локального кандидата: `RELEASE_EVIDENCE_0.8.7-preview-candidate-2.md`.
