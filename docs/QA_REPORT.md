# NeVision: проверка цикла 0.2.1-preview

> Исторический QA-отчёт только для 0.2.0/0.2.1. Его PASS, FAIL и открытые
> пункты нельзя переносить на другой commit или ZIP. Для текущего выпуска
> сверяйте `release-version.json`, release manifest, SHA-256 публичного ZIP и
> [RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md).

Дата: 2026-10-11. Это журнал доказательств, не заявление «всё протестировано».
Состояние: **0.2.1-preview опубликован; проверенный диапазон и ограничения ниже**.

## Среда и границы

- Windows 11 Pro x64 10.0.26200, Ryzen 7 9700X (16 logical CPU), около 31.1 GiB RAM.
- Python 3.12.10, PyInstaller 6.21.0; установленный Chrome 154.0.8037.99.
- Portable onedir включает Python/runtime, но не Chrome. Исходный компьютер содержит инструменты разработки: это не отдельная чистая VM.
- Ручные снимки проверены при системном DPI 150%; другие DPI и отдельный Windows 10/ARM64 не подтверждены.
- Только синтетические профили. Рабочие cookies, proxy и личный Chrome владельца не использовались.

## Кандидат 0.2.0: результат проверки и отказ от публикации

ZIP `NeVisionWin-portable-v0.2.0-preview.zip`: 14 314 176 bytes,
SHA-256 `14b73f7e15f09cbeb9e0fb1bf47f8e4c88428bb4b9d0e5331b26e238da5e008c`.
Он сохранён локально для диагностики, но **не рекомендован и не опубликован**.

Пройдено: 44 core unit tests (повтор 2.182 s), 7 Tk event-loop checks,
13 release-tool checks, source и packaged self-test. Проверка ZIP: 1026 файлов,
manifest/hashes/licenses, без Data. Defender custom scan завершился; обнаружений
в проверенном интервале событий не было. Это не гарантия отсутствия всех угроз.

Фактический GUI распакованного EXE в папке с пробелами и кириллицей:

| Шаг | Наблюдение | Результат |
| --- | --- | --- |
| Первый запуск | Пустая рабочая область, системная светлая тема, Data рядом с EXE | Пройдено |
| Ctrl+N, имя QA portable 0.2.0, сохранить | Один профиль появился в списке | Пройдено |
| Расширения | Запущен отдельный процесс/окно Chrome; страница extensions не подтверждена | Частично |
| Backup открытого профиля | Показано требование закрыть браузер | Пройдено |
| Закрыть и повторно открыть менеджер | Профиль сохранён, закрытый браузер показан как готовый | Пройдено |
| Backup закрытого профиля после реального Chrome | WinError 3 на файле расширения по пути длиной 261 символ | **P1: кандидат отклонён** |

Нативный UI-инструмент ранее остановил обращение к Chrome из-за невозможности
достоверно определить URL. Клики по странице браузера не считаются проверенными.
Вторая попытка ручного теста NeVision выявила дефект, которого не было в коротких
синтетических backup-фикстурах. Неудачный backup сообщил ошибку, а не ложный успех.

## Связь дефектов с выбранным циклом

| ID | Проблема → решение | Проверка / доказательство |
| --- | --- | --- |
| C01 | Поиск браузера только в типичных местах → per-user/App Paths | Browser discovery unit tests; packaged Chrome launch |
| C02 | Ожидание запуска в UI, неограниченные jobs → 3 workers / 6 outstanding | `test_async_launch_does_not_block_event_loop`, bounded queue / safe close Tk tests |
| C03 | Старое состояние UI и второй manager recovery → locks, reload перед launch | stale launch, changed proxy binding, active delete/restore recovery tests |
| C04 | Перестроение списка и обрезанные действия → incremental rows, scroll, hotkeys | Tk search/theme/selection и minimum-window bounds; ручные светлая/тёмная темы на source |
| C05 | Небезопасный host и ложное применение credentials → validation/fail-closed | IPv6/IDNA/host injection, missing proxy, SOCKS5 auth, CLI secret omission tests |
| C06 | Секрет остаётся в clipboard → условная очистка; extensions → штатная страница | ownership-aware Tk clipboard test, target argv test; реальная страница extensions ещё не доказана |
| C07 | Неясная чувствительность ZIP и опасные paths → manifest/warning/strict validation | hostile ZIP, legacy format, atomic failure/recovery tests; long-path P1 требует нового кандидата |
| C08 | Неоднозначная сборка → версия JSON, allowlist, licenses, hashes | 13 tooling checks, archive validator, EXE version metadata |
| C09 | Нет публичного ZIP → versioned artifact и согласованный сайт | **Пока не закрыто**: нужен deploy и публичное повторное скачивание |

