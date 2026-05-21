const statusLine = document.querySelector("#status-line");
const setupButton = document.querySelector("#setup-button");
const helpButton = document.querySelector("#help-button");
const fontToggle = document.querySelector("#font-toggle");
const settingsButton = document.querySelector("#settings-button");
const settingsSummary = document.querySelector("#settings-summary");
const quickActions = document.querySelectorAll("[data-action]");
const summaryCard = document.querySelector("#summary-card");
const summaryKicker = document.querySelector("#summary-kicker");
const summaryTitle = document.querySelector("#summary-title");
const summaryCopy = document.querySelector("#summary-copy");
const nextTime = document.querySelector("#next-time");
const nextTimeCaption = document.querySelector("#next-time-caption");
const scheduleBadge = document.querySelector("#schedule-badge");
const scheduleList = document.querySelector("#schedule-list");

let largeTextEnabled = false;
let appState = { medications: [] };
let assistantClient = null;

function setStatus(text) {
  statusLine.textContent = text;
}

function formatMedicationCount(count) {
  const lastTwo = count % 100;
  const last = count % 10;
  if (lastTwo >= 11 && lastTwo <= 14) {
    return `${count} лекарств`;
  }
  if (last === 1) {
    return `${count} лекарство`;
  }
  if (last >= 2 && last <= 4) {
    return `${count} лекарства`;
  }
  return `${count} лекарств`;
}

function formatTimes(times) {
  return [...(times || [])].sort().join(", ");
}

function minutesUntilTime(value) {
  const [hour, minute] = value.split(":").map(Number);
  const now = new Date();
  const target = new Date(now);
  target.setHours(hour, minute, 0, 0);
  const currentMinute = new Date(now);
  currentMinute.setSeconds(0, 0);
  if (target < currentMinute) {
    target.setDate(target.getDate() + 1);
  }
  return Math.round((target - currentMinute) / 60000);
}

function nearestTime(times) {
  const safeTimes = times || [];
  if (!safeTimes.length) {
    return "";
  }
  return [...safeTimes].sort((left, right) => minutesUntilTime(left) - minutesUntilTime(right))[0];
}

function sortMedications(medications) {
  return [...(medications || [])].sort((left, right) => {
    const leftTime = left.next_time || nearestTime(left.schedule_times);
    const rightTime = right.next_time || nearestTime(right.schedule_times);
    const minutesDiff = minutesUntilTime(leftTime) - minutesUntilTime(rightTime);
    if (minutesDiff !== 0) {
      return minutesDiff;
    }
    return left.name.localeCompare(right.name, "ru");
  });
}

function formatCourse(medication) {
  return medication.course_days ? `курс ${medication.course_days} дней` : "курс не задан";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderSettings() {
  settingsSummary.innerHTML = `
    <span>Крупный текст: ${largeTextEnabled ? "включен" : "выключен"}</span>
    <span>Повтор напоминания: через 10 минут</span>
    <span>Уведомление близкому: не задано</span>
  `;
}

function renderSchedule(medications) {
  appState = { medications: sortMedications(medications) };

  if (!appState.medications.length) {
    summaryCard.classList.add("empty-dose");
    summaryKicker.textContent = "Первый запуск";
    summaryTitle.textContent = "Расписание пока пустое";
    summaryCopy.textContent = "Добавьте первый препарат и задайте время приема. Готовых лекарств здесь нет.";
    nextTime.textContent = "--:--";
    nextTimeCaption.textContent = "время задаст пользователь";
    scheduleBadge.textContent = "пусто";
    scheduleList.className = "empty-state";
    scheduleList.innerHTML = `
      <strong>Нет добавленных препаратов</strong>
      <p>После настройки здесь появятся названия, время приема и статус курса.</p>
    `;
    return;
  }

  const firstMedication = appState.medications[0];
  const firstTime = firstMedication.next_time || nearestTime(firstMedication.schedule_times);
  summaryCard.classList.remove("empty-dose");
  summaryKicker.textContent = "Расписание";
  summaryTitle.textContent = formatMedicationCount(appState.medications.length);
  summaryCopy.textContent = `Ближайший прием: ${firstMedication.name}, ${firstTime}, ${formatCourse(firstMedication)}.`;
  nextTime.textContent = firstTime || "--:--";
  nextTimeCaption.textContent = "ближайшее время приема";
  scheduleBadge.textContent = formatMedicationCount(appState.medications.length);
  scheduleList.className = "schedule-list";
  scheduleList.innerHTML = appState.medications
    .map(
      (medication, index) => {
        const nextMedicationTime = medication.next_time || nearestTime(medication.schedule_times);
        const allTimes = formatTimes(medication.schedule_times);
        return `
        <div class="schedule-item ${index === 0 ? "is-next" : ""}">
          <span class="time">${escapeHtml(nextMedicationTime || "--:--")}</span>
          <div>
            <strong>${escapeHtml(medication.name)}</strong>
            <p>${escapeHtml(`${formatCourse(medication)}${allTimes && allTimes !== nextMedicationTime ? `, все приемы: ${allTimes}` : ""}`)}</p>
          </div>
        </div>
      `;
      },
    )
    .join("");
}

function handleSmartAppData(data) {
  if (!data) {
    return;
  }
  const payload = data.payload || data;
  if (data.type === "health_state" || Array.isArray(payload.medications)) {
    renderSchedule(payload.medications || []);
  }
}

function sendAssistantText(text) {
  if (!assistantClient || typeof assistantClient.sendData !== "function") {
    setStatus(text);
    return;
  }

  assistantClient.sendData({
    action: {
      action_id: "frontend_text_action",
      parameters: { text },
    },
  });
}

function initAssistantClient() {
  if (!window.assistant || typeof window.assistant.createAssistant !== "function") {
    return;
  }

  assistantClient = window.assistant.createAssistant({
    getState: () => appState,
    getRecoveryState: () => appState,
  });
  assistantClient.on("data", (command) => {
    if (command && command.type === "smart_app_data") {
      handleSmartAppData(command.smart_app_data);
    }
  });
}

setupButton.addEventListener("click", () => {
  sendAssistantText("Добавь лекарство");
  setStatus("Скажите название препарата, затем время приема и длительность курса.");
});

helpButton.addEventListener("click", () => {
  sendAssistantText("Помощь");
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
  setStatus(
    appState.medications.length
      ? "Настройки проверены. Уведомление близкому не задано."
      : "Настройки проверены. Расписание пока пустое, уведомление близкому не задано.",
  );
});

quickActions.forEach((button) => {
  button.addEventListener("click", () => {
    const action = button.dataset.action;
    const messages = {
      add: "Добавь лекарство",
      list: "Показать лекарства",
      course: appState.medications[0] ? `День курса ${appState.medications[0].name}` : "День курса",
      info: "Справка о препарате",
      pharmacy: "Найти аптеку",
      safety: "Что мне принимать от давления?",
    };

    quickActions.forEach((item) => item.classList.remove("is-active"));
    button.classList.add("is-active");
    sendAssistantText(messages[action]);
  });
});

renderSettings();
renderSchedule([]);
initAssistantClient();
