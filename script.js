const images = [
  { colors: ["#1d3557", "#78b3ce"], sun: "#ffd166", label: "Horská krajina" },
  { colors: ["#4d2d52", "#ef8354"], sun: "#ffe8a3", label: "Západ slunce" },
  { colors: ["#264653", "#7ab896"], sun: "#f4d35e", label: "Lesní jezero" }
];

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
let currentIndex = 0;
let respondentData = {};

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
  const item = images[currentIndex];
  image.src = makeIllustration(item);
  image.alt = `Testovací obrázek: ${item.label}`;
  imageNumber.textContent = `Obrázek ${currentIndex + 1} z ${images.length}`;
  nextButton.textContent = currentIndex === images.length - 1 ? "Dokončit test" : "Další obrázek";
  form.reset();
  updateButtonState();
}

function updateRespondentData() {
  respondentData = {
    age: ageInput.value ? Number(ageInput.value) : null,
    gender: genderInputs.find((input) => input.checked)?.value || "",
    experience: experienceSelect.value
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
});

introForm.addEventListener("change", () => {
  introStatus.textContent = "";
});

introForm.addEventListener("submit", (event) => {
  event.preventDefault();

  if (!validateIntroForm()) {
    introStatus.textContent = "Vyplňte všechna pole před pokračováním.";
    return;
  }

  console.info("Respondent data:", respondentData);
  introScreen.classList.add("is-hidden");
  testScreen.classList.remove("is-hidden");
  showImage();
});

form.addEventListener("submit", (event) => {
  event.preventDefault();

  if (currentIndex < images.length - 1) {
    currentIndex += 1;
    showImage();
  } else {
    imageNumber.textContent = "Test dokončen";
    status.textContent = "Děkujeme";
    form.innerHTML = '<p class="intro">Vaše odpovědi byly zaznamenány pouze v rámci této ukázky. Děkujeme za účast.</p>';
  }
});

