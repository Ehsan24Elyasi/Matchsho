import { api, post } from "../api.js";
import { session } from "../session.js";
import { el, field, selectField, link, notice, bindForm, announce } from "../ui.js";
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
  const emailAuth = ctx.config.email_verification_required === true;
  const directRegister = mode === "register" && !emailAuth;
  if (!emailAuth && !["login", "register"].includes(mode)) {
    history.replaceState(null, "", `${location.pathname}#${ctx.path}`);
    return el("section", { class: "container card auth-card" },
      el("h1", { tabindex: "-1" }, "ورود با ایمیل و رمز عبور"),
      notice("فعلاً فعال‌سازی و بازیابی ایمیلی نداریم. برای مشکل ورود با مسئول خوابگاه تماس بگیر."),
      link("ورود به حساب", "#login", "button"));
  }
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
    register: directRegister
      ? "مشخصاتت را وارد کن و برای حسابت رمز عبور انتخاب کن."
      : "شمارهٔ دانشجویی و ایمیل ثبت‌شده در فهرست خوابگاه را وارد کن.",
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
        required: mode !== "register" || directRegister,
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
        minlength: directRegister ? 2 : 1,
        maxlength: 50,
      }),
    );
  if (directRegister) {
    form.prepend(field("نام و نام خانوادگی", "name", { required: true, minlength: 2, maxlength: 100, autocomplete: "name" }));
    form.append(
      field("رشتهٔ تحصیلی", "class_name", { required: true, maxlength: 100 }),
      selectField("گروه خوابگاه", "gender", [
        { value: "", label: "انتخاب کن" },
        { value: "male", label: "پسران" },
        { value: "female", label: "دختران" },
      ], "", { required: true }),
    );
  }
  if (["login", "activate", "reset"].includes(mode) || directRegister)
    form.append(
      field(mode === "login" || directRegister ? "رمز عبور" : "رمز عبور جدید", "password", {
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
  if (directRegister)
    form.append(field("تکرار رمز عبور", "password_confirm", {
      type: "password", required: true, minlength: 12, maxlength: 128, autocomplete: "new-password", dir: "ltr",
    }));
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
    register: directRegister ? "ساخت حساب" : "دریافت لینک فعال‌سازی",
    activate: "فعال‌سازی حساب",
    forgot: "ارسال لینک بازیابی",
    reset: "ذخیرهٔ رمز جدید",
    "verify-email": "تأیید ایمیل",
  };
  form.append(el("button", { type: "submit" }, labels[mode] || "ادامه"));
  bindForm(form, async (data) => {
    const values = Object.fromEntries(data);
    if (directRegister) {
      if (values.password !== values.password_confirm) throw new Error("تکرار رمز عبور یکسان نیست.");
      delete values.password_confirm;
      await post("/auth/register", values);
      await session.load();
      announce("حسابت ساخته شد و وارد شدی.");
      ctx.navigate("home");
      return;
    }
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
        el("span", {}, emailAuth ? "هویت تأییدشده" : "ثبت‌نام ساده"),
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
        emailAuth ? link("رمزم را فراموش کرده‌ام", "#forgot")
          : el("span", { class: "small muted" }, "برای مشکل ورود با مسئول خوابگاه تماس بگیر."),
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
