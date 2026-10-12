# NeAntik Win — public product site

Deployable Vinext / OpenAI Sites-приложение для публичного сайта NeAntik Win. Визуал, иконки и продуктовые документы остаются локальными: без Google Fonts, CDN и сторонних трекеров.

Это публичная копия исходников сайта. Hosting identity, Git-метаданные, токены,
кеши, `node_modules`, сборочные файлы и архивы приложения намеренно исключены.

## Структура

- `app/layout.tsx` — метаданные, manifest и подключение визуальной системы;
- `app/page.tsx` — публичная страница, версии и интерактивный changelog;
- `app/globals.css` + `public/assets/styles.css` — адаптивный дизайн и анимации с учётом `prefers-reduced-motion`;
- `public/assets/icons.svg`, `brand.svg`, `favicon.svg` — локальная айдентика и SVG-спрайт;
- `public/assets/nevision-hero-atmosphere.png` — оригинальная hero-иллюстрация;
- корневые `CHANGELOG.md`, `RELEASE_POLICY.md` — источники полной истории и правил; маршруты `app/CHANGELOG.md/route.ts` и `app/RELEASE_POLICY.md/route.ts` отдают их с явным `charset=utf-8`;
- Актуальный portable ZIP, SHA-256 и внешний manifest размещаются в GitHub Releases, а не в исходниках сайта;
- `public/release.json` — метаданные текущего проверенного архива; размер и SHA-256 на странице берутся из него;
- `.openai/hosting.json` — привязка OpenAI Hosting в рабочем приватном checkout; в этой публичной копии её нет;
- `docs/legacy-static-index.html` и `assets/` — исходный статический дизайн-архив, не являющийся entry point Vinext. В корне нет `index.html`, чтобы старый макет не подменял preview.

## Локальная проверка

```powershell
cd website
npm install
npm run dev
```

Для production-проверки используйте `npm run build`, затем `npm run start`. В output появятся `dist/client` и `dist/server`; это артефакты сборки, они не коммитятся.

## Публикация

Рабочий checkout OpenAI Sites использует сохранённый `.openai/hosting.json`, а Cloudflare-compatible edge output формирует Vinext. Публичная копия не содержит этот идентификатор и не предоставляет доступ к развёртыванию.

Перед тем как включать на странице прямую кнопку скачивания, сначала опубликуйте проверенный ZIP/EXE по стабильному URL. Не указывайте ссылку на локальный путь и не меняйте SHA-256 вручную.

## Как оформить следующий релиз

Следуйте [RELEASE_POLICY.md](RELEASE_POLICY.md). В один релизный PR/коммит обновляются:

1. `CHANGELOG.md`: полная запись с датой, совместимостью, ограничениями, SHA-256 и откатом.
2. `app/page.tsx`: краткая карточка на главной странице и её видимая версия.
3. Блок `#download` в `app/page.tsx`: требования, формат backup, статус подписи и инструкция обновления.
4. GitHub Release: неизменяемый versioned ZIP, его `.zip.sha256` и `.manifest.json`, полученные из проверенной сборки.
5. `public/release.json`: краткие метаданные этой сборки с реальным `archive.download_url`. Поля `version`, `archive.filename`, `archive.size_bytes` и `archive.sha256` должны совпадать с артефактом; не заполняйте их оценочными значениями.

Загрузка работает обычной ссылкой без JavaScript. Страница получает `/release.json` с
ограничением ожидания 5 секунд и показывает размер/hash только для совпадающей версии и имени
архива. Если JSON недоступен, прямые ссылки на ZIP, checksum и manifest остаются доступны.
Не выкладывайте новую страницу до публикации и проверки всех связанных файлов релиза.

Для этого цикла проверяется Windows 11 x64 build 26200. Windows 10 в этом цикле не
проверена; Chrome/Edge устанавливаются отдельно, EXE не подписан. История предыдущих
релизов сохраняется со своими датами и условиями совместимости.

Проверяйте, чтобы обещания сайта совпадали с фактическими возможностями сборки. В частности, NeAntik Win не позиционируется как средство обхода антифрода, банов или подмены fingerprint.
