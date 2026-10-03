import { api } from "../api.js";
import {
  el,
  heading,
  field,
  selectField,
  check,
  button,
  notice,
  bindForm,
  announce,
} from "../ui.js";
export async function questionnairePage(ctx) {
  const [schema, saved, draft] = await Promise.all([
    api("/questionnaire/schema", { signal: ctx.signal }),
    api("/questionnaire/me", { signal: ctx.signal }),
    api("/questionnaire/draft", { signal: ctx.signal }),
  ]);
  const compatibleDraft =
    draft.version === schema.version && Object.keys(draft.answers || {}).length;
  const source = compatibleDraft
    ? draft
    : saved.version === schema.version
      ? saved
      : { answers: {}, capacities: [] };
  const form = el("form", { class: "stack" });
  const progress = el("progress", {
    class: "progress",
    max: schema.dimensions.filter((d) => d.required).length,
    value: 0,
    "aria-label": "پیشرفت پاسخ‌های ضروری",
  });
  const progressText = el("span", { class: "small muted" });
  const draftState = el("span", { class: "small muted", role: "status" });
  form.append(
    notice(
      "رفتار واقعی خودت و آنچه از هم‌اتاقی می‌پذیری دو پاسخ جدا هستند. پاسخ‌های خام به هیچ هم‌اتاقی نشان داده نمی‌شوند.",
    ),
  );
  if (saved.version !== schema.version || draft.version !== schema.version)
    form.append(
      notice(
        "نسخهٔ پرسشنامه تغییر کرده است. پاسخ‌های پیشین به رفتار واقعی تبدیل نشده‌اند؛ لطفاً نسخهٔ فعلی را تکمیل کن. گروه و اتاق فعلی تغییری نمی‌کنند.",
        "warning",
      ),
    );
  if (compatibleDraft)
    form.append(
      notice(
        "پیش‌نویس ذخیره‌شده بازیابی شد. این پاسخ‌ها تا ثبت نهایی روی پیشنهادها اثر ندارند.",
        "success",
      ),
    );
  form.append(el("div", {}, progressText, progress));
  for (const dim of schema.dimensions) {
    const answer = source.answers?.[dim.key] || {};
    const question = el(
      "fieldset",
      { class: "question" },
      el("legend", {}, dim.label, dim.required ? " · ضروری" : " · اختیاری"),
    );
    if (dim.key === "tobacco")
      question.append(
        el(
          "p",
          { class: "small muted" },
          "این سؤال فقط برای بررسی ترجیح هم‌اتاقی است. پاسخ‌دادن اختیاری است و پاسخ یا دلیل ناسازگاری برای دیگران نمایش داده نمی‌شود.",
        ),
      );
    const own =
      dim.kind === "time"
        ? field("زمان معمول من", `${dim.key}.own`, {
            type: "time",
            step: 900,
            value: answer.own || "",
            required: dim.required,
            dir: "ltr",
          })
        : selectField(
            "رفتار معمول من",
            `${dim.key}.own`,
            [
              {
                value: "",
                label: dim.required ? "انتخاب کن" : "ترجیح می‌دهم پاسخ ندهم",
              },
              ...(dim.options || []),
            ],
            answer.own || "",
            { required: dim.required },
          );
    let accepted;
    if (dim.kind === "time")
      accepted = el(
        "div",
        { class: "stack" },
        el(
          "div",
          { class: "form-grid" },
          field("بازهٔ پذیرفته‌شده از", `${dim.key}.start`, {
            type: "time",
            step: 900,
            value: answer.accepted?.[0] || "",
            required: dim.required,
            dir: "ltr",
          }),
          field("تا", `${dim.key}.end`, {
            type: "time",
            step: 900,
            value: answer.accepted?.[1] || "",
            required: dim.required,
            dir: "ltr",
          }),
        ),
        el(
          "small",
          { class: "muted" },
          "مثلاً ۲۲:۰۰ تا ۰۱:۰۰، از نیمه‌شب عبور می‌کند. دو سر بازه پذیرفته می‌شوند.",
        ),
      );
    else
      accepted = el(
        "fieldset",
        {},
        el("legend", { class: "small" }, "رفتارهای قابل‌پذیرش از هم‌اتاقی"),
        el(
          "div",
          { class: "choice-list" },
          ...(dim.options || []).map((option) =>
            el(
              "label",
              { class: "choice" },
              el("input", {
                type: "checkbox",
                name: `${dim.key}.accepted`,
                value: option.value,
                checked: answer.accepted?.includes(option.value),
              }),
              option.label,
            ),
          ),
        ),
      );
    const importance = el(
      "fieldset",
      {},
      el("legend", { class: "small" }, "اهمیت این ترجیح برای من"),
      el(
        "div",
        { class: "choice-list" },
        ...[
          ["1", "کم"],
          ["2", "متوسط"],
          ["3", "زیاد"],
        ].map(([value, label]) =>
          el(
            "label",
            { class: "choice" },
            el("input", {
              type: "radio",
              name: `${dim.key}.importance`,
              value,
              checked: String(answer.importance || 2) === value,
            }),
            label,
          ),
        ),
      ),
    );
    question.append(
      el("div", { class: "question-grid" }, own, accepted),
      importance,
      check(
        "خط قرمز است؛ فرد ناسازگار پیشنهاد نشود.",
        `${dim.key}.hard`,
        Boolean(answer.hard),
      ),
    );
    form.append(question);
  }
  const capacities = el(
    "fieldset",
    {},
    el("legend", {}, "ظرفیت‌های قابل‌قبول اتاق"),
    el(
      "p",
      { class: "small muted" },
      "ظرفیت از اتاق‌های مجاز خوابگاه می‌آید و مستقل از امتیاز هم‌خوانی است.",
    ),
    el(
      "div",
      { class: "choice-list" },
      ...schema.capacities.map((capacity) =>
        el(
          "label",
          { class: "choice" },
          el("input", {
            type: "checkbox",
            name: "capacities",
            value: capacity,
            checked: source.capacities?.includes(capacity),
          }),
          `${capacity.toLocaleString("fa-IR")} نفره`,
        ),
      ),
    ),
  );
  if (!schema.capacities.length)
    capacities.append(
      notice(
        "هنوز ظرفیت مجازی برای دوره و خوابگاه شما تعریف نشده است. با پشتیبانی تماس بگیرید.",
        "warning",
      ),
    );
  form.append(capacities);
  function payload() {
    const data = new FormData(form);
    const answers = {};
    for (const dim of schema.dimensions) {
      const own = data.get(`${dim.key}.own`);
      answers[dim.key] = {
        own: own || null,
        accepted:
          dim.kind === "time"
            ? [
                data.get(`${dim.key}.start`) || "",
                data.get(`${dim.key}.end`) || "",
              ]
            : data.getAll(`${dim.key}.accepted`),
        importance: Number(data.get(`${dim.key}.importance`) || 2),
        hard: data.has(`${dim.key}.hard`),
      };
    }
    return {
      version: schema.version,
      answers,
      capacities: data.getAll("capacities").map(Number),
    };
  }
  let dirty = false,
    saving = Promise.resolve(),
    timer;
  async function saveDraft() {
    clearTimeout(timer);
    if (!dirty) return;
    dirty = false;
    const data = payload();
    draftState.textContent = "در حال ذخیرهٔ پیش‌نویس…";
    saving = saving
      .catch(() => {})
      .then(() => api("/questionnaire/draft", { method: "PUT", body: data }))
      .then(() => {
        draftState.textContent = "پیش‌نویس در حساب شما ذخیره شد.";
      })
      .catch((error) => {
        dirty = true;
        draftState.textContent =
          "ذخیرهٔ پیش‌نویس انجام نشد؛ پیش از خروج دوباره تلاش کنید.";
        throw error;
      });
    return saving;
  }
  function update() {
    const data = payload();
    const completed = schema.dimensions.filter(
      (d) =>
        d.required &&
        data.answers[d.key].own &&
        data.answers[d.key].accepted.length &&
        data.answers[d.key].accepted.every(Boolean),
    ).length;
    progress.value = completed;
    progressText.textContent = `${completed.toLocaleString("fa-IR")} از ${progress.max.toLocaleString("fa-IR")} پاسخ ضروری تکمیل شده`;
  }
  form.addEventListener("input", () => {
    dirty = true;
    update();
    clearTimeout(timer);
    timer = setTimeout(() => saveDraft().catch(() => {}), 700);
  });
  // Radio and select change also fire input in supported browsers; explicit draft action works everywhere.
  form.append(
    el(
      "div",
      { class: "form-footer row between" },
      el("div", {}, draftState),
      el(
        "div",
        { class: "row" },
        button(
          "ذخیرهٔ پیش‌نویس",
          async () => {
            try {
              await saveDraft();
              announce("پیش‌نویس ذخیره شد.");
            } catch {
              announce("ذخیره انجام نشد. دوباره تلاش کنید.");
            }
          },
          "secondary",
        ),
        el("button", { type: "submit" }, "ثبت نهایی ترجیحات"),
      ),
    ),
  );
  bindForm(form, async () => {
    clearTimeout(timer);
    await saving.catch(() => {});
    const data = payload();
    for (const dim of schema.dimensions) {
      if (
        !dim.required &&
        !data.answers[dim.key].own &&
        !data.answers[dim.key].accepted.length
      )
        delete data.answers[dim.key];
    }
    if (!data.capacities.length)
      throw new Error("حداقل یک ظرفیت اتاق انتخاب کن.");
    for (const dim of schema.dimensions) {
      const a = data.answers[dim.key];
      if (!a) continue;
      if ((dim.required || a.own) && !a.accepted.filter(Boolean).length)
        throw new Error(
          `برای «${dim.label}» دست‌کم یک رفتار قابل‌پذیرش انتخاب کن.`,
        );
    }
    await api("/questionnaire/me", { method: "PUT", body: data });
    dirty = false;
    announce(
      "ترجیحات ثبت شد. دعوت‌های وابسته ممکن است به تأیید دوباره نیاز داشته باشند.",
    );
    ctx.navigate("matches");
  });
  update();
  ctx.signal.addEventListener(
    "abort",
    () => {
      clearTimeout(timer);
      if (dirty) saveDraft().catch(() => {});
    },
    { once: true },
  );
  return el(
    "div",
    {},
    heading(
      "عادت‌ها و ترجیحات من",
      "شناخت بهتر، انتخاب آگاهانه‌تر. نسخهٔ " + schema.version,
    ),
    form,
  );
}
