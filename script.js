let images = [];
let participantId = null;
let currentIndex = 0;
let respondentData = {};

const form = document.querySelector("#test-form");
const image = document.querySelector("#test-image");
const imageNumber = document.querySelector("#image-number");
const status = document.querySelector("#status");
const nextButton = document.querySelector("#next-button");
const aiReasonWrap = document.querySelector("#ai-reason-wrap");
const aiReasonInput = document.querySelector("#ai-reason");
const startButton = document.querySelector("#start-button");
const introForm = document.querySelector("#intro-form");
const introStatus = document.querySelector("#intro-status");
const introScreen = document.querySelector("#intro-screen");
const testScreen = document.querySelector("#test-screen");
const ageInput = document.querySelector("#age");
const genderInputs = Array.from(document.querySelectorAll('input[name="gender"]'));
const experienceSelect = document.querySelector("#experience");

// Fetch images from API
async function loadImages() {
  try {
    const response = await fetch("/api/images");
    const data = await response.json();
    images = data;
    console.log("Images loaded:", images);
  } catch (error) {
    console.error("Chyba při načítání obrázků:", error);
  }
}

// Počkej na obrázky, než povolíš formulář
loadImages().then(() => {
  startButton.disabled = false;
});

const resetIntroBtn = document.querySelector('#reset-intro');
if (resetIntroBtn) {
  resetIntroBtn.addEventListener('click', () => {
    participantId = null;
    currentIndex = 0;
    ageInput.value = "";
    genderInputs.forEach(g => g.checked = false);
    experienceSelect.value = "";
    introScreen.classList.remove("is-hidden");
    testScreen.classList.add("is-hidden");
  });
}

