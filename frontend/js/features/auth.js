import { api, post } from "../api.js";
import { session } from "../session.js";
import { el, field, link, notice, bindForm, announce } from "../ui.js";
export const authRoutes = new Set([
  "login",
  "register",
  "activate",
  "forgot",
  "reset",
  "reset-password",
  "verify-email",
]);
export function authPage(ctx) {
  const mode = ctx.path === "reset-password" ? "reset" : ctx.path;
  const titles = {
    login: "خوش برگشتی",
    register: "شروع یک آشنایی تازه",
    activate: "حسابت را فعال کن",
    forgot: "بازیابی دسترسی",
    reset: "رمز تازه انتخاب کن",
    "verify-email": "تأیید ایمیل",
  };
  const subtitles = {
    login: "برای ادامهٔ انتخاب هم‌اتاقی وارد حسابت شو.",
    register: "شمارهٔ دانشجویی و ایمیل ثبت‌شده در فهرست خوابگاه را وارد کن.",
    activate: "با این دعوت، هویت ثبت‌شدهٔ دانشگاه به حساب تو متصل می‌شود.",
    forgot: "لینک بازیابی به ایمیل ثبت‌شده در حساب ارسال می‌شود.",
    reset:
      "رمز جدید باید حداقل ۱۲ نویسه داشته باشد. نشست‌های قبلی بسته خواهند شد.",
    "verify-email": "لینک ایمیل را تأیید کن تا وضعیت حسابت به‌روز شود.",
  };
  const form = el("form", {});
  const response = el("div", {});
  if (["login", "register", "forgot"].includes(mode))
    form.append(
      field("ایمیل", "email", {
        type: "email",
        required: mode !== "register",
        autocomplete: "email",
        dir: "ltr",
        placeholder: "name@university.ac.ir",
        maxlength: 254,
      }),
    );
  if (mode === "register")
    form.prepend(
      field("شمارهٔ دانشجویی", "student_id", {
        required: true,
        autocomplete: "username",
        dir: "ltr",
        maxlength: 64,
      }),
    );
  if (["login", "activate", "reset"].includes(mode))
    form.append(
      field(mode === "login" ? "رمز عبور" : "رمز عبور جدید", "password", {
        type: "password",
        required: true,
        minlength: 12,
        maxlength: 128,
        autocomplete: mode === "login" ? "current-password" : "new-password",
        dir: "ltr",
        hint:
          mode === "login"
            ? undefined
            : "حداقل ۱۲ نویسه؛ ترکیبی که در سایت دیگری استفاده نکرده‌ای.",
      }),
    );
  let token =
    ctx.params.get("token") ||
    new URLSearchParams(location.search).get("token");
  if (["activate", "reset", "verify-email"].includes(mode)) {
    if (!token)
      form.append(
        field("کد لینک دریافت‌شده", "token", {
          required: true,
          autocomplete: "off",
          dir: "ltr",
        }),
      );
    else history.replaceState(null, "", `${location.pathname}#${ctx.path}`);
  }
  const labels = {
    login: "ورود به حساب",
    register: "دریافت لینک فعال‌سازی",
    activate: "فعال‌سازی حساب",
    forgot: "ارسال لینک بازیابی",
    reset: "ذخیرهٔ رمز جدید",
    "verify-email": "تأیید ایمیل",
  };
  form.append(el("button", { type: "submit" }, labels[mode] || "ادامه"));
  bindForm(form, async (data) => {
    const values = Object.fromEntries(data);
    if (mode === "register" && !values.email) delete values.email;
    if (token) values.token = token;
    if (mode === "login") {
      await session.login(values);
      announce("با موفقیت وارد شدید.");
      ctx.navigate(ctx.admin ? "admin/groups" : "home");
      return;
    }
    const endpoints = {
      register: "/auth/register",
      activate: "/auth/activate",
      forgot: "/auth/forgot-password",
      reset: "/auth/reset-password",
      "verify-email": "/auth/verify-email",
    };
    await post(endpoints[mode], values);
    if (mode === "activate" || mode === "reset") {
      response.replaceChildren(
        notice(
          mode === "activate"
            ? "حساب شما فعال شد. اکنون وارد شوید."
            : "رمز جدید ذخیره و نشست‌های قبلی باطل شد.",
          "success",
        ),
        link("ورود به حساب", "#login", "button"),
      );
      form.hidden = true;
    } else if (mode === "verify-email") {
      response.replaceChildren(
        notice("ایمیل تأیید شد. اکنون وارد شوید.", "success"),
      );
      form.hidden = true;
    } else {
      response.replaceChildren(
        notice(
          "اگر اطلاعات با یک حساب مجاز مطابقت داشته باشد، لینک ارسال می‌شود. پوشهٔ هرزنامه را هم بررسی کنید.",
          "success",
        ),
      );
    }
  });
  return el(
    "div",
    { class: "container auth-layout" },
    el(
      "section",
      { class: "auth-intro" },
      el("span", { class: "eyebrow" }, "کنار هم، سازگارتر"),
      el(
        "h2",
        {class:"auth-headline"},
        "از یک انتخاب آگاهانه،",
        " ",
        el("span", {}, "یک همراهی خوب بساز."),
      ),
      el(
        "p",
        {},
        "عادت‌ها و انتظاراتت را ثبت کن، پیشنهادها را بشناس و با رضایت همهٔ اعضا گروه بساز.",
      ),
      el(
        "div",
        { class: "steps-inline" },
        el("span", {}, "هویت تأییدشده"),
        el("span", {}, "اطلاعات خصوصی"),
        el("span", {}, "رضایت مشترک"),
      ),
      el("img", {
        class: "auth-illustration",
        src: "/assets/original-brand/dorm-life.jpg",
        width: 367,
        height: 403,
        alt: "",
        decoding: "async",
      }),
    ),
    el(
      "section",
      { class: "card auth-card" },
      el(
        "h1",
        { tabindex: "-1" },
        ctx.admin && mode === "login" ? "ورود مسئول خوابگاه" : titles[mode],
      ),
      el("p", { class: "muted small" }, subtitles[mode]),
      response,
      form,
      el(
        "div",
        { class: "auth-links" },
        link(
          ctx.admin ? "ورود دانشجو" : mode === "login" ? "هنوز حساب نداری؟ شروع کن" : "حساب داری؟ وارد شو",
          ctx.admin ? "/dashboard/index_dashboard.html#login" : mode === "login" ? "#register" : "#login",
        ),
        link("رمزم را فراموش کرده‌ام", "#forgot"),
      ),
      el("div", { class: "divider" }),
      el(
        "p",
        { class: "small muted" },
        "ادامهٔ استفاده با اطلاع از ",
        link("حریم خصوصی", "/privacy.html"),
        " و قواعد خوابگاه انجام می‌شود.",
      ),
    ),
  );
}
