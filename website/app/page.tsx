"use client";

import { useEffect, useRef } from "react";

type ChangeType = "added" | "fixed" | "security";

type Change = {
  type: ChangeType;
  label: string;
  text: string;
};

type Release = {
  version: string;
  date: string;
  status: string;
  compatibility: string;
  changes: Change[];
};

const releaseVersion = "0.5.1-preview";
const releaseArchive = `NeAntikWin-portable-v${releaseVersion}.zip`;
const releaseDownload = `https://github.com/AffPapa/NeAntik-Win/releases/download/v${releaseVersion}/${releaseArchive}`;
const releaseChecksum = `${releaseDownload}.sha256`;
const releaseManifest = `https://github.com/AffPapa/NeAntik-Win/releases/download/v${releaseVersion}/NeAntikWin-portable-v${releaseVersion}.manifest.json`;

const releases: Release[] = [
  {
    version: `v${releaseVersion}`,
    date: "12 октября 2026",
    status: "Проще интерфейс · меньше portable ZIP",
    compatibility: "Windows x64 · встроенный Chromium 155 · данные 0.5.0 сохраняются · схема профилей 1",
    changes: [
      { type: "fixed", label: "Понятнее", text: "Редко нужный путь к старому Chrome или Edge скрыт в дополнительных настройках. Названия действий и подсказки стали яснее; рядом с профилем показана его браузерная семья." },
      { type: "fixed", label: "Легче", text: "Встроенный Chromium поставляется с русским, английским и тайским языковыми пакетами. ZIP стал меньше примерно на 13 МБ; другие языки интерфейса браузера переходят на английский." },
      { type: "security", label: "WebRTC и proxy", text: "Для профиля с proxy встроенный Chromium ограничивает WebRTC UDP, обходящий proxy. Это не подтверждение маршрута всех соединений и не гарантия анонимности." },
      { type: "security", label: "Без ложных обещаний", text: "Часовой пояс остаётся системным: автоматическое определение по proxy без надёжной проверки IP дало бы неверный результат. Подмены отпечатка устройства нет." },
    ],
  },
  {
    version: "v0.5.0-preview",
    date: "12 октября 2026",
    status: "Chromium внутри · один portable ZIP",
    compatibility: "Windows x64 · встроенный Chromium 155 · установленный Chrome не нужен · схема профилей 1",
    changes: [
      { type: "added", label: "Браузер внутри", text: "Архив включает Chromium 155.0.8059.40, собранный из закреплённого исходного кода. Новый профиль запускается без отдельно установленного Chrome или Edge." },
      { type: "fixed", label: "Совместимость", text: "Профили с привязкой сохраняют исходный Chrome или Edge. Старые профили без привязки, но уже с данными, не открываются встроенным Chromium без явного выбора." },
      { type: "security", label: "Проверяемость", text: "В архиве находятся лицензия, credits и сведения о сборке Chromium; опубликованы SHA-256 и манифест. Профильные Data и пароли в ZIP не входят." },
      { type: "security", label: "Честные границы", text: "Подмены fingerprint, автоматического обновления Chromium и гарантии анонимности нет. Новую версию ядра нужно получать вместе с новым portable-релизом." },
    ],
  },
  {
    version: "v0.4.1-preview",
    date: "12 октября 2026",
    status: "Portable reliability · usability",
    compatibility: "Windows x64 · установленный Chrome или Edge · portable ZIP · схема профилей 1",
    changes: [
      { type: "fixed", label: "Профили", text: "Профиль закрепляется за Chrome или Edge при первом запуске: смена браузерной семьи не смешивает данные в одном каталоге. Привязка сохраняется в backup." },
      { type: "fixed", label: "Proxy", text: "Одинаковые подписи proxy больше не сбивают назначение. Повторное копирование пароля обновляет 30-секундный таймер очистки буфера." },
      { type: "fixed", label: "Интерфейс", text: "Убраны устаревшие подсказки о Native-ядре. Диалоги закрываются по Escape; при смене темы сохраняются поиск и прокрутка." },
      { type: "security", label: "Публикация", text: "Проверка публичных исходников анализирует точные staged-данные Git. Сборка portable ZIP не включает локальные Data или браузерное ядро." },
    ],
  },
  {
    version: "v0.4.0-preview",
    date: "12 октября 2026",
    status: "Profile manager · safer public release",
    compatibility: "Windows x64 · установленный Chrome или Edge · portable ZIP · схема профилей 1",
    changes: [
      { type: "security", label: "Границы продукта", text: "Удалены экспериментальные файлы движка и код изменения fingerprint. Обычные профили Chrome/Edge запускаются без fingerprint- и User-Agent-переопределений." },
      { type: "fixed", label: "Наследуемые профили", text: "Профили из старых экспериментальных сборок с неподдерживаемым режимом нельзя редактировать, клонировать или запускать; исходные данные сохраняются." },
      { type: "security", label: "Публикация", text: "Публичный экспорт и CI исключают экспериментальные компоненты. Архив проверен на отсутствие Engine и включённого изменения fingerprint." },
      { type: "added", label: "Сборка", text: "Чистый portable ZIP собран из опубликованного коммита; приложены manifest, SHA-256 и runtime-лицензии." },
    ],
  },
  {
    version: "v0.2.1-preview",
    date: "11 октября 2026",
    status: "Удобство и надёжность",
    compatibility: "Схема данных 1 и backup nevision-profile-backup-v1 сохранены · нужен установленный Chrome или Edge",
    changes: [
      { type: "fixed", label: "Backup", text: "Исправлены резервное копирование и восстановление длинных Windows-путей — без изменения настроек системы." },
      { type: "fixed", label: "Отзывчивость", text: "Запуск браузера вынесен в фон. Число фоновых задач ограничено, а закрытие приложения дожидается завершения операций с данными." },
      { type: "fixed", label: "Профили", text: "Менеджер распознаёт профиль, открытый вне текущего экземпляра NeVision, и обнаруживает браузеры, установленные для текущего Windows-пользователя." },
      { type: "added", label: "Удобство", text: "Добавлены переход к штатной странице расширений выбранного профиля, горячие клавиши и прокрутка панели профиля в небольшом окне." },
      { type: "security", label: "Хранение", text: "Усилена проверка Windows-путей и дубликатов внутри backup. Интерфейс предупреждает: архив может содержать cookies, сессии и другие чувствительные данные браузера." },
      { type: "fixed", label: "Proxy", text: "Исправлен формат IPv6 endpoint. TCP-проверка явно отделена от проверки авторизации; ограничения HTTP(S)- и SOCKS5-аутентификации показаны до запуска." },
      { type: "security", label: "Пароли", text: "Скопированный proxy-пароль удаляется из обычного буфера обмена по таймеру, если содержимое не было заменено. Это не очищает историю буфера Windows." },
      { type: "added", label: "Поставка", text: "Portable ZIP сопровождают SHA-256, manifest и лицензионные тексты runtime. Версия EXE и номер релиза берутся из одного источника." },
    ],
  },
  {
    version: "v0.1.3-preview",
    date: "26 июля 2026",
    status: "Reliability & recovery preview",
    compatibility: "Совместимо с 0.1.2-preview · схема данных и формат backup nevision-profile-backup-v1 не менялись",
    changes: [
      {
        type: "added",
        label: "Новое",
        text: "Каждый новый backup получает уникальное имя и создаётся атомарно: существующий архив не перезаписывается частично.",
      },
      {
        type: "added",
        label: "Новое",
        text: "Backup, restore, profile health и TCP-проверка proxy выполняются в фоне, чтобы рабочее окно оставалось отзывчивым.",
      },
      {
        type: "fixed",
        label: "Надёжность",
        text: "Создание, удаление и восстановление профиля используют rollback-safe последовательности: при ошибке операция возвращает своё рабочее состояние.",
      },
      {
        type: "fixed",
        label: "Надёжность",
        text: "Busy guard не допускает одновременные изменяющие операции с одним профилем и показывает, что профиль занят.",
      },
      {
        type: "fixed",
        label: "Интерфейс",
        text: "Форма Proxy Vault теперь оставляет заметку о DPAPI и кнопки сохранения видимыми при распространённом масштабе Windows 150%.",
      },
      {
        type: "security",
        label: "Границы",
        text: "Обновление не добавляет подмену fingerprint, обход антифрода, банов или автоматизацию аккаунтов; local-first и DPAPI-границы сохранены.",
      },
    ],
  },
  {
    version: "v0.1.2-preview",
    date: "25 июля 2026",
    status: "System theme preview",
    compatibility: "Совместимо с 0.1.1-preview · схема данных и формат backup не менялись",
    changes: [
      {
        type: "added",
        label: "Новое",
        text: "NeVision Win по умолчанию следует режиму приложений Windows: светлая и тёмная палитры переключаются без перезапуска, когда окно настроек закрыто.",
      },
      {
        type: "added",
        label: "Новое",
        text: "В настройках появился понятный выбор: Системная, Светлая или Тёмная тема.",
      },
      {
        type: "fixed",
        label: "Изменено",
        text: "Титульная строка Windows, элементы выбора, полосы прокрутки, Canvas-бейджи и состояния фокуса приведены к одной палитре; на сайте устранено горизонтальное переполнение на desktop и 320 px.",
      },
      {
        type: "security",
        label: "Границы",
        text: "Определение темы читает только системную настройку Windows; профильные данные и секреты по-прежнему остаются локальными.",
      },
    ],
  },
  {
    version: "v0.1.1-preview",
    date: "25 июля 2026",
    status: "Visual portable preview",
    compatibility: "Совместимо с 0.1.0-preview · формат backup: nevision-profile-backup-v1",
    changes: [
      {
        type: "added",
        label: "Новое",
        text: "Полностью обновлены desktop workspace, фирменный знак, native line icons и Windows-иконка приложения.",
      },
      {
        type: "added",
        label: "Новое",
        text: "Сайт получил оригинальную графику, локальные SVG-ассеты и адаптивную визуальную систему без CDN.",
      },
      {
        type: "fixed",
        label: "Изменено",
        text: "Улучшены контраст, focus-состояния, размеры действий и иерархия рабочего пространства.",
      },
      {
        type: "security",
        label: "Безопасность",
        text: "Визуальные ресурсы приложения и сайта локальные: без трекеров, CDN и обязательных аккаунтов.",
      },
    ],
  },
  {
    version: "v0.1.0-preview",
    date: "25 июля 2026",
    status: "Portable preview",
    compatibility: "Формат backup: nevision-profile-backup-v1 · миграция не требуется",
    changes: [
      {
        type: "added",
        label: "Новое",
        text: "Собран portable Windows .exe с отдельными локальными профилями для установленного Chrome или Edge.",
      },
      {
        type: "added",
        label: "Новое",
        text: "Добавлены Proxy vault, журнал действий, проверка TCP, profile health, чистая копия и backup/restore.",
      },
      {
        type: "security",
        label: "Безопасность",
        text: "Proxy-пароли защищаются Windows DPAPI, не попадают в командную строку браузера и не входят в backup.",
      },
      {
        type: "fixed",
        label: "Надёжность",
        text: "Restore проверяет пути архива и ограничивает импорт до 20 000 файлов и 8 GB распакованных данных.",
      },
    ],
  },
  {
    version: "v0.1.0-dev",
    date: "25 июля 2026",
    status: "В разработке",
    compatibility: "Формат профилей: ещё не зафиксирован",
    changes: [
      {
        type: "added",
        label: "Новое",
        text: "Создан публичный продуктовый сайт NeVision Win с отдельной страницей истории изменений.",
      },
      {
        type: "added",
        label: "Новое",
        text: "Добавлена политика релизов: для каждой версии фиксируются изменения, безопасность, совместимость и возможность отката.",
      },
      {
        type: "security",
        label: "Принцип",
        text: "Зафиксирована local-first модель: рабочие профили и секреты не предполагают обязательной облачной синхронизации.",
      },
    ],
  },
];

