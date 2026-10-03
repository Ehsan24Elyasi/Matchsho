# Frontend pilot implementation

The UI uses semantic HTML and browser ES modules. `js/app.js` composes one shell; `router.js` dispatches hash routes and rejects superseded responses. `api.js` owns same-origin `/api`, CSRF, single-flight refresh with Web Locks across tabs, and retry identity. `features/` contains student, questionnaire, auth and operator screens. User values become text nodes, never HTML.

## Development and production

- `npm ci && npm run build` produces only deployable pages and assets in `dist/`.
- Build output uses a SHA-256-derived `/assets/<version>/` namespace including modules, original fonts, images and image provenance. References in HTML, CSS and ES modules are rewritten together. HTML is revalidated by Nginx.
- `npm test` exercises routing, URL safety and quoted roster import.
- `npm run test:e2e` launches an isolated static server and browser contract tests.
- `BASE_URL=http://localhost:8088 MAILPIT_URL=http://localhost:8025 PILOT_ENV_FILE=../.env.pilot-test npm run test:e2e` adds the real PostgreSQL/Nginx/API/Mailpit journey. The supplied environment must be isolated test data. Fixtures are named `frontend-*` and never use production recipients.
- `API_TARGET=http://127.0.0.1:8000 npm run serve:test` optionally proxies a local backend for development. It is not a production server.

## Visual system and acceptance

The original landing composition uses isolated `landing.css` with the existing locally compiled `tailwind.css`: centered headline, rotating words, circular dorm pictures, emoji cards and dark footer. Dashboard and supporting pages share `styles.css`. Regular and bold fonts have separate original files. Controls are at least 44 px, focus is an amber 3 px outline, native inputs and FAQ remain focusable, and motion can pause or follow reduced-motion preferences. Layout acceptance widths: 360, 390, 768, 1280, 1440 px.

Landing performance fixture: Chromium, 390x844 or 1280x720, cold cache disabled using CDP, wait for `document.fonts.ready` and image decoding, sum navigation and resource encoded response body sizes. Maximum 600 KiB. The build also enforces a conservative raw-byte budget across HTML, CSS, initial script, both fonts and all landing images. Each logo must remain below 40 KiB and each avatar below 80 KiB. All meaningful content works before decorative scripting.

## Original project artwork

The original blue roof in `src/Matchsho.jpg` appears in every public page, the shared student/operator shell and browser icon. The source is a transparent PNG despite its historical extension. The restored landing uses original pictures1,2,3,4,5,7 in its original circle composition; the authentication introduction uses `src/4.jpg`. Prepared avatar illustrations and picture6 remain available in the bundle; real profile cards use initials. Original `IRANYekanXFaNum-Regular.woff2` and `IRANYekanXFaNum-Bold.woff2` bytes are copied unchanged. No original file is modified.

`assets/original-brand/manifest.json` records source and output SHA-256 hashes, byte counts, dimensions and encoder versions. The normal `npm run build` verifies these hashes and budgets before shipping the prepared images; it requires no image package. All small JPEG illustrations are copied byte for byte. The logo removes its nearly transparent outside padding, then downsizes to 192 pixels and uses lossless WebP. The avatars downsize to 192 pixels with WebP quality 88, preserving alpha.

To deliberately regenerate prepared artwork, use Sharp 0.35.4 with libvips 8.18.6 and WebP 1.6.0, then run `node scripts/prepare-brand-assets.mjs` followed by `npm run build`. Sharp is an optional authoring dependency, not a runtime or default build dependency. If it lives outside this project, set `MATCHSHO_SHARP_PATH` to its absolute package directory. The script rejects other encoder versions so regeneration stays reproducible. Review both images and provenance changes together.

Questionnaire drafts persist only through the authenticated server endpoint; no raw response enters localStorage or URL state. The only localStorage value is a timestamp coordinating refresh-token rotation. Mutations remain disabled while pending. Failed resource reads are distinct from successful empty states; a 409 prompts authoritative refresh.

Privacy retention values and institution support policy require institution sign-off before production. Generated tests prove UI and integration behavior; they do not substitute for that operational approval.
