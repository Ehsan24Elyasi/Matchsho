import { api, post } from "../api.js";
import {
  el,
  heading,
  card,
  field,
  selectField,
  button,
  link,
  notice,
  badge,
  items,
  date,
  statuses,
  pagination,
  empty,
  bindForm,
  dialog,
  announce,
} from "../ui.js";
const resources = {
  groups: "گروه‌ها و تخصیص",
  rooms: "اتاق‌ها",
  users: "دانشجویان",
  roster: "فهرست مجاز",
  cases: "پشتیبانی و گزارش‌ها",
  departures: "درخواست‌های خروج",
  requests: "دعوت‌ها",
  audit: "تاریخچهٔ عملیات",
  outbox: "تحویل ایمیل",
};
function table(headers, rows) {
  return el(
    "div",
    { class: "table-scroll", tabindex: "0", "aria-label": "جدول قابل پیمایش" },
    el(
      "table",
      {},
      el(
        "thead",
        {},
        el("tr", {}, ...headers.map((h) => el("th", { scope: "col" }, h))),
      ),
      el(
        "tbody",
        {},
        ...rows.map((cells) =>
          el("tr", {}, ...cells.map((c) => el("td", {}, c))),
        ),
      ),
    ),
  );
}
function reasonField() {
  return field("دلیل عملیات", "reason", {
    type: "textarea",
    required: true,
    minlength: 5,
    maxlength: 1000,
  });
}
async function userRecord(user) {
  const record = await api(`/admin/users/${user.id}`);
  const body = el(
    "div",
    { class: "stack" },
    el(
      "p",
      {},
      `دانشجو: ${record.name} · وضعیت: ${statuses[record.account_status] || record.account_status}`,
    ),
    el(
      "p",
      {},
      `گروه فعلی: ${record.group_id || "ندارد"} · اتاق فعلی: ${record.room_id || "ندارد"}`,
    ),
    record.enrollment &&
      el(
        "p",
        {},
        `گروه مجاز: ${record.enrollment.pool} · دوره: ${record.enrollment.cycle}`,
      ),
    el("h3", {}, "تاریخچهٔ تخصیص"),
    record.allocation_history.length
      ? table(
          ["گروه / اتاق", "شروع", "پایان"],
          record.allocation_history.map((a) => [
            `${a.group_id} / ${a.room_id}`,
            date(a.opened_at),
            a.closed_at ? date(a.closed_at) : "فعال",
          ]),
        )
      : el("p", {}, "سابقهٔ تخصیصی ندارد."),
    el("h3", {}, "خروج‌های فردی"),
    ...record.departures.map((d) =>
      el(
        "div",
        {},
        badge(statuses[d.status] || d.status),
        el("p", {}, d.reason),
        d.resolution && el("p", {}, d.resolution),
      ),
    ),
  );
  dialog({
    title: "پروندهٔ عملیاتی دانشجو",
    description: body,
    submitLabel: "بستن پرونده",
    onSubmit: async () => {},
  });
}
function mutations(ctx, path, method, values, message) {
  return api(path, { method, body: values })
    .then(async () => {
      announce(message);
      await ctx.reload();
    })
    .catch(async (error) => {
      if (error.status === 409 && !error.protocolMismatch) {
        document.querySelector("dialog[open]")?.close();
        await ctx.reload();
        announce(
          "وضعیت تغییر کرده است. اطلاعات تازه را بررسی و عملیات را دوباره آغاز کنید.",
        );
      }
      throw error;
    });
}
function reasonDialog(ctx, title, description, path, method, extra = {}) {
  dialog({
    title,
    description,
    fields: [reasonField()],
    submitLabel: "ثبت تصمیم",
    onSubmit: (data) =>
      mutations(
        ctx,
        path,
        method,
        { ...extra, reason: data.get("reason") },
        "تصمیم ثبت شد.",
      ),
  });
}
export function parseCSV(text) {
  const rows = [];
  let row = [],
    cell = "",
    quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') {
      if (quoted && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else quoted = !quoted;
    } else if (c === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((c === "\n" || c === "\r") && !quoted) {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(cell);
      if (row.some((x) => x.trim())) rows.push(row);
      row = [];
      cell = "";
    } else cell += c;
  }
  if (quoted) throw new Error("علامت نقل‌قول فایل CSV بسته نشده است.");
  row.push(cell);
  if (row.some((x) => x.trim())) rows.push(row);
  if (!rows.length) throw new Error("فایل خالی است.");
  const headers = rows.shift().map((x) => x.trim().replace(/^\uFEFF/, ""));
  const required = [
    "student_id",
    "email",
    "name",
    "class_name",
    "gender",
    "pool",
    "cycle",
  ];
  if (required.some((k) => !headers.includes(k)))
    throw new Error(
      "ستون‌های فایل باید شامل " + required.join(", ") + " باشند.",
    );
  return rows.map((values, index) => {
    if (values.length !== headers.length)
      throw new Error(`تعداد ستون‌ها در ردیف ${index + 2} نادرست است.`);
    return Object.fromEntries(headers.map((h, i) => [h, values[i].trim()]));
  });
}
async function rosterImport(ctx) {
  let validated = null;
  let validatedReason = "";
  let validatedRebind = false;
  const file = field("فایل CSV فهرست دانشگاه", "roster", {
    type: "file",
    accept: ".csv,text/csv",
    required: true,
    hint: "ستون‌ها: student_id,email,name,class_name,gender,pool,cycle. gender برابر male یا female.",
  });
  const output = el("div", { class: "stack" });
  const commit = button("ثبت فهرست تأییدشده", async () => {
    if (!validated) return;
    commit.disabled = true;
    try {
      await post("/admin/roster/import", {
        rows: validated,
        dry_run: false,
        reason: validatedReason,
        allow_legacy_email_rebind: validatedRebind,
      });
      announce("فهرست مجاز ثبت شد.");
      node.close();
      await ctx.reload();
    } catch (e) {
      output.append(notice(e.message, "error"));
      commit.disabled = false;
    }
  });
  commit.hidden = true;
  const node = dialog({
    title: "ورود فهرست مجاز",
    closeOnSubmit: false,
    description:
      "ابتدا فایل را بررسی کن. تا تأیید نهایی هیچ ردیفی ثبت نمی‌شود؛ فایل خام در مرورگر بارگذاری و به ردیف‌های داده تبدیل می‌شود.",
    fields: [
      file,
      reasonField(),
      el(
        "label",
        { class: "check-label" },
        el("input", { type: "checkbox", name: "allow_legacy_email_rebind" }),
        el(
          "span",
          {},
          "تأیید تطبیق ایمیل دانشجویان قدیمیِ تأییدنشده با فهرست رسمی؛ این انتخاب فقط پس از بررسی مسئول مجاز فعال شود.",
        ),
      ),
      output,
      commit,
    ],
    submitLabel: "پیش‌نمایش و بررسی",
    onSubmit: async (data) => {
      const selected = data.get("roster");
      if (selected.size > 2 * 1024 * 1024)
        throw new Error("حجم فایل باید کمتر از ۲ مگابایت باشد.");
      const raw = await selected.text();
      const rows = parseCSV(raw);
      const result = await post("/admin/roster/import", {
        rows,
        dry_run: true,
        reason: data.get("reason"),
        allow_legacy_email_rebind: data.has("allow_legacy_email_rebind"),
      });
      output.replaceChildren(
        notice(
          `پیش‌نمایش ${rows.length} ردیف آماده شد. پیش از ثبت، خطاها را بررسی کنید.`,
        ),
        el("pre", { class: "small break" }, JSON.stringify(result, null, 2)),
      );
      const errors = result.errors || [];
      validated = errors.length ? null : rows;
      validatedReason = data.get("reason");
      validatedRebind = data.has("allow_legacy_email_rebind");
      commit.hidden = !validated;
      if (errors.length)
        throw new Error("فایل دارای خطاست؛ اصلاح و دوباره بارگذاری کنید.");
      announce(
        "پیش‌نمایش آماده است. نتیجه را بررسی و ثبت نهایی را انتخاب کنید.",
      );
    },
  });
  node.querySelectorAll("input,textarea").forEach((control) =>
    control.addEventListener("input", () => {
      validated = null;
      commit.hidden = true;
      output.replaceChildren();
    }),
  );
}
function reconcileGroup(ctx, group) {
  dialog({
    title: "بازبینی سیاست گروه",
    description:
      "اعضا: " +
      group.members.map((m) => m.name).join("، ") +
      ". ظرفیت مورد توافق " +
      group.capacity +
      " حفظ می‌شود. ابتدا هویت و گروه خوابگاهی همهٔ اعضا باید بررسی شده باشد.",
    fields: [
      field("گروه مجاز خوابگاهی", "pool", {
        value: group.pool || "",
        required: true,
      }),
      field("دوره", "cycle", {
        value: group.cycle || ctx.config.cycle || ctx.config.active_cycle || "",
        required: true,
      }),
      reasonField(),
    ],
    submitLabel: "ثبت بازبینی",
    onSubmit: (data) =>
      mutations(
        ctx,
        `/admin/groups/${group.id}/reconcile`,
        "POST",
        { ...Object.fromEntries(data), capacity: group.capacity },
        "سیاست گروه بازبینی شد.",
      ),
  });
}
function roomDialog(ctx, room, config) {
  const edit = Boolean(room);
  dialog({
    title: edit ? `ویرایش اتاق ${room.number}` : "اتاق تازه",
    description:
      "ظرفیت و گروه مجاز باید با تخصیص موجود سازگار باشد. تغییر نام یا ظرفیت، افراد را خودکار جابه‌جا نمی‌کند.",
    fields: [
      field("شمارهٔ اتاق", "number", {
        required: true,
        maxlength: 30,
        value: room?.number || "",
      }),
      field("نام خوابگاه", "dormitory", {
        required: true,
        maxlength: 100,
        value: room?.dormitory || "",
      }),
      field("ظرفیت فیزیکی", "capacity", {
        type: "number",
        required: true,
        min: 1,
        max: 20,
        value: room?.capacity || "",
      }),
      field("گروه مجاز خوابگاهی", "pool", {
        required: true,
        maxlength: 100,
        value: room?.pool || "",
      }),
      field("دوره", "cycle", {
        required: true,
        maxlength: 100,
        value: room?.cycle || config?.cycle || config?.active_cycle || "",
      }),
      reasonField(),
    ],
    submitLabel: "ثبت اتاق",
    onSubmit: (data) =>
      mutations(
        ctx,
        edit ? `/admin/rooms/${room.id}` : "/admin/rooms",
        edit ? "PATCH" : "POST",
        { ...Object.fromEntries(data), capacity: Number(data.get("capacity")) },
        "اتاق ذخیره شد.",
      ),
  });
}
async function allocate(ctx, group) {
  const rooms = [];
  let page = 1;
  while (true) {
    const response = await api(`/admin/rooms?limit=50&page=${page}`);
    rooms.push(...items(response));
    if (rooms.length >= response.total || items(response).length < 50) break;
    page++;
  }
  const eligible = rooms.filter(
    (r) =>
      Number(r.capacity) === Number(group.capacity) &&
      (!r.current_occupancy || r.id === group.room?.id),
  );
  const description = el(
    "div",
    {},
    el(
      "p",
      {},
      "اعضای تحت تأثیر: " + group.members.map((m) => m.name).join("، "),
    ),
    el(
      "p",
      {},
      `تعداد اعضای واقعی: ${group.members.length}، ظرفیت مورد توافق: ${group.capacity}. اتاق فعلی: ${group.room ? group.room.number : "ندارد"}.`,
    ),
    notice(
      "در جابه‌جایی، تخصیص قبلی و مقصد در یک عملیات تغییر می‌کنند. شرایط خوابگاه دوباره در سرور بررسی می‌شود.",
    ),
  );
  dialog({
    title: "تخصیص یا اصلاح اتاق گروه",
    description,
    fields: [
      selectField(
        "اتاق مقصد و ظرفیت",
        "room_id",
        eligible.map((r) => ({
          value: r.id,
          label: `${r.dormitory} · اتاق ${r.number} · ظرفیت ${r.capacity} · اشغال پس از عمل ${group.members.length}`,
        })),
        undefined,
        { required: true },
      ),
      reasonField(),
    ],
    submitLabel: "تأیید تخصیص این اعضا",
    onSubmit: (data) =>
      mutations(
        ctx,
        `/admin/groups/${group.id}/allocation`,
        "POST",
        { room_id: Number(data.get("room_id")), reason: data.get("reason") },
        "تخصیص اتاق ثبت شد.",
      ),
  });
}
async function exportCSV(resource) {
  const response = await fetch(`/api/admin/export?resource=${resource}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    announce("دریافت خروجی انجام نشد. دوباره تلاش کنید.");
    return;
  }
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `matchsho-${resource}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
export async function adminPage(ctx) {
  const resource = ctx.parts[1] || "groups";
  if (!Object.hasOwn(resources, resource))
    throw new Error("صفحهٔ مدیریت پیدا نشد.");
  const page = Math.max(1, Number(ctx.params.get("page") || 1)),
    limit = 20;
  const query = new URLSearchParams(ctx.params);
  query.set("page", page);
  query.set("limit", limit);
  query.set("offset", (page - 1) * limit);
  const data = await api(
    `/admin/${resource === "outbox" ? "delivery" : resource}?${query}`,
    { signal: ctx.signal },
  );
  const entries = items(data);
  const deliveryHealth =
    resource === "outbox"
      ? await api("/admin/delivery/health", { signal: ctx.signal })
      : null;
  const filter = el(
    "form",
    { class: "filter-form" },
    field("جست‌وجو", "q", {
      value: ctx.params.get("q") || "",
      placeholder: "نام، شناسه یا عبارت موردنظر",
    }),
    el("button", { type: "submit", class: "secondary" }, "جست‌وجو"),
  );
  if (resource === "cases")
    filter.insertBefore(
      selectField(
        "وضعیت",
        "status",
        [
          { value: "", label: "همه" },
          { value: "open", label: "ثبت‌شده" },
          { value: "reviewing", label: "در حال بررسی" },
          { value: "resolved", label: "رسیدگی‌شده" },
          { value: "dismissed", label: "بسته‌شده" },
        ],
        ctx.params.get("status"),
      ),
      filter.lastChild,
    );
  filter.addEventListener("submit", (event) => {
    event.preventDefault();
    ctx.navigate(
      `admin/${resource}?${new URLSearchParams(new FormData(filter))}`,
    );
  });
  const actions = el("div", { class: "row" });
  if (resource === "roster")
    actions.append(button("ورود فهرست CSV", () => rosterImport(ctx)));
  if (resource === "rooms")
    actions.append(
      button("تعریف اتاق", () => roomDialog(ctx, null, ctx.config)),
    );
  if (["groups", "rooms"].includes(resource))
    actions.append(button("خروجی CSV", () => exportCSV(resource), "secondary"));
  let content;
  if (resource === "groups")
    content = el(
      "div",
      { class: "stack" },
      ...entries.map((g) =>
        card(
          el(
            "div",
            { class: "row between" },
            el("h2", {}, `گروه ${g.id}`),
            badge(
              `${g.members.length} / ${g.capacity} عضو`,
              g.room ? "success" : "blue",
            ),
          ),
          el("p", {}, g.members.map((m) => m.name).join("، ")),
          el(
            "p",
            { class: "small" },
            g.room
              ? `اتاق ${g.room.number} · ${g.room.dormitory}`
              : "بدون تخصیص",
          ),
          g.allocation_issues?.length
            ? notice(g.allocation_issues.join("؛ "), "warning")
            : null,
          el(
            "div",
            { class: "form-actions" },
            button(
              "بازبینی سیاست گروه",
              () => reconcileGroup(ctx, g),
              "secondary",
            ),
            button(g.room ? "اصلاح تخصیص" : "تخصیص اتاق", () =>
              allocate(ctx, g),
            ),
            g.room &&
              button(
                "آزادکردن اتاق گروه",
                () =>
                  reasonDialog(
                    ctx,
                    "آزادکردن تخصیص کل گروه",
                    `تخصیص ${g.members.map((m) => m.name).join("، ")} از اتاق ${g.room.number} آزاد می‌شود. اعضای گروه باقی می‌مانند. این اقدام با خروج فردی متفاوت است.`,
                    `/admin/groups/${g.id}/allocation`,
                    "DELETE",
                  ),
                "secondary",
              ),
          ),
          el(
            "details",
            {},
            el("summary", {}, "رسیدگی به عضویت فردی"),
            ...g.members.map((m) =>
              el(
                "div",
                { class: "row between" },
                el("span", {}, m.name),
                button(
                  "خروج این فرد",
                  () =>
                    reasonDialog(
                      ctx,
                      "خروج یک عضو",
                      `فقط ${m.name} از گروه و جای تخصیص‌یافته خارج می‌شود؛ ${g.members.length - 1} عضو دیگر و تخصیص آن‌ها حفظ می‌شوند.`,
                      `/admin/groups/${g.id}/members/${m.id}`,
                      "DELETE",
                    ),
                  "secondary",
                ),
              ),
            ),
          ),
        ),
      ),
    );
  if (resource === "rooms")
    content = table(
      ["اتاق", "خوابگاه", "ظرفیت / اشغال", "گروه مجاز و دوره", "عملیات"],
      entries.map((r) => [
        r.number,
        r.dormitory,
        `${r.capacity} / ${r.current_occupancy || 0}`,
        `${r.pool || "تعیین نشده"} · ${r.cycle || "تعیین نشده"}`,
        button("ویرایش", () => roomDialog(ctx, r, ctx.config), "secondary"),
      ]),
    );
  if (resource === "users")
    content = table(
      ["دانشجو", "ایمیل / شمارهٔ دانشجویی", "وضعیت", "عملیات"],
      entries.map((u) => [
        el(
          "div",
          {},
          u.name,
          el("div", { class: "small muted" }, u.class_name),
        ),
        el(
          "div",
          {},
          el("bdi", { dir: "ltr" }, u.email),
          el("br"),
          el("bdi", { dir: "ltr" }, u.student_id),
        ),
        badge(statuses[u.account_status] || u.account_status || "فعال"),
        el(
          "div",
          { class: "row" },
          button("پرونده و تخصیص", () => userRecord(u), "secondary"),
          button(
            "بستن نشست‌ها",
            () =>
              reasonDialog(
                ctx,
                "ابطال نشست‌های دانشجو",
                `تمام نشست‌های ${u.name} بسته می‌شوند.`,
                `/admin/users/${u.id}/security`,
                "POST",
                { action: "revoke_sessions" },
              ),
            "secondary",
          ),
          button(
            u.account_status === "suspended" ? "فعال‌سازی" : "تعلیق",
            () =>
              reasonDialog(
                ctx,
                "تغییر دسترسی حساب",
                `${u.name}: وضعیت دسترسی تغییر می‌کند. تخصیص موجود خودکار آزاد نمی‌شود.`,
                `/admin/users/${u.id}/security`,
                "POST",
                {
                  action:
                    u.account_status === "suspended" ? "reactivate" : "suspend",
                },
              ),
            "secondary",
          ),
        ),
      ]),
    );
  if (resource === "roster")
    content = table(
      ["دانشجو", "شماره و ایمیل", "گروه / دوره", "وضعیت", "اصلاح"],
      entries.map((r) => [
        r.name,
        el(
          "div",
          {},
          el("bdi", { dir: "ltr" }, r.student_id),
          el("br"),
          el("bdi", { dir: "ltr" }, r.email),
        ),
        `${r.pool} · ${r.cycle}`,
        statuses[r.status] || r.status,
        button(
          "بررسی اصلاح",
          () => {
            let validated = null;
            const outcome = el("div");
            const commit = button(
              "اعمال اصلاح بررسی‌شده",
              async () => {
                if (!validated) return;
                await mutations(
                  ctx,
                  `/admin/enrollments/${r.id}`,
                  "PATCH",
                  { ...validated, dry_run: false },
                  "اصلاح ثبت شد.",
                );
                node.close();
              },
              "secondary",
            );
            commit.hidden = true;
            const node = dialog({
              title: `اصلاح پروندهٔ ${r.name}`,
              closeOnSubmit: false,
              description:
                "تغییرهای مؤثر بر eligibility می‌توانند دعوت‌های باز را نامعتبر کنند. ابتدا نتیجه را بررسی کنید.",
              fields: [
                selectField("فیلد", "field", [
                  { value: "email", label: "ایمیل" },
                  { value: "student_id", label: "شمارهٔ دانشجویی" },
                  { value: "pool", label: "گروه خوابگاهی" },
                  { value: "cycle", label: "دوره" },
                  { value: "status", label: "وضعیت" },
                ]),
                field("مقدار جدید", "value", {
                  required: true,
                  maxlength: 254,
                }),
                reasonField(),
                outcome,
                commit,
              ],
              submitLabel: "بررسی اثر تغییر",
              onSubmit: async (data) => {
                validated = Object.fromEntries(data);
                const result = await api(`/admin/enrollments/${r.id}`, {
                  method: "PATCH",
                  body: { ...validated, dry_run: true },
                });
                outcome.replaceChildren(notice(JSON.stringify(result)));
                commit.hidden = false;
                announce(
                  "نتیجه آماده است. برای ثبت نهایی دکمهٔ اعمال را بزنید.",
                );
              },
            });
            node.querySelectorAll("input,select,textarea").forEach((control) =>
              control.addEventListener("input", () => {
                validated = null;
                commit.hidden = true;
              }),
            );
          },
          "secondary",
        ),
      ]),
    );
  if (resource === "cases")
    content = el(
      "div",
      { class: "stack" },
      ...entries.map((c) =>
        card(
          el(
            "div",
            { class: "row between" },
            el("h2", {}, `پیگیری ${c.reference || c.id}`),
            badge(statuses[c.status] || c.status),
          ),
          el("p", {}, c.description),
          el(
            "p",
            { class: "small muted" },
            `${c.kind || c.category || ""} · ${date(c.created_at)}`,
          ),
          c.resolution && notice(c.resolution),
          button(
            "رسیدگی",
            () =>
              dialog({
                title: "رسیدگی به درخواست",
                description: `پروندهٔ ${c.reference || c.id}. پاسخ برای درخواست‌دهنده قابل‌مشاهده خواهد بود.`,
                fields: [
                  selectField("تصمیم", "status", [
                    { value: "reviewing", label: "در حال بررسی" },
                    { value: "resolved", label: "رسیدگی‌شده" },
                    { value: "dismissed", label: "بسته‌شده" },
                  ]),
                  reasonField(),
                ],
                submitLabel: "ثبت رسیدگی",
                onSubmit: (data) =>
                  mutations(
                    ctx,
                    `/admin/cases/${c.id}`,
                    "PATCH",
                    Object.fromEntries(data),
                    "پاسخ ثبت شد.",
                  ),
              }),
            "secondary",
          ),
        ),
      ),
    );
  if (resource === "departures")
    content = el(
      "div",
      { class: "stack" },
      ...entries.map((d) =>
        card(
          el(
            "div",
            { class: "row between" },
            el("h2", {}, d.user?.name || d.name || `درخواست ${d.id}`),
            badge(statuses[d.status] || d.status),
          ),
          el("p", {}, d.reason),
          el(
            "p",
            { class: "small muted" },
            `گروه ${d.group_id || d.group?.id || "—"} · ${date(d.created_at)}`,
          ),
          d.status === "pending" &&
            el(
              "div",
              { class: "form-actions" },
              button("تأیید خروج فردی", () =>
                reasonDialog(
                  ctx,
                  "تأیید خروج فردی",
                  "فقط فرد درخواست‌دهنده از گروه و تخصیص خارج می‌شود؛ جای دیگر اعضا حفظ می‌شود.",
                  `/admin/departures/${d.id}/resolve`,
                  "POST",
                  { decision: "approved" },
                ),
              ),
              button(
                "رد درخواست",
                () =>
                  reasonDialog(
                    ctx,
                    "رد درخواست خروج",
                    "عضویت و تخصیص فرد حفظ می‌شود؛ دلیل تصمیم ثبت خواهد شد.",
                    `/admin/departures/${d.id}/resolve`,
                    "POST",
                    { decision: "rejected" },
                  ),
                "secondary",
              ),
            ),
        ),
      ),
    );
  if (resource === "requests")
    content = table(
      ["شناسه", "فرستنده / متقاضی", "ظرفیت", "وضعیت", "انقضا"],
      entries.map((r) => [
        r.id,
        `${r.initiator?.name || "—"} / ${r.candidate?.name || "—"}`,
        r.capacity,
        statuses[r.status] || r.status,
        date(r.expires_at),
      ]),
    );
  if (resource === "audit")
    content = table(
      ["زمان", "عامل", "عملیات", "موضوع", "دلیل", "تغییر ثبت‌شده"],
      entries.map((a) => [
        date(a.created_at || a.timestamp),
        a.actor_name || a.actor_id || "سیستم",
        a.action || a.event,
        a.entity_type
          ? `${a.entity_type} ${a.entity_id || ""}`
          : a.target_id || "—",
        a.reason || a.details?.reason || "—",
        el(
          "details",
          {},
          el("summary", {}, "قبل و بعد"),
          el(
            "pre",
            { class: "audit-detail", dir: "ltr" },
            JSON.stringify({ before: a.before, after: a.after }, null, 2),
          ),
        ),
      ]),
    );
  if (resource === "outbox")
    content = table(
      ["زمان", "نوع", "وضعیت", "تلاش‌ها", "عملیات"],
      entries.map((m) => [
        date(m.created_at),
        {
          claim: "فعال‌سازی حساب",
          reset_password: "بازیابی رمز",
          verify_email: "تأیید ایمیل",
          notification: "اعلان",
        }[m.purpose] || m.purpose,
        {
          pending: "در صف",
          leased: "در حال ارسال",
          "retry-scheduled": "در انتظار تلاش دوباره",
          "terminal-failure": "ناموفق",
          delivered: "تحویل‌شده",
          sent: "ارسال‌شده",
          cancelled: "لغوشده",
        }[m.status] || m.status,
        m.attempts || 0,
        ["retry-scheduled", "terminal-failure"].includes(m.status)
          ? button(
              "بررسی و تلاش دوباره",
              () =>
                reasonDialog(
                  ctx,
                  "تلاش دوباره برای ارسال ایمیل",
                  "فقط پیام معتبرِ ناموفق دوباره صف‌بندی می‌شود. نتیجهٔ عملیات گروه تکرار نمی‌شود.",
                  `/admin/delivery/${m.id}/retry`,
                  "POST",
                ),
              "secondary",
            )
          : "—",
      ]),
    );
  const normalized = {
    ...data,
    page,
    limit,
    total: data.total ?? entries.length,
  };
  return el(
    "div",
    { class: "stack" },
    heading(
      resources[resource],
      "مدیریت پایلوت · هر تغییر مهم با دلیل ثبت می‌شود.",
      actions,
    ),
    deliveryHealth &&
      card(
        el("h2", {}, "سلامت ارسال ایمیل"),
        el(
          "div",
          { class: "row" },
          badge(`در صف: ${deliveryHealth.pending_count}`),
          badge(`تلاش دوباره: ${deliveryHealth.retry_count}`),
          badge(
            `ناموفق: ${deliveryHealth.terminal_failures}`,
            deliveryHealth.terminal_failures ? "warning" : "success",
          ),
        ),
        el(
          "p",
          { class: "small muted" },
          `آخرین فعالیت ارسال‌کننده: ${date(deliveryHealth.last_heartbeat_at)} · قدیمی‌ترین پیام صف: ${deliveryHealth.oldest_pending_age_seconds} ثانیه`,
        ),
        ...(deliveryHealth.alerts || []).map((alert) =>
          notice(
            {
              worker_missing:
                "ارسال‌کنندهٔ ایمیل پاسخ نمی‌دهد؛ مسئول فنی را مطلع کنید.",
              queue_age_exceeded: "زمان انتظار صف از ۵ دقیقه بیشتر شده است.",
              terminal_delivery_failure:
                "پیام ناموفق وجود دارد؛ علت و اعتبار پیام را بررسی کنید.",
            }[alert] || "ارسال ایمیل نیازمند بررسی است.",
            "warning",
          ),
        ),
      ),
    card(
      filter,
      entries.length
        ? content
        : empty(
            "موردی در این فهرست نیست",
            "جست‌وجو را تغییر بده یا اطلاعات موردنیاز پایلوت را ثبت کن.",
          ),
    ),
    pagination(normalized, `admin/${resource}`, ctx.params),
  );
}