const pageMarkup = String.raw`<a class="skip-link" href="#main">К содержанию</a>
    <div class="page-noise" aria-hidden="true"></div>
    <div class="page-aura aura-one" aria-hidden="true"></div>
    <div class="page-aura aura-two" aria-hidden="true"></div>

    <header class="site-header" data-header>
      <a class="brand" href="#top" aria-label="NeAntik Win — на главную">
        <img class="brand-mark" src="/assets/brand.svg" width="36" height="36" alt="" />
        <span class="brand-name">NeAntik <small>WIN</small></span>
      </a>

      <nav class="site-nav" id="primary-navigation" aria-label="Основная навигация" data-nav>
        <a href="#product">Возможности</a>
        <a href="#workflow">Как устроено</a>
        <a href="#security">Безопасность</a>
        <a href="#changelog">Изменения</a>
      </nav>

      <div class="header-actions">
        <a class="version-chip" href="#download">
          <span class="pulse-dot" aria-hidden="true"></span>
          v${releaseVersion}
          <svg aria-hidden="true"><use href="/assets/icons.svg#arrow-down"></use></svg>
        </a>
        <button class="menu-button" type="button" aria-controls="primary-navigation" aria-expanded="false" data-menu-button>
          <span class="sr-only" data-menu-label>Открыть меню</span>
          <svg aria-hidden="true"><use href="/assets/icons.svg#menu"></use></svg>
        </button>
      </div>
    </header>

    <main id="main">
      <section class="hero shell" id="top" aria-labelledby="hero-title">
        <div class="hero-copy reveal">
          <p class="eyebrow"><span></span> Windows · local-first · portable</p>
          <h1 id="hero-title">Профили в порядке.<br /><em>Темп — ваш.</em></h1>
          <p class="hero-lead">
            NeAntik Win — локальный браузер с отдельными профилями для Windows. В одном portable-архиве уже есть Chromium: отдельный Chrome устанавливать не нужно.
            Данные, proxy-настройки и история работы остаются на вашем компьютере.
          </p>
          <div class="hero-actions">
            <a class="button button-primary" href="#download">
              Доступная версия
              <svg aria-hidden="true"><use href="/assets/icons.svg#arrow-up-right"></use></svg>
            </a>
            <a class="button button-secondary" href="https://github.com/AffPapa/NeAntik-Win" target="_blank" rel="noopener noreferrer">
              Исходники на GitHub
              <svg aria-hidden="true"><use href="/assets/icons.svg#arrow-down"></use></svg>
            </a>
          </div>
          <p class="download-note">Новый профиль запускается во встроенном Chromium. Настройки упрощены, архив стал меньше. Подмены отпечатка устройства и гарантии анонимности нет.</p>
          <dl class="hero-facts" aria-label="Ключевые свойства NeAntik Win">
            <div><dt>local</dt><dd>данные не требуют облака</dd></div>
            <div><dt>DPAPI</dt><dd>защита proxy-паролей</dd></div>
            <div><dt>portable</dt><dd>данные рядом с приложением</dd></div>
          </dl>
        </div>

        <div class="showcase reveal showcase-delay" aria-label="Иллюстрация рабочего пространства NeAntik Win">
          <img class="showcase-atmosphere" src="/assets/nevision-hero-atmosphere.png" alt="" aria-hidden="true" fetchpriority="high" />
          <div class="showcase-orbit orbit-one" aria-hidden="true"></div>
          <div class="showcase-orbit orbit-two" aria-hidden="true"></div>
          <div class="showcase-chip chip-one" aria-hidden="true"><svg><use href="/assets/icons.svg#spark"></use></svg> LOCAL</div>
          <div class="showcase-chip chip-two" aria-hidden="true"><span></span> ON DEVICE</div>

          <div class="app-window" aria-hidden="true">
            <div class="window-bar">
              <div class="window-controls"><i></i><i></i><i></i></div>
              <div class="window-app-title"><img src="/assets/brand.svg" width="16" height="16" alt="" /> NeAntik Win</div>
              <span class="window-build">v${releaseVersion}</span>
            </div>
            <div class="app-body">
              <aside class="app-sidebar">
                <div class="app-brand"><img src="/assets/brand.svg" width="23" height="23" alt="" /><b>NeAntik</b></div>
                <div class="new-profile"><svg><use href="/assets/icons.svg#plus"></use></svg><span>Новый профиль</span></div>
                <p class="app-label">WORKSPACE</p>
                <ul class="app-navigation">
                  <li class="current"><svg><use href="/assets/icons.svg#grid"></use></svg><span>Все профили</span><b>12</b></li>
                  <li><svg><use href="/assets/icons.svg#folder"></use></svg><span>Клиенты</span><b>5</b></li>
                  <li><svg><use href="/assets/icons.svg#folder"></use></svg><span>Исследования</span><b>4</b></li>
                  <li><svg><use href="/assets/icons.svg#folder"></use></svg><span>Личное</span><b>3</b></li>
                </ul>
                <p class="app-label app-label-tools">TOOLS</p>
                <ul class="app-navigation app-tools">
                  <li><svg><use href="/assets/icons.svg#vault"></use></svg><span>Proxy vault</span></li>
                  <li><svg><use href="/assets/icons.svg#activity"></use></svg><span>Profile health</span></li>
                  <li><svg><use href="/assets/icons.svg#backup"></use></svg><span>Backups</span></li>
                </ul>
                <div class="app-local"><span></span> Данные локально</div>
              </aside>
              <div class="app-content">
                <div class="app-toolbar">
                  <div><p class="app-heading">Все профили</p><p>12 профилей · 2 активны</p></div>
                  <div class="toolbar-actions"><span><svg><use href="/assets/icons.svg#search"></use></svg> Поиск</span><span>Фильтр <svg><use href="/assets/icons.svg#chevron"></use></svg></span></div>
                </div>
                <div class="profile-grid">
                  <article class="profile-card selected">
                    <div class="profile-card-top"><span class="profile-avatar purple">A</span><span class="profile-status ready">готов</span><svg><use href="/assets/icons.svg#more"></use></svg></div>
                    <p class="profile-name">Affiliate Research</p>
                    <p><i class="purple-dot"></i> SOCKS5 · DE</p>
                    <footer><span>8 мин назад</span><b>Запустить <svg><use href="/assets/icons.svg#arrow-up-right"></use></svg></b></footer>
                  </article>
                  <article class="profile-card">
                    <div class="profile-card-top"><span class="profile-avatar orange">B</span><span class="profile-status">закрыт</span><svg><use href="/assets/icons.svg#more"></use></svg></div>
                    <p class="profile-name">Brand QA</p>
                    <p><i class="orange-dot"></i> HTTPS · BR</p>
                    <footer><span>Вчера, 19:42</span><b>Запустить <svg><use href="/assets/icons.svg#arrow-up-right"></use></svg></b></footer>
                  </article>
                  <article class="profile-card cool">
                    <div class="profile-card-top"><span class="profile-avatar blue">C</span><span class="profile-status">закрыт</span><svg><use href="/assets/icons.svg#more"></use></svg></div>
                    <p class="profile-name">Client · Nord</p>
                    <p><i class="blue-dot"></i> Без proxy</p>
                    <footer><span>12 июл, 10:16</span><b>Запустить <svg><use href="/assets/icons.svg#arrow-up-right"></use></svg></b></footer>
                  </article>
                  <article class="profile-card add-profile"><span><svg><use href="/assets/icons.svg#plus"></use></svg></span><p>Создать профиль</p></article>
                </div>
              </div>
            </div>
          </div>
          <p class="showcase-caption"><span></span> Иллюстрация рабочего пространства · не снимок приложения</p>
        </div>
      </section>

      <section class="signal-strip" aria-label="Основные свойства">
        <div class="signal-inner shell">
          <p><span>01</span> Chromium-профили изолированы по каталогам</p>
          <p><span>02</span> Секреты — через Windows DPAPI</p>
          <p><span>03</span> Никакой обязательной синхронизации</p>
          <p><span>04</span> История каждой версии — публична</p>
        </div>
      </section>

      <section class="capabilities shell" id="product" aria-labelledby="capabilities-title">
        <div class="section-heading reveal">
          <p class="eyebrow"><span></span> Инструмент, а не тяжёлая панель</p>
          <h2 id="capabilities-title">Одна быстрая среда.<br /><em>Без лишнего слоя.</em></h2>
          <p>Профили, proxy, запуск и резервные копии — рядом, в одном локальном приложении.</p>
        </div>

        <div class="capability-grid">
          <article class="capability-card isolation-card reveal">
            <div class="card-topline"><span class="feature-icon lime"><svg><use href="/assets/icons.svg#layers"></use></svg></span><span class="card-number">01</span></div>
            <h3>Изолированные профили</h3>
            <p>Каждый профиль запускается со своей папкой user-data: cookies, история, разрешения и расширения отделены друг от друга.</p>
            <div class="isolation-graphic" aria-hidden="true">
              <div class="folder-root"><svg><use href="/assets/icons.svg#folder"></use></svg><span>Profiles</span></div>
              <div class="folder-line line-one"></div><div class="folder-line line-two"></div><div class="folder-line line-three"></div>
              <div class="profile-folder folder-a"><span>A</span><p>affiliate</p><i>Chromium data</i></div>
              <div class="profile-folder folder-b"><span>B</span><p>brand qa</p><i>Edge data</i></div>
              <div class="profile-folder folder-c"><span>C</span><p>client nord</p><i>Chromium data</i></div>
            </div>
          </article>

          <article class="capability-card vault-card reveal reveal-delay-one">
            <div class="card-topline"><span class="feature-icon purple"><svg><use href="/assets/icons.svg#vault"></use></svg></span><span class="card-number">02</span></div>
            <h3>Proxy vault</h3>
            <p>HTTP, HTTPS и SOCKS5-параметры хранятся локально. Пароль защищается Windows DPAPI. Авторизацию HTTP(S) запрашивает браузер; SOCKS5 с логином и паролем не поддерживается этим запуском.</p>
            <div class="vault-graphic" aria-hidden="true">
              <div class="vault-lock"><svg><use href="/assets/icons.svg#lock"></use></svg></div>
              <div><b>LOCAL VAULT</b><span>Windows DPAPI</span></div>
              <i>sealed</i>
            </div>
          </article>

          <article class="capability-card velocity-card reveal reveal-delay-two">
            <div class="card-topline"><span class="feature-icon blue"><svg><use href="/assets/icons.svg#bolt"></use></svg></span><span class="card-number">03</span></div>
            <h3>Тихий, быстрый запуск</h3>
            <p>Поиск, теги, группы, чистое клонирование настроек и один клик на запуск — без загрузки удалённого workspace.</p>
            <div class="velocity-graphic" aria-hidden="true">
              <span class="velocity-line line-a"></span><span class="velocity-line line-b"></span><span class="velocity-line line-c"></span>
              <b><svg><use href="/assets/icons.svg#bolt"></use></svg> launch local</b>
            </div>
          </article>

          <article class="capability-card restore-card reveal reveal-delay-three">
            <div class="card-topline"><span class="feature-icon ink"><svg><use href="/assets/icons.svg#backup"></use></svg></span><span class="card-number">04</span></div>
            <h3>Backup без сюрпризов</h3>
            <p>Создавайте ZIP-копии закрытого профиля и восстанавливайте их в новый. Сохранённые proxy-пароли исключены, но cookies и сессии могут попасть в архив — храните его как конфиденциальный файл.</p>
            <div class="restore-graphic" aria-hidden="true">
              <div class="archive-file"><svg><use href="/assets/icons.svg#archive"></use></svg><span>profile.backup</span></div>
              <div class="restore-arrow"><svg><use href="/assets/icons.svg#arrow-right"></use></svg></div>
              <div class="restore-target"><svg><use href="/assets/icons.svg#check"></use></svg><span>New profile</span></div>
            </div>
          </article>
        </div>
      </section>

      <section class="workflow" id="workflow" aria-labelledby="workflow-title">
        <div class="shell workflow-grid">
          <div class="workflow-copy reveal">
            <p class="eyebrow"><span></span> Понятная локальная архитектура</p>
            <h2 id="workflow-title">Не обещает магию.<br /><em>Показывает устройство.</em></h2>
            <p>NeAntik Win поставляется со своим Chromium и запускает каждый новый профиль с отдельным каталогом данных. Старые профили с известным Chrome или Edge сохраняют эту привязку.</p>
            <a class="text-link" href="#security">Границы продукта <svg aria-hidden="true"><use href="/assets/icons.svg#arrow-right"></use></svg></a>
          </div>
          <div class="workflow-console reveal reveal-delay-one">
            <div class="console-top"><span>LOCAL STORAGE MAP</span><span><i></i> READY</span></div>
            <div class="console-tree">
              <div class="tree-item root"><svg><use href="/assets/icons.svg#folder"></use></svg><strong>NeAntikWin portable</strong><em>ваша папка</em></div>
              <div class="tree-item"><span class="tree-branch">├─</span><svg><use href="/assets/icons.svg#app"></use></svg><b>NeAntikWin.exe</b><em>launcher</em></div>
              <div class="tree-item"><span class="tree-branch">├─</span><svg><use href="/assets/icons.svg#folder"></use></svg><b>_internal/</b><em>локальный runtime</em></div>
              <div class="tree-item"><span class="tree-branch">├─</span><svg><use href="/assets/icons.svg#folder"></use></svg><b>Engine/Chromium/</b><em>встроенный браузер</em></div>
              <div class="tree-item"><span class="tree-branch">└─</span><svg><use href="/assets/icons.svg#folder"></use></svg><b>Data/</b><em>создаётся при первом запуске</em></div>
              <div class="tree-item nested"><span class="tree-branch">├─</span><svg><use href="/assets/icons.svg#database"></use></svg><b>nevision.db</b><em>метаданные + DPAPI</em></div>
              <div class="tree-item nested"><span class="tree-branch">├─</span><svg><use href="/assets/icons.svg#folder"></use></svg><b>Profiles/</b><em>изолированные данные</em></div>
              <div class="tree-item nested"><span class="tree-branch">└─</span><svg><use href="/assets/icons.svg#archive"></use></svg><b>Backups/</b><em>ZIP без proxy-секретов</em></div>
            </div>
            <div class="console-foot"><span><svg><use href="/assets/icons.svg#shield"></use></svg> Проверяемые локальные границы</span><span>v1 format</span></div>
          </div>
        </div>
      </section>

      <section class="security shell" id="security" aria-labelledby="security-title">
        <div class="security-head reveal">
          <div>
            <p class="eyebrow"><span></span> Предсказуемость важнее громких обещаний</p>
            <h2 id="security-title">Контроль — у вас.</h2>
          </div>
          <p>В preview мы открыто фиксируем возможности, ограничения и модель хранения — прежде, чем добавлять новые функции.</p>
        </div>
        <div class="boundary-grid">
          <article class="boundary-card reveal"><span class="boundary-icon"><svg><use href="/assets/icons.svg#computer"></use></svg></span><h3>Только ваш компьютер</h3><p>Нет обязательной учётной записи и облачной панели. Менеджер не отправляет свою телеметрию; сам Chromium и расширения могут обращаться к сети.</p></article>
          <article class="boundary-card reveal reveal-delay-one"><span class="boundary-icon"><svg><use href="/assets/icons.svg#key"></use></svg></span><h3>Секреты привязаны к Windows</h3><p>DPAPI даёт доступ к proxy-паролям только тому же Windows-пользователю на том же устройстве.</p></article>
          <article class="boundary-card boundary-card-contrast reveal reveal-delay-two"><span class="boundary-icon"><svg><use href="/assets/icons.svg#eye-off"></use></svg></span><h3>Без ложных гарантий</h3><p>NeAntik Win не заявляет обход проверок сайтов, антифрода, банов или подмену fingerprint.</p></article>
        </div>
      </section>

      <section class="release shell" id="download" aria-labelledby="release-title">
        <div class="release-main reveal" id="release">
          <div class="release-stamp"><span>WINDOWS</span><b>v${releaseVersion.split("-")[0]}</b><i>preview</i></div>
          <div>
            <p class="eyebrow"><span></span> NeAntik Win · Windows x64 · v${releaseVersion}</p>
            <h2 id="release-title">Скачайте.<br /><em>Распакуйте. Запустите.</em></h2>
            <p>Установка не нужна. Скачайте один ZIP, распакуйте его целиком в доступную для записи папку NTFS и откройте NeAntikWin.exe. Chromium уже внутри; отдельно устанавливать Chrome не требуется. Для профилей с proxy ограничен прямой WebRTC UDP, но весь сетевой маршрут этим не проверяется.</p>
          </div>
        </div>
        <aside class="release-side reveal reveal-delay-one" id="release-details">
          <div class="release-side-row"><span>Проверено на</span><b>Windows 11 x64, build 26200</b></div>
          <div class="release-side-row"><span>Windows 10</span><b>в этом выпуске не проверена</b></div>
          <div class="release-side-row" data-release-size-row hidden><span>Размер ZIP</span><b data-release-size></b></div>
          <div class="release-side-row"><span>Формат backup</span><b>nevision-profile-backup-v1</b></div>
          <div class="release-side-row"><span>Профильные данные</span><b>локально в Data/</b></div>
          <div class="release-side-row"><span>Права песочницы</span><b>чтение Engine/Chromium, не Data/</b></div>
          <div class="release-side-row"><span>Proxy-пароли</span><b>Windows DPAPI</b></div>
          <div class="release-side-row"><span>Подпись приложения</span><b>нет цифровой подписи (unsigned preview)</b></div>
          <div class="release-side-row release-hash-row" data-release-hash-row hidden><span>SHA-256 архива</span><code data-release-hash></code></div>
          <div class="release-links">
            <a class="button button-dark" href="${releaseDownload}" target="_blank" rel="noopener noreferrer">Скачать NeAntik Win v${releaseVersion} <svg aria-hidden="true"><use href="/assets/icons.svg#arrow-down"></use></svg></a>
            <a class="text-link" href="${releaseChecksum}" target="_blank" rel="noopener noreferrer">SHA-256</a>
            <a class="text-link" href="${releaseManifest}" target="_blank" rel="noopener noreferrer">Manifest сборки</a>
            <a class="text-link" href="https://github.com/AffPapa/NeAntik-Win/releases/tag/v${releaseVersion}" target="_blank" rel="noopener noreferrer">Все файлы релиза</a>
            <a class="text-link" href="/CHANGELOG.md">Что изменилось</a>
          </div>
          <p class="download-note">SHA-256 проверяет целостность файла и не заменяет цифровую подпись. Если Windows показывает предупреждение, проверьте источник загрузки и checksum.</p>
        </aside>
      </section>

      <section class="update-guide shell" aria-labelledby="update-title">
        <div>
          <p class="eyebrow"><span></span> Ваши данные остаются с вами</p>
          <h2 id="update-title">Как обновиться</h2>
          <ol>
            <li>Закройте окна профилей и NeAntik Win. Сохраните резервную копию старой portable-папки вместе с Data.</li>
            <li>Распакуйте новый ZIP в отдельную папку. Скопируйте туда свою Data, не удаляя исходную копию.</li>
            <li>Запустите новый NeAntikWin.exe под тем же Windows-пользователем и проверьте профили перед дальнейшей работой.</li>
          </ol>
        </div>
        <div class="update-caveats">
          <h3>Перенос и возврат к прошлой версии</h3>
          <p>DPAPI-пароли привязаны к вашему Windows-пользователю и компьютеру. На другом устройстве потребуется повторный ввод; перенос cookies и входов в сайты также зависит от Chromium.</p>
          <p>Для отката используйте сохранённую старую папку. Замена одного EXE не откатывает формат профиля Chromium, Chrome или Edge: после обновления браузера старое ядро может не открыть эти данные.</p>
          <p>NeAntik разделяет локальные профили, но не подменяет fingerprint и не гарантирует прохождение проверок сайтов.</p>
          <a class="text-link" href="/RELEASE_POLICY.md">Политика релизов и совместимость <svg aria-hidden="true"><use href="/assets/icons.svg#arrow-right"></use></svg></a>
        </div>
      </section>

      <section class="changelog shell" id="changelog" aria-labelledby="changelog-title">
        <div class="changelog-intro reveal">
          <div>
            <p class="eyebrow"><span></span> Версии без тумана</p>
            <h2 id="changelog-title">История изменений</h2>
          </div>
          <p>После каждой версии здесь появляются дата, совместимость, новое, исправления и изменения безопасности.</p>
        </div>
        <div class="changelog-controls reveal" role="group" aria-label="Фильтр истории изменений">
          <button class="change-filter active" type="button" data-filter="all" aria-pressed="true">Все</button>
          <button class="change-filter" type="button" data-filter="added" aria-pressed="false">Новое</button>
          <button class="change-filter" type="button" data-filter="fixed" aria-pressed="false">Надёжность</button>
          <button class="change-filter" type="button" data-filter="security" aria-pressed="false">Безопасность</button>
          <a href="/CHANGELOG.md" target="_blank" rel="noopener">Открыть CHANGELOG.md <svg aria-hidden="true"><use href="/assets/icons.svg#arrow-up-right"></use></svg></a>
        </div>
        <p class="sr-only" id="changelog-status" role="status" aria-live="polite" aria-atomic="true"></p>
        <div class="changelog-list" id="changelog-list"><article class="release-card no-js-changelog"><header><div><h3>История версий</h3><span>доступна</span></div></header><p>Полный журнал изменений доступен без JavaScript в отдельном Markdown-файле.</p><a class="text-link" href="/CHANGELOG.md">Открыть CHANGELOG.md <svg aria-hidden="true"><use href="/assets/icons.svg#arrow-up-right"></use></svg></a></article></div>
      </section>

      <section class="final-cta shell" aria-labelledby="cta-title">
        <div class="cta-grid-pattern" aria-hidden="true"></div>
        <div class="final-cta-copy reveal">
          <p class="eyebrow"><span></span> NeAntik Win</p>
          <h2 id="cta-title">Рабочая среда,<br /><em>которую видно.</em></h2>
        </div>
        <div class="final-cta-actions reveal reveal-delay-one">
          <p>Начните с версии, где хранение и ограничения не спрятаны за маркетинговыми словами.</p>
          <a class="button button-light" href="#download">Скачать v${releaseVersion} <svg aria-hidden="true"><use href="/assets/icons.svg#arrow-up-right"></use></svg></a>
          <small><svg aria-hidden="true"><use href="/assets/icons.svg#windows"></use></svg> Windows x64 · Chromium внутри · portable ZIP</small>
        </div>
      </section>
    </main>

    <footer class="site-footer shell">
      <a class="brand" href="#top" aria-label="NeAntik Win — наверх">
        <img class="brand-mark" src="/assets/brand.svg" width="32" height="32" alt="" />
        <span class="brand-name">NeAntik <small>WIN</small></span>
      </a>
      <p>© <span id="year"></span> NeAntik Win. Built local-first.</p>
      <div class="footer-links"><a href="/CHANGELOG.md" target="_blank" rel="noopener">Changelog</a><a href="/RELEASE_POLICY.md" target="_blank" rel="noopener">Release policy</a></div>
    </footer>`;

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export default function Home() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const list = root.querySelector<HTMLElement>("#changelog-list");
    const changelogStatus = root.querySelector<HTMLElement>("#changelog-status");
    const filters = Array.from(root.querySelectorAll<HTMLButtonElement>(".change-filter"));
    const year = root.querySelector<HTMLElement>("#year");
    const header = root.querySelector<HTMLElement>("[data-header]");
    const menuButton = root.querySelector<HTMLButtonElement>("[data-menu-button]");
    const menuLabel = root.querySelector<HTMLElement>("[data-menu-label]");
    const navigation = root.querySelector<HTMLElement>("[data-nav]");

    document.documentElement.classList.add("has-js");
    if (year) year.textContent = String(new Date().getFullYear());

    // The release owner writes this metadata from the verified shipping archive.
    // Download links remain ordinary anchors, usable without JavaScript.
    const releaseRequest = new AbortController();
    const releaseTimeout = window.setTimeout(() => releaseRequest.abort(), 5000);
    void fetch("/release.json", { signal: releaseRequest.signal, cache: "no-cache" })
      .then((response) => {
        if (!response.ok) throw new Error("Release metadata unavailable");
        return response.json() as Promise<unknown>;
      })
      .then((value) => {
        if (!value || typeof value !== "object") return;
        const metadata = value as Record<string, unknown>;
        if (metadata.version !== releaseVersion || !metadata.archive || typeof metadata.archive !== "object") return;
        const archive = metadata.archive as Record<string, unknown>;
        if (archive.filename !== releaseArchive) return;
        if (typeof archive.size_bytes === "number" && Number.isSafeInteger(archive.size_bytes) && archive.size_bytes > 0) {
          const size = root.querySelector<HTMLElement>("[data-release-size]");
          if (size) {
            size.textContent = `${(archive.size_bytes / 1_000_000).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} МБ · ${archive.size_bytes.toLocaleString("ru-RU")} байт`;
            root.querySelector<HTMLElement>("[data-release-size-row]")?.removeAttribute("hidden");
          }
        }
        if (typeof archive.sha256 === "string" && /^[a-f0-9]{64}$/i.test(archive.sha256)) {
          const hash = root.querySelector<HTMLElement>("[data-release-hash]");
          if (hash) {
            hash.textContent = archive.sha256.toLowerCase();
            root.querySelector<HTMLElement>("[data-release-hash-row]")?.removeAttribute("hidden");
          }
        }
      })
      .catch(() => { /* Keep the checksum/manifest links when metadata cannot load. */ })
      .finally(() => window.clearTimeout(releaseTimeout));

    const renderChangelog = (filter: "all" | ChangeType) => {
      if (!list) return;

      const visible = releases
        .map((release) => ({
          release,
          changes: filter === "all" ? release.changes : release.changes.filter((change) => change.type === filter),
        }))
        .filter((item) => item.changes.length > 0);

      if (!visible.length) {
        list.innerHTML = '<p class="empty-changelog">Для этой категории пока нет записей.</p>';
        return;
      }

      list.innerHTML = visible
        .map(({ release, changes }) => {
          const rows = changes
            .map(
              (change) =>
                '<li class="change-item type-' +
                escapeHtml(change.type) +
                '"><span class="change-label">' +
                escapeHtml(change.label) +
                '</span><p>' +
                escapeHtml(change.text) +
                "</p></li>",
            )
            .join("");

          return (
            '<article class="release-card"><header><div><h3>' +
            escapeHtml(release.version) +
            '</h3><span>' +
            escapeHtml(release.status) +
            '</span></div><time>' +
            escapeHtml(release.date) +
            "</time></header><ul>" +
            rows +
            "</ul><footer>◌ " +
            escapeHtml(release.compatibility) +
            "</footer></article>"
          );
        })
        .join("");
    };

    const setNavigationOpen = (isOpen: boolean) => {
      if (!navigation || !menuButton) return;
      navigation.classList.toggle("is-open", isOpen);
      menuButton.setAttribute("aria-expanded", String(isOpen));
      if (menuLabel) menuLabel.textContent = isOpen ? "Закрыть меню" : "Открыть меню";
      document.body.classList.toggle("menu-open", isOpen);
    };

    const closeNavigation = () => setNavigationOpen(false);

    const filterListeners = filters.map((button) => {
      const listener = () => {
        filters.forEach((other) => {
          other.classList.remove("active");
          other.setAttribute("aria-pressed", "false");
        });
        button.classList.add("active");
        button.setAttribute("aria-pressed", "true");
        const filter = button.dataset.filter;
        renderChangelog(filter === "added" || filter === "fixed" || filter === "security" ? filter : "all");
        if (changelogStatus) changelogStatus.textContent = `Фильтр истории изменений: ${button.textContent?.trim() ?? "Все"}.`;
      };
      button.addEventListener("click", listener);
      return [button, listener] as const;
    });

    const menuListener = () => {
      if (!navigation || !menuButton) return;
      setNavigationOpen(!navigation.classList.contains("is-open"));
    };
    menuButton?.addEventListener("click", menuListener);

    const navigationLinks = Array.from(navigation?.querySelectorAll<HTMLAnchorElement>("a") ?? []);
    navigationLinks.forEach((link) => link.addEventListener("click", closeNavigation));

    const updateHeader = () => header?.classList.toggle("is-scrolled", window.scrollY > 10);
    const onResize = () => {
      if (window.matchMedia("(min-width: 761px)").matches) closeNavigation();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && navigation?.classList.contains("is-open")) {
        const focusWasInNavigation = navigation.contains(document.activeElement);
        closeNavigation();
        if (focusWasInNavigation) menuButton?.focus();
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!navigation?.classList.contains("is-open") || !menuButton) return;
      const target = event.target as Node;
      if (!navigation.contains(target) && !menuButton.contains(target)) closeNavigation();
    };
    updateHeader();
    window.addEventListener("scroll", updateHeader, { passive: true });
    window.addEventListener("resize", onResize);
    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);

    let observer: IntersectionObserver | undefined;
    if ("IntersectionObserver" in window) {
      observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-visible");
              observer?.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.1, rootMargin: "0px 0px -24px" },
      );
      root.querySelectorAll<HTMLElement>(".reveal").forEach((element) => observer?.observe(element));
    } else {
      root.querySelectorAll<HTMLElement>(".reveal").forEach((element) => element.classList.add("is-visible"));
    }

    renderChangelog("all");

    return () => {
      releaseRequest.abort();
      window.clearTimeout(releaseTimeout);
      filterListeners.forEach(([button, listener]) => button.removeEventListener("click", listener));
      menuButton?.removeEventListener("click", menuListener);
      navigationLinks.forEach((link) => link.removeEventListener("click", closeNavigation));
      window.removeEventListener("scroll", updateHeader);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
      observer?.disconnect();
      document.documentElement.classList.remove("has-js");
      document.body.classList.remove("menu-open");
    };
  }, []);

  return <div ref={rootRef} dangerouslySetInnerHTML={{ __html: pageMarkup }} />;
}
