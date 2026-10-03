export function parseRoute(hash = location.hash) {
  const raw = hash.replace(/^#\/?/, "") || "home";
  const split = raw.indexOf("?");
  const path = (split < 0 ? raw : raw.slice(0, split)).replace(/\/$/, "");
  const params = new URLSearchParams(split < 0 ? "" : raw.slice(split + 1));
  return { path, parts: path.split("/"), params };
}
export function createRouter(render) {
  let controller,
    revision = 0;
  async function dispatch() {
    controller?.abort();
    controller = new AbortController();
    const own = ++revision;
    const route = parseRoute();
    await render({
      ...route,
      signal: controller.signal,
      isCurrent: () => own === revision,
    });
  }
  const navigate = (route) => {
    const hash = `#${route}`;
    if (location.hash === hash) return;
    location.hash = hash;
  };
  window.addEventListener("hashchange", dispatch);
  return {
    start: dispatch,
    reload: dispatch,
    navigate,
    destroy() {
      controller?.abort();
      window.removeEventListener("hashchange", dispatch);
    },
  };
}
