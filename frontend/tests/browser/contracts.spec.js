import { test, expect } from "@playwright/test";
const owner = {
  id: 1,
  name: "سارا رضایی",
  class_name: "مهندسی کامپیوتر",
  student_id: "1405001",
  email: "sara@example.test",
  role: "student",
  discovery_consent: true,
  explanation_consent: false,
  notification_email: true,
  eligibility: { status: "eligible", pool: "female", cycle: "1405" },
};
const normal = {
  id: 2,
  name: "نگار محمدی",
  class_name: "معماری",
  score: 82,
  explanations: [],
  capacities: [2, 4],
  can_invite: true,
  group: null,
};
const dimensions = [
  {
    key: "sleep",
    label: "زمان خواب",
    kind: "time",
    required: true,
    options: [],
  },
  {
    key: "wake",
    label: "زمان بیداری",
    kind: "time",
    required: true,
    options: [],
  },
  ...["cleaning", "guests", "noise"].map((key) => ({
    key,
    label: key,
    kind: "choice",
    required: true,
    options: [
      { value: "a", label: "انتخاب اول" },
      { value: "b", label: "انتخاب دوم" },
    ],
  })),
  {
    key: "tobacco",
    label: "دخانیات اختیاری",
    kind: "choice",
    required: false,
    options: [{ value: "never", label: "مصرف نمی‌کنم" }],
  },
];
async function fixture(page, overrides = {}) {
  const calls = [];
  let draft = { version: 2, answers: {}, capacities: [] };
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.slice(4);
    const method = route.request().method();
    calls.push({ path, method, body: route.request().postDataJSON() });
    if (overrides[path]) {
      const value = await overrides[path](route);
      if (value === undefined) return;
      await route.fulfill({
        status: value.status || 200,
        contentType: "application/json",
        body: JSON.stringify(value.data ?? value),
      });
      return;
    }
    let data = {};
    if (path === "/auth/me") data = owner;
    else if (path === "/auth/csrf") data = { csrf_token: "test-token" };
    else if (path === "/pilot/config")
      data = { institution_name: "خوابگاه آزمایشی", active_cycle: "1405" };
    else if (path === "/matches")
      data = {
        items: [
          {
            kind: "user",
            id: 2,
            user: normal,
            score: 82,
            capacities: [2, 4],
            can_invite: true,
            explanations: [],
          },
        ],
        total: 1,
        page: 1,
        limit: 12,
      };
    else if (path === "/profiles/2") data = normal;
    else if (path === "/profiles/3")
      data = { ...normal, id: 3, name: "مهسا احمدی" };
    else if (path === "/questionnaire/schema")
      data = { version: 2, dimensions, capacities: [2, 4] };
    else if (path === "/questionnaire/me")
      data = { version: 2, complete: false, answers: {}, capacities: [] };
    else if (path === "/questionnaire/draft") {
      if (method === "PUT") draft = route.request().postDataJSON();
      data = draft;
    } else if (path === "/group/me") {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: '{"detail":"no group"}',
      });
      return;
    } else if (path === "/requests" || path === "/notifications")
      data = { items: [], total: 0, page: 1, limit: 12 };
    else if (
      path === "/auth/sessions" ||
      path === "/me/blocks" ||
      path === "/me/cases"
    )
      data = { items: [] };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  return calls;
}
for (const width of [360, 390, 768, 1280, 1440])
  test(`landing first paint and horizontal bounds ${width}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: width < 768 ? 844 : 720 });
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    const title = await page.locator(".hero h1").boundingBox();
    const cta = await page
      .locator(".hero-actions .button")
      .first()
      .boundingBox();
    expect(title.y + title.height).toBeLessThan(width < 768 ? 844 : 720);
    expect(cta.y + cta.height).toBeLessThan(width < 768 ? 844 : 720);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    if (width >= 768) await expect(page.locator(".menu-toggle")).toBeHidden();
  });
test("mobile navigation opens with keyboard, closes on Escape and restores focus", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const toggle = page.getByRole("button", { name: "منو" });
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toBeFocused();
});
test("original landing remains usable without decoration scripts", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  try {
    const page = await context.newPage();
    await page.goto(process.env.BASE_URL || "http://127.0.0.1:4173");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("یه هم‌اتاقی می‌خوای؟");
    await expect(page.locator(".hero-actions .button")).toHaveAttribute("href", "/dashboard/index_dashboard.html#register");
    const question = page.locator(".faq-item summary").first();
    await question.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator("#faq-answer-1")).toBeVisible();
    await expect(page.locator("#splash")).toHaveCount(0);
  } finally {
    await context.close();
  }
});
test("original word animation can pause and respects reduced motion", async ({ page }) => {
  await page.goto("/");
  const control = page.locator("#motion-toggle");
  await expect(control).toHaveText("توقف حرکت");
  await control.click();
  const pausedWord = await page.locator("#rotator .word.active").textContent();
  await page.waitForTimeout(2200);
  expect(await page.locator("#rotator .word.active").textContent()).toBe(pausedWord);
  await expect(control).toHaveAttribute("aria-pressed", "true");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator("#motion-toggle")).toBeHidden();
  await expect(page.locator("#rotator .word.active")).toHaveCount(1);
  await expect(page.locator("#rotator .word.pos1")).toHaveCount(0);
});
for (const budgetWidth of [390,1280]) test(`cold landing resource budget including fonts at ${budgetWidth}`, async ({
  page,
}) => {
  await page.setViewportSize({width:budgetWidth,height:budgetWidth===390?844:720});
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  await page.goto("/", { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  const resources = await page.evaluate(() =>
    performance
      .getEntriesByType("resource")
      .map((r) => ({ name: r.name, encoded: r.encodedBodySize })),
  );
  const navigation = await page.evaluate(
    () => performance.getEntriesByType("navigation")[0].encodedBodySize,
  );
  await test
    .info()
    .attach("landing-resource-size-report", {
      body: JSON.stringify(
        {
          viewport: page.viewportSize(),
          navigation,
          resources,
          total: resources.reduce((sum, r) => sum + r.encoded, 0) + navigation,
        },
        null,
        2,
      ),
      contentType: "application/json",
    });
  expect(
    resources.reduce((sum, r) => sum + r.encoded, 0) + navigation,
  ).toBeLessThan(600 * 1024);
  expect(resources.filter((r) => r.name.endsWith(".woff2")).length).toBe(2);
  await expect(page.locator(".hero-actions .button").first()).toBeVisible();
});
test("untrusted profile names render inert without CSP and never change destination", async ({
  page,
}) => {
  const payload =
    '<img src=x onerror="window.compromised=true"> " onclick="alert(1)';
  await fixture(page, { "/profiles/2": () => ({ ...normal, name: payload }) });
  await page.goto("/dashboard/index_dashboard.html#profile/2");
  await expect(page.getByText(payload, { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.compromised)).toBeUndefined();
  await expect(page.locator("main img")).toHaveCount(0);
  await expect(page.locator("main [onclick]")).toHaveCount(0);
});
test("route clicks fetch once, entity refresh and browser history preserve identity", async ({
  page,
}) => {
  const calls = await fixture(page);
  await page.goto("/dashboard/index_dashboard.html#matches");
  await page.getByRole("link", { name: "شناخت بیشتر" }).click();
  await expect(page.getByText(normal.name, { exact: true })).toBeVisible();
  expect(calls.filter((c) => c.path === "/profiles/2").length).toBe(1);
  await page.reload();
  await expect(page.getByText(normal.name, { exact: true })).toBeVisible();
  await page.goBack();
  await expect(
    page.getByRole("heading", { name: "همراه‌های پیشنهادی" }),
  ).toBeVisible();
  expect(calls.filter((c) => c.path === "/matches").length).toBe(2);
  await page.goForward();
  await expect(page.getByText(normal.name, { exact: true })).toBeVisible();
});
test("slow superseded profile cannot overwrite current route", async ({
  page,
}) => {
  await fixture(page, {
    "/profiles/2": async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 350));
      try {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify(normal),
        });
      } catch {}
    },
  });
  const requested = page.waitForRequest("**/api/profiles/2");
  await page.goto("/dashboard/index_dashboard.html#profile/2");
  await requested;
  await page.evaluate(() => (location.hash = "profile/3"));
  await expect(page.getByText("مهسا احمدی", { exact: true })).toBeVisible();
  await page.waitForTimeout(500);
  await expect(page.getByText(normal.name, { exact: true })).toHaveCount(0);
});
test("failed group lookup is never an empty group and offers explicit retry", async ({
  page,
}) => {
  let failed = true;
  await fixture(page, {
    "/group/me": () =>
      failed
        ? { status: 503, data: { detail: "offline" } }
        : { status: 404, data: { detail: "none" } },
  });
  await page.goto("/dashboard/index_dashboard.html#group");
  await expect(
    page.getByRole("heading", { name: "دریافت اطلاعات انجام نشد" }),
  ).toBeVisible();
  await expect(page.getByText("هنوز عضو گروهی نیستی")).toHaveCount(0);
  failed = false;
  await page.getByRole("button", { name: "تلاش دوباره" }).click();
  await expect(
    page.getByRole("heading", { name: "هنوز عضو گروهی نیستی" }),
  ).toBeVisible();
});
test("questionnaire native radios are keyboard reachable and owner draft restores after refresh", async ({
  page,
}) => {
  const calls = await fixture(page);
  await page.goto("/dashboard/index_dashboard.html#questionnaire");
  await page.locator('[name="sleep.own"]').fill("23:00");
  await page.locator('[name="sleep.start"]').fill("22:00");
  await page.locator('[name="sleep.end"]').fill("01:00");
  const radio = page.locator('[name="sleep.importance"][value="2"]');
  await radio.focus();
  await page.keyboard.press("ArrowRight");
  expect(
    await page.locator('[name="sleep.importance"]:checked').inputValue(),
  ).not.toBe("2");
  await expect(page.getByText("پیش‌نویس در حساب شما ذخیره شد.")).toBeVisible();
  expect(
    calls.some((c) => c.path === "/questionnaire/draft" && c.method === "PUT"),
  ).toBeTruthy();
  await page.reload();
  await expect(page.locator('[name="sleep.own"]')).toHaveValue("23:00");
  const keys = await page.evaluate(() => Object.keys(localStorage));
  expect(keys).not.toContain("questionnaire");
});
test("invitation confirmation traps focus and submits one exact capacity", async ({
  page,
}) => {
  const calls = await fixture(page);
  await page.goto("/dashboard/index_dashboard.html#profile/2");
  await page.getByRole("button", { name: "دعوت به تشکیل گروه" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByLabel("ظرفیت مورد توافق").selectOption("4");
  await page
    .getByRole("button", { name: "ارسال درخواست", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "درخواست‌ها", exact: true }),
  ).toBeVisible();
  const request = calls.find(
    (c) => c.path === "/requests" && c.method === "POST",
  );
  expect(request.body).toEqual({ receiver_id: 2, capacity: 4 });
});

test("incompatible release requires full reload without replaying a mutation", async ({
  page,
}) => {
  await fixture(page);
  let mutations = 0;
  await page.route("**/api/requests", async (route) => {
    if (route.request().method() === "POST") {
      mutations++;
      expect(route.request().headers()["x-matchsho-protocol"]).toBe("3");
      await route.fulfill({
        status: 409,
        headers: { "X-Matchsho-Protocol": "4" },
        contentType: "application/json",
        body: JSON.stringify({ detail: "New protocol" }),
      });
    } else await route.fallback();
  });
  await page.goto("/dashboard/index_dashboard.html#profile/2");
  await page.getByRole("button", { name: "دعوت به تشکیل گروه" }).click();
  await page
    .getByRole("button", { name: "ارسال درخواست", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "بارگذاری نسخهٔ تازه" }),
  ).toBeVisible();
  expect(mutations).toBe(1);
});
test("lost mutation response retains one idempotency key on explicit retry", async ({
  page,
}) => {
  await fixture(page);
  const keys = [];
  await page.route("**/api/requests", async (route) => {
    if (route.request().method() === "POST") {
      keys.push(route.request().headers()["idempotency-key"]);
      if (keys.length === 1) {
        await route.abort("failed");
        return;
      }
      await route.fulfill({ contentType: "application/json", body: "{}" });
    } else await route.fallback();
  });
  await page.goto("/dashboard/index_dashboard.html#profile/2");
  await page.getByRole("button", { name: "دعوت به تشکیل گروه" }).click();
  await page
    .getByRole("button", { name: "ارسال درخواست", exact: true })
    .click();
  await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
  await page
    .getByRole("button", { name: "ارسال درخواست", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "درخواست‌ها", exact: true }),
  ).toBeVisible();
  expect(keys.length).toBe(2);
  expect(keys[0]).toBe(keys[1]);
});
test("refresh rotation is single-flight across browser tabs", async ({
  context,
}) => {
  let rotated = false,
    refreshes = 0;
  await context.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me") {
      await route.fulfill({
        status: rotated ? 200 : 401,
        contentType: "application/json",
        body: JSON.stringify(rotated ? owner : { detail: "expired" }),
      });
      return;
    }
    if (path === "/api/auth/refresh") {
      refreshes++;
      await new Promise((resolve) => setTimeout(resolve, 180));
      rotated = true;
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(owner),
      });
      return;
    }
    const data =
      path === "/api/auth/csrf"
        ? { csrf_token: "012345678901234567890123456789012345" }
        : path === "/api/matches"
          ? { items: [], total: 0, page: 1, limit: 12 }
          : {};
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  const [a, b] = await Promise.all([context.newPage(), context.newPage()]);
  await Promise.all([
    a.goto("/dashboard/index_dashboard.html#matches"),
    b.goto("/dashboard/index_dashboard.html#matches"),
  ]);
  await expect(
    a.getByRole("heading", { name: "همراه‌های پیشنهادی", exact: true }),
  ).toBeVisible();
  await expect(
    b.getByRole("heading", { name: "همراه‌های پیشنهادی", exact: true }),
  ).toBeVisible();
  expect(refreshes).toBe(1);
});

test('complete core student journey using only keyboard input',async({page})=>{
  test.setTimeout(90000);
  await fixture(page,{'/auth/me':()=>({status:401,data:{detail:'no session'}}),'/auth/refresh':()=>({status:401,data:{detail:'no session'}}),'/auth/login':()=>owner});
  async function tabTo(locator){for(let count=0;count<140;count++){if(await locator.evaluate(node=>node===document.activeElement))return;await page.keyboard.press('Tab');}throw new Error('Control was not keyboard reachable');}
  async function timeInput(name){const control=page.locator(`[name="${name}"]`);await tabTo(control);await page.keyboard.type('0100a');await expect(control).toHaveValue('01:00');}
  await page.goto('/dashboard/index_dashboard.html#login');await tabTo(page.getByLabel('ایمیل',{exact:true}));await page.keyboard.type('keyboard@example.com');await page.keyboard.press('Tab');await page.keyboard.type('Keyboard-Example-2026!');await page.keyboard.press('Tab');await page.keyboard.press('Enter');await expect(page.getByRole('heading',{name:/سلام/})).toBeVisible();
  await tabTo(page.getByRole('link',{name:'عادت‌ها و ترجیحات',exact:true}));await page.keyboard.press('Enter');await expect(page.getByRole('heading',{name:'عادت‌ها و ترجیحات من',exact:true})).toBeVisible();
  for(const key of ['sleep','wake'])for(const part of ['own','start','end'])await timeInput(`${key}.${part}`);
  for(const key of ['cleaning','guests','noise']){await tabTo(page.locator(`[name="${key}.own"]`));await page.keyboard.press('ArrowDown');await tabTo(page.locator(`[name="${key}.accepted"][value=a]`));await page.keyboard.press('Space');}
  await tabTo(page.locator('[name=capacities][value="2"]'));await page.keyboard.press('Space');await tabTo(page.getByRole('button',{name:'ثبت نهایی ترجیحات'}));await page.keyboard.press('Enter');await expect(page.getByRole('heading',{name:'همراه‌های پیشنهادی',exact:true})).toBeVisible();
  await tabTo(page.getByRole('link',{name:'شناخت بیشتر'}));await page.keyboard.press('Enter');await tabTo(page.getByRole('button',{name:'دعوت به تشکیل گروه'}));await page.keyboard.press('Enter');await expect(page.getByRole('dialog')).toBeVisible();await tabTo(page.getByRole('button',{name:'ارسال درخواست',exact:true}));await page.keyboard.press('Enter');await expect(page.getByRole('heading',{name:'درخواست‌ها',exact:true})).toBeVisible();
});

test('owner privacy, email preference and report controls send scoped payloads',async({page})=>{
  const calls=await fixture(page);await page.goto('/dashboard/index_dashboard.html#account');await page.locator('[name=explanations]').check();await page.getByRole('button',{name:'ذخیرهٔ انتخاب‌ها'}).click();await expect(page.getByRole('status').filter({hasText:'انتخاب‌های حریم خصوصی ذخیره شد.'})).toBeVisible();expect(calls.find(c=>c.path==='/me/consent').body).toEqual({discovery:true,explanations:true});await page.locator('[name=email]').uncheck();await page.getByRole('button',{name:'ذخیرهٔ ترجیح ایمیل'}).click();await expect(page.getByRole('status').filter({hasText:'ترجیح ایمیل ذخیره شد.'})).toBeVisible();expect(calls.find(c=>c.path==='/me/notification-preference').body).toEqual({email:false});
  await page.goto('/dashboard/index_dashboard.html#profile/2');await page.getByRole('button',{name:'گزارش',exact:true}).click();await page.getByLabel('شرح گزارش').fill('درخواست بررسی رفتار نامناسب');await page.getByRole('button',{name:'ثبت گزارش',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);expect(calls.find(c=>c.path==='/me/reports').body).toEqual({target_id:2,category:'harassment',description:'درخواست بررسی رفتار نامناسب'});
});
test('operator roster import requires a reviewed preview and preserves explicit migration consent',async({page})=>{
  const calls=await fixture(page,{'/auth/me':()=>({...owner,role:'admin'}),'/admin/roster':()=>({items:[],total:0,offset:0,limit:20}),'/admin/roster/import':route=>({valid:true,errors:[],rows:1,imported:route.request().postDataJSON().dry_run?0:1})});
  await page.goto('/dashboard/admin.html#admin/roster');await page.getByRole('button',{name:'ورود فهرست CSV'}).click();await page.getByLabel('فایل CSV فهرست دانشگاه').setInputFiles({name:'roster.csv',mimeType:'text/csv',buffer:Buffer.from('student_id,email,name,class_name,gender,pool,cycle\n99,student@example.com,دانشجوی آزمایشی,مهندسی,male,male,pilot-2026')});await page.getByLabel('دلیل عملیات').fill('بررسی فهرست رسمی دانشگاه');await page.locator('[name=allow_legacy_email_rebind]').check();await page.getByRole('button',{name:'پیش‌نمایش و بررسی'}).click();await expect(page.getByRole('button',{name:'ثبت فهرست تأییدشده'})).toBeVisible();const preview=calls.find(c=>c.path==='/admin/roster/import');expect(preview.body.dry_run).toBe(true);expect(preview.body.allow_legacy_email_rebind).toBe(true);expect(calls.filter(c=>c.path==='/admin/roster/import').length).toBe(1);await page.getByRole('button',{name:'ثبت فهرست تأییدشده'}).click();await expect(page.getByRole('dialog')).toHaveCount(0);const apply=calls.filter(c=>c.path==='/admin/roster/import')[1];expect(apply.body).toEqual({...preview.body,dry_run:false});
});
test('delivery health displays actual queue state and never retries a delivered message',async({page})=>{
  const calls=await fixture(page,{'/auth/me':()=>({...owner,role:'admin'}),'/admin/delivery':()=>({items:[{id:9,purpose:'claim',status:'delivered',attempts:1,created_at:'2026-10-02T08:00:00Z'}],total:1}),'/admin/delivery/health':()=>({last_heartbeat_at:'2026-10-02T08:00:00Z',oldest_pending_age_seconds:350,pending_count:2,retry_count:1,terminal_failures:0,alerts:['queue_age_exceeded']})});await page.goto('/dashboard/admin.html#admin/outbox');await expect(page.getByRole('heading',{name:'سلامت ارسال ایمیل'})).toBeVisible();await expect(page.getByText('زمان انتظار صف از ۵ دقیقه بیشتر شده است.')).toBeVisible();await expect(page.getByRole('button',{name:'بررسی و تلاش دوباره'})).toHaveCount(0);expect(calls.filter(c=>c.path==='/admin/delivery/health').length).toBe(1);
});

test('block, correction case and remote session revocation use owner-scoped routes',async({page})=>{
  let blocked=false,revoked=false;
  const calls=await fixture(page,{'/me/blocks/2':route=>{blocked=route.request().method()==='POST';return {};},'/me/blocks':()=>({items:blocked?[{user_id:2,name:normal.name}]:[]}),'/auth/sessions':()=>({items:revoked?[]:[{sid:'other-device',device:'مرورگر دیگر',current:false,created_at:'2026-10-02T07:00:00Z',last_used_at:'2026-10-02T07:00:00Z'}]}),'/auth/sessions/other-device':()=>{revoked=true;return {};},'/me/cases':()=>({items:[{id:1,reference:'CASE-100',kind:'correction',status:'reviewing',description:'بررسی ایمیل دانشجو',created_at:'2026-10-02T08:00:00Z'}]})});
  await page.goto('/dashboard/index_dashboard.html#profile/2');await page.getByRole('button',{name:'مسدودکردن',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'مسدودکردن',exact:true}).click();await expect(page.getByRole('heading',{name:'حساب و حریم خصوصی',exact:true})).toBeVisible();await expect(page.getByText(normal.name,{exact:true})).toBeVisible();expect(calls.some(c=>c.path==='/me/blocks/2'&&c.method==='POST')).toBeTruthy();await page.getByRole('button',{name:'رفع مسدودی',exact:true}).click();await expect(page.getByText('ارتباط مسدودشده‌ای ندارید.')).toBeVisible();
  await page.getByRole('button',{name:'بستن نشست',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'بستن نشست',exact:true}).click();await expect(page.getByText('مرورگر دیگر',{exact:true})).toHaveCount(0);expect(calls.some(c=>c.path==='/auth/sessions/other-device'&&c.method==='DELETE')).toBeTruthy();
  await page.getByRole('link',{name:'پشتیبانی و پیگیری',exact:true}).click();await expect(page.getByText('پیگیری CASE-100')).toBeVisible();await page.getByLabel('نوع درخواست').selectOption('correction');await page.getByLabel('شرح درخواست').fill('لطفاً ایمیل رسمی پرونده اصلاح شود');await page.getByRole('button',{name:'ثبت و دریافت شمارهٔ پیگیری'}).click();await expect(page.getByRole('status').filter({hasText:'درخواست ثبت شد.'})).toBeVisible();expect(calls.find(c=>c.path==='/me/corrections').body).toEqual({field:'email',description:'لطفاً ایمیل رسمی پرونده اصلاح شود'});
});
test('password reset form consumes the supplied token and does not leave it in the route',async({page})=>{
  const calls=await fixture(page);const token='sample-reset-token-1234567890';await page.goto(`/dashboard/index_dashboard.html#reset-password?token=${token}`);await page.getByLabel('رمز عبور جدید',{exact:true}).fill('Changed-Password-2026!');expect(page.url()).not.toContain(token);await page.getByRole('button',{name:'ذخیرهٔ رمز جدید'}).click();await expect(page.getByText('رمز جدید ذخیره و نشست‌های قبلی باطل شد.')).toBeVisible();expect(calls.find(c=>c.path==='/auth/reset-password').body).toEqual({password:'Changed-Password-2026!',token});
});
test('operator move and unassign confirmations retain exact people capacity and reason',async({page})=>{
  const roomA={id:9,number:'A',dormitory:'خوابگاه آزمون',capacity:2,current_occupancy:2,pool:'male',cycle:'pilot-2026'};const roomB={...roomA,id:10,number:'B',current_occupancy:0};let group={id:5,capacity:2,members:[owner,normal],room:roomA,pool:'male',cycle:'pilot-2026',allocation_issues:[]};
  const calls=await fixture(page,{'/auth/me':()=>({...owner,role:'admin'}),'/admin/groups':()=>({items:[group],total:1,page:1,limit:20}),'/admin/rooms':()=>({items:[roomA,roomB],total:2,page:1,limit:50}),'/admin/groups/5/allocation':route=>{group={...group,room:route.request().method()==='DELETE'?null:roomB};return group;}});
  await page.goto('/dashboard/admin.html#admin/groups');await page.getByRole('button',{name:'اصلاح تخصیص',exact:true}).click();await expect(page.getByRole('dialog').getByText(/اعضای تحت تأثیر:/)).toContainText(normal.name);await page.getByLabel('اتاق مقصد و ظرفیت').selectOption('10');await page.getByLabel('دلیل عملیات').fill('اصلاح اتاق پس از بررسی اعضا');await page.getByRole('button',{name:'تأیید تخصیص این اعضا'}).click();await expect(page.getByText('اتاق B · خوابگاه آزمون',{exact:true})).toBeVisible();expect(calls.find(c=>c.path==='/admin/groups/5/allocation').body).toEqual({room_id:10,reason:'اصلاح اتاق پس از بررسی اعضا'});
  await page.getByRole('button',{name:'آزادکردن اتاق گروه'}).click();await page.getByLabel('دلیل عملیات').fill('لغو تخصیص با درخواست بررسی‌شده');await page.getByRole('button',{name:'ثبت تصمیم',exact:true}).click();await expect(page.getByText('بدون تخصیص',{exact:true})).toBeVisible();expect(calls.some(c=>c.path==='/admin/groups/5/allocation'&&c.method==='DELETE'&&c.body.reason==='لغو تخصیص با درخواست بررسی‌شده')).toBeTruthy();
});
test('operator case resolution and eligible email retry preserve review reasons',async({page})=>{
  let status='open',delivery='retry-scheduled';const calls=await fixture(page,{'/auth/me':()=>({...owner,role:'admin'}),'/admin/cases':()=>({items:[{id:7,reference:'CASE-007',status,description:'درخواست بررسی مشکل فنی',created_at:'2026-10-02T07:00:00Z'}],total:1}),'/admin/cases/7':route=>{status=route.request().postDataJSON().status;return {};},'/admin/delivery':()=>({items:[{id:11,purpose:'claim',status:delivery,attempts:1,created_at:'2026-10-02T07:00:00Z'}],total:1}),'/admin/delivery/health':()=>({pending_count:1,retry_count:1,terminal_failures:0,oldest_pending_age_seconds:10,alerts:[]}),'/admin/delivery/11/retry':()=>{delivery='pending';return {};}});
  await page.goto('/dashboard/admin.html#admin/cases');await page.getByRole('button',{name:'رسیدگی',exact:true}).click();await page.getByLabel('تصمیم').selectOption('resolved');await page.getByLabel('دلیل عملیات').fill('درخواست بررسی و مشکل برطرف شد');await page.getByRole('button',{name:'ثبت رسیدگی'}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.locator('.badge').filter({hasText:'رسیدگی‌شده'})).toBeVisible();expect(calls.find(c=>c.path==='/admin/cases/7').body).toEqual({status:'resolved',reason:'درخواست بررسی و مشکل برطرف شد'});
  await page.getByRole('link',{name:'تحویل ایمیل',exact:true}).click();await page.getByRole('button',{name:'بررسی و تلاش دوباره'}).click();await page.getByLabel('دلیل عملیات').fill('اعتبار پیام و گیرنده بررسی شد');await page.getByRole('button',{name:'ثبت تصمیم',exact:true}).click();await expect(page.getByRole('cell',{name:'در صف',exact:true})).toBeVisible();expect(calls.filter(c=>c.path==='/admin/delivery/11/retry').length).toBe(1);
});
