import { api, post, ApiError } from "../api.js";
import { session } from "../session.js";
import {
  el,
  link,
  button,
  badge,
  notice,
  heading,
  card,
  avatar,
  items,
  date,
  statuses,
  pagination,
  empty,
  field,
  selectField,
  check,
  bindForm,
  announce,
  dialog,
} from "../ui.js";
const row = (...children) => el("div", { class: "row" }, ...children);
const requestReasons = {
  expired: "مهلت این دعوت به پایان رسیده است.",
  unavailable: "شرایط این دعوت دیگر برقرار نیست.",
  state_changed: "ترکیب یا شرایط پیشنهاد تغییر کرده است؛ دوباره بررسی کنید.",
  questionnaire_changed:
    "ترجیحات یکی از افراد تغییر کرده است؛ رضایت تازه لازم است.",
  account_changed: "وضعیت دسترسی یا رضایت یکی از افراد تغییر کرده است.",
  allocated: "تخصیص اتاق انجام شده و پذیرش تازه ممکن نیست.",
  policy_upgrade:
    "این دعوت مربوط به قواعد پیشین است. یک پیشنهاد تازه با رضایت فعلی ایجاد کنید.",
};
function person(user) {
  return row(
    avatar(user.name, user.id),
    el(
      "div",
      { class: "break" },
      el("strong", {}, user.name),
      el("div", { class: "small muted" }, user.class_name || "دانشجو"),
    ),
  );
}
function scoreView(score) {
  return el(
    "div",
    {},
    el(
      "div",
      { class: "score" },
      score === null || score === undefined
        ? "—"
        : Math.round(score).toLocaleString("fa-IR"),
      el("small", {}, score === null || score === undefined ? "" : "٪"),
    ),
    el("div", { class: "score-label" }, "هم‌خوانی ترجیحات"),
  );
}
function explanations(data) {
  return el(
    "div",
    { class: "row" },
    ...(data.explanations || []).map((x) =>
      badge(
        typeof x === "string" ? x : x.label || x.summary || "هم‌خوانی ترجیحات",
        "success",
      ),
    ),
  );
}
function params(ctx, limit = 12) {
  const p = new URLSearchParams(ctx.params);
  p.set("limit", limit);
  if (!p.has("page")) p.set("page", "1");
  return p.toString();
}
async function conflictReload(ctx, error) {
  if (error.status === 409 && !error.protocolMismatch) {
    document.querySelector("dialog[open]")?.close();
    announce("وضعیت تغییر کرده؛ اطلاعات تازه دریافت شد.");
    await ctx.reload();
  }
  throw error;
}
async function invite(ctx, profile) {
  const capacities = profile.capacities || [];
  dialog({
    title: "پیشنهاد تشکیل گروه",
    description: profile.group
      ? `درخواست پیوستن به گروه ${profile.group.members.map((u) => u.name).join("، ")}. عضویت به تأیید همهٔ اعضا نیاز دارد و اتاق رزرو نمی‌کند.`
      : `دعوت از ${profile.name}. ظرفیت انتخاب‌شده فقط با رضایت هر دو نفر معتبر است؛ ساخت گروه به معنی رزرو اتاق نیست.`,
    fields: [
      selectField(
        "ظرفیت مورد توافق",
        "capacity",
        capacities.map((c) => ({
          value: c,
          label: `${c.toLocaleString("fa-IR")} نفره`,
        })),
        capacities[0],
        { required: true },
      ),
    ],
    submitLabel: "ارسال درخواست",
    onSubmit: async (data) => {
      try {
        await post("/requests", {
          ...(profile.group
            ? { group_id: profile.group.id }
            : { receiver_id: profile.id }),
          capacity: Number(data.get("capacity")),
        });
        announce("درخواست ارسال شد. وضعیت را در درخواست‌ها دنبال کن.");
        ctx.navigate("requests");
      } catch (e) {
        await conflictReload(ctx, e);
      }
    },
  });
}
export async function homePage(ctx) {
  const results = await Promise.allSettled([
    api("/questionnaire/me", { signal: ctx.signal }),
    api("/group/me", { signal: ctx.signal }),
    api("/notifications?limit=3", { signal: ctx.signal }),
  ]);
  for (let i = 0; i < results.length; i++)
    if (
      results[i].status === "rejected" &&
      !(i === 1 && results[i].reason.status === 404)
    )
      throw results[i].reason;
  const q = results[0].value,
    g = results[1].value,
    n = results[2].value;
  const user = session.user;
  return el(
    "div",
    { class: "stack" },
    heading(
      `سلام ${user.name} 👋`,
      "اینجا مسیر انتخاب هم‌اتاقی و وضعیت گروهت را دنبال می‌کنی.",
    ),
    !user.discovery_consent
      ? notice(
          el(
            "span",
            {},
            "برای حضور در پیشنهادها، رضایت نمایش پروفایل را بررسی کن. ",
            link("تنظیم حریم خصوصی", "#account"),
          ),
        )
      : null,
    !q.complete
      ? notice(
          el(
            "span",
            {},
            "پرسشنامهٔ فعلی هنوز تکمیل نشده است. ",
            link("تکمیل عادت‌ها و ترجیحات", "#questionnaire"),
          ),
          "warning",
        )
      : null,
    el(
      "div",
      { class: "metric-grid" },
      card(
        el("span", { class: "small muted" }, "ترجیحات شما"),
        el("strong", { class: "metric-value" }, q.complete ? "کامل" : "ناتمام"),
        link("بررسی پاسخ‌ها", "#questionnaire"),
      ),
      card(
        el("span", { class: "small muted" }, "گروه شما"),
        el(
          "strong",
          { class: "metric-value" },
          g ? `${g.members.length} / ${g.capacity}` : "—",
        ),
        link(g ? "مشاهدهٔ گروه" : "پیداکردن همراه", g ? "#group" : "#matches"),
      ),
      card(
        el("span", { class: "small muted" }, "وضعیت اتاق"),
        el(
          "strong",
          { class: "metric-value" },
          g?.room ? "تخصیص‌یافته" : "در انتظار",
        ),
        link("جزئیات", "#group"),
      ),
    ),
    card(
      el(
        "div",
        { class: "row between" },
        el(
          "div",
          {},
          el("h2", {}, "همراه بعدی‌ات را بشناس"),
          el(
            "p",
            {},
            "فقط افراد و گروه‌هایی نمایش داده می‌شوند که امکان پیوستن به آن‌ها را داری.",
          ),
        ),
        link("دیدن پیشنهادها ←", "#matches", "button"),
      ),
    ),
    el(
      "div",
      { class: "row between" },
      el("h2", {}, "تازه‌ترین اعلان‌ها"),
      link("همهٔ اعلان‌ها", "#notifications"),
    ),
    items(n).length
      ? el(
          "div",
          { class: "stack" },
          ...items(n).map((x) => notificationCard(ctx, x)),
        )
      : empty(
          "هنوز اعلانی نداری",
          "تغییر درخواست‌ها، عضویت و تخصیص اتاق اینجا نمایش داده می‌شود.",
        ),
  );
}
export async function matchesPage(ctx) {
  const data = await api(`/matches?${params(ctx)}`, { signal: ctx.signal });
  return el(
    "div",
    {},
    heading(
      "همراه‌های پیشنهادی",
      "پیشنهادهای قابل‌پیوستن، بر پایهٔ رفتار و ترجیحات دوطرفه.",
      link("ویرایش ترجیحات", "#questionnaire", "button secondary"),
    ),
    el(
      "div",
      { class: "notice" },
      "درصد، شاخص هم‌خوانی ترجیحات است و موفقیت هم‌اتاقی را تضمین نمی‌کند. توضیح‌های کلی فقط با رضایت افراد نمایش داده می‌شوند.",
    ),
    el("div", { class: "divider" }),
    items(data).length
      ? el(
          "div",
          { class: "match-grid" },
          ...items(data).map((item) =>
            el(
              "article",
              { class: "card match-card" },
              el(
                "div",
                { class: "row between" },
                person(item.user),
                badge(
                  item.kind === "group"
                    ? `گروه ${item.group.members.length} نفره`
                    : "بدون گروه",
                  item.kind === "group" ? "blue" : "",
                ),
              ),
              item.group &&
                el(
                  "p",
                  { class: "small muted" },
                  item.group.members.map((u) => u.name).join("، "),
                ),
              explanations(item),
              el(
                "div",
                { class: "card-footer" },
                scoreView(item.score),
                link(
                  "شناخت بیشتر ←",
                  `#profile/${item.user.id}`,
                  "button secondary",
                ),
              ),
            ),
          ),
        )
      : empty(
          "فعلاً پیشنهاد قابل‌پیوستنی نیست",
          "با کامل‌شدن پرسشنامهٔ دانشجویان یا تغییر ظرفیت، پیشنهادهای تازه نمایش داده می‌شوند.",
          link("بررسی ترجیحات", "#questionnaire", "button"),
        ),
    pagination(data, "matches", ctx.params),
  );
}
export async function profilePage(ctx) {
  const id = ctx.parts[1];
  if (!/^\d+$/.test(id || "")) throw new ApiError(404, "شناسهٔ نامعتبر");
  const p = await api(`/profiles/${id}`, { signal: ctx.signal });
  const block = () =>
    dialog({
      title: "مسدودکردن ارتباط",
      description: `با ${p.name} پیشنهاد یا دعوت تازه‌ای ردوبدل نمی‌شود و دعوت‌های باز مرتبط بسته می‌شوند. عضویت و اتاق فعلی خودکار تغییر نمی‌کنند.`,
      submitLabel: "مسدودکردن",
      danger: true,
      onSubmit: async () => {
        await post(`/me/blocks/${p.id}`);
        announce("ارتباط مسدود شد.");
        ctx.navigate("account");
      },
    });
  const report = () =>
    dialog({
      title: "گزارش به مسئول خوابگاه",
      description:
        "نام و متن گزارش شما به فرد گزارش‌شده نمایش داده نمی‌شود. گزارش، درخواست بررسی است.",
      fields: [
        selectField("موضوع", "category", [
          { value: "harassment", label: "مزاحمت" },
          { value: "identity", label: "اشکال هویتی" },
          { value: "other", label: "سایر" },
        ]),
        field("شرح گزارش", "description", {
          type: "textarea",
          required: true,
          maxlength: 2000,
        }),
      ],
      submitLabel: "ثبت گزارش",
      onSubmit: async (data) => {
        const result = await post("/me/reports", {
          target_id: p.id,
          ...Object.fromEntries(data),
        });
        announce(
          `گزارش ثبت شد. پیگیری: ${result.reference || result.id || ""}`,
        );
      },
    });
  return el(
    "div",
    { class: "stack" },
    heading(
      "شناخت هم‌اتاقی",
      "فقط اطلاعاتی که اجازهٔ مشاهدهٔ آن را داری.",
      link("بازگشت به پیشنهادها", "#matches", "button secondary"),
    ),
    card(
      el("div", { class: "row between" }, person(p), scoreView(p.score)),
      el("div", { class: "divider" }),
      explanations(p),
      p.group &&
        el(
          "div",
          {},
          el("h3", {}, `اعضای گروه · ظرفیت ${p.group.capacity} نفر`),
          el("div", { class: "stack" }, ...p.group.members.map(person)),
        ),
      notice(
        "پاسخ‌های پرسشنامه، ایمیل و شمارهٔ دانشجویی خصوصی هستند. دعوت‌کردن یا هم‌گروه‌شدن این اطلاعات را آشکار نمی‌کند.",
      ),
      el(
        "div",
        { class: "form-actions" },
        p.can_invite
          ? button(
              p.group ? "درخواست پیوستن به گروه" : "دعوت به تشکیل گروه",
              () => invite(ctx, p),
            )
          : notice("این پروفایل در حال حاضر برای دعوت تازه در دسترس نیست."),
        button("گزارش", report, "secondary"),
        button("مسدودکردن", block, "secondary"),
      ),
    ),
  );
}
export async function requestsPage(ctx) {
  const data = await api(`/requests?${params(ctx)}`, { signal: ctx.signal });
  const focusId = ctx.params.get("id");
  const cards = items(data).map((request) => {
    const actions = el("div", { class: "form-actions" });
    for (const [action, label, flag, style] of [
      ["approve", "تأیید این پیشنهاد", "can_approve", ""],
      ["reconfirm", "بازبینی و تأیید دوباره", "can_reconfirm", ""],
      ["reject", "رد پیشنهاد", "can_reject", "secondary"],
      ["cancel", "لغو درخواست من", "can_cancel", "secondary"],
    ])
      if (request[flag])
        actions.append(
          button(
            label,
            () =>
              dialog({
                title: label,
                description: `${request.initiator.name} و ${request.candidate.name}${request.group ? "؛ اعضای گروه: " + request.group.members.map((x) => x.name).join("، ") : ""}. ظرفیت ${request.capacity} نفر. ${action === "reconfirm" ? "ترکیب و ترجیحات تغییر کرده‌اند؛ تأییدهای قبلی معتبر نیستند. همهٔ افراد باید پیشنهاد تازه را تأیید کنند." : action === "approve" ? "این اقدام رضایت شما را ثبت می‌کند. عضویت پس از تأیید همه و بررسی شرایط نهایی می‌شود." : "این تصمیم عضویت پذیرفته‌شدهٔ قبلی را تغییر نمی‌دهد."}`,
                submitLabel: label,
                onSubmit: async () => {
                  try {
                    await post(`/requests/${request.id}/${action}`);
                    announce("تصمیم ثبت شد.");
                    await ctx.reload();
                  } catch (e) {
                    await conflictReload(ctx, e);
                  }
                },
              }),
            style,
          ),
        );
    return el(
      "article",
      { class: "card stack", id: `request-${request.id}` },
      el(
        "div",
        { class: "row between" },
        el(
          "h2",
          {},
          request.initiator.id === session.user.id
            ? `درخواست به ${request.candidate.name}`
            : `پیشنهاد ${request.initiator.name}`,
        ),
        badge(
          statuses[request.status] || request.status,
          request.status === "accepted" ? "success" : "blue",
        ),
      ),
      el(
        "div",
        { class: "row" },
        badge(`${request.capacity} نفره`),
        badge(
          `${request.approvals.length} از ${request.required_approvals.length} رضایت`,
        ),
      ),
      request.group &&
        el(
          "p",
          { class: "small" },
          "اعضای فعلی: " + request.group.members.map((x) => x.name).join("، "),
        ),
      el(
        "p",
        { class: "small muted" },
        "مهلت اصلی: " + date(request.expires_at),
      ),
      request.reason &&
        notice(
          requestReasons[request.reason] ||
            "شرایط این دعوت تغییر کرده است. وضعیت فعلی و اقدامات مجاز را بررسی کنید.",
          "warning",
        ),
      request.status === "needs_reconfirmation" &&
        notice(
          "تغییری در عضویت یا ترجیحات رخ داده؛ پیشنهاد تازه را پیش از تأیید بررسی کنید.",
          "warning",
        ),
      actions,
    );
  });
  const result = el(
    "div",
    { class: "stack" },
    heading(
      "درخواست‌ها",
      "پیشنهاد، ظرفیت و رضایت افراد را پیش از تصمیم بررسی کن.",
    ),
    cards.length
      ? cards
      : empty(
          "هنوز درخواستی نیست",
          "از میان پیشنهادهای قابل‌پیوستن، یک نفر یا یک گروه را انتخاب کن.",
          link("دیدن پیشنهادها", "#matches", "button"),
        ),
    pagination(data, "requests", ctx.params),
  );
  if (focusId)
    setTimeout(
      () =>
        document
          .getElementById(`request-${focusId}`)
          ?.scrollIntoView({ block: "center" }),
      0,
    );
  return result;
}
export async function groupPage(ctx) {
  let group;
  try {
    group = await api("/group/me", { signal: ctx.signal });
  } catch (error) {
    if (error.status === 404)
      return el(
        "div",
        {},
        heading("گروه من", "عضویت و تخصیص اتاق"),
        empty(
          "هنوز عضو گروهی نیستی",
          "با دعوت و پذیرش یک پیشنهاد مشترک، گروه تشکیل می‌شود.",
          link("انتخاب هم‌اتاقی", "#matches", "button"),
        ),
      );
    throw error;
  }
  const leave = () =>
    dialog({
      title: group.room ? "درخواست خروج فردی" : "خروج از گروه",
      description: group.room
        ? "فقط خروج شما برای بررسی مسئول خوابگاه ثبت می‌شود. جای دیگر اعضا محفوظ است و تا تأیید مسئول، تخصیص شما برقرار می‌ماند."
        : "فقط عضویت شما پایان می‌یابد. اعضای دیگر باقی می‌مانند و تأییدهای دعوت‌های باز نیازمند بازبینی می‌شوند.",
      fields: group.room
        ? [
            field("دلیل درخواست خروج", "reason", {
              type: "textarea",
              required: true,
              maxlength: 1000,
            }),
          ]
        : [],
      submitLabel: group.room ? "ثبت درخواست بررسی" : "خروج از گروه",
      danger: true,
      onSubmit: async (data) => {
        if (group.room)
          await post("/group/me/departure", Object.fromEntries(data));
        else await api("/group/me", { method: "DELETE" });
        announce(
          group.room ? "درخواست خروج برای بررسی ثبت شد." : "از گروه خارج شدی.",
        );
        await ctx.reload();
      },
    });
  return el(
    "div",
    { class: "stack" },
    heading(
      "گروه من",
      `ظرفیت مورد توافق: ${group.capacity} نفر. تشکیل گروه به معنی رزرو اتاق نیست.`,
      !group.room && group.members.length < group.capacity
        ? link("دعوت همراه جدید", "#matches", "button")
        : null,
    ),
    el(
      "div",
      { class: "grid" },
      card(
        el("span", { class: "eyebrow" }, "ترکیب فعلی"),
        el("h2", {}, `${group.members.length} نفر از ${group.capacity} نفر`),
        el("div", { class: "divider" }),
        el(
          "div",
          { class: "stack" },
          ...group.members.map((u) =>
            row(
              person(u),
              u.id === session.user.id
                ? badge("شما")
                : link("مشاهده", `#profile/${u.id}`),
            ),
          ),
        ),
      ),
      card(
        el("span", { class: "eyebrow" }, "وضعیت تخصیص"),
        el(
          "h2",
          {},
          group.room ? `اتاق ${group.room.number}` : "هنوز اتاقی تخصیص نیافته",
        ),
        el(
          "p",
          {},
          group.room
            ? group.room.dormitory
            : "مسئول خوابگاه پس از بررسی شرایط، اتاق گروه را تخصیص می‌دهد.",
        ),
        group.room && badge("تخصیص تأییدشده", "success"),
      ),
    ),
    group.departure &&
      notice(
        `درخواست خروج فردی شما: ${statuses[group.departure.status] || group.departure.status}`,
        "warning",
      ),
    card(
      el(
        "h3",
        {},
        group.room
          ? "نیاز به خروج یا اصلاح تخصیص داری؟"
          : "تغییر در تصمیم گروه",
      ),
      el(
        "p",
        {},
        "خروج یک فرد، مجوز آزادکردن اتاق همهٔ اعضا نیست. مشکلات تخصیص را از پشتیبانی پیگیری کن.",
      ),
      el(
        "div",
        { class: "form-actions" },
        !group.departure &&
          button(
            group.room ? "درخواست خروج فردی" : "خروج از گروه",
            leave,
            "secondary",
          ),
        link("پشتیبانی و پیگیری", "#support", "button secondary"),
      ),
    ),
  );
}
function notificationCard(ctx, n) {
  const targets = {
    request: `#requests?id=${n.entity_id}`,
    invitation: `#requests?id=${n.entity_id}`,
    group: "#group",
    allocation: "#group",
    departure: "#support",
    case: "#support",
    support: "#support",
  };
  return el(
    "article",
    { class: `card notification ${n.read ? "" : "unread"}` },
    el("span", { class: "avatar", "aria-hidden": "true" }, n.read ? "✓" : "•"),
    el(
      "div",
      { class: "break" },
      el("p", {}, n.message),
      el("time", { datetime: n.created_at }, date(n.created_at)),
      el(
        "div",
        { class: "form-actions" },
        link("مشاهدهٔ وضعیت فعلی", targets[n.entity_type] || "#home"),
        !n.read &&
          button(
            "خوانده شد",
            async () => {
              try {
                await post(`/notifications/${n.id}/read`);
                await ctx.reload();
              } catch (e) {
                announce(e.message);
              }
            },
            "plain",
          ),
      ),
    ),
  );
}
export async function notificationsPage(ctx) {
  const data = await api(`/notifications?${params(ctx)}`, {
    signal: ctx.signal,
  });
  return el(
    "div",
    { class: "stack" },
    heading(
      "اعلان‌ها",
      "زمان‌ها به وقت تهران نمایش داده می‌شوند. خواندن اعلان، تصمیمی دربارهٔ درخواست نیست.",
    ),
    items(data).length
      ? items(data).map((n) => notificationCard(ctx, n))
      : empty(
          "اعلان تازه‌ای نداری",
          "تصمیم‌ها و تغییرهای مربوط به حسابت اینجا ثبت می‌شوند.",
        ),
    pagination(data, "notifications", ctx.params),
  );
}
export async function accountPage(ctx) {
  const [sessions, blocks] = await Promise.all([
    api("/auth/sessions", { signal: ctx.signal }),
    api("/me/blocks", { signal: ctx.signal }),
  ]);
  const user = session.user;
  const profile = el(
    "form",
    { class: "stack" },
    el("h2", {}, "اطلاعات حساب"),
    el(
      "div",
      { class: "form-grid" },
      field("نام نمایشی", "name", {
        value: user.name,
        required: true,
        maxlength: 100,
      }),
      field("رشته یا مقطع", "class_name", {
        value: user.class_name,
        required: true,
        maxlength: 100,
      }),
    ),
    el(
      "p",
      { class: "small muted" },
      el("bdi", { dir: "ltr" }, user.email),
      " · شمارهٔ دانشجویی ",
      el("bdi", { dir: "ltr" }, user.student_id),
    ),
    el(
      "p",
      { class: "small muted" },
      "اطلاعات هویتی یا خوابگاهی نادرست را از ",
      link("درخواست اصلاح", "#support"),
      " پیگیری کن.",
    ),
    el("button", { type: "submit" }, "ذخیرهٔ اطلاعات"),
  );
  bindForm(profile, async (data) => {
    await api("/me/profile", {
      method: "PATCH",
      body: Object.fromEntries(data),
    });
    await session.load();
    announce("اطلاعات حساب ذخیره شد.");
  });
  const consent = el(
    "form",
    { class: "stack" },
    el("h2", {}, "انتخاب‌های حریم خصوصی"),
    check(
      "نمایش نام، رشته و شاخص کلی هم‌خوانی من به هم‌اتاقی‌های مجاز را می‌پذیرم.",
      "discovery",
      user.discovery_consent,
    ),
    check(
      "نمایش توضیح‌های کلی و غیرحساس دربارهٔ هم‌خوانی را می‌پذیرم؛ فقط وقتی هر دو طرف رضایت دارند.",
      "explanations",
      user.explanation_consent,
    ),
    notice(
      "پاسخ‌های خام، ایمیل و شمارهٔ دانشجویی هرگز به هم‌اتاقی‌ها نمایش داده نمی‌شوند. لغو رضایت، پیشنهادهای تازه را متوقف و رضایت دعوت‌های وابسته را نامعتبر می‌کند.",
    ),
    link("سیاست حریم خصوصی", "/privacy.html"),
    el("button", { type: "submit" }, "ذخیرهٔ انتخاب‌ها"),
  );
  bindForm(consent, async (data) => {
    await api("/me/consent", {
      method: "PATCH",
      body: {
        discovery: data.has("discovery"),
        explanations: data.has("explanations"),
      },
    });
    await session.load();
    announce("انتخاب‌های حریم خصوصی ذخیره شد.");
  });
  function revoke(sid) {
    dialog({
      title: "بستن نشست",
      description:
        "دسترسی این نشست فوراً قطع می‌شود. برای استفادهٔ دوباره باید وارد شوید.",
      submitLabel: "بستن نشست",
      onSubmit: async () => {
        await api(`/auth/sessions/${encodeURIComponent(sid)}`, {
          method: "DELETE",
        });
        await ctx.reload();
      },
    });
  }
  function closure(remove) {
    dialog({
      title: remove ? "درخواست حذف حساب" : "انصراف از دوره",
      description:
        "پروفایل شما از پیشنهادها خارج و نشست‌ها بسته می‌شوند. اگر اتاق دارید، خروج فردی باید توسط مسئول تأیید شود. حذف داده پس از انجام این فرایند و طبق سیاست نگهداری انجام می‌شود.",
      fields: [
        field("دلیل یا توضیح", "reason", { type: "textarea", maxlength: 1000 }),
      ],
      submitLabel: remove ? "ثبت درخواست حذف" : "ثبت انصراف",
      danger: true,
      onSubmit: async (data) => {
        await post("/me/closure", {
          delete: remove,
          reason: data.get("reason"),
        });
        session.clear();
        announce("درخواست ثبت و دسترسی حساب بسته شد.");
        ctx.navigate("login");
      },
    });
  }
  const emailPreference = el(
    "form",
    { class: "stack" },
    el("h2", {}, "اعلان‌های ایمیلی"),
    check(
      "تصمیم‌های گروه و اتاق از طریق ایمیل هم اطلاع‌رسانی شوند.",
      "email",
      user.notification_email,
    ),
    el(
      "p",
      { class: "small muted" },
      ctx.config.email_verification_required
        ? "پیام‌های ضروری امنیتی و بازیابی حساب همیشه ارسال می‌شوند."
        : "فعال‌سازی و بازیابی ایمیلی فعلاً غیرفعال است.",
    ),
    el("button", { type: "submit" }, "ذخیرهٔ ترجیح ایمیل"),
  );
  bindForm(emailPreference, async (data) => {
    await api("/me/notification-preference", {
      method: "PATCH",
      body: { email: data.has("email") },
    });
    await session.load();
    announce("ترجیح ایمیل ذخیره شد.");
  });
  return el(
    "div",
    { class: "stack" },
    heading(
      "حساب و حریم خصوصی",
      "اطلاعات، رضایت‌ها و دستگاه‌های متصل را مدیریت کن.",
    ),
    card(profile),
    card(consent),
    user.email_verified === true && card(emailPreference),
    card(
      el("h2", {}, "نشست‌های فعال"),
      el(
        "div",
        { class: "stack" },
        ...items(sessions).map((s) =>
          el(
            "div",
            { class: "row between" },
            el(
              "div",
              { class: "break" },
              el("strong", {}, s.device || "مرورگر"),
              s.current && badge("این دستگاه", "blue"),
              el(
                "div",
                { class: "small muted" },
                "آخرین فعالیت: " + date(s.last_used_at || s.created_at),
              ),
            ),
            button("بستن نشست", () => revoke(s.sid), "secondary"),
          ),
        ),
      ),
      button(
        "بستن تمام نشست‌ها",
        () =>
          dialog({
            title: "بستن تمام نشست‌ها",
            description: "از این دستگاه و همهٔ دستگاه‌های دیگر خارج می‌شوید.",
            submitLabel: "خروج از همه",
            onSubmit: async () => {
              await api("/auth/sessions", { method: "DELETE" });
              session.clear();
              ctx.navigate("login");
            },
          }),
        "secondary",
      ),
    ),
    card(
      el("h2", {}, "ارتباط‌های مسدودشده"),
      items(blocks).length
        ? items(blocks).map((b) =>
            el(
              "div",
              { class: "row between" },
              el("span", {}, b.name),
              button(
                "رفع مسدودی",
                async () => {
                  try {
                    await api(`/me/blocks/${b.user_id}`, { method: "DELETE" });
                    await ctx.reload();
                  } catch (e) {
                    announce(e.message);
                  }
                },
                "secondary",
              ),
            ),
          )
        : el("p", {}, "ارتباط مسدودشده‌ای ندارید."),
    ),
    card(
      el("h2", {}, "انصراف و حذف حساب"),
      el(
        "p",
        {},
        "خروج عملیاتی از اتاق توسط مسئول بررسی می‌شود و به جای دیگر اعضا آسیب نمی‌زند.",
      ),
      el(
        "div",
        { class: "form-actions" },
        button("انصراف از دوره", () => closure(false), "secondary"),
        button("درخواست حذف حساب", () => closure(true), "secondary"),
      ),
    ),
  );
}
export async function supportPage(ctx) {
  const [cases, departures] = await Promise.all([
    api("/me/cases", { signal: ctx.signal }),
    api("/departures/me", { signal: ctx.signal }),
  ]);
  const form = el(
    "form",
    { class: "stack" },
    el("h2", {}, "درخواست تازه"),
    selectField("نوع درخواست", "type", [
      { value: "technical", label: "مشکل فنی" },
      { value: "correction", label: "اصلاح اطلاعات هویتی یا خوابگاهی" },
      { value: "other", label: "سایر درخواست‌ها" },
    ]),
    selectField("در صورت اصلاح، کدام اطلاعات؟", "field", [
      { value: "email", label: "ایمیل" },
      { value: "student_id", label: "شمارهٔ دانشجویی" },
      { value: "pool", label: "گروه مجاز خوابگاه" },
      { value: "cycle", label: "دوره" },
      { value: "other", label: "سایر" },
    ]),
    field("شرح درخواست", "description", {
      type: "textarea",
      required: true,
      minlength: 5,
      maxlength: 2000,
      hint: "رمز عبور، کد ورود و پاسخ‌های حساس را در متن ننویس.",
    }),
    el("button", { type: "submit" }, "ثبت و دریافت شمارهٔ پیگیری"),
  );
  bindForm(form, async (data) => {
    const result =
      data.get("type") === "correction"
        ? await post("/me/corrections", {
            field: data.get("field"),
            description: data.get("description"),
          })
        : await post("/me/reports", {
            category: data.get("type"),
            description: data.get("description"),
          });
    announce(
      `درخواست ثبت شد. شمارهٔ پیگیری: ${result.reference || result.id || ""}`,
    );
    await ctx.reload();
  });
  return el(
    "div",
    { class: "stack" },
    heading(
      "پشتیبانی و پیگیری",
      "درخواست‌ها توسط مسئول دانشگاه یا خوابگاه بررسی می‌شوند.",
    ),
    ctx.config.support_contact &&
      notice(`مسیر پشتیبانی مؤسسه: ${ctx.config.support_contact}`),
    card(form),
    items(departures).length
      ? card(
          el("h2", {}, "پیگیری خروج از گروه"),
          ...items(departures).map((d) =>
            el(
              "div",
              {},
              badge(statuses[d.status] || d.status),
              el("p", {}, d.reason),
              d.resolution && el("p", {}, d.resolution),
            ),
          ),
        )
      : null,
    el("h2", {}, "درخواست‌های من"),
    items(cases).length
      ? items(cases).map((c) =>
          card(
            el(
              "div",
              { class: "row between" },
              el("strong", {}, `پیگیری ${c.reference || c.id}`),
              badge(statuses[c.status] || c.status),
            ),
            el("p", {}, c.description),
            el("small", { class: "muted" }, date(c.created_at)),
            c.resolution && notice(c.resolution, "success"),
          ),
        )
      : empty(
          "درخواستی ثبت نشده",
          "در صورت نیاز از فرم بالا برای تماس با مسئول استفاده کن.",
        ),
  );
}
