مبنای اجرا `design.md` و هشت فایل `specs/*/spec.md` همین تغییر است. شمارهٔ «ممیزی» در جدول پایانی به یافته‌های بررسی ۲۰۲۶-۱۰-۰۲ اشاره دارد. هر checkbox فقط پس از پیاده‌سازی و شاهد مربوط تیک بخورد؛ آیتم‌های محیط واقعی بدون اجرای واقعی کامل محسوب نمی‌شوند. وضعیت زیر بر اساس اجرای محلی به‌روز شده است. دستورهای آزمون در `README.md` و workflow مربوط به CI هستند؛ شواهد نسخه در `artifacts/pilot/evidence/` تولید می‌شوند و از Git خارج‌اند. گزارش‌های قبلی برای سابقه بیرون ریپو بایگانی شده‌اند. موارد راه‌اندازی واقعی در بخش ۱۴ باز می‌مانند.

## 1. خط مبنا و محیط بررسی

- [x] 1.1 وضعیت working tree، نسخه‌های runtime، schema و تست فعلی را ثبت و snapshot قابل‌بازگشت از کار موجود تهیه کن؛ هیچ تغییر قبلی کاربر revert نشود.
- [x] 1.2 fixture مستقل از دادهٔ اصلی برای roster، دو pool، یک cycle، کاربران، گروه‌های ناقص/پر/تخصیص‌یافته و ناسازگاری‌های legacy بساز؛ همهٔ تست‌ها target مجزا و guard عدم استفاده از DB واقعی داشته باشند.
- [x] 1.3 harness PostgreSQL 16 با connectionهای مستقل، barrier و timeout برای بازتولید رقابت‌ها اضافه کن؛ regressionهای privacy، accept/cancel، overcapacity و API Compose قبل از رفع قابل‌شکست باشند.
- [x] 1.4 router/schema/serviceهای backend و moduleهای api/session/router/UI فرانت را استخراج کن؛ رفتار پوشش‌داده‌شدهٔ قبلی حفظ و وابستگی circular یا commit پنهان در helperها حذف شود.
- [x] 1.5 محل شواهد `docs/pilot/` و `artifacts/pilot/`، نام‌گذاری بر اساس release و الگوی ثبت دستور/محیط/نتیجه را تعریف کن؛ secrets و دادهٔ واقعی در Git ثبت نشوند.

## 2. مدل داده و migration افزایشی

- [x] 2.1 مدل و revision جدید برای auth_version، session پایدار و bucket محدودسازی با index/expiry اضافه کن؛ JWT legacy پس از cutover قابل‌پذیرش نباشد.
- [x] 2.2 مدل Enrollment، claim intent، pool و active cycle با uniqueness و conflictهای import اضافه کن؛ حساب یا اتاق ناقص به‌صورت پیش‌فرض eligible نشود.
- [x] 2.3 schema نسخه‌دار questionnaire/submission/draft/consent و revisionها را اضافه کن؛ v1 بدون تبدیل معنا privately حفظ شود.
- [x] 2.4 مدل invitation/admission، approval snapshot، membership revision، expiry، idempotency و active uniqueness را اضافه کن؛ state constraintهای DB با تمام وضعیت‌های جدید منطبق شوند.
- [x] 2.5 مدل departure، block/report/correction، closure و تاریخچهٔ append-only عملیاتی را اضافه کن؛ audit قبل/بعد فاقد پاسخ خام و secret باشد.
- [x] 2.6 مدل notification، outbox رمز‌شده و lease/dedup/retention را اضافه کن؛ indexهای polling و unread/read متناسب باشند.
- [x] 2.7 ابزار preflight فقط خواندنی برای duplicate membership، چندگروهی‌بودن اتاق، overcapacity، occupancy mismatch و pool/roster conflicts بساز؛ گزارش actionable و ممنوعیت اصلاح مخرب خودکار آزموده شود.
- [x] 2.8 migration را روی DB خالی و fixture نسخهٔ فعلی اجرا و Alembic/model drift را بررسی کن؛ دعوت‌های legacy با policy_upgrade بسته، گروه‌ها/تخصیص‌ها حفظ و revision قبلی ویرایش نشود.

## 3. امنیت هویت و نشست

