// Only application-relative destinations can become links. User text never becomes markup.
export function safeHref(value) {
  const text = String(value ?? "");
  return /^(?:\/(?!\/)|#[a-zA-Z0-9/_?=&%.-]*$)/.test(text) &&
    !/[\u0000-\u0020\\]/.test(text)
    ? text
    : "#";
}
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function")
      node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "href") node.setAttribute(key, safeHref(value));
    else if (["value", "checked", "disabled", "selected"].includes(key))
      node[key] = value;
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child !== undefined && child !== null && child !== false)
      node.append(
        child instanceof Node ? child : document.createTextNode(String(child)),
      );
  }
  return node;
}
export const link = (text, href, cls = "") =>
  el("a", { href, class: cls }, text);
export const button = (text, onClick, cls = "") =>
  el(
    "button",
    {
      type: "button",
      class: cls,
      onClick: async (event) => {
        const control = event.currentTarget;
        if (control.disabled) return;
        control.disabled = true;
        try {
          await onClick(event);
        } catch (error) {
          announce(errorText(error));
        } finally {
          control.disabled = false;
        }
      },
    },
    text,
  );
export const badge = (text, cls = "") =>
  el("span", { class: `badge ${cls}` }, text);
export const notice = (text, cls = "") =>
  el(
    "div",
    { class: `notice ${cls}`, role: cls === "error" ? "alert" : "note" },
    text,
  );
export const heading = (title, text, action) =>
  el(
    "div",
    { class: "page-heading" },
    el(
      "div",
      {},
      el("h1", { tabindex: "-1" }, title),
      text && el("p", {}, text),
    ),
    action,
  );
export const card = (...children) =>
  el("section", { class: "card" }, ...children);
export const avatar = (name, id = 0, large = false) =>
  el(
    "span",
    {
      class: `avatar ${["", "green", "lavender"][Number(id) % 3]} ${large ? "large" : ""}`,
      "aria-hidden": "true",
    },
    String(name || "؟")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((s) => [...s][0])
      .join(""),
  );
let controlSequence=0;
export function field(label, name, options = {}) {
  const { hint, type = "text", value, ...attrs } = options;
  const id = `field-${name}-${++controlSequence}`;
  const input =
    type === "textarea"
      ? el("textarea", { id, name, ...attrs }, value || "")
      : el("input", { id, name, type, value, ...attrs });
  if (hint) input.setAttribute("aria-describedby", `${id}-hint`);
  return el(
    "div",
    { class: "field" },
    el("label", { for: id }, label),
    input,
    hint && el("small", { id: `${id}-hint` }, hint),
  );
}
export function selectField(label, name, choices, value = "", attrs = {}) {
  const id = `field-${name}-${++controlSequence}`;
  return el(
    "div",
    { class: "field" },
    el("label", { for: id }, label),
    el(
      "select",
      { id, name, ...attrs },
      ...choices.map((o) =>
        el(
          "option",
          { value: o.value, selected: String(o.value) === String(value) },
          o.label,
        ),
      ),
    ),
  );
}
export function check(label, name, checked = false, props = {}) {
  return el(
    "label",
    { class: "check-label" },
    el("input", { type: "checkbox", name, checked, ...props }),
    el("span", {}, label),
  );
}
export function announce(message) {
  const region = document.getElementById("status");
  if (!region) return;
  region.textContent = message;
  clearTimeout(announce.timer);
  announce.timer = setTimeout(() => {
    region.textContent = "";
  }, 8000);
}
export function errorText(error) {
  if (error.protocolMismatch) return error.message;
  if (error.status === 0)
    return "ارتباط با سرور برقرار نشد. اتصال اینترنت را بررسی و دوباره تلاش کنید.";
  if (error.status === 401)
    return "نشست شما پایان یافته است. دوباره وارد حساب شوید.";
  if (error.status === 403)
    return error.message || "این عملیات برای حساب شما مجاز نیست.";
  if (error.status === 404) return "این مورد در دسترس نیست یا پیدا نشد.";
  if (error.status === 409)
    return "وضعیت این مورد تغییر کرده است. اطلاعات تازه را بررسی و دوباره تصمیم بگیرید.";
  if (error.status === 429)
    return `تعداد تلاش‌ها بیش از حد مجاز است. ${error.retryAfter ? `${error.retryAfter} ثانیه دیگر` : "کمی بعد"} دوباره تلاش کنید.`;
  if (error.status >= 500)
    return "سرویس موقتاً در دسترس نیست. اطلاعات شما حذف نشده؛ کمی بعد دوباره تلاش کنید.";
  return error.message || "عملیات انجام نشد. اطلاعات فرم را بررسی کنید.";
}
export function errorPanel(error, retry) {
  return el(
    "section",
    { class: "card empty" },
    el(
      "h2",
      {},
      error.status === 404 ? "موردی پیدا نشد" : "دریافت اطلاعات انجام نشد",
    ),
    notice(errorText(error), "error"),
    el(
      "div",
      { class: "form-actions" },
      error.protocolMismatch
        ? button("بارگذاری نسخهٔ تازه", () => location.reload())
        : error.status === 401
          ? link("ورود دوباره", "#login", "button")
          : button("تلاش دوباره", retry),
      link("بازگشت به خانه", "#home", "button secondary"),
    ),
  );
}
export function empty(title, text, action) {
  return el(
    "section",
    { class: "card empty" },
    el("div", { class: "empty-symbol", "aria-hidden": "true" }, "◇"),
    el("h2", {}, title),
    el("p", {}, text),
    action,
  );
}
export function loading() {
  return el(
    "div",
    { class: "loading", role: "status" },
    el("span", { class: "spinner", "aria-hidden": "true" }),
    "در حال دریافت اطلاعات…",
  );
}
export const items = (data) => (Array.isArray(data) ? data : data?.items || []);
export const date = (value) =>
  value
    ? new Intl.DateTimeFormat("fa-IR", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Tehran",
      }).format(
        new Date(/[Z+-]\d*:?.*$/.test(value.slice(10)) ? value : `${value}Z`),
      )
    : "—";
