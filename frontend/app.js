const countdown = document.querySelector("#countdown");
const statusLine = document.querySelector("#status-line");
const takenButton = document.querySelector("#taken-button");
const snoozeButton = document.querySelector("#snooze-button");
const fontToggle = document.querySelector("#font-toggle");
const settingsButton = document.querySelector("#settings-button");

let remainingSeconds = 12 * 60;

function renderCountdown() {
  const minutes = String(Math.floor(remainingSeconds / 60)).padStart(2, "0");
  const seconds = String(remainingSeconds % 60).padStart(2, "0");
  countdown.textContent = `${minutes}:${seconds}`;
}

function setStatus(text) {
  statusLine.textContent = text;
}

takenButton.addEventListener("click", () => {
  setStatus("Приём подтверждён. Следующее напоминание появится по расписанию.");
});

snoozeButton.addEventListener("click", () => {
  remainingSeconds = 10 * 60;
  renderCountdown();
  setStatus("Напоминание отложено на 10 минут.");
});

fontToggle.addEventListener("click", () => {
  document.body.classList.toggle("large-text");
});

settingsButton.addEventListener("click", () => {
  setStatus("Настройки проверены. Уведомление близкому подготовится после нескольких пропусков.");
});

renderCountdown();

window.setInterval(() => {
  if (remainingSeconds > 0) {
    remainingSeconds -= 1;
    renderCountdown();
  }
}, 1000);
