# NeVision Win: Windows, Chromium, прокси, fingerprint и расширения

Дата исследования: **2026-10-11**. Источники открыты в эту дату, если отдельно не указано иное. Документ относится к лёгкой архитектуре NeVision: Python/Tkinter/SQLite/DPAPI, PyInstaller `onedir`, установленный Chrome или Edge. Прочитана исходная база `0.1.3-preview`; номер следующего релиза задаёт общий выпуск.

Обозначения: **Факт** — документация платформы или непосредственно прочитанный код; **заявление** — описание поставщика без независимой проверки; **вывод** — инженерное решение для NeVision. Это исследование, **не отчёт о выполненных runtime-тестах**. Расширения здесь не устанавливались, замеры их RAM/CPU не выполнялись. Фактические проверки релиза должны находиться в QA-отчёте.

## 1. Решения для текущего цикла

| ID | Решение | Основание и ожидаемый результат |
| --- | --- | --- |
| ADR-P01 | Сохранить Tkinter/ttk и `onedir`, отдельно измерять оболочку и браузер | Не добавлять второй browser runtime и постоянную службу; обеспечить быстрый доступ к профилям |
| ADR-P02 | Продолжать использовать актуальный установленный Chrome/Edge | Обновления безопасности ядра остаются у поставщика; размер дистрибутива не включает Chromium |
| ADR-P03 | Показывать честные ограничения fingerprint | Разделение папок профилей не меняет GPU, ОС, сетевые характеристики и большинство API |
| ADR-P04 | Ввести короткий путь к штатной странице расширений выбранного профиля | Пользователь устанавливает и обновляет дополнения через магазин; нет собственного marketplace |
| ADR-P05 | Отделить сохранённый proxy password от автоматической авторизации | Штатный HTTP/HTTPS auth prompt возможен; stock Chrome не реализует SOCKS5 username/password |
| ADR-P06 | Не включать незашифрованный локальный proxy broker в этот выпуск | Loopback сам по себе не ограничивает доступ конкретным браузером; нужен отдельный защищённый прототип |
| ADR-P07 | Описывать portable как переносимость приложения и файлов | Переносимость cookies/паролей на другую машину или Windows-учётную запись не гарантируется |

Рекомендуемый минимальный функционал: открытие расширений, более полезная диагностика proxy с точным уровнем проверки, понятные сообщения об авторизации, сохранение выбранного ядра, обнаружение per-user браузера, быстрые неблокирующие операции и ясный backup UX. Реализация определяется общим планом цикла; запись в этой таблице не означает, что функция уже выпущена.

## 2. Windows и лёгкая оболочка

### Поддержка ОС и архитектур