function makeIllustration(item) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500">
    <defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="${item.colors[0]}"/><stop offset="1" stop-color="${item.colors[1]}"/></linearGradient></defs>
    <rect width="800" height="500" fill="url(#sky)"/>
    <circle cx="620" cy="115" r="58" fill="${item.sun}" opacity=".9"/>
    <path d="M0 390 170 205 325 370 470 160 670 370 800 260V500H0Z" fill="#172033" opacity=".72"/>
    <path d="M0 435 210 315 370 420 575 275 800 410V500H0Z" fill="#0d1728" opacity=".8"/>
    <path d="M0 430 Q210 390 400 440 T800 415V500H0Z" fill="#bcd9e8" opacity=".45"/>
  </svg>`;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

function saveStateToStorage() {
  // Zrušeno - již neukládáme do localStorage
  // Data se nyní ukládají na server
}

function updateButtonState() {
  const hasAnswer = form.elements.answer.value !== "";
  const hasConfidence = form.elements.confidence.value !== "";
  nextButton.disabled = !(hasAnswer && hasConfidence);
  status.textContent = nextButton.disabled ? "Vyberte odpověď" : "Připraveno";
}

function toggleAiReasonField() {
  const selectedAnswer = form.elements.answer.value;
  if (selectedAnswer === "ai") {
    aiReasonWrap.classList.remove("is-hidden");
  } else {
    aiReasonWrap.classList.add("is-hidden");
    aiReasonInput.value = "";
  }
}

function restoreQuestionState() {
  // Nyní neobnovujeme stav, protože se počítá s novým participantem
  form.reset();
  updateButtonState();
}

function showImage() {
  if (!images || images.length === 0) {
    console.error("Images not loaded yet");
    return;
  }

  const item = images[currentIndex];

  if (item.type === "photo") {
    image.src = item.src;
    image.alt = `Testovací obrázek: ${item.label}`;
  } else {
    image.src = makeIllustration(item);
    image.alt = `Testovací obrázek: ${item.label}`;
  }

  imageNumber.textContent = `Obrázek ${currentIndex + 1} z ${images.length}`;
  nextButton.textContent = currentIndex === images.length - 1 ? "Dokončit test" : "Další obrázek";
  form.reset();
  aiReasonWrap.classList.add("is-hidden");
  aiReasonInput.value = "";
  updateButtonState();
}

function updateRespondentData() {
  respondentData = {
    age: ageInput.value ? Number(ageInput.value) : null,
    gender: genderInputs.find((input) => input.checked)?.value || "",
    experience: experienceSelect.value
  };
}

function updateQuizState() {
  const answer = form.elements.answer.value;
  const confidence = form.elements.confidence.value;
  return {
    answer,
    confidence,
    aiReason: aiReasonInput.value
  };
}

function validateIntroForm() {
  updateRespondentData();

  const isAgeValid = Number.isInteger(respondentData.age) && respondentData.age > 0;
  const isGenderValid = Boolean(respondentData.gender);
  const isExperienceValid = Boolean(respondentData.experience);

  return isAgeValid && isGenderValid && isExperienceValid;
}

form.addEventListener("change", () => {
  updateButtonState();
  toggleAiReasonField();
});

introForm.addEventListener("input", () => {
  introStatus.textContent = "";
  updateRespondentData();
});

introForm.addEventListener("change", () => {
  introStatus.textContent = "";
  updateRespondentData();
});

introForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!validateIntroForm()) {
    introStatus.textContent = "Vyplňte všechna pole před pokračováním.";
    return;
  }

  introStatus.textContent = "Odesílám...";

  try {
    const response = await fetch("/api/participants", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(respondentData)
    });

    if (!response.ok) {
      const error = await response.json();
      introStatus.textContent = `Chyba: ${error.error || "Neznámá chyba"}`;
      return;
    }

    const data = await response.json();
    participantId = data.participant_id;
    currentIndex = 0;

    console.info("Participant created:", participantId);
    introScreen.classList.add("is-hidden");
    testScreen.classList.remove("is-hidden");
    showImage();
  } catch (error) {
    introStatus.textContent = `Chyba při odesílání: ${error.message}`;
    console.error("Error:", error);
  }
});

function initializeApp() {
  // Vždy zobraz úvodní screen
  participantId = null;
  currentIndex = 0;
  ageInput.value = "";
  genderInputs.forEach((input) => {
    input.checked = false;
  });
  experienceSelect.value = "";
  introStatus.textContent = "";
  introScreen.classList.remove("is-hidden");
  testScreen.classList.add("is-hidden");
}

// Inicializuj aplikaci
initializeApp();

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const answerData = updateQuizState();

  // Odešli odpověď na server
  try {
    const response = await fetch("/api/answers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        participant_id: participantId,
        question_index: currentIndex,
        answer: answerData.answer,
        confidence: parseInt(answerData.confidence),
        ai_reason: answerData.aiReason
      })
    });

    if (!response.ok) {
      const error = await response.json();
      status.textContent = `Chyba: ${error.error || "Neznámá chyba"}`;
      console.error("Error:", error);
      return;
    }

    // Přejdi na další obrázek
    if (currentIndex < images.length - 1) {
      currentIndex += 1;
      showImage();
    } else {
      // Test je hotov
      imageNumber.textContent = "Test dokončen";
      status.textContent = "Děkujeme";
      form.innerHTML = '<p class="intro">Vaše odpovědi byly uloženy. Děkujeme za účast v našem výzkumu!</p>';
    }
  } catch (error) {
    status.textContent = `Chyba při odesílání: ${error.message}`;
    console.error("Error:", error);
  }
});

// Export current quiz state to CSV and download
function exportToCSV() {
  const state = quizState;
  if (!state || !state.intro) {
    alert('Žádná data k exportu. Najprv dokončete nebo začněte test.');
    return;
  }

  const rows = [];
  const header = ['age','gender','experience','question_index','question_label','answer','confidence','ai_reason'];
  for (let i = 0; i < state.answers.length; i++) {
    const a = state.answers[i] || { answer: '', confidence: '', aiReason: '' };
    const label = images[i] ? (images[i].label || '') : '';
    rows.push([
      state.intro.age || '',
      state.intro.gender || '',
      state.intro.experience || '',
      i+1,
      label,
      a.answer || '',
      a.confidence || '',
      (a.aiReason || '').replace(/\r?\n/g, ' ')
    ].map(v => '"' + String(v).replace(/"/g, '""') + '"').join(','));
  }

  const csv = [header.join(','), ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const ts = new Date().toISOString().replace(/[:.]/g,'-');
  a.download = `diplomka_results_${ts}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Send current quiz state to server API (POST JSON)
async function sendToServer() {
  const apiInput = document.querySelector('#server-api');
  const statusEl = document.querySelector('#server-status');
  if (!apiInput) return;
  const url = apiInput.value.trim();
  if (!url) {
    statusEl.textContent = 'Zadejte URL API pro odeslání.';
    return;
  }
  statusEl.textContent = 'Odesílám...';
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ participant: quizState.intro, answers: quizState.answers })
    });
    if (!resp.ok) {
      const text = await resp.text();
      statusEl.textContent = `Chyba: ${resp.status} ${text}`;
      return;
    }
    const json = await resp.json().catch(() => null);
    statusEl.textContent = 'Odesláno úspěšně.' + (json && json.id ? ` ID: ${json.id}` : '');
  } catch (err) {
    statusEl.textContent = 'Odeslání selhalo: ' + err.message;
  }
}

// Hook up buttons
const exportBtn = document.querySelector('#export-csv');
if (exportBtn) exportBtn.addEventListener('click', exportToCSV);
const sendBtn = document.querySelector('#send-server');
if (sendBtn) sendBtn.addEventListener('click', sendToServer);


