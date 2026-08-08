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

function showImage() {
  if (!images || images.length === 0) {
    console.error("Images not loaded yet");
    return;
  }

  const item = images[currentIndex];

  image.src = item.src;
  image.alt = `Testovací obrázek: ${item.label}`;

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
