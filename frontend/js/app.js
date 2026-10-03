import { api, ApiError } from "./api.js";
import { session } from "./session.js";
import { createRouter } from "./router.js";
import {
  el,
  link,
  button,
  loading,
  errorPanel,
  notice,
  announce,
} from "./ui.js";
import { authPage, authRoutes } from "./features/auth.js";
import { questionnairePage } from "./features/questionnaire.js";
import {
  homePage,
  matchesPage,
  profilePage,
  requestsPage,
  groupPage,
  notificationsPage,
  accountPage,
  supportPage,
} from "./features/student.js";
import { adminPage } from "./features/admin.js";
const admin = document.body.dataset.mode === "admin";
let config = {},
  initialized = false,
  initialError = null;
const studentNav = [
  ["home", "⌂", "خانهٔ من"],
  ["matches", "◇", "همراه‌های پیشنهادی"],
  ["questionnaire", "☷", "عادت‌ها و ترجیحات"],
  ["requests", "⇄", "درخواست‌ها"],
  ["group", "♧", "گروه من"],
  ["notifications", "◉", "اعلان‌ها"],
  ["account", "⚙", "حساب و حریم خصوصی"],
  ["support", "؟", "پشتیبانی و پیگیری"],
];
const adminNav = [
  ["admin/groups", "♧", "گروه‌ها و تخصیص"],
  ["admin/rooms", "▤", "اتاق‌ها"],
  ["admin/users", "◉", "دانشجویان"],
  ["admin/roster", "☷", "فهرست مجاز"],
  ["admin/requests", "⇄", "دعوت‌ها"],
  ["admin/departures", "↪", "خروج‌های فردی"],
  ["admin/cases", "؟", "گزارش‌ها و پشتیبانی"],
  ["admin/audit", "◷", "تاریخچهٔ عملیات"],
  ["admin/outbox", "✉", "تحویل ایمیل"],
];
function shell(path, publicPage) {
  const app = document.getElementById("app");
  const brand = link("", "/", "brand");
  brand.append(
    el("img", { class: "brand-logo", src: "/assets/original-brand/matchsho-logo.webp", width: 56, height: 40, alt: "", decoding: "async" }),
    el("span", {}, "مچ‌شو", el("small", {}, "MATCHSHO")),
  );
  const controls = el(
    "div",
    { class: "row", id: "header-actions" },
    publicPage
      ? link("بازگشت به خانه", "/", "small")
      : el("span", { class: "small muted" }, session.user?.name),
    !publicPage &&
      button(
        "خروج",
        async () => {
          try {
            await session.logout();
            router.navigate("login");
          } catch (e) {
            announce(e.message);
          }
        },
        "secondary",
      ),
  );
  const header = el(
    "header",
    { class: "header" },
    el("div", { class: "container header-inner between" }, brand, controls),
  );
  const main = el("main", {
    id: "main",
    class: publicPage ? "" : "app-main",
    tabindex: "-1",
  });
  let body = main;
  if (!publicPage) {
    const nav = el(
      "nav",
      { "aria-label": admin ? "بخش‌های مدیریت" : "بخش‌های حساب" },
      ...(admin ? adminNav : studentNav).map(([route, icon, label]) =>
        el(
          "a",
          {
            href: `#${route}`,
            "aria-current":
              path === route ||
              (path.startsWith("profile/") && route === "matches")
                ? "page"
                : undefined,
          },
          el("span", { class: "nav-icon", "aria-hidden": "true" }, icon),
          label,
        ),
      ),
    );
    body = el(
      "div",
      { class: "container app-layout" },
      el(
        "aside",
        { class: "sidebar" },
        el(
          "div",
          { class: "sidebar-label" },
          admin ? "میز مسئول خوابگاه" : "فضای دانشجویی",
        ),
        nav,
        el(
          "div",
          { class: "sidebar-bottom" },
          el(
            "strong",
            {},
            config.institution || config.institution_name || "پایلوت خوابگاه",
          ),
          el("p", {}, "زندگی مشترک با انتخاب آگاهانه"),
          link("حریم خصوصی", "/privacy.html"),
        ),
      ),
      main,
    );
  }
  app.replaceChildren(
    header,
    body,
    el(
      "footer",
      { class: "footer" },
      el(
        "div",
        { class: "container footer-inner" },
        el("span", {}, "مچ‌شو · کنار هم، سازگارتر"),
        link("راهنما و حریم خصوصی", "/privacy.html"),
      ),
    ),
  );
  return main;
}
const renderers = {
  home: homePage,
  matches: matchesPage,
  profile: profilePage,
  questionnaire: questionnairePage,
  requests: requestsPage,
  group: groupPage,
  notifications: notificationsPage,
  account: accountPage,
  support: supportPage,
  admin: adminPage,
};
const router = createRouter(async (route) => {
  const publicPage = authRoutes.has(route.path);
  const main = shell(route.path, publicPage);
  main.replaceChildren(loading());
  try {
    if (!initialized) {
      const outcomes = await Promise.allSettled([
        session.load(),
        api("/pilot/config"),
      ]);
      initialized = true;
      if (outcomes[1].status === "fulfilled") config = outcomes[1].value;
      if (
        outcomes[0].status === "rejected" &&
        outcomes[0].reason.status !== 401
      )
        initialError = outcomes[0].reason;
    }
    if (!route.isCurrent()) return;
    if (initialError && !publicPage) {
      const err = initialError;
      initialError = null;
      initialized = false;
      throw err;
    }
    if (!publicPage && !session.user) {
      router.navigate("login");
      return;
    }
    if (!publicPage && admin && session.user.role !== "admin")
      throw new ApiError(403, "فقط مسئول مجاز خوابگاه به این بخش دسترسی دارد.");
    if (admin && !publicPage && !route.path.startsWith("admin/")) {
      router.navigate("admin/groups");
      return;
    }
    const ctx = {
      ...route,
      admin,
      config,
      navigate: router.navigate,
      reload: router.reload,
    };
    const renderer = publicPage ? authPage : renderers[route.parts[0]];
    if (!renderer) throw new ApiError(404, "صفحه پیدا نشد.");
    const content = await renderer(ctx);
    if (!route.isCurrent()) return;
    // Rebuild after initial identity resolves so the common shell contains the correct name.
    const destination = shell(route.path, publicPage);
    destination.replaceChildren(content);
    const title = destination.querySelector("h1");
    if (title) {
      document.title = `${title.textContent} — مچ‌شو`;
      title.focus({ preventScroll: true });
    } else destination.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" });
  } catch (error) {
    if (error.name === "AbortError" || !route.isCurrent()) return;
    const target = document.getElementById("main");
    target.replaceChildren(errorPanel(error, router.reload));
    target.focus({ preventScroll: true });
  }
});
router.start();
