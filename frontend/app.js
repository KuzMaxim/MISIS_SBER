const statusLine = document.querySelector("#status-line");
const setupButton = document.querySelector("#setup-button");
const helpButton = document.querySelector("#help-button");
const fontToggle = document.querySelector("#font-toggle");
const settingsButton = document.querySelector("#settings-button");
const settingsSummary = document.querySelector("#settings-summary");
const quickActions = document.querySelectorAll("[data-action]");

let largeTextEnabled = false;

function setStatus(text) {
  statusLine.textContent = text;
}

function renderSettings() {
  settingsSummary.innerHTML = `
    <span>Крупный текст: ${largeTextEnabled ? "включен" : "выключен"}</span>
    <span>Повтор напоминания: через 10 минут</span>
    <span>Уведомление близкому: не задано</span>
  `;
}

setupButton.addEventListener("click", () => {
  setStatus("Скажите ассистенту: «Добавь лекарство». Затем назовите препарат, время приема и длительность курса.");
});

helpButton.addEventListener("click", () => {
  setStatus("Я помогу добавить лекарство, напомню о приеме, покажу день курса и дам справку по инструкции.");
});

fontToggle.addEventListener("click", () => {
  largeTextEnabled = !largeTextEnabled;
  document.body.classList.toggle("large-text", largeTextEnabled);
  fontToggle.textContent = largeTextEnabled ? "А-" : "А+";
  renderSettings();
  setStatus(largeTextEnabled ? "Крупный текст включён." : "Крупный текст выключен.");
});

settingsButton.addEventListener("click", () => {
  settingsButton.classList.add("is-checked");
  renderSettings();
  setStatus("Настройки проверены. Расписание пока пустое, уведомление близкому не задано.");
});

quickActions.forEach((button) => {
  button.addEventListener("click", () => {
    const action = button.dataset.action;
    const messages = {
      add: "Скажите: «Добавь лекарство». Я задам вопросы о названии, времени и курсе.",
      list: "Список лекарств пока пуст. После добавления препараты появятся в расписании.",
      course: "День курса станет доступен после добавления препарата с длительностью курса.",
      info: "Справка по инструкции доступна по фразе: «Для чего препарат».",
      pharmacy: "Поиск аптек включится после того, как вы назовете нужный препарат.",
      safety: "Я не назначаю лечение и не даю индивидуальные рекомендации. Обратитесь к врачу.",
    };

    quickActions.forEach((item) => item.classList.remove("is-active"));
    button.classList.add("is-active");
    setStatus(messages[action]);
  });
});

renderSettings();
