const toggle = document.querySelector(".menu-toggle");
const menu = document.getElementById("mobile-menu");
function closeMenu(restoreFocus = false) {
  menu?.classList.add("hidden");
  toggle?.setAttribute("aria-expanded", "false");
  if (restoreFocus) toggle?.focus();
}
toggle?.addEventListener("click", () => {
  const open = toggle.getAttribute("aria-expanded") !== "true";
  toggle.setAttribute("aria-expanded", String(open));
  menu?.classList.toggle("hidden", !open);
});
menu?.addEventListener("click", (event) => {
  const anchor = event.target.closest("a");
  if (anchor) {
    closeMenu();
    if (anchor.hash) {
      const destination = document.getElementById(anchor.hash.slice(1));
      if (destination) {
        destination.tabIndex = -1;
        destination.focus({ preventScroll: true });
      }
    }
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && toggle?.getAttribute("aria-expanded") === "true") {
    closeMenu(true);
  }
});
const desktop = matchMedia("(min-width: 768px)");
desktop.addEventListener("change", (event) => {
  if (event.matches) closeMenu();
});

const motionPreference = matchMedia("(prefers-reduced-motion: reduce)");
const words = [...document.querySelectorAll("#rotator .word")];
const motionToggle = document.getElementById("motion-toggle");
const positions = ["pos2", "pos1", "active", "neg1", "neg2"];
let activeWord = 0;
let timer;
let paused = false;
function renderWords() {
  for (const word of words) word.classList.remove(...positions);
  if (!words.length) return;
  if (motionPreference.matches) {
    words[activeWord].classList.add("active");
    return;
  }
  for (let offset = -2; offset <= 2; offset++) {
    words[(activeWord + offset + words.length) % words.length]
      .classList.add(positions[offset + 2]);
  }
}
function updateMotion() {
  clearInterval(timer);
  renderWords();
  document.body.classList.toggle("motion-paused", paused || motionPreference.matches);
  if (motionToggle) {
    motionToggle.hidden = motionPreference.matches;
    motionToggle.textContent = paused ? "ادامهٔ حرکت" : "توقف حرکت";
    motionToggle.setAttribute("aria-pressed", String(paused));
  }
  if (!paused && !motionPreference.matches && !document.hidden && words.length) {
    timer = setInterval(() => {
      activeWord = (activeWord + 1) % words.length;
      renderWords();
    }, 2000);
  }
}
motionToggle?.addEventListener("click", () => {
  paused = !paused;
  updateMotion();
});
motionPreference.addEventListener("change", updateMotion);
document.addEventListener("visibilitychange", updateMotion);
updateMotion();

const cards = [...document.querySelectorAll("#scrollContainer > div")];
const previous = document.getElementById("scrollRight");
const next = document.getElementById("scrollLeft");
let currentCard = 0;
function navigateCards(delta) {
  currentCard = Math.max(0, Math.min(cards.length - 1, currentCard + delta));
  cards[currentCard]?.scrollIntoView({
    block: "nearest", inline: "center",
    behavior: motionPreference.matches ? "instant" : "smooth",
  });
}
previous?.addEventListener("click", () => navigateCards(-1));
next?.addEventListener("click", () => navigateCards(1));
