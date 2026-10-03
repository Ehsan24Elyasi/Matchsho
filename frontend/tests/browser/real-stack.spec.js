import { test, expect, request as playwrightRequest } from "@playwright/test";
import fs from "node:fs";
const enabled = Boolean(process.env.BASE_URL && process.env.PILOT_ENV_FILE);
function fixtureEnv() {
  const content = fs.readFileSync(process.env.PILOT_ENV_FILE, "utf8");
  return Object.fromEntries(
    content
      .split(/\r?\n/)
      .filter((line) => line && !line.startsWith("#") && line.includes("="))
      .map((line) => {
        const at = line.indexOf("=");
        return [
          line.slice(0, at),
          line.slice(at + 1).replace(/^['"]|['"]$/g, ""),
        ];
      }),
  );
}
async function mutation(client, path, body) {
  const csrf = await (await client.get("/api/auth/csrf")).json();
  const r = await client.post(`/api${path}`, {
    data: body,
    headers: {
      "X-CSRF-Token": csrf.csrf_token,
      "Idempotency-Key": crypto.randomUUID(),
    },
  });
  expect(r.ok(), `${path}: ${r.status()}`).toBeTruthy();
  return r.json();
}
async function tokenFor(email) {
  const mail = await playwrightRequest.newContext({
    baseURL: process.env.MAILPIT_URL || "http://localhost:8025",
  });
  try {
    let token;
    await expect
      .poll(
        async () => {
          const result = await (await mail.get("/api/v1/messages")).json();
          for (const msg of result.messages || []) {
            if (!msg.To?.some((to) => to.Address === email)) continue;
            const full = await (
              await mail.get(`/api/v1/message/${msg.ID}`)
            ).json();
            const match = (full.Text || "").match(/token=([A-Za-z0-9_-]+)/);
            if (match) {
              token = match[1];
              return true;
            }
          }
          return false;
        },
        { timeout: 60000, intervals: [1000, 2000, 3000] },
      )
      .toBeTruthy();
    return token;
  } finally {
    await mail.dispose();
  }
}
async function login(page, email, password, admin = false) {
  await page.goto(
    `/dashboard/${admin ? "admin.html" : "index_dashboard.html"}#login`,
  );
  await page.getByLabel("ایمیل", { exact: true }).fill(email);
  await page.getByLabel("رمز عبور", { exact: true }).fill(password);
  await page.getByRole("button", { name: "ورود به حساب", exact: true }).click();
  await expect(page.locator("aside")).toBeVisible();
}
test("real Compose student claim → questionnaire → invitation → group, and operator allocation", async ({
  browser,
  baseURL,
}) => {
  test.skip(!enabled, "Requires isolated Compose, Mailpit and PILOT_ENV_FILE.");
  test.setTimeout(180000);
  const env = fixtureEnv();
  const admin = await playwrightRequest.newContext({ baseURL });
  await mutation(admin, "/auth/login", {
    email: env.ADMIN_EMAIL,
    password: env.ADMIN_PASSWORD,
  });
  const config = await (await admin.get("/api/pilot/config")).json();
  const suffix = Date.now().toString(36);
  const pool = (env.PILOT_ALLOWED_POOLS || env.ALLOWED_POOLS || "male")
    .split(",")[0]
    .trim();
  const cycle = config.cycle || config.active_cycle;
  const rows = [0, 1].map((i) => ({
    student_id: `frontend-${suffix}-${i}`,
    email: `frontend-${suffix}-${i}@example.com`,
    name: `آزمون فرانت ${suffix} ${i}`,
    class_name: "مهندسی",
    gender: "male",
    pool,
    cycle,
  }));
  await mutation(admin, "/admin/roster/import", {
    rows,
    dry_run: false,
    reason: "ثبت دانشجویان موقت آزمون مسیر کامل فرانت",
  });
  const room = await mutation(admin, "/admin/rooms", {
    number: `fe-${suffix}`,
    dormitory: "آزمون خودکار فرانت",
    capacity: 2,
    pool,
    cycle,
    reason: "اتاق موقت آزمون خودکار مسیر مرورگر",
  });
  const password = `Frontend-${suffix}-Strong!`;
  const contexts = [];
  const pages = [];
  try {
    for (const row of rows) {
      const context = await browser.newContext({ baseURL });
      contexts.push(context);
      const page = await context.newPage();
      pages.push(page);
      await page.goto("/dashboard/index_dashboard.html#register");
      await page
        .getByLabel("شمارهٔ دانشجویی", { exact: true })
        .fill(row.student_id);
      await page.getByLabel("ایمیل", { exact: true }).fill(row.email);
      await page.getByRole("button", { name: "دریافت لینک فعال‌سازی" }).click();
      await expect(
        page.getByText(
          "اگر اطلاعات با یک حساب مجاز مطابقت داشته باشد، لینک ارسال می‌شود. پوشهٔ هرزنامه را هم بررسی کنید.",
        ),
      ).toBeVisible();
      const token = await tokenFor(row.email);
      await page.goto(
        `/dashboard/index_dashboard.html#activate?token=${token}`,
      );
      await page.getByLabel("رمز عبور جدید", { exact: true }).fill(password);
      await page
        .getByRole("button", { name: "فعال‌سازی حساب", exact: true })
        .click();
      await expect(
        page.getByText("حساب شما فعال شد. اکنون وارد شوید."),
      ).toBeVisible();
      await login(page, row.email, password);
      await page
        .getByRole("link", { name: "حساب و حریم خصوصی", exact: true })
        .click();
      await page.locator("[name=discovery]").check();
      await page.getByRole("button", { name: "ذخیرهٔ انتخاب‌ها" }).click();
      await expect(
        page
          .getByRole("status")
          .filter({ hasText: "انتخاب‌های حریم خصوصی ذخیره شد." }),
      ).toBeVisible();
      await page
        .getByRole("link", { name: "عادت‌ها و ترجیحات", exact: true })
        .click();
      await page.locator('[name="sleep.own"]').fill("23:00");
      await page.locator('[name="sleep.start"]').fill("21:00");
      await page.locator('[name="sleep.end"]').fill("02:00");
      await page.locator('[name="wake.own"]').fill("07:00");
      await page.locator('[name="wake.start"]').fill("06:00");
      await page.locator('[name="wake.end"]').fill("09:00");
      for (const [key, value] of [
        ["cleaning", "weekly"],
        ["guests", "never"],
        ["noise", "quiet"],
      ]) {
        await page.locator(`[name="${key}.own"]`).selectOption(value);
        await page
          .locator(`[name="${key}.accepted"][value="${value}"]`)
          .check();
      }
      await page.locator('[name="capacities"][value="2"]').check();
      await page.getByRole("button", { name: "ثبت نهایی ترجیحات" }).click();
      await expect(
        page.getByRole("heading", { name: "همراه‌های پیشنهادی", exact: true }),
      ).toBeVisible();
    }
    // The isolated load cohort can occupy earlier match pages. Use the peer's public route ID.
    const peer=await (await contexts[1].request.get("/api/auth/me")).json();
    await pages[0].goto(`/dashboard/index_dashboard.html#profile/${peer.id}`);
    await pages[0].getByRole("button", { name: "دعوت به تشکیل گروه" }).click();
    await pages[0]
      .getByRole("button", { name: "ارسال درخواست", exact: true })
      .click();
    await expect(
      pages[0].getByRole("heading", { name: "درخواست‌ها", exact: true }),
    ).toBeVisible();
    await pages[1]
      .getByRole("link", { name: "درخواست‌ها", exact: true })
      .click();
    const invitation = pages[1]
      .locator("article")
      .filter({ hasText: rows[0].name });
    await invitation.getByRole("button", { name: "تأیید این پیشنهاد" }).click();
    await pages[1]
      .getByRole("dialog")
      .getByRole("button", { name: "تأیید این پیشنهاد" })
      .click();
    await expect(
      pages[1].getByText("پذیرفته‌شده", { exact: true }),
    ).toBeVisible();
    const adminContext = await browser.newContext({ baseURL });
    contexts.push(adminContext);
    const operator = await adminContext.newPage();
    await login(operator, env.ADMIN_EMAIL, env.ADMIN_PASSWORD, true);
    const group = operator
      .locator("main section.card")
      .filter({ hasText: rows[0].name })
      .last();
    await group
      .getByRole("button", { name: "تخصیص اتاق", exact: true })
      .click();
    await operator
      .getByLabel("اتاق مقصد و ظرفیت")
      .selectOption(String(room.id));
    await operator
      .getByLabel("دلیل عملیات")
      .fill("تأیید تخصیص آزمایشی دو دانشجوی فرانت");
    await operator
      .getByRole("button", { name: "تأیید تخصیص این اعضا" })
      .click();
    await expect(
      group.getByText(`اتاق ${room.number} · آزمون خودکار فرانت`),
    ).toBeVisible();
    await pages[0].getByRole("link", { name: "گروه من", exact: true }).click();
    await expect(
      pages[0].getByRole("heading", {
        name: `اتاق ${room.number}`,
        exact: true,
      }),
    ).toBeVisible();
    await pages[0].setViewportSize({ width: 1280, height: 720 });
    await pages[0].screenshot({
      path: "../docs/pilot/evidence/student-allocation-desktop.png",
      fullPage: true,
    });
    await operator.screenshot({
      path: "../docs/pilot/evidence/operator-allocation-desktop.png",
      fullPage: true,
    });
    await pages[0].setViewportSize({ width: 390, height: 844 });
    await pages[0].screenshot({
      path: "../docs/pilot/evidence/student-allocation-mobile.png",
      fullPage: true,
    });
    await pages[0]
      .getByRole("button", { name: "درخواست خروج فردی", exact: true })
      .click();
    await pages[0]
      .getByLabel("دلیل درخواست خروج")
      .fill("درخواست خروج فردی برای آزمون حفظ جای هم‌گروهی");
    await pages[0]
      .getByRole("button", { name: "ثبت درخواست بررسی", exact: true })
      .click();
    await expect(
      pages[0].getByText("درخواست خروج فردی شما: منتظر تأیید"),
    ).toBeVisible();
    await operator
      .getByRole("link", { name: "خروج‌های فردی", exact: true })
      .click();
    const departure = operator
      .locator("section.card")
      .filter({
        has: operator.getByRole("heading", { name: rows[0].name, exact: true }),
      })
      .last();
    await departure
      .getByRole("button", { name: "تأیید خروج فردی", exact: true })
      .click();
    await operator
      .getByLabel("دلیل عملیات")
      .fill("تأیید خروج یک فرد و حفظ تخصیص عضو باقی‌مانده");
    await operator
      .getByRole("button", { name: "ثبت تصمیم", exact: true })
      .click();
    await expect(
      departure.getByText("تأییدشده", { exact: true }),
    ).toBeVisible();
    await pages[0].reload();
    await expect(
      pages[0].getByRole("heading", {
        name: "هنوز عضو گروهی نیستی",
        exact: true,
      }),
    ).toBeVisible();
    await pages[1].getByRole("link", { name: "گروه من", exact: true }).click();
    await expect(
      pages[1].getByRole("heading", {
        name: `اتاق ${room.number}`,
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      pages[1].getByRole("heading", { name: "1 نفر از 2 نفر", exact: true }),
    ).toBeVisible();
    await pages[0]
      .getByRole("link", { name: "پشتیبانی و پیگیری", exact: true })
      .first()
      .click();
    await expect(
      pages[0].getByRole("heading", {
        name: "پیگیری خروج از گروه",
        exact: true,
      }),
    ).toBeVisible();
    await expect(pages[0].getByText("تأییدشده", { exact: true })).toBeVisible();
    await pages[0].getByRole("link", { name: "اعلان‌ها", exact: true }).click();
    const unread = pages[0].locator("article.unread").first();
    const notificationText = await unread.locator("p").textContent();
    await unread
      .getByRole("button", { name: "خوانده شد", exact: true })
      .click();
    await pages[0].reload();
    await expect(
      pages[0].locator("article").filter({ hasText: notificationText }),
    ).not.toHaveClass(/unread/);
    const denied = await contexts[0].request.get("/api/admin/users");
    expect(denied.status()).toBe(403);
    await pages[0].goto("/dashboard/admin.html#admin/users");
    await expect(
      pages[0].getByText("فقط مسئول مجاز خوابگاه به این بخش دسترسی دارد."),
    ).toBeVisible();
  } finally {
    for (const context of contexts) await context.close();
    await admin.dispose();
  }
});