- [x] 3.1 صدور/اعتبارسنجی access و refresh با sid/auth_version و DB session را اجرا کن؛ cookie/CSRF/no-store و role جاری از DB حفظ شوند.
- [x] 3.2 logout، reset و suspension را با ابطال اتمیک و ترتیب قفل user سپس session/token اجرا کن؛ login درحال‌اجرا نتواند credential قدیمی را بعد از reset معتبر کند.
- [x] 3.3 rotation/replay refresh، سقف مطلق هفت‌روزه و مدیریت فهرست/لغو نشست‌های خود کاربر را اجرا کن؛ replay همان session را ببندد و یک refresh branch بیشتر معتبر نماند.
- [x] 3.4 limiter اتمیک PostgreSQL، کلید HMAC، cleanup و quota مستقل از rollback تجاری را پیاده کن؛ defaultها مطابق identity spec و ورود موفق حساب دیگر بی‌اثر بر quota باشند.
- [x] 3.5 محدودسازی پیش از hashing/claim/ایمیل و مصرف token دعوت را اعمال کن؛ خطای ذخیره‌ساز 503، حد مصرف 429/Retry-After و پاسخ عمومی بدون enumeration باشد.
- [x] 3.6 تست race reset/login/refresh، دوبار مصرف token، copied access پس از logout/reset، دو worker limiter و onboarding پنجاه کاربر پشت یک NAT را اجرا کن.
- [x] 3.7 logهای auth و audit را از token/password/cookie/link پاک کن و روش دسترسی به actor/session reference امن را تست کن؛ مسیرهای قدیمی نیز همین کنترل‌ها را اعمال کنند.

## 4. پذیرش دانشجو و حریم خصوصی

- [x] 4.1 import فهرست مجاز با preview، خطای ردیفی، conflict review و reason بساز؛ ایمیل/شناسهٔ claimed بدون بررسی overwrite نشود.
- [x] 4.2 ثبت intent، دعوت به ایمیل فهرست و تعیین credential توسط گیرنده را اجرا کن؛ دانستن شماره/ایمیل و انتخاب رمز توسط مهاجم به account takeover منجر نشود.
- [x] 4.3 policy مشترک و purpose-aware برای account/enrollment/cycle/pool/block/consent تعریف کن؛ discovery/admission از مشاهدهٔ امن گروه جاری و تاریخچهٔ مجاز تفکیک شوند.
- [x] 4.4 DTOهای owner/peer/operator را صریح کن؛ پاسخ خام، ایمیل و student_id از تمام profile/match/request/group/notificationهای peer حذف و arbitrary pair-score محدود/حذف شود.
- [x] 4.5 consent جدا برای discovery و توضیح دسته‌ای با version و withdrawal اجرا کن؛ دلیل گروه رضایت candidate و تمام اعضای مشارکت‌کننده را لازم داشته باشد و موضوع حساس هیچ‌گاه نام برده نشود.
- [x] 4.6 اصلاح display fields توسط owner و اصلاح identity/email/pool/cycle توسط اپراتور با preview، reason و verification ایمیل جدید را اجرا کن.
- [x] 4.7 block دوطرفه، لغو دعوت‌های باز با reason عمومی و report خصوصی با صف triage، محدودسازی و سقف متن اجرا کن؛ هیچ گزارش/بلاکی خودکار تخت فرد را آزاد نکند.
- [x] 4.8 درخواست deactivation/deletion، acknowledgement قبل از revoke، pending-exit فرد تخصیص‌یافته و purge پس از خروج عملیاتی را اجرا کن؛ claim مجدد خودکار حساب بسته ممنوع باشد.
- [x] 4.9 job نگهداری audit از ایجاد/تاریخچه از closure تا۹۰روز، report از ایجاد تا۳۰روز، receipt تا۳۰روز و deletion ledger قابل‌اعمال پس از restore بساز؛ notice و پیکربندی با رفتار واقعی برابر باشند.
- [x] 4.10 ماتریس دسترسی unrelated/pending/accepted/same-group/assigned/blocked/owner/operator را تست کن؛ JSON و HTML و export نباید مرز حریم خصوصی را دور بزنند.

## 5. پرسشنامه و مچ قابل‌استفاده

