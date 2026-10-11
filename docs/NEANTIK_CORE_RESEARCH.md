# NeAntik Win: выбор ядра с native fingerprint

Дата исследования: 11 октября 2026, Asia/Bangkok. Только первичные источники; факты о релизах дополнительно прочитаны через официальный GitHub Releases API. Это архитектурное исследование, а не результат запуска этих бинарников.

## Решение

Для проверяемого первого прототипа наиболее простой адаптер — **adryfish/fingerprint-chromium Windows x64 ZIP 150.0.7871.186**: это обычный самостоятельный Chromium, которому можно передавать профиль и fingerprint через командную строку. Он не требует Playwright, Node, фонового CDP-сервера или JavaScript-инъекции. Но версия Chromium 150 отстаёт от установленного Chrome 154, исходники latest release задержаны, а все поверхности Windows/worker необходимо измерить. Поэтому его нельзя описывать как современное полностью проверенное собственное ядро NeAntik.

Для долгосрочной поставки со всеми исходниками предпочтительнее собственная воспроизводимая сборка актуального Chromium с небольшой опубликованной patch series. Её нельзя обещать как уже готовую: требуются toolchain, много диска, длительная сборка и тестирование. Прототип и release gate должны явно различаться.

## Доступные релизы

| Проект | Реально найденный Windows asset | Дата и размер | Подход | Решение |
|---|---|---|---|---|
| [fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium/releases/tag/150.0.7871.186) | `ungoogled-chromium_150.0.7871.186-1.1_windows_x64.zip` | 2026-10-02T14:02:29Z; 193,743,241 bytes | Chromium 150, C++ patches, native GUI | Самый компактный кандидат для испытаний; security freshness gate обязателен |
| [Anti-Fingerprint Browser](https://github.com/pppi21/anti-fingerprint-browser/releases/tag/153.0.8010.47-1) | `chromium-153.0.8010.47-1.zip` | 2026-09-20T04:28:28Z; 1,594,647,985 bytes | Chromium 153, опубликованная patch series | Исходники интересны для собственного fork; готовый ZIP тяжёлый и содержит отдельные компоненты с ограничениями |
| [Camoufox](https://github.com/daijro/camoufox/releases/tag/v156.0.1-beta.37) | `camoufox-156.0.1-beta.37-win.x86_64.zip` | 2026-10-11T03:22:00Z; 1,311,732,603 bytes; prerelease | Firefox 156, engine modifications | Подходит для отдельного automation-продукта; не основной Chrome-compatible GUI |
| [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) | Проект указывает Windows x86_64: free Chromium 146, latest Chromium 154 | У latest binary subscription; точный ZIP не выбирался | Native Chromium + automation wrapper | Не включать в распространяемый NeAntik без отдельной OEM-лицензии |
| [BrowserForge](https://github.com/daijro/browserforge) | Самостоятельного browser core нет | Python library | Генерация согласованных данных; прежняя JS injection deprecated | Можно исследовать генерацию persona, но это не реализация native spoofing |

Проверенные SHA-256 из API, до скачивания и запуска:

```text
fingerprint-chromium 150 Windows ZIP
4d549c326e51ebbabf562fd365eb5380d9d4a81200da2c60f075c688d9a77e03

Anti-Fingerprint Browser 153 Windows ZIP
b2be4f085c196e76de39420f22c1dcbc3bbfe9d6dc49ec95f309fb8206549e3c

Camoufox 156 beta.37 Windows ZIP
784f12697c7caef12415aefd8d77eac9601e9e13ee4670c27c3c0c03200a446b
```

API: [adryfish release](https://api.github.com/repos/adryfish/fingerprint-chromium/releases/tags/150.0.7871.186), [pppi21 release](https://api.github.com/repos/pppi21/anti-fingerprint-browser/releases/tags/153.0.8010.47-1), [Camoufox release](https://api.github.com/repos/daijro/camoufox/releases/tags/v156.0.1-beta.37). API digest подтверждает целостность относительно опубликованного GitHub asset, а не отсутствие вредоносного кода или воспроизводимость сборки.

## Fingerprint Chromium: что известно и что проверять

[Документация проекта](https://github.com/adryfish/fingerprint-chromium/blob/main/README.md) описывает seed, UA/Client Hints, CPU, canvas, audio, fonts, rects, GPU, язык и timezone. Latest patches публикуются после следующей версии; tag 148 содержит исходники, tag 150 на момент проверки ещё не даёт equivalent current patch source. GPU и detection-site результаты являются заявлениями автора, а не нашими тестами.

Минимальный адаптер использует `--fingerprint=<uint32>`, `--fingerprint-platform=windows`, `--fingerprint-brand=Chrome`, `--fingerprint-brand-version=<actual core version>`, `--fingerprint-hardware-concurrency=<value>`, `--timezone=<IANA>`, `--lang=<BCP47>`, `--accept-lang=<list>`, `--user-data-dir=<isolated profile>`, `--proxy-server=<endpoint>`. `--disable-spoofing` избирательно выключает font/audio/canvas/clientrects/gpu. GPU vendor/renderer switches из старых версий удалены с 144. Не добавлять неподтверждённые флаги только потому, что Chromium молча принимает неизвестные arguments.

Аудит опубликованного **tag 148**, не эквивалент аудиту готового 150:

- [UA patch](https://github.com/adryfish/fingerprint-chromium/blob/148.0.7778.215/patches/extra/fingerprint/002-user-agent-fingerprint.patch) меняет browser client-hints и Blink metadata. В нём есть fallback version pool; задавать фактическую версию явно и сверять HTTP headers с JS, чтобы seed не выбирал старый UA.
- [CPU/memory patch](https://github.com/adryfish/fingerprint-chromium/blob/148.0.7778.215/patches/extra/fingerprint/005-hardware-concurrency-fingerprint.patch) меняет native NavigatorConcurrentHardware и NavigatorDeviceMemory. Следующий [memory patch](https://github.com/adryfish/fingerprint-chromium/blob/148.0.7778.215/patches/extra/fingerprint/021-device-memory-cap.patch) корректирует варианты memory. Общие Blink accessor пути — основание ожидать часть worker consistency, но не доказательство всех workers.
- [Canvas patch](https://github.com/adryfish/fingerprint-chromium/blob/148.0.7778.215/patches/extra/fingerprint/012-canvas-get-image-data.patch) меняет BaseRenderingContext2D и bitmap/image buffer; содержит OffscreenCanvas ветви. [toDataURL patch](https://github.com/adryfish/fingerprint-chromium/blob/148.0.7778.215/patches/extra/fingerprint/013-canvas-toDataURL.patch) отдельно изменяет HTMLCanvasElement. Поэтому тестировать pixel equality между getImageData, dataURL, blob и Offscreen, а не один canvas hash.
- [Timezone patch](https://github.com/adryfish/fingerprint-chromium/blob/148.0.7778.215/patches/extra/fingerprint/018-timezone.patch) действует через Blink TimeZoneController/ICU/V8. Нужны Date/Intl/worker сравнения и DST cases, а не только label timezone.
- [Switch forwarding patch](https://github.com/adryfish/fingerprint-chromium/blob/148.0.7778.215/patches/extra/fingerprint/000-add-fingerprint-switches.patch) передаёт собственные switches в child processes. Само объявление screen flags в нём ещё не доказывает изменение screen metrics в бинарнике.

## Альтернативы и redistribution

**fingerprint-chromium:** [BSD-3-Clause LICENSE](https://github.com/adryfish/fingerprint-chromium/blob/main/LICENSE) разрешает source/binary redistribution с сохранением notice, условий и disclaimer. Это не отменяет Chromium third-party notices. В архиве сохранить upstream license, credits и точный provenance. Нельзя использовать имя автора как endorsement. Не называть delayed-source binary нашей опубликованной полностью воспроизводимой сборкой.

**Anti-Fingerprint Browser:** [LICENSE](https://github.com/pppi21/anti-fingerprint-browser/blob/main/LICENSE) BSD-3-Clause. [Build documentation](https://github.com/pppi21/anti-fingerprint-browser/blob/main/README.md#building-from-source) требует Windows toolchain, порядка 45 GB free disk и 32 GB RAM; several hours указаны автором, не измерены здесь. Release README отдельно предупреждает про Widevine и font bundle, отсутствующие в исходниках из-за redistribution restrictions. Нельзя автоматически перенести весь готовый ZIP под BSD license. Опубликованные [patches](https://github.com/pppi21/anti-fingerprint-browser/tree/main/patches) включают screen, WebGPU, canvas, timezone и hardware. Его default privacy preset выключает Safe Browsing; это учитывать при сравнении безопасности.

**Camoufox:** [project licensing](https://github.com/daijro/camoufox#licensing) — browser MPL-2.0, Python/TypeScript launcher MIT, отдельный LGPLv3-or-later компонент trajectory. Firefox extensions несовместимы напрямую с Chromium extension packages. [Официальная установка](https://camoufox.com/python/installation/#debugging) прямо сообщает, что он не рассчитан на human use и возможны проблемы window resizing/fonts. [Native config reader](https://github.com/daijro/camoufox/blob/main/browser/additions/camoucfg/MaskConfig.hpp) принимает CAMOU_CONFIG JSON. [Worker regression test](https://github.com/daijro/camoufox/blob/main/browser/tests/playwright/patches/worker-config-reads.py) сравнивает platform/CPU/timezone окна и workers и проверяет race; комментарий описывает старый beta.30 crash. Это полезный пример необходимого coverage, не результат наших испытаний beta.37.

**CloakBrowser:** [Binary License v1.3](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md) отдельно от MIT wrapper запрещает redistribution/repackage и требует отдельной OEM/SaaS license для customer browser functionality. latest major требует subscription. Поэтому бесплатный GitHub wrapper не даёт права упаковать ядро в NeAntik.

**BrowserForge:** [README](https://github.com/daijro/browserforge#injecting-fingerprints) помечает fingerprint injection deprecated. Статистическая генерация данных может улучшить consistency, но не меняет Blink/Firefox реализацию сама по себе. Требуется native adapter, проверяемая schema и pinning данных; добавлять library только при реальной пользе относительно нескольких компактных Windows presets.

## Архитектура без постоянных накладных расходов

NeAntik хранит persona рядом с profile metadata: schema version, stable seed, exact engine id/version, Windows desktop preset, CPU, language, timezone, UDP/WebRTC policy. Persona создаётся один раз, сохраняется в backup и не рандомизируется каждый запуск. Clone получает новый seed; restore сохраняет seed. Изменение identity открытого profile запрещено.

Launcher формирует validated argument list и запускает один portable native core. Основной UI продолжает использовать лёгкий существующий стек; нет второго browser window в WebView, Electron, automation daemon или background fingerprint polling. Browser pages не получают global JavaScript wrappers. CPU-intensive шум должен измеряться именно на чтениях canvas/audio, а не объявляться бесплатным.

Installer/downloader проверяет pinned upstream URL, размер, SHA-256, safe ZIP paths и извлечение во временную папку; promotion atomic. Данные остаются вне Engine. Browser updater не перезаписывает running engine и не даёт тихий downgrade. Строгая попытка запуска с fingerprint никогда не заменяется автоматически installed Chrome, который эти flags проигнорирует.

## Gate для реального anti-detect release

1. Бинарник реально загружен, digest совпал; runtime version и provenance записаны.
2. A/A-restart сохраняет fingerprint, A/B различаются; direct user run headed проверен.
3. Main frame, same-origin/cross-origin frames, dedicated/shared/service workers сравнивают platform, UA/UA-CH, CPU/memory, languages и timezone.
4. Seed меняет canvas/audio/rects; rendering и repeated reads стабильны. OffscreenCanvas и WebGL/WebGPU не выдают несовместимые GPU сведения.
5. HTTP User-Agent, Accept-Language и Client Hints соответствуют JS. Версия соответствует actual core; viewport/screen/window/CSS media не конфликтуют.
6. Proxy failure не раскрывает direct traffic, WebRTC/UDP policy проверена; auth credentials отсутствуют в argv/logs. Здесь fingerprint не заменяет routing.
7. Естественный GUI, downloads, history, permissions, profile close/reopen, backup/restore и хотя бы одно расширение реально проверены. У ungoogled extension installation отличается от official Chrome — подтвердить путь пользователю.
8. CPU/RAM/launch сравниваются с прежним launcher и stock Chromium на этом компьютере. Anti-detect claims не получаются из одного процента стороннего scanner.
9. Security freshness: release age не равен Chromium security age. На хосте ранее установлен Chrome 154; Chromium150 нельзя выдавать за updated security baseline. Проверить upstream current stable и наличие backports, при отсутствии — явно статус experimental и дальнейший core update gate.
10. Public source включает свой adapter и tests, лицензии и доступные patches; upstream third-party binary/source limitations описаны без обещания владения или полной reproducibility.

Официальный Chrome release blog [October desktop update](https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop.html) вернул 429 при проверке; конкретный CVE/номер latest patch на основе поисковых сниппетов здесь не утверждается. Это остаётся отдельной проверкой до security-sensitive public release.
