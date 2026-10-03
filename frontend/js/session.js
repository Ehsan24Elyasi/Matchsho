import { api, post } from "./api.js";
let current;
export const session = {
  get user() {
    return current;
  },
  set user(value) {
    current = value;
  },
  async load() {
    current = await api("/auth/me");
    return current;
  },
  async login(values) {
    current = await post("/auth/login", values);
    return current;
  },
  async logout() {
    await post("/auth/logout");
    current = null;
  },
  clear() {
    current = null;
  },
};