**Факт.** Общая поддержка Windows 10 Home/Pro закончилась 14 октября 2025. На открытой странице Microsoft Consumer ESU уже указан срок **12 октября 2027**; более старые статьи с октябрём 2026 нельзя переносить в продукт без перепроверки. Consumer ESU относится к подходящим редакциям Windows 10 22H2; для корпоративного использования есть отдельная программа. [Жизненный цикл Windows 10](https://learn.microsoft.com/en-us/lifecycle/products/windows-10-home-and-pro), [текущие условия Consumer ESU](https://www.microsoft.com/en-gb/windows/extended-security-updates).

**Факт.** В актуальной таблице Windows 11 Home/Pro: обслуживание 23H2 завершено; 24H2 заканчивается в октябре 2026; 25H2 — в октябре 2027; 26H2 — в октябре 2028. Enterprise/Education имеют другие сроки: 23H2 — ноябрь 2026, 24H2 — октябрь 2027, 25H2 — октябрь 2028, 26H2 — октябрь 2029. Срок существования ОС и совместимость нашего EXE — разные характеристики. [Home/Pro](https://learn.microsoft.com/en-us/lifecycle/products/windows-11-home-and-pro), [Enterprise/Education](https://learn.microsoft.com/en-us/lifecycle/products/windows-11-enterprise-and-education).

**Факт.** Google указывает Windows 10+ для Intel/SSE3 и Windows 11+ для ARM. Microsoft обещает обновления Edge/WebView2 на Windows 10 22H2 минимум до октября 2028; участие в ESU для этих browser updates не требуется. Это не продлевает общую поддержку самой ОС. [Требования Chrome](https://support.google.com/chrome/a/answer/7100626?hl=en), [поддерживаемые ОС Edge](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-supported-operating-systems).

**Вывод для поставки.** В manifest и на сайте указывать архитектуру собранного EXE, конкретную протестированную ОС/build и версию ядра. Сборка x64 не является доказательством нативной поддержки ARM64 или x86. Оставить непроверенные комбинации явно непроверенными. При наличии только одной машины нельзя объявить завершённую матрицу Windows 10/11.

### Tk, потоки, DPI, процесс браузера

**Факт.** Документация именно Python 3.12 описывает поставляемый threaded Tcl/Tk 8.6. Event loop должен получать управление быстро; долгие обработчики блокируют отрисовку и ввод. Некоторые вызовы Tk имеют дополнительные ограничения потока. Более новая документация Python описывает уже другой bundled Tk, поэтому её нельзя считать паспортом нашей сборки. [Tkinter 3.12, threading model](https://docs.python.org/3.12/library/tkinter.html#threading-model).

**Вывод.** Держать операции с виджетами в UI thread; ограниченная очередь фоновых задач возвращает результат через `after`. DNS, ожидание Chromium lock, ZIP, сканирование файлов и ожидание subprocess должны иметь границы времени/отмену. Не делать отдельный поток на каждое повторное нажатие. В shutdown не обращаться к уничтоженному Tcl-интерпретатору. Эти рекомендации требуют проверки кода и нагрузки, а не смены UI-фреймворка.

**Факт.** Per-monitor DPI awareness требует корректной реакции приложения на изменение DPI; сам manifest не обеспечивает правильный layout. [Microsoft: High DPI desktop development](https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows).

**Вывод.** Проверять 100/125/150/200%, минимальный размер окна, перенос между мониторами, клавиатурный фокус, системную светлую/тёмную тему. Не включать новый DPI-режим только по названию API без проверки Tk, шрифтов и диалогов.

**Факт.** Windows Job Objects управляют группой процессов; `KILL_ON_JOB_CLOSE` завершает группу при закрытии последнего handle. [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

**Вывод.** Не подключать этот флаг к браузеру без явного продуктового решения: закрытие менеджера не должно неожиданно уничтожать работу в браузере. Для статуса профиля проверять ownership каталога/lock и фактический lifecycle, а не только один ранее созданный `Popen`. Не завершать процессы по общему имени `chrome.exe`/`msedge.exe`.

### Упаковка

**Факт.** `onefile` распаковывает runtime во временную папку при запуске; `onedir` избегает этого этапа и проще для диагностики. PyInstaller пакует интерпретатор и зависимости, но не делает программу переносимой между ОС. В прочитанном `requirements-build.txt` зафиксирован PyInstaller 6.21.0; открытая актуальная документация описывает 6.22.3. [Operating mode](https://pyinstaller.org/en/stable/operating-mode.html), [Usage](https://pyinstaller.org/en/stable/usage.html).

**Вывод.** Сохранить `onedir` ZIP, не обновлять toolchain посреди выпуска без причины и повторной проверки. Не удалять DLL/Tcl-файлы ради размера методом проб и ошибок. Бенчмарк должен отдельно считать cold/warm start EXE, RAM менеджера и дерево процессов браузера. Не обещать старт Chromium как у текстового редактора на основании быстрого окна Tk.

## 3. Изоляция и fingerprint: карта контроля

**Факт.** Chromium user-data-dir хранит историю, cookies, профильные настройки и другие данные; параметр запуска позволяет выбрать отдельный каталог. Это штатное разделение состояния. [Chromium: User Data Directory](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/user_data_dir.md).

**Факт.** W3C рассматривает fingerprint как совокупность наблюдаемых свойств, включая активные API, пассивные заголовки и сетевой слой. Очистка cookie или смена IP не означает отсутствия корреляции. Документ — Group Note от 25.09.2025, не сертификат конкретного браузера. [W3C fingerprinting guidance](https://www.w3.org/TR/fingerprinting-guidance/).

Таблица ниже — **инженерная карта**, а не декларация подмены всех параметров. «Требует ядра» означает: для устойчивого, согласованного охвата всех контекстов одних обычных настроек/JS-инъекций недостаточно; даже собственное ядро нуждается в независимой проверке.

| Поверхность | Основной слой | Что доступно в stock Chrome/Edge | Граница для NeVision |
| --- | --- | --- | --- |
| Cookies, localStorage, IndexedDB | Профиль + origin + partitioning движка | Разные user-data-dir; штатная очистка site data | Реально проверять взаимную изоляцию и сохранение, не читать личный профиль |
| Service workers, Cache Storage, HTTP cache | Профиль/движок | Отдельное профильное состояние | Backup должен учитывать закрытое ядро; восстановление кэша не равно восстановлению авторизации |
| User-Agent и Client Hints | Движок + HTTP + JS | DevTools/CDP допускают тестовые overrides | Одна строка UA не меняет остальные сведения о платформе |
| Accept-Language, navigator.language(s) | Настройки браузера + движок | Выбор языка и языковых предпочтений | Изменение языка не задаёт страну сети, timezone и всю ICU locale |
| Locale, timezone, Intl | ОС + ICU/движок | Sensors/DevTools эмуляция для тестов | Не считать временную эмуляцию постоянной настройкой всех вкладок и workers |
| Геолокация и разрешения | ОС + профиль + origin | Разрешить/запретить доступ; тестовая эмуляция координат | Запрет разрешения снижает раскрытие; не равен достоверной геопозиции |
| Screen, viewport, DPR, DPI | Монитор/Windows + окно + движок | Размер окна, zoom, device emulation | Viewport не заменяет всю модель дисплея; проверять согласованность |
| WebGL/WebGPU, GPU/driver | GPU/ОС/движок | Обычные graphics settings; отдельные диагностические возможности | Нет универсальной штатной настройки «GPU на профиль»; полный контроль — другой runtime/core |
| Canvas/rendering | Движок + GPU + шрифты | Блокировка некоторых трекеров расширением | JS-noise в главной странице не доказывает охват iframe/OffscreenCanvas/worker |
| AudioContext | Аудиостек + движок | Разрешения медиадоступа не меняют все результаты синтеза | Поддерживаемого полного per-profile spoof в обычном UI не найдено |
| Шрифты и text metrics | ОС + web fonts + rendering | Управление web fonts/разрешениями; часть контента может блокироваться | Перечень системных шрифтов/метрики не изолированы отдельной папкой профиля |
| Media devices | ОС + permissions + origin | Отклонить camera/mic; разрешения отдельно по профилю | Виртуальные devices/полная идентичность требуют отдельного решения и тестов |
| WebRTC | Движок + сеть + permissions | Документированная `webRTCIPHandlingPolicy` через privacy API | Это политика транспорта, не гарантия отсутствия любых сетевых утечек |
| DNS | Резолвер движка/ОС + proxy scheme | Разрешение адресов для проксируемых URL зависит от схемы | Отдельно проверять browser background traffic, prefetch и DNS; TCP-тест этого не показывает |
| IP, TLS, HTTP/2, TCP | Сеть + ядро + сервер | Proxy меняет маршрут запросов, которые через него идут | Он не превращает TLS fingerprint Chrome в другое ядро; нельзя обещать полное сетевое обезличивание |
| Расширения | Профиль + API/permissions | Изолированные storage и настройки по профилям | Account sync, native host, файловый экспорт могут снова связать данные |

Источники конкретных механизмов: [UA Client Hints](https://developer.chrome.com/docs/privacy-security/user-agent-client-hints), [DevTools Device Mode](https://developer.chrome.com/docs/devtools/device-mode), [Sensors](https://developer.chrome.com/docs/devtools/sensors), [privacy API/WebRTC](https://developer.chrome.com/docs/extensions/reference/api/privacy), [storage API](https://developer.chrome.com/docs/extensions/reference/api/storage).

**Факт.** Content scripts обычно работают в isolated world; доступ в MAIN world, frames и момент выполнения имеют отдельные правила. [Content scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts).

**Вывод.** Не добавлять «anti-fingerprint» checkbox на базе переопределения пары `navigator`-свойств. Для любого будущего override нужен тест main frame, same-origin и cross-origin iframe, dedicated/shared worker, service worker, OffscreenCanvas, рестарт и обновление ядра. Отсутствие исключений JavaScript не доказывает согласованность отпечатка. В текущем цикле полезнее privacy-настройки с точными названиями и измерениями.

### Выбор архитектуры browser core

| Вариант | Польза | Стоимость/риски | Решение |
| --- | --- | --- | --- |
| Установленный Chrome/Edge + лёгкая оболочка | Минимальная поставка; знакомый UI; штатные updates и extensions | Нет полного управления fingerprint; версии меняются независимо | Сейчас |
| Отдельный поддерживаемый Chromium runtime | Предсказуемая версия, собственный профиль поставки | Сотни файлов ядра, собственная доставка security updates; сам по себе не антидетект | Позже, если доказана потребность |
| Лицензируемое готовое ядро/SDK | Возможность получить более широкий контроль | Лицензия, стоимость, зависимость от поставщика; нужна отдельная проверка обещаний | Исследовать только под конкретные требования |
| Собственный fork Chromium | Максимально доступный контроль реализации | Сборочная инфраструктура, постоянный rebase, sandbox/security, совместимость | Вне текущего лёгкого цикла |

Это оценка архитектуры, а не результаты сравнительного benchmark. Нельзя переносить маркетинговые заявления конкурента в спецификацию собственного продукта без работающего механизма.

## 4. Прокси: достижимая и честная реализация

**Факты Chromium.** HTTP proxy поддерживает CONNECT для HTTPS-целей; HTTPS proxy дополнительно шифрует соединение до самого proxy. Chrome поддерживает HTTP authentication, но игнорирует credentials, встроенные в manual proxy settings. SOCKS5 в Chrome не поддерживает никакой авторизации, разрешает имена проксируемых целевых хостов на стороне proxy и передаёт TCP, не UDP. Без добавленного `direct://` единичный недоступный proxy вызывает ошибку. Есть штатные bypass-исключения для localhost/link-local. [Документация Chrome proxy](https://chromium.googlesource.com/chromium/src/+/HEAD/net/docs/proxy.md).

| Конфигурация | Stock browser | Минимальный UX NeVision |
| --- | --- | --- |
| HTTP без auth | Документирован | Указать endpoint, проверить протокол и выбранный маршрут |
| HTTP с auth | Штатный challenge/prompt | «Логин/пароль сохранены; браузер запросит их отдельно» |
| HTTPS без/с auth | Документирован; TLS к proxy отдельно от TLS к сайту | Не переименовывать в HTTPS обычный HTTP proxy только из-за HTTPS-цели |
| SOCKS5 без auth | Документирован | Тестировать handshake и маршрут |
| SOCKS5 с username/password | Не поддерживается stock Chrome | Не показывать готовность; предложить совместимую схему/endpoint |

Для настройки расширением существует `proxy` API с режимами и bypass list, но оно само не является хранилищем/передатчиком proxy credentials. [Chrome proxy API](https://developer.chrome.com/docs/extensions/reference/api/proxy).

**Факт MV3.** `webRequest.onAuthRequired` доступен с разрешениями `webRequest` и `webRequestAuthProvider`, нужными host permissions; async-обработка документирована. Обычный `webRequestBlocking` ограничен policy-installed extensions. Это механизм HTTP authentication, а не добавление SOCKS5 auth в сетевой стек. [webRequest и authentication](https://developer.chrome.com/docs/extensions/reference/api/webRequest).

**Вывод по автоauth.** Рабочий будущий вариант — устанавливаемое из официального магазина минимальное расширение и защищённый native-messaging канал к vault либо отдельно проверенный broker. Он требует устойчивого extension ID, контроля источника challenge, исключения утечек credentials и тестов ошибок/обновлений. Генерировать plaintext extension с паролем в JS нельзя. MV3 worker может останавливаться; держать необходимое состояние только в глобальной переменной worker ненадёжно. [Service worker lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle).

**Почему не простой loopback relay.** Любой локальный процесс может попытаться подключиться к открытому `127.0.0.1:port`; случайный порт не аутентификация. Новый helper должен иметь lifecycle на профиль, ограничение соединений, таймауты, fail-closed поведение, аутентификацию клиента, отсутствие секретов в URL/CLI/логах, проверку TLS до HTTPS proxy и очистку состояния. Для stock browser обеспечение такой аутентификации без второго механизма непросто. До проверенного дизайна лучше точное ограничение, чем автоматически поднятый общий proxy.

### Уровни диагностики и критерии

| Уровень | Что доказано | Что ещё не доказано |
| --- | --- | --- |
| D0: parsing | Схема, host, port синтаксически корректны | Существование сервера |
| D1: TCP | Установлено соединение до endpoint | Протокол, пароль, доступ в интернет |
| D2: handshake/auth | Сервер ответил ожидаемым протоколом; auth принят/не нужен | HTTPS end-to-end и браузерный маршрут |
| D3: HTTPS fetch | Проверен сертификат и получен ответ через proxy | Что сам выбранный браузер использует тот же маршрут |
| D4: observed egress | Контролируемый endpoint видит IP запроса | Репутация IP и доступность другого сайта |
| D5: actual browser | Отдельный профиль посетил стенд через назначенный proxy | Универсальные гарантии для всех видов фонового трафика |

Это предлагаемая модель UI и QA, а не выполненные проверки. Для D2–D5 нужен управляемый стенд: правильный/ошибочный пароль, timeout, refused, 407, IPv4/IPv6, DNS hostname, TLS failure, обрыв, большие заголовки и Unicode credentials. Прогон должен подтверждать, что ошибку не заменили незаметным прямым подключением. В diagnostic URL нельзя включать пароль; логи должны редактировать чувствительные поля.

Изменение proxy у открытого профиля следует считать отложенным до подтверждённого перезапуска/применения, а не менять только label. Тестовый IP-сервис получает IP и характеристики запроса; использовать синтетические профили и явно указанную тестовую цель.

## 5. Секреты, backup и переносимость

**Факт.** `CryptProtectData` обычно связывает расшифровку с тем же пользователем и компьютером; документация оговаривает roaming и machine scope. Это не общий межкомпьютерный формат шифрованного экспорта. В текущем коде NeVision вызов DPAPI использует пользовательский scope. [Microsoft CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).

**Факт.** Google ввёл App-Bound Encryption в Chrome 127, начиная с cookies: ключ связан с приложением и машиной. Материал 30.07.2024 отдельно предупреждает об ограничениях roaming. Он не доказывает, что каждый тип секрета в любой текущей установке уже мигрирован. [Google Security Blog, июль 2024](https://security.googleblog.com/2024/07/?hl=en). У Edge есть отдельная политика application-bound encryption с собственными условиями поддержки. [Edge policy](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/ApplicationBoundEncryptionEnabled).

**Вывод для пользователя.** Можно переносить папку NeVision и выполнять восстановление файлов; иногда придётся заново ввести proxy-пароли и авторизоваться на сайтах. Даже одинаковое имя пользователя на другом ПК не доказывает доступность ключей. Отключать DPAPI/App-Bound Encryption ради обещания «всё переносится» нельзя.

**Вывод для backup.** Архив профиля может содержать cookies, access tokens в web storage, историю, содержимое сайтов и extension data. Исключение proxy vault не делает ZIP нечувствительным. Нужны отдельные поля `proxy_secrets_included` и `browser_data_may_include_secrets` либо эквивалентная недвусмысленная семантика; совместимость старого manifest проверяется тестом. Backup файлов закрытого профиля, backup SQLite metadata и перенос на другую учётную запись — три разных сценария.

**Факт.** С Chrome 136 remote-debugging flags не применяются к стандартному data directory без отдельного `--user-data-dir`. Google рассматривает debugging interface как чувствительный механизм. [Chrome remote debugging changes, 17.03.2025](https://developer.chrome.com/blog/remote-debugging-port).

**Вывод.** Не включать remote debugging в обычный запуск ради простого UI или auth. Если он нужен QA, использовать временный синтетический профиль, изолированный канал и закрывать интерфейс после теста.

## 6. MV3 и доставка расширений

**Факт.** В официальном Chrome начиная с 137 убрана поддержка загрузки unpacked extension через `--load-extension`. Это не запрет ручного developer-mode тестирования и не утверждение об идентичном поведении всех Chromium-forks. [Chrome Extensions, June 2025](https://developer.chrome.com/blog/extension-news-june-2025).

**Факт.** Для обычной внешней установки Chrome на Windows механизм registry/update URL должен указывать Chrome Web Store, и пользователь подтверждает включение. Просто скачанный CRX не является универсальным автоматическим способом поставки на Windows. [Alternative installation methods](https://developer.chrome.com/docs/extensions/how-to/distribute/install-extensions). Edge документирует ручной `Load unpacked` как сценарий локальной разработки и тестирования. [Edge sideloading](https://learn.microsoft.com/en-us/microsoft-edge/extensions/getting-started/extension-sideloading).

**Факт.** MV3 запрещает remote-hosted исполняемый код; это не запрет на все сетевые данные. [Remote hosted code](https://developer.chrome.com/docs/extensions/develop/migrate/remote-hosted-code). Стабильный extension ID при разработке связан с ключом/упаковкой; копирование каталога не заменяет правильную identity. [Manifest key](https://developer.chrome.com/docs/extensions/reference/manifest/key).

**Вывод для текущего UI.** Команда «Расширения профиля» открывает штатную страницу (`chrome://extensions` или `edge://extensions`) именно в выбранном user-data-dir. Не использовать default browser Windows, который может открыть личный профиль. Для уже работающего профиля учитывать routing URL в существующий процесс и не запускать конкурирующее управление тем же каталогом. Пользователь сам подтверждает установку и permissions в магазине.

**Вывод для будущего inventory.** `manifest.json` показывает заявленные разрешения, но не доказывает, что расширение включено, какие optional permissions выданы и какие enterprise policies действуют. Label должен различать «найдено на диске» и «активно». Нельзя тихо редактировать Chromium `Preferences`/`Secure Preferences` ради установки. Магазин обновляет собственные расширения; менеджер должен учитывать смену permissions и возможное отключение расширения браузером.

**Граница изоляции.** Разные каталоги профилей не должны использовать общую папку extension data. `storage.sync` и вход в один extension/cloud account могут синхронизировать данные намеренно. Для конфиденциального local-first сценария это нужно объяснить. [Chrome extension storage](https://developer.chrome.com/docs/extensions/reference/api/storage).

## 7. Кандидаты расширений: 11 предметных вариантов

Это набор для самостоятельного выбора и QA, **не предустановка**. Стоимость указана на уровне модели «free/paid», без неподтверждённых числовых тарифов. Точные permissions зависят от версии и должны быть подтверждены в install prompt. Где открыт manifest, это отмечено; где изучено только описание поставщика, это не аудит CRX. Для всех 11 расход RAM/CPU и влияние на cold start **не измерены**. Ни одно дополнение не получает статус «проверено с NeVision» только из-за наличия Chrome/Edge в описании.

| Кандидат, источник и актуальность | Польза | Данные/permissions и account/цена | Решение для NeVision |
| --- | --- | --- | --- |
| **uBO Lite** — [официальный repo](https://github.com/uBlockOrigin/uBOL-home), [MV3 manifest](https://github.com/uBlockOrigin/uBOL-home/blob/main/chromium/manifest.json); есть ссылки Chrome/Edge | Контент/трекер blocking | Декларативные правила; расширенный site access зависит от режима. Бесплатный open-source, account не нужен. Заявление автора: без постоянного процесса фильтрации; нулевая стоимость всего browser filtering этим не доказана | Кандидат для research-профиля; выключать при проверке собственных рекламных тегов |
| **Privacy Badger (EFF)** — [официальный сайт](https://privacybadger.org/); видимый release v2026.9.15, Chrome/Edge | Privacy/GPC, ограничение сторонних трекеров | Широкий доступ к сайтам; поставщик объясняет его назначение и отсутствие передачи browsing data без добровольного report. Бесплатно, без account. Есть сетевые updates | Альтернатива по потребности; не предустанавливать несколько блокировщиков сразу; не считать fingerprint spoof |
| **Cookie-Editor** — [сайт](https://cookie-editor.com/), [privacy](https://cookie-editor.com/privacy.html); Chrome/Edge указаны | Смотреть/изменять cookies собственного QA-профиля, экспорт/импорт | Доступ к cookies и соответствующим сайтам критически чувствителен; точный текущий CRX здесь не проверен. Поставщик заявляет отсутствие сбора пользовательских данных. Free/open-source, обязательный account не описан | Полезен QA; экспорт cookies считать секретом; не встраивать импорт чужих сессий |
| **Bitwarden** — [официальная инструкция](https://bitwarden.com/help/getting-started-browserext/), [цены](https://bitwarden.com/pricing/), [permissions FAQ](https://bitwarden.com/it-it/help/security-faqs/) | Зрелый vault/autofill вместо собственного менеджера всех web-паролей | Account/vault обязателен; есть free и paid функции. Для autofill нужен site access, для отдельных возможностей clipboard/native messaging. Vault sync нарушает предположение «всё только локально» | Опционально по явному выбору; не использовать общий vault account как скрытую настройку всех профилей |
| **Tab Session Manager** — [repo](https://github.com/sienori/Tab-Session-Manager), [manifest 7.4.0/MV3](https://raw.githubusercontent.com/sienori/Tab-Session-Manager/master/src/manifest.json) | Сохранять наборы вкладок/окон и восстанавливать их | Manifest: tabs, storage, unlimitedStorage, downloads, identity, alarms, offscreen; optional tabGroups и Google APIs. Локальная работа, optional cloud sync; free/open-source | Устанавливать только тем, кому недостаточно штатных bookmarks; session export содержит URL |
| **SingleFile** — [repo/официальные магазины](https://github.com/gildas-lormeau/SingleFile), [privacy/FAQ](https://github.com/gildas-lormeau/SingleFile/blob/master/faq.md); Chrome/Edge | Сохранить страницу с заметками в один HTML | Доступ к содержимому страницы; локальный сценарий без account. Есть optional uploads, требующие отдельной настройки. Free/open-source; сохранённый HTML может содержать личные данные | Хороший research-инструмент по нажатию; не включать autosave всех посещений по умолчанию |
| **GoFullPage** — [FAQ](https://gofullpage.com/faq), [permissions 02.09.2025](https://blog.gofullpage.com/2025/09/02/your-privacy-our-priority-a-guide-to-gofullpages-permissions/) | Длинный screenshot/PDF лендинга | Free capture/export; отдельные premium tools. Optional downloads, iframe capture может запросить tabs/webNavigation/all-sites. Поставщик описывает локальное хранение screenshots; premium account отдельно | По требованию; проверять страницу на случайное попадание токенов/кабинетов в screenshot |
| **Google Translate** — [официальная Store-карточка](https://chromewebstore.google.com/detail/google-translate/aapbdbdomjkkjkaonfhkkikfgjllcleb); доступна на дату исследования | Перевод выделенного текста | Store disclosure включает website content/user activity/location; текст может передаваться Google. Free; обязательный account для базового сценария не указан. Карточка говорит, что перевод всей страницы уже встроен в Chrome | Сначала штатный перевод браузера; отдельный extension только при реальном удобстве, без конфиденциальных текстов |
| **Ayima Redirect Path 4** — [официальная страница](https://www.ayima.com/chrome/redirect-path-4/), [publisher/store](https://chromewebstore.google.com/publisher/ayima-uk-ltd/ub9f536b7e661cfc964eba1bfb1f29b78); MV3 указан в changelog | Цепочки redirects, HTTP headers, JS/meta redirects | Имеет доступ к навигациям/ответам; точный manifest не прочитан. Описание базового анализа заявляет локальность; v4 добавляет AI, поэтому его обработку данных нельзя приравнять к базовой. Условия AI отдельно | QA-кандидат; базовая альтернатива — DevTools Network с Preserve log. Не обещать Edge без install test |
| **Google Tag Assistant** — [официальная помощь](https://support.google.com/tagmanager/answer/10039345?hl=en-GB), [Google Dev Tools](https://ga-dev-tools.google/tag-assistant/) | Проверка собственных Google tags/events | Нужен доступ читать/менять данные тестируемого сайта; debug session взаимодействует с Google. Basic tool free; доступ к защищённым account/container зависит от прав пользователя | Только отдельный marketing-QA профиль; блокировщики могут менять результат; не включать постоянно |
| **axe DevTools** — [официальные Chrome/Edge версии](https://www.deque.com/axe/devtools/extension/), [account/Pro](https://docs.deque.com/devtools-for-web/4/en/devtools-extension/), [тарифы](https://www.deque.com/axe/devtools/pricing/) | Доступность собственных лендингов: automated checks | Анализирует DOM тестируемой страницы; free single-page automated checks, расширенные функции требуют account/trial/Pro. Здесь не проверена телеметрия конкретной сборки | QA по запросу; автоматический scan не заменяет ручную клавиатуру/скринридер |

**Обновления и происхождение.** Для каждого кандидата: переходить в магазин по ссылке официального автора, сверять publisher/ID, проверять requested permissions и privacy policy, устанавливать через штатный UI профиля. Store updates могут изменить функциональность и разрешения. Происхождение нельзя доказывать совпадением иконки/названия; копировать неизвестный CRX с сайта-посредника не требуется.

**Категории, где расширение не нужно.** Для UTM есть [официальный Campaign URL Builder](https://ga-dev-tools.google/campaign-url-builder/); простой локальный URL parser/builder можно рассмотреть позже без all-sites permissions. Сначала достаточно bookmark на выбранный инструмент. Сетевой выход проверять контролируемым endpoint и встроенной диагностикой, а не устанавливать непроверенный «IP checker» с broad permissions. Cookies/storage/requests доступны также в штатных DevTools.

**Наборы по задаче, без автоустановки.** Research: SingleFile или GoFullPage + штатный перевод; marketing QA: Tag Assistant + Redirect Path; site QA: Cookie-Editor + axe; personal productivity: Bitwarden по осознанному выбору + Tab Session Manager при необходимости. Набор — список рекомендаций, а не общий storage между профилями. Для проверки аналитики нужен также чистый контрольный профиль без blockers.

## 8. Что обязательно проверить отдельно от исследования

| ID | Будущая проверка | Условие успеха |
| --- | --- | --- |
| PLAT-01 | Portable EXE в распакованной тестовой копии без Python/node в PATH | Реальный запуск, создание Data, видимая ошибка при read-only, рабочая базовая операция |
| PLAT-02 | Нагрузка оболочки и search на синтетических профилях | Нет долгого block UI; зарегистрированы startup, RAM, CPU и набор данных |
| PLAT-03 | Сохранение собственного cookie/localStorage/IndexedDB | Профиль A сохраняет после restart, профиль B не читает A |
| PLAT-04 | Service worker/cache/история/bookmarks | Проверить отдельно; факт сохранения cookie не покрывает остальные типы |
| PLAT-05 | Открыть extensions у нового и уже работающего профиля | Нужный user-data-dir; личный профиль пользователя не открыт по ошибке |
| PLAT-06 | Один безопасный store extension в двух тестовых профилях | Различные локальные настройки, ID ожидаемый; clean duplicate не копирует extension state |
| PLAT-07 | Extension update/disable/restart/backup/restore | Сохранение только ожидаемых настроек; disabled не маркируется active; permissions не выданы скрыто |
| PLAT-08 | Proxy D1–D5 и отрицательные случаи | Наблюдаемая ступень точно совпадает с сообщением; ошибки auth не маскируются успехом TCP |
| PLAT-09 | Перенос/restore в другом каталоге на той же машине | Документированное поведение keys и sessions; исходный профиль не изменён |
| PLAT-10 | Другая Windows-учётная запись/машина | Только при доступной среде; иначе явно not tested, нельзя заявить переносимость авторизаций |
| PLAT-11 | Browser manager exit/restart, открытый профиль, повторный launch | Нет неожиданного kill, два процесса не меняют каталог одновременно, status корректен |
| PLAT-12 | Fingerprint diagnostics на synthetic profile | Только наблюдения с версиями, датой, контекстами; никаких универсальных оценок «антидетект пройден» |

## 9. Приоритеты после текущего цикла

| Приоритет | Работа | Почему не считать уже реализованной |
| --- | --- | --- |
| Сейчас | Честные auth/backup/fingerprint тексты, расширения через штатный UI, быстрые фоновые операции | Небольшая поверхность изменений, легко проверить основные сценарии |
| Сейчас при готовом стенде | Диагностика proxy глубже TCP с ограничениями/таймаутами | Код диагностического клиента не доказывает browser route; нужны отдельные тесты |
| Следующий прототип | Безопасный MV3/native-messaging auth для HTTP/HTTPS | Доставка store extension, identity, lifecycle и secrets требуют самостоятельной проверки |
| Следующий прототип | Read-only inventory extensions с версиями и permissions | На диске есть устаревшие/выключенные записи; нельзя показывать ложную активность |
| После доказанной потребности | Локальные presets расширений/URL, более удобный экспорт metadata | Не должны превращаться в скрытую облачную синхронизацию или копирование секретов |
| Отдельный продуктовый этап | Полный browser-core/fingerprint проект | Несовместим с обещанием быстро добавить несколько лёгких форм; нужны бюджет сопровождения и security updates |

Любой внешний fingerprint checker видит IP, browser signals и результаты своего скрипта. Его единичный «зелёный» результат не сертификат приватности. В текущем выпуске продукт следует описывать как локальный менеджер изолированных браузерных профилей с явно перечисленными реализованными возможностями.