## Производительность кандидата 0.2.0

Raw evidence: `qa/baseline-0.1.3.json`, `qa/after-0.2.0.json`,
`qa/portable-idle-0.2.0.json`. Metadata benchmark: по 30 операций для 10/100/1000
профилей, не одновременно открытых браузеров.

1000 профилей: поиск p50 3.726 → 5.636 ms, p95 4.645 → 6.574 ms;
refresh p50 10.735 → 14.310 ms. Это **не ускорение поиска**: добавленная работа
и шум увеличили абсолютные значения на несколько ms; они остались ниже UI-бюджета.
Основное улучшение отзывчивости — перенос блокирующего launch из Tk thread.

Portable idle, 30.002 s / 115 samples: 0.1758% суммарной мощности 16 logical CPU;
working set peak 46 993 408 bytes; private bytes peak 23 695 360 bytes; 12 threads.
Handles 264 → 290 (peak 291). Короткий замер не доказывает отсутствие утечек.
Одно наблюдение WaitForInputIdle 320.2646 ms не является cold-start/first-paint p95.
Chrome и его дочерние процессы исключены из этих цифр.

## Реальный браузер, отдельно от GUI

`tools/browser_integration.py` и `qa/browser-integration-0.2.0.json`: отдельные
headless Chrome процессы на loopback-странице, реальные Storage/AppPaths.
Первый прогон подтвердил изоляцию cookie/localStorage/IndexedDB между A/B,
сохранение при перезапуске, восстановление на этом же компьютере и пустой
settings-only clone. Это не перенос между компьютерами и не проверка packaged GUI.
После изменения filesystem-кода нужен повтор на окончательной версии.

## Итог повторной проверки и публикации

### Повторная проверка 0.2.1 (2026-10-11)

Long-path P1 исправлен. Чистая сборка: 51 core + 7 Tk + 13 tooling tests
пройдены; source self-test и frozen self-test (реальный путь >260 символов,
backup и restore) завершились с кодом 0. ZIP проверен: 1026 файлов, без Data.
Окончательный ZIP: 14 312 967 bytes, SHA-256
`73a294ed2580a262888b8505eba10e816d3fbfb4d958eeee116a77aac857b373`.
Defender custom scan завершён без обнаружений в проверенном журнале событий.

Ручной packaged GUI повтор на том же синтетическом Chrome-профиле: backup
успешно создан (146 178 999 bytes); импорт через файловый диалог завершён,
в списке два независимых профиля, исходный сохранён. Проверка файлов выполняется
отдельно; этот результат не является проверкой переноса на другой компьютер.

`qa/browser-integration-0.2.1.json`: 14 assertions, 7 headless Chrome processes,
изоляция cookie/localStorage/IndexedDB, сохранение после закрытия, backup/restore,
settings-only clone. `qa/proxy-integration-0.2.1.json`: 17 assertions, 6 процессов,
HTTP/SOCKS5 без авторизации и отказ без прямого fallback на контролируемом
loopback-стенде. Не покрывает authenticated proxy, HTTPS CONNECT, WebRTC/DNS leaks
или полную цепочку BrowserLauncher GUI. Хеш исходника в обоих отчётах совпадает
со snapshot сборки: `6b6364c3c1f353f35d6ecd77954c3fa6640e84ff833a8c35fec0ace5b2deeb7d`.

