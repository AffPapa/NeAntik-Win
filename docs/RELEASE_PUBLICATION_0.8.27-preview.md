# Release evidence: NeAntik Win 0.8.27-preview

Дата: 2026-10-15. Публичный prerelease для Windows x64; EXE не подписан.
Встроенный Chromium 155.0.8059.79 source-built, без изменения browser/device
fingerprint (`fingerprint_modification=false`).

## Идентичность

- Binary source commit: `5e1b83b7dcdf2a965a2f53c33aab73522fed6879`.
- Annotated tag `v0.8.27-preview` на этот commit; GitHub Release создан с
  `--verify-tag`, prerelease, ZIP, checksum и build manifest.
- Chromium source commit `a49e2e3d4addfd84e765b52afe230bedb81096db`, source
  tree `dfc35f957fa026cbaef804169c8aca70faacd3ef`; использован повторно
  проверенный engine из portable 0.8.26. Chromium заново не собирался.
- Local ZIP: `NeAntikWin-portable-v0.8.27-preview.zip`, 262,390,106 bytes,
  SHA-256 `daa9da39bb19428e2989439b6200fbf4d9ee0a5d999f834880e2bbb800ba2eb0`.
- Packaged EXE SHA-256:
  `c23f9801057c3d532f26471b8a238db1278e016a063a8d89377a941f27093bcb`.

## Проверки

| Проверка | Вход | Результат |
|---|---|---|
| Новая hardlink-регрессия + лимит scan + fail-closed scan error | commit `5e1b83b…`, synthetic local profile | 3/3 PASS на Windows |
| Полный `unittest discover` | commit `5e1b83b…` | 296 PASS, 3 skipped |
| GUI callback regression | тот же source commit | 21/21 PASS |
| Release tooling | тот же source commit | 58 checks PASS |
| Public source guard | тот же source commit | 228 файлов PASS |
| Windows CI | run `38753547574`, commit выше | PASS |
| Local + fresh public ZIP verifier | по 1,066 files; public ZIP download повторно скачан из GitHub | PASS |
| Packaged EXE `--self-test` | свежая отдельная распаковка точного local ZIP | exit 0, PASS |
| GitHub API asset digest | точный ZIP | совпадает с локальным SHA-256 |
| Site build | Site source `1979350bb75198664400cf00851fb875b3410e47` | TypeScript + production build PASS |
| Production Site | version 64, публичный URL | `/`, `/release.json`, `/CHANGELOG.md` HTTP 200; JSON version/source/asset bytes/hash совпали; ZIP HEAD 200, Content-Length 262,390,106 — PASS |

### Дополнительная проверка уже опубликованного бинарника — 15 октября 2026

После публикации точный public ZIP (повторно проверенный SHA-256 выше) прошёл
`tools/wsl_stun_route_audit.py` с Chromium SHA-256
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa` и
локальным STUN-приёмником в отдельном Ubuntu WSL network namespace. Прямой
контроль: 5 STUN Binding requests получено при 5 NetLog sends; HTTP proxy:
0 получено / 0 UDP sends; SOCKS5: 0 получено / 0 UDP sends, синтетический
proxy route control и 4 запроса тестовой страницы подтверждены. Итог обоих
proxy gate — PASS. Локальный отчёт (с приватным адресом WSL, не для публикации):
`build/qa-0.8.27-preview-5e1b83b7dcdf2a965a2f53c33aab73522fed6879/wsl-stun-report.json`.

Это независимый от Chromium локальный UDP-счётчик между Windows и WSL, а не
внешний сетевой наблюдатель. Публичные DNS, IPv6, TURN, другая машина/сеть и
анонимность не проверяются. После релиза также добавлен Windows-only launch-path
regression test для junction в Local Storage LevelDB: отдельный тест PASS;
все 49 `PortableCoreRegressionTests` PASS, один существующий test skipped.
Эта правка только тестовая/документационная: binary source commit и ZIP не менялись.

Также exact public ZIP .27 прошёл `tools/browser_integration.py`:
**21/21 assertions, семь Chromium visits**. Проверены синтетическая изоляция и
перезапуск cookies/localStorage/IndexedDB/Cache Storage/service workers,
разрешения A/B, backup/restore и чистый configuration clone. Только localhost;
28 фоновых HTTP(S) запросов заблокированы rejecting proxy. Это source-level
headless integration на одном Windows 11 account, не GUI/cross-PC тест.
Хеши и ограничения — в [P3.1 протоколе](PROFILE_ISOLATION_2026-10.md).

GUI smoke именно для 0.8.27 — **NOT RUN**; запуск окна 0.8.26 не переносится
на этот EXE. Внешние DNS/IPv6/UDP/STUN/TURN, иная физическая машина,
Windows 10/ARM64 и UIA/MSAA/NVDA — **NOT RUN**. Это не меняет fingerprint и
не доказывает полную анонимность. Hardlink/reparse scan ограничен прямыми
записями выбранных каталогов (до 10,000 entries на каталог); вложенные пути,
TOCTOU и намеренное изменение тем же Windows-пользователем не покрыты.

Production URL: https://nevision-win.mail782861.chatgpt.site/