- [x] 5.1 schema v2 برای رفتار، accepted set/range، importance و hard requirement را با labelهای روشن فارسی تعریف کن؛ ساعات ۱۵دقیقه‌ای، بازهٔ نیمه‌شب، عدم پاسخ اختیاری دخانیات و حذف اعتقادات اعتبارسنجی شوند.
- [x] 5.2 owner draft و submission اتمیک نسخه‌دار را اجرا کن؛ incomplete draft روی matching منتشرشده اثر نگذارد و schema نامنطبق به کاربر برای بازبینی برگردد.
- [x] 5.3 شروط قطعی دوطرفه و امتیاز directed-weight با round-half-up را پیاده کن؛ unknown شرط سخت را پاس نکند و رفتار واقعی از میزان اهمیت جدا بماند.
- [x] 5.4 scorer گروه با حداقل امتیاز جفت‌ها، رد گروه دارای عضو inactive/pending-closure و ظرفیت مشترک صریح را پیاده کن؛ ادغام گروه یا ظرفیت حدسی مجاز نباشد.
- [x] 5.5 discovery را قبل از limit به افراد/گروه‌های قابل‌پیوستن محدود کن؛ sort پایدار، pagination، matching page حداکثر۵۰ و queryهای کنترل‌شده داشته باشد.
- [x] 5.6 توضیح عمومی و allowlist غیرحساس را مطابق consent بساز؛ score version و عنوان «هم‌خوانی ترجیحات» برگردد و private failure reason افشا نشود.
- [x] 5.7 سناریوهای خواب متفاوت با اهمیت برابر، نیمه‌شب، optional unknown، hard conflict، ظرفیت نامشترک، گروه پر/assigned/blocked و تغییر revision را تست کن.

## 6. چرخهٔ اتمیک دعوت و گروه

- [x] 6.1 service واحد transaction/lock را مطابق design با قفل تراکنشی مشترک دامنه در پایلوت و بازخوانی بعد از قفل اجرا کن؛ مجوز و دادهٔ تصمیم پس از انتظار تازه خوانده شوند و از ORM cache قدیمی تصمیم گرفته نشود.
- [x] 6.2 تشکیل گروه دو نفر solo با ظرفیت موردتوافق و active invitation uniqueness اجرا کن؛ تغییر وضعیت یکی از نفرات، دعوت قبلی را به پذیرش ضمنی گروه تبدیل نکند.
- [x] 6.3 proposal پیوستن یک candidate و approval تک‌تک اعضای جاری را بساز؛ عضویت تا تکمیل رضایت snapshot جاری ایجاد نشود و group-to-group merge مسدود باشد.
- [x] 6.4 invalidation بر اثر membership/answer/consent/capacity revision و UI/API reconfirmation را پیاده کن؛ مهلت هفت‌روزه با reconfirmation تمدید نشود.
- [x] 6.5 transitionهای accept/reject/cancel/expire را single-winner و تکرار همان terminal action را idempotent کن؛ terminal رقیب 409 و بدون side effect باشد.
- [x] 6.6 حفظ دعوت‌های مستقلِ معتبر، بستن موارد ناممکن با system reason و کنترل انقضا در read/action/worker را اجرا کن؛ invalidation هرگز rejection انسانی معرفی نشود.
- [x] 6.7 خروج گروه تخصیص‌نیافته، حفظ سایر اعضا، پاک‌کردن گروه خالی و تبدیل خروج assigned به departure request را اجرا کن.
- [x] 6.8 notificationهای داخل‌برنامه و outbox ترجیحی را در همان transaction هر رویداد ثبت کن؛ retry شبکه duplicate membership یا notification نسازد.
- [x] 6.9 تست PostgreSQL با connectionهای مستقل برای آخرین ظرفیت، accept/cancel/reject، تغییر questionnaire/عضویت و accept/allocate را اجرا کن؛ committed state و occupancy را از DB تازه assert کن.

## 7. تخصیص اتاق و خروج فرد