Новые замеры: `qa/after-0.2.1.json`, `qa/portable-idle-0.2.1.json`.
1000 профилей: поиск p50 4.226 ms / p95 6.004 ms, refresh p50 14.956 ms.
30.015 s простоя менеджера с открытым подтверждением backup: working set peak
49 848 320 bytes, private bytes peak 24 584 192 bytes, CPU 0.2896% всей машины,
handles 295→295, threads 6→6. Chrome исключён. Это не cold-start и не длительный soak.

Пункты ниже — исходный gate; перечисленные выше автоматические проверки,
proxy route, повтор browser integration и ручной backup/import уже выполнены.
Публичная доставка подтверждена ниже.

`qa/gui-backup-restore-0.2.1.json`: CRC ZIP чист, все 7248 файлов совпадают
с восстановленной копией по SHA-256 и длине, включая 6495 файлов расширений
с абсолютными путями >260 символов (максимум 314). Исходный профиль сохранён.

Ручной upgrade smoke: в отдельно распакованном EXE 0.1.3 создан профиль,
приложение штатно закрыто. Data скопирована в соседнюю чистую распаковку 0.2.1.
Новый EXE запущен, профиль и его идентификатор отображаются без ошибок.
После закрытия нового EXE повторно запущен исходный 0.1.3: профиль доступен.
Это проверяет метаданные и сценарий отката к сохранённой старой папке;
не является тестом переноса browser credentials между компьютерами или downgrade
уже изменённой новым Chrome базы. Браузерное состояние проверяется отдельной
integration-проверкой, описанной выше.

### Публичная доставка

- URL: https://nevision-win.mail782861.chatgpt.site/downloads/NeVisionWin-portable-v0.2.1-preview.zip
- Неавторизованный HTTP GET: 200, `application/zip`, 14 312 967 bytes.
- SHA-256 полученного тела: `73a294ed2580a262888b8505eba10e816d3fbfb4d958eeee116a77aac857b373`, точное совпадение с проверенным локальным ZIP.
- Повторное выполнение скачанного EXE: **не выполнено**, объединённая команда download/extract/run отклонена политикой среды. Обход не предпринимался. Отдельная read-only проверка публичного тела пройдена. Frozen self-test и GUI выполнены на локальной распаковке побайтно идентичного ZIP.
- Первая публикация Sites v8 выкладывала файлы с временно отключённым CTA. После успешной проверки публичного hash включена загрузка в Sites v9.
- Финальный source commit сайта: `7ce47bf62e8d782ee0dc76b2c751a066c8b81981`.
- Финальный deployment: `appgdep_6acb88b106288191ac57dc448dcad784`, `succeeded`, 2026-10-11T13:02:02Z.
- CHANGELOG.md и RELEASE_POLICY.md: GET и HEAD 200, `text/markdown; charset=utf-8`, кириллица читается, replacement characters нет.
- Browser QA публичного сайта: видимая 0.2.1, точные размер/hash, переход CTA, desktop и 320px, мобильное меню и закрытие после перехода, фильтр security и возврат All. При 320px content/client width одинаковы (305px с scrollbar), горизонтального переполнения нет. Viewport reset выполнен.
- Повторная визуальная проверка текущей тёмной системной темы сайта не проводилась; CSS и предыдущие theme tests сохранены. Нет заявления о проверке всех тем/DPI/платформ.
- Независимый release audit: 1026 ZIP files и 41 site payload files; Data/runtime secrets не выявлены. Это signature/allowlist scan, не абсолютная гарантия отсутствия произвольного секрета.

Недоступные среды и сценарии (чистая VM, Windows 10, ARM64, другой Windows account,
SmartScreen reputation, установка расширений, все сочетания authenticated proxies)
не превращаются в «pass» по коду или скриншоту. Их ограничения должны оставаться
в публичной матрице preview. Полноценной подмены fingerprint в этом цикле нет.