export const statuses = {
  pending: "منتظر تأیید",
  needs_reconfirmation: "نیازمند تأیید دوباره",
  accepted: "پذیرفته‌شده",
  rejected: "ردشده",
  cancelled: "لغوشده",
  expired: "منقضی‌شده",
  open: "ثبت‌شده",
  reviewing: "در حال بررسی",
  resolved: "رسیدگی‌شده",
  dismissed: "بسته‌شده",
  approved: "تأییدشده",
  active: "فعال",
  suspended: "تعلیق‌شده",
  pending_closure: "در انتظار بستن حساب",
};
export function pagination(data, path, params = new URLSearchParams()) {
  const page = Number(data.page || 1),
    limit = Number(data.limit || 12),
    total = Number(data.total || 0);
  function href(next) {
    const q = new URLSearchParams(params);
    q.set("page", next);
    return `#${path}?${q}`;
  }
  return el(
    "div",
    { class: "pagination" },
    page > 1
      ? link("→ صفحهٔ قبل", href(page - 1), "button secondary")
      : el("span"),
    el(
      "span",
      { class: "small muted" },
      `صفحهٔ ${page.toLocaleString("fa-IR")} · ${total.toLocaleString("fa-IR")} مورد`,
    ),
    page * limit < total
      ? link("صفحهٔ بعد ←", href(page + 1), "button secondary")
      : el("span"),
  );
}
let formSequence = 0;
export function bindForm(form, submit) {
  const errorId = `form-error-${++formSequence}`;
  const errors = el("div", { id: errorId, tabindex: "-1", "data-errors": "" });
  form.prepend(errors);
  let busy = false;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !form.reportValidity()) return;
    const values = new FormData(form);
    busy = true;
    errors.replaceChildren();
    form
      .querySelectorAll('[aria-invalid="true"]')
      .forEach((input) => input.removeAttribute("aria-invalid"));
    const buttons = [...form.querySelectorAll("button[type=submit]")];
    buttons.forEach((b) => (b.disabled = true));
    form.setAttribute("aria-busy", "true");
    try {
      await submit(values, form);
    } catch (error) {
      errors.append(notice(errorText(error), "error"));
      if (error.protocolMismatch)
        errors.append(button("بارگذاری نسخهٔ تازه", () => location.reload()));
      for (const issue of error.fields || []) {
        const input = form.elements.namedItem(issue.name);
        if (input?.setAttribute) {
          input.setAttribute("aria-invalid", "true");
          input.setAttribute("aria-describedby", errorId);
        }
      }
      errors.focus();
      announce(errorText(error));
    } finally {
      busy = false;
      buttons.forEach((b) => (b.disabled = false));
      form.removeAttribute("aria-busy");
    }
  });
  return form;
}
export function dialog({
  title,
  description,
  fields = [],
  submitLabel = "تأیید",
  danger = false,
  closeOnSubmit = true,
  onSubmit,
}) {
  const previous = document.activeElement;
  const node = el("dialog", {
    class: "dialog",
    "aria-labelledby": "dialog-title",
  });
  const close = () => node.close();
  const form = el(
    "form",
    {},
    el("h2", { id: "dialog-title" }, title),
    el("div", { class: "muted" }, description),
    ...fields,
    el(
      "div",
      { class: "form-actions" },
      button("انصراف", close, "secondary"),
      el(
        "button",
        { type: "submit", class: danger ? "danger" : "" },
        submitLabel,
      ),
    ),
  );
  bindForm(form, async (data) => {
    await onSubmit(data);
    if (closeOnSubmit) node.close();
  });
  node.append(form);
  document.body.append(node);
  node.addEventListener(
    "close",
    () => {
      node.remove();
      if (previous?.isConnected) previous.focus();
    },
    { once: true },
  );
  node.showModal();
  return node;
}