- [x] 7.1 assign/move/unassign را فقط به مدیر بده و مسیر self-service قدیمی آزادسازی کل گروه را حذف/رد کن؛ کنترل نقش فقط UI نباشد.
- [x] 7.2 eligibility تمام اعضا، pool/cycle، برابر بودن ظرفیت فیزیکی با target و یک گروه در هر اتاق جدید را زیر قفل اتاق enforce کن؛ چندگروهی legacy فقط flag شود.
- [x] 7.3 occupancy را از همهٔ عضویت‌های جاری، مستقل از فعال/معلق‌بودن حساب، محاسبه و cache را transactionally نگه دار؛ suspend تخت را آزاد نکند.
- [x] 7.4 move اتمیک زیر قفل تراکنشی مشترک دامنه، تغییر capacity امن و retry/idempotency مناسب اجرا کن؛ شکست مقصد تخصیص مبدأ را حفظ کند.
- [x] 7.5 approve/reject departure فردی و حذف با دلیل مدیر را اجرا کن؛ دقیقاً یک ظرفیت آزاد، سایرین حفظ و آخرین عضو تخصیص/گروه خالی را ببندد.
- [x] 7.6 audit قبل/بعد، notification افراد متأثر، reconciliation اپراتوری و history را اجرا کن؛ عملیات راه پشتی برای دورزدن ظرفیت/eligibility نداشته باشند.
- [x] 7.7 تست رقابت تخصیص، خروج/تخصیص، move، capacity edit و تکرار approve را اجرا کن؛ یک گروه در اتاق جدید، حفظ گروه legacy و عدم آزادسازی با suspension بررسی شوند.

## 8. ایمیل پایدار و نگهداری worker

- [x] 8.1 enqueue اتمیک business event و EmailOutbox، dedup key و envelope رمز‌شده با key مستقل/version اضافه کن؛ metadata و token table لینک plaintext نگیرند.
- [x] 8.2 worker claim با SKIP LOCKED، lease محدود و commit پیش از SMTP بساز؛ کار شبکه داخل transaction تجاری اجرا نشود.
- [x] 8.3 retry با شش تلاش، backoff۳۰ثانیه تا۱۵دقیقه، expiry/supersession/recipient binding و cancellation ایمیل قدیمی را اجرا کن.
- [x] 8.4 Message-ID ثابت، semantics at-least-once، erasure payload نهایی و rotation کلیدهای دارای پیام queued را پیاده/مستند کن.
- [x] 8.5 tooling مدیر برای delivery status و retry مجاز بدون دسترسی به credential، heartbeat/lag/failure و cleanup bucket/expiry/retention را فراهم کن.
- [x] 8.6 mail capture محلی را از همان مسیر worker وصل و تست دو worker، crash قبل/بعد ارسال، SMTP قطع، token مصرف‌شده و retry exhaustion را اجرا کن.

## 9. تجربهٔ دانشجو و ظاهر

- [x] 9.1 tokenهای طراحی و اجزای مشترک فارسی/RTL را بساز؛ mapping regular/bold، فاصله، focus، contrast و نمایش رشته‌های mixed-direction درست باشد.
- [x] 9.2 لندینگ و منوی موبایل را اصلاح و splash اجباری حذف کن؛ عنوان/CTA در 1280×720 و390×844 در نمای اول و محتوا با شکست script تزئینی قابل‌استفاده باشد.
- [x] 9.3 shell و navigation مشترک و router entity-idدار بساز؛ refresh/back/forward پروفایل و active tab درست و هر feature resource در انتقال عادی یک‌بار خوانده شود.
- [x] 9.4 API/session module را با single-flight و هماهنگی refresh میان tabها، لغو پاسخ stale و stateهای مجزای 401/403/404/409/429/network/5xx تکمیل کن.
- [x] 9.5 UI دعوت/فعال‌سازی/ورود/بازیابی و مدیریت نشست‌های خود کاربر را با پیام queued و خطای قابل‌فهم اجرا کن؛ password در فرم عمومی claim فعال نشود.
- [x] 9.6 UI پرسشنامه با label معنایی، progress، prefill، draft save/resume و invalid schema review بساز؛ پاسخ خام در localStorage، URL یا telemetry نوشته نشود.
- [x] 9.7 مچ‌ها و پروفایل را با grid responsive، avatar سبک، score/consent و eligibility جاری بساز؛ توضیح حساس یا اطلاعات خصوصی نمایش داده نشود.
- [x] 9.8 صفحات دعوت/رأی/گروه/اتاق و خروج فرد را با snapshot افراد، ظرفیت، expiry، reconfirmation و اثر عمل پیاده کن؛ موفقیت فقط پس از نتیجهٔ قطعی اعلام شود.
- [x] 9.9 صفحات notification/unread، اصلاح حساب، privacy consent، report/block و withdrawal/support را بساز؛ لینک اعلان وضعیت جاری مجاز را باز کند و mark-read اقدام کسب‌وکار انجام ندهد.
- [x] 9.10 radio/کارت/دیالوگ را keyboard-accessible، focus و live-region را قابل‌اتکا و reduced-motion را مؤثر کن؛ keyboard-only مسیر اصلی بدون mouse کامل شود.
- [x] 9.11 تمام rendering دادهٔ غیرقابل‌اعتماد را به DOM APIهای context-safe منتقل کن؛ آزمون payload کوتیشن/HTML/URL بدون اتکا به CSP inert بماند.
- [x] 9.12 assetها را فشرده و dimension/lazy-loading تنظیم کن؛ report cold load<=600KiB، logo<=40KiB وavatar<=80KiB برای هر دو viewport ثبت شود.

