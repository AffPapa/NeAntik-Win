# Встроенный Chromium в portable NeAntik Win — решение и выпускные барьеры

Дата исследования: 2026-10-12. Это инженерный план, а не обещание анонимности.

## Вывод

Для сценария «распаковать ZIP и запустить на Windows x64 без Chrome» встроенное ядро логично. Приложение NeAntik остаётся лёгкой оболочкой, но итоговый ZIP станет на сотни мегабайт больше, а команда продукта обязана выпускать обновления ядра вслед за стабильными security-релизами Chromium. Последний стабильный выпуск, а не самый свежий произвольный snapshot, должен быть основанием публичного релиза. [Chromium security FAQ](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/security/faq.md), [Chromium downloads](https://www.chromium.org/getting-involved/download-chromium/).

## Что действительно делают конкуренты

| Продукт | Подтверждённый подход | Что брать в NeAntik |
| --- | --- | --- |
| Multilogin | Профили, proxy manager, отдельный Mimic core; core обновляется автоматически при запуске профиля. [Release notes](https://multilogin.com/release-notes/), [proxy settings](https://www.multilogin.org/help/en_US/browser-profile-setup/profile-settings-proxy-section) | Один локальный пакет и понятная версия core в интерфейсе; не копировать облачную зависимость. |
| Dolphin Anty | Отдельный профиль с proxy и параметрами браузера; приложение требует установки и входа. [Quick start](https://docs.dolphin-anty.com/en/getting-started/quick-start-in-dolphin-anty) | Изоляция профилей и ясный onboarding без регистрации. |
| AdsPower | Выбор локально загруженного browser kernel; опция matching timezone/location для динамического IP. [Profiles](https://help.adspower.com/docs/creating_browser_profiles), [global settings](https://help.adspower.com/docs/global_settings) | Явная версия ядра, проверка proxy, объяснение timezone; не обещать точное совпадение только по GeoIP. |
| Vision | Профиль содержит settings/extensions/bookmarks/proxy; Windows-дистрибутив предлагается как installer и требует входа. [Profiles](https://docs.browser.vision/profiles/overview), [download](https://browser.vision/download/windows) | Локальный portable-путь и отсутствие учётной записи остаются отличием NeAntik. |

Заявления поставщиков о невыявляемости являются маркетинговыми; перечисленные страницы не доказывают работу на всех антифрод-системах.

## Решение по составу portable-папки

```
NeAntikWin-portable-vX/
  NeAntikWin.exe
  _internal/                 # Python/Tk runtime
  Engine/Chromium/           # проверенная unbranded x64 сборка Chromium
  licenses/                  # Python/Tk и Chromium/third-party notices
  release-manifest.json      # хэши, версия core, upstream commit
  Data/                      # создаётся только после первого запуска
```

GitHub-репозиторий хранит наш исходный код, скрипты сборки и зафиксированную спецификацию ядра; большой бинарник ядра принадлежит **релиз-архиву**, а не Git-истории. Сборщик должен отбрасывать test executables, symbols, build cache, private keys и пользовательский Data. Архив проверяется по SHA-256 после повторной распаковки. В `Engine/Chromium` нельзя тихо положить старое или модифицированное ядро: provenance и лицензии — выпускной барьер.

## Proxy и «анонимность»

Профиль хранит назначение proxy; Chromium использует `--proxy-server` без прямого fallback в списке. Это покрывает URL-трафик, но **не** гарантирует проксирование каждого сетевого пакета, отсутствие WebRTC/UDP-различий или скрытие личности. Chromium не поддерживает SOCKS5-аутентификацию и SOCKS5 UDP relay; у SOCKS5 DNS для URL разрешается на стороне proxy. [Официальная документация Chromium по proxy](https://chromium.googlesource.com/chromium/src/+/HEAD/net/docs/proxy.md).

Перед заявлением «без утечек» нужны интеграционные проверки DNS, WebRTC/UDP, локальных адресов, отказа proxy и внешнего IP на Windows 10/11 в IPv4/IPv6 сетях. Если proxy не работает, приложение должно показывать ошибку и не переключать профиль на прямое соединение. Не хранить пароль в командной строке.

## Телеметрия и часовой пояс

NeAntik не имеет собственной телеметрии. Для Chromium нужно измерять и документировать фоновые соединения на чистом профиле; `--disable-background-networking` нельзя представлять как проверенное «нулевое соединение». Бездумное отключение Safe Browsing и других защит ухудшит безопасность. Изменение IP через proxy не меняет системный timezone браузера. Автовыбор timezone по IP требует источника геолокации, раскрывает этому источнику IP proxy и часто ошибается для VPN/датацентров. Без отдельной проверенной реализации лучше показывать реальный timezone и предупреждать о расхождении, чем тайно подменять частичную характеристику.

## Реальная переносимость

Portable означает отсутствие установки Chrome и сохранение файлов профиля рядом с EXE. Это не означает «одинаково на любом ПК»: нужны поддерживаемая Windows x64, права на запись в папку и совместимый CPU. Proxy-секреты NeAntik и часть cookies/passwords Chromium на Windows защищены DPAPI и могут потребовать повторного входа после переноса на другой аккаунт/ПК. [Chromium security FAQ, password storage](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/security/faq.md#L326).

## Проверка перед публичным 0.5.x

1. Чистая **стабильная** сборка Chromium x64 из исходного upstream commit, воспроизводимый build receipt, `LICENSE` и third-party notices. Не Chrome for Testing: он не автообновляется, и Chromium прямо ограничивает его использованием для доверенного контента. Не использовать старое локальное патченое ядро как «обычный Chromium». [Security FAQ](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/security/faq.md#L120).
2. ZIP проходит проверку manifest/hash/signature/provenance, и после распаковки запускается на машине без Chrome/Edge. Отдельно проверить обновление ядра без порчи старых профилей, rollback и совместимость версий профиля.
3. Прогнать реальные сценарии: чистый запуск, несколько профилей, proxy failure, backup/restore, перенос папки, открытие extensions, системная светлая/тёмная тема, 64-bit Windows 10 и 11, чистый Windows-пользователь.
4. Затем менять сайт и release notes; до этого публичный сайт должен честно описывать существующий 0.4.1 как менеджер профилей установленного Chrome/Edge.

## Локальная разведка ядра 2026-10-12

Официальный Chromium snapshot `Win_x64/1716555` скачан для прототипа: SHA-256 ZIP `25c221a48bcb2a9ebd456251b1b249db045c7b1e1038ec9b08b4bcd6e18f7948`, бинарная версия `157.0.8101.0`. Loopback-интеграция прошла 14 assertions / 7 visits. Локальный `0.5.0-dev` ZIP с приложением и этим ядром занимает 225 940 735 байт, SHA-256 `337b7c1017d4079b551a184298b40cfdb789d91ee4b7de72762dca866bf0e284`; проверка полного архива прошла 1285 файлов. Это **snapshot development-ветки**, не выпускной stable core, поэтому его нельзя объявлять публичной production-сборкой. Локальная имеющаяся сборка `155.0.8059.40` содержит ранее разработанные модификации и также не является чистым ядром для текущего плана.