## 10. پنل عملیاتی مدیر

- [x] 10.1 جست‌وجو و pagination دانشجو/roster و صف claim/correction را بساز؛ دادهٔ حساس عملیاتی فقط با مجوز و audit نمایش داده شود.
- [x] 10.2 نمای گروه/دعوت و eligibility آمادهٔ تخصیص با خطاهای روشن و snapshot جاری بساز؛ فهرست‌ها به کل جدول نامحدود وابسته نباشند.
- [x] 10.3 فرم assign/move/unassign/capacity-policy را با preview افراد و ظرفیت، reason اجباری و conflict refresh اجرا کن.
- [x] 10.4 صف departure/closure و report/support را با تصمیم ثبت‌شده و اطلاع‌رسانی نتیجه پیاده کن؛ اپراتور بدون SQL جریان را تکمیل کند.
- [x] 10.5 history و خروجی CSV مجاز با حداقل داده و جلوگیری از formula injection بساز؛ questionnaire/secret قابل‌export نباشد.
- [x] 10.6 پنل delivery health و retry امن را متصل و عملیات تأییدشدهٔ مدیر را در مرورگر با نقش کاربر عادی نیز منفی تست کن.

## 11. قرارداد استقرار و پیکربندی

- [x] 11.1 API پیش‌فرض same-origin `/api` و override صریح development را اجرا کن؛ Nginx prefix/cookie/CSRF/CSP/CORS با Compose و production هماهنگ شوند.
- [x] 11.2 مرز public edge/ingress/Nginx/Uvicorn و trusted peers را پیکربندی کن؛ wildcard trust حذف و headerهای ورودی بازنویسی شوند، spoof test روی مسیر منتشرشده پاس شود.
- [x] 11.3 effective DB URL و verify-full/CA را اعتبارسنجی کن؛ sslmode=disable/allow/prefer/require بدون identity verification در production رد و استثنای local فقط development باشد.
- [x] 11.4 liveness مستقل و readiness وابسته به DB+schema سازگار بساز؛ SELECT1 با schema ناقص آماده گزارش نشود و outage ایمیل API را بی‌دلیل unready نکند.
- [x] 11.5 migration service/command با advisory lock و worker مجزا در Compose و release-specific Job در Kubernetes تعریف کن؛ API replica migration را در startup تکرار نکند.
- [x] 11.6 build فرانت با fingerprint و cache immutable برای asset/ revalidate برای HTML ایجاد کن؛ دو release پی‌درپی با JS قدیمی ناسازگار اجرا نشوند.
- [x] 11.7 dependency lock/hash، image digest، env example بدون secret و اجرای non-root/read-only لازم را یکپارچه کن؛ نسخهٔ schema و برنامه در release record ثبت شوند.

## 12. آزمون و CI مانع انتشار معیوب

- [x] 12.1 CI Python3.11/PostgreSQL16 را برای unit/service، migration و testهای رقابتی مستقل فعال کن؛ SQLite شاهد صحت قفل محسوب نشود.
- [x] 12.2 ماتریس security/privacy و revocation/limiter/proxy/outbox را در CI اجباری کن؛ هر regression ممیزی از مسیر فعلی و legacy بررسی شود.
- [x] 12.3 Playwright را روی imageهای ساخته‌شده پشت Nginx واقعی با DB/mail sink disposable اجرا کن؛ claim تا questionnaire، دعوت/رضایت، تخصیص و departure بدون SQL دستی کامل شود.
- [x] 12.4 تست geometry و keyboard/RTL در عرض‌های360/390/768/1280/1440، deep link/history، error/retry، empty، duplicate-fetch و stale-response را اضافه کن؛ trace و تصویر failure نگهداری شود.
- [x] 12.5 scan dependency، usable secrets و container image را همراه lint/static checks اجباری کن؛ high/critical قابل‌اعمال و secret مصرف‌شدنی release را متوقف کنند.
- [x] 12.6 سناریوی release ناسازگار، migration failure و rollback سازگار را در staging-like stack تمرین کن؛ rollback به نسخهٔ افشاگر/فاقد session guard مجاز نباشد.
- [ ] 12.7 workload پنجاه session/ده‌دقیقه و fixture ثبت‌شده را اجرا کن؛ p95 read/match<=500ms وwrite<=1s، 5xx<=1٪ وzero invariant violation، auth/SMTP جداگانه گزارش شوند.
- [x] 12.8 pagination bounded حداکثر۱۰۰ برای فهرست‌ها، matching<=50، query-count و N+1 را با دادهٔ اندازهٔ پایلوت بررسی کن؛ تنها در صورت شکست شاخص، query/index را اصلاح کن.

## 13. ابزار و راهنمای بهره‌برداری

- [x] 13.1 log ساخت‌یافته/request ID، metrics latency/5xx/conflict/limiter و worker/outbox را پیاده و حفظ حریم خصوصی log را verify کن.
- [x] 13.2 alertهای readiness/worker loss/queued mail>5min/terminal mail/backup failure را با runbook owner و دستور آزمون هشدار آماده کن.
- [x] 13.3 backup روزانهٔ رمز‌شده بیرون host با retention۳۰روز و guard مقصد restore مجزا بساز؛ worker/email در محیط restore تا تأیید خاموش بماند.
- [x] 13.4 restore harness شامل اعمال deletion ledger، schema، invariantها و smoke امن نقش‌ها را بساز؛ RPO24h/RTO4h و drill ماهانه در runbook ثبت شوند.
- [x] 13.5 راهنمای اپراتور برای roster/correction/eligibility، report، دعوت/گروه، تخصیص/خروج و ایمیل تهیه کن؛ اقدامات عادی به SQL مستقیم نیاز نداشته باشند.
- [x] 13.6 release/maintenance/expand-migrate-contract/rollback و reconciliation داده را با دستورهای قابل‌اجرا و محدودهٔ سازگاری بنویس؛ downgrade مخرب خودکار حذف شود.
- [x] 13.7 README، privacy/about و متن‌های محصول را با دادهٔ واقعی قابل‌نمایش، معنای score، queued email و نقش مدیر هماهنگ کن؛ ادعای تکمیل عملیات بدون شاهد حذف شود.

## 14. پذیرش staging و راه‌اندازی پایلوت

- [x] 14.1 همهٔ ۳۰ ردیف نگاشت زیر را با commit/test/evidence مربوط پر کن؛ مورد ناتمام صریحاً باز و ریسک شدید حل‌نشده مانع release باشد.
- [ ] 14.2 روی host هدف، schema/image/asset نسخه‌دار و HTTPS/cookie/DB CA/trusted proxy واقعی را ثبت و smoke امنیتی اجرا کن؛ fixture به‌جای این شاهد قبول نشود.
- [ ] 14.3 دعوت/verification/reset واقعی را تا دریافت و مصرف توسط صندوق آزمون تأیید و alert آزمایشی را در مقصد اپراتور دریافت کن؛ نتیجه و timestamp ثبت شوند.
- [ ] 14.4 backup واقعی را در DB جدا restore و deletion ledger، invariant و smoke را اجرا کن؛ backup age<=24h و زمان بازیابی<=4h را اندازه بگیر و rollback staging را ثبت کن.
- [ ] 14.5 مؤسسه، cycle/pool، roster، قواعد تخصیص، retention/notice، اپراتور و پشتیبانی را با مسئول پایلوت نهایی کن؛ نتیجهٔ walkthrough دانشجو/مدیر بدون راهنمایی فنی ثبت شود.
- [ ] 14.6 فقط پس از تکمیل شواهد الزامی، release record cohort محدود پیشنهادی۲۰تا۵۰ نفر، زمان شروع، owner، معیار توقف و مسیر rollback را تأیید کند؛ صرف پایان کدنویسی این checkbox را کامل نمی‌کند.

## 15. نگاشت ممیزی به کار و شاهد اتمام

این جدول task جدید نیست؛ برای هر ردیف باید پیاده‌سازی و شاهد موارد ارجاع‌داده‌شده در release record موجود باشد.

| ممیزی | ایراد اولیه | کارهای پوشش‌دهنده | شاهد مورد انتظار |
|---|---|---|---|
| 1 | پاسخ خام و شماره دانشجویی در peer | 4.4–4.5،4.10 | ماتریس پاسخ JSON/HTML چهار رابطه بدون دادهٔ خصوصی |
| 2 | overcapacity و occupancy کهنه | 6.1،6.9،7.3،7.7 | رقابت PostgreSQL آخرین ظرفیت و accept/allocate |
| 3 | accept/cancel/reject متناقض | 6.5،6.9 | تنها یک outcome نهایی و membership منطبق |
| 4 | پاک‌شدن quota با login دیگر | 3.4–3.6 | حساب A محدودیت B/IP را صفر نکند |
| 5 | جعل IP proxy | 11.2،12.2 | درخواست با XFF جعلی از public edge |
| 6 | access معتبر بعد reset/logout | 3.1–3.3،3.6 | copied token و race reset/login/refresh رد شوند |
| 7 | ثبت‌نام بدون محدودیت | 3.4–3.6،4.2 | pre-hash limit و onboarding NAT قابل‌استفاده |
| 8 | API نامنطبق Compose | 11.1،12.3 | activation/login/mutation از frontend port |
| 9 | مچ براساس اهمیت به‌جای رفتار | 5.1،5.3،5.7 | مثال خواب واقعی نامنطبق و score قابل‌بازتولید |
| 10 | پیشنهاد فرد غیرقابل‌پیوستن | 4.3،5.4–5.5 | full/assigned/blocked حذف و پذیرش دوباره بررسی شود |
| 11 | نبود قواعد eligibility اتاق | 2.2،7.2،7.7 | pool/cycle/room-size نامنطبق رد شود |
| 12 | خروج یک فرد اتاق همه را آزاد می‌کند | 7.1،7.5،7.7 | خروج یک نفر، حفظ جای سایرین |
| 13 | قواعد ناقص گروه چندنفره | 6.2–6.6 | unanimous revision-bound consent و حفظ دعوت مستقل |
| 14 | نبود workflow حساب/مزاحمت/پشتیبانی | 4.6–4.9،9.9،10.4 | گردش کار owner/operator با reference و نتیجه |
| 15 | منوی موبایل/hero خراب | 9.2،12.4 | geometry در دو viewport و toggle واقعی |
| 16 | تایپوگرافی و چیدمان ناهماهنگ | 9.1،9.7،12.4 | وزن فونت، grid و RTL در عرض‌های پذیرش |
| 17 | پرسشنامه بدون معنی/prefill | 5.1–5.2،9.6 | label/prefill/draft refresh و schema review |
| 18 | keyboard غیرقابل‌استفاده | 9.10،12.4 | سفر کامل keyboard و focus/announcement |
| 19 | پروفایل خالی پس از refresh | 9.3،12.4 | entity route refresh/back/forward |
| 20 | خطا به‌شکل empty | 9.4،12.4 | 5xx/timeout گروه/درخواست به‌صورت failure |
| 21 | fetch تکراری و active nav اشتباه | 9.3–9.4،12.4 | یک load در route و navigation مشترک |
| 22 | asset سنگین و splash/motion | 9.2،9.12،12.4 | گزارش بودجهٔ۶۰۰/۴۰/۸۰KiB و reduced-motion |
| 23 | پنل مدیر ناکافی | 10.1–10.6،13.5 | اپراتور بدون SQL مشکل را حل کند |
| 24 | کد monolithic | 1.4،12.1 | ماژول‌های قابل‌آزمون و سیاست واحد |
| 25 | escaping نامناسب attribute | 9.11،12.2 | payload inert بدون اتکا به CSP |
| 26 | bypass sslmode validation | 11.3،12.2 | URL واقعی نامعتبر/CA اشتباه رد شود |
| 27 | ایمیل غیرپایدار | 8.1–8.6،14.3 | crash/retry/دوworker و تحویل واقعی |
| 28 | تست‌های ناکافی برای stack | 12.1–12.6 | PG concurrency و مرورگر پشت Nginx در CI |
| 29 | عملیات/readiness/cache/migration نامطمئن | 11.4–11.7،13.1–13.6،14.2–14.4 | دوrelease، schema خراب، alert،restore،rollback |
| 30 | پردازش/لیست نامحدود | 5.5،12.7–12.8 | pagination/query/load report ثبت‌شده |
